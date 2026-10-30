
import os
import re
import sqlite3
from datetime import datetime, date
from math import isfinite

from flask import Flask, render_template, request, redirect, url_for, flash
from google import genai

app = Flask(__name__)
app.secret_key = "local-learning-key"

# Keep the database in the same folder as app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "patients.db")


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def create_table():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dob TEXT NOT NULL,
                email TEXT NOT NULL,
                glucose REAL NOT NULL,
                haemoglobin REAL NOT NULL,
                cholesterol REAL NOT NULL,
                remarks TEXT NOT NULL DEFAULT ''
            )
        """)


def validate_patient(data):
    name = data.get("name", "").strip()
    dob = data.get("dob", "").strip()
    email = data.get("email", "").strip()

    if not name:
        return "Please enter the patient's name."

    try:
        birth_date = datetime.strptime(dob, "%d/%m/%Y").date()
        if birth_date > date.today():
            return "Date of birth cannot be in the future."
    except ValueError:
        return "Enter DOB in DD/MM/YYYY format."

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Please enter a valid email address."

    for field in ("glucose", "haemoglobin", "cholesterol"):
        try:
            value = float(data.get(field, ""))
            if not isfinite(value) or value <= 0:
                return f"{field.title()} must be a positive number."
        except (ValueError, TypeError):
            return f"{field.title()} must be numeric."

    return None


def generate_ai_remarks(glucose, haemoglobin, cholesterol):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        app.logger.error("GEMINI_API_KEY environment variable is missing.")
        return "AI unavailable: Configure your Gemini API key."

    # You can override this model in the terminal if needed.
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    prompt = f"""
You are generating educational remarks for a Health Prediction
System. These measurements may be sample data.

Glucose: {glucose}
Haemoglobin: {haemoglobin}
Cholesterol: {cholesterol}

The measurement units, glucose test type, and laboratory reference
ranges have not been provided.

Do not classify values as high, low, normal, or abnormal.
Do not diagnose a disease or recommend treatment.
Do not assume units or claim that results are medically verified.

In simple English, explain that these measurements need their
units, laboratory reference ranges, and clinical context for
proper interpretation. Keep the answer to 3-5 short sentences.
"""

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=model,
            contents=prompt
        )

        remarks = (response.text or "").strip()

        if not remarks:
            app.logger.error("Gemini returned an empty response.")
            return "AI returned no remarks. Please try again."

        app.logger.info("Gemini AI remarks generated successfully.")
        return remarks

    except Exception as error:
        # Print the full error details in the VS Code terminal.
        app.logger.exception("Gemini API request failed")

        # Show a useful diagnostic message on the website.
        error_message = str(error).replace(api_key, "[hidden]").strip()
        return (
            "AI error: "
            + (error_message[:400] if error_message else
               "Unknown API error. Check the VS Code terminal.")
        )


@app.route("/")
def home():
    with get_db() as db:
        patients = db.execute(
            "SELECT * FROM patients ORDER BY id DESC"
        ).fetchall()

    return render_template("index.html", patients=patients)


@app.route("/add", methods=["POST"])
def add_patient():
    error = validate_patient(request.form)

    if error:
        flash(error, "error")
        return redirect(url_for("home"))

    glucose = float(request.form["glucose"])
    haemoglobin = float(request.form["haemoglobin"])
    cholesterol = float(request.form["cholesterol"])

    remarks = generate_ai_remarks(
        glucose, haemoglobin, cholesterol
    )

    with get_db() as db:
        db.execute("""
            INSERT INTO patients
            (name, dob, email, glucose, haemoglobin,
             cholesterol, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"].strip(),
            request.form["dob"].strip(),
            request.form["email"].strip(),
            glucose,
            haemoglobin,
            cholesterol,
            remarks
        ))

    flash("Patient saved successfully!", "success")
    return redirect(url_for("home"))


@app.route("/edit/<int:patient_id>", methods=["GET", "POST"])
def edit_patient(patient_id):
    with get_db() as db:
        patient = db.execute(
            "SELECT * FROM patients WHERE id = ?",
            (patient_id,)
        ).fetchone()

        if patient is None:
            flash("Patient record not found.", "error")
            return redirect(url_for("home"))

        if request.method == "POST":
            error = validate_patient(request.form)

            if error:
                flash(error, "error")
                return redirect(url_for(
                    "edit_patient", patient_id=patient_id
                ))

            glucose = float(request.form["glucose"])
            haemoglobin = float(request.form["haemoglobin"])
            cholesterol = float(request.form["cholesterol"])

            remarks = generate_ai_remarks(
                glucose, haemoglobin, cholesterol
            )

            db.execute("""
                UPDATE patients
                SET name = ?, dob = ?, email = ?,
                    glucose = ?, haemoglobin = ?,
                    cholesterol = ?, remarks = ?
                WHERE id = ?
            """, (
                request.form["name"].strip(),
                request.form["dob"].strip(),
                request.form["email"].strip(),
                glucose,
                haemoglobin,
                cholesterol,
                remarks,
                patient_id
            ))

            flash("Patient updated successfully!", "success")
            return redirect(url_for("home"))

    return render_template("edit.html", patient=patient)


@app.route("/delete/<int:patient_id>", methods=["POST"])
def delete_patient(patient_id):
    with get_db() as db:
        db.execute(
            "DELETE FROM patients WHERE id = ?",
            (patient_id,)
        )

    flash("Patient record deleted successfully!", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    create_table()
    app.run(debug=True)
