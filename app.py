from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
import os, re, time, requests
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sendgrid
from sendgrid.helpers.mail import Mail

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Anti-spam configuration
app.config["TURNSTILE_SITE_KEY"] = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
limiter = Limiter(get_remote_address, app=app, default_limits=["100/hour"])
URL_RE = re.compile(r'https?://', re.I)
DISPOSABLE = {"mailinator.com","guerrillamail.com","10minutemail.com","tempmail.dev","yopmail.com","getnada.com","trashmail.com"}

@app.route("/")
def index():
    return render_template("index.html", TURNSTILE_SITE_KEY=app.config["TURNSTILE_SITE_KEY"])

@app.route("/services")
def services():
    return render_template("services.html")

@app.route("/projects")
def projects():
    return render_template("projects.html")

@app.route("/contact", methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        company = request.form.get('company')
        message = request.form.get('message')
        
        # Here you would typically send an email or save to database
        # For now, we'll just flash a success message
        flash(f'Thank you {name}! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template("contact.html")

@app.post("/send_message")
@limiter.limit("3/minute")
def send_message():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    msg = (request.form.get("message") or "").strip()
    honeypot = request.form.get("company", "")
    started_at = request.form.get("started_at", "0")
    token = request.form.get("cf-turnstile-response", "")
    
    # Debug logging (remove in production)
    print(f"Form data: name={name}, email={email}, started_at={started_at}, honeypot={honeypot}, token={'present' if token else 'missing'}")

    if honeypot:
        return jsonify(success=False, message="Bad request"), 400

    try:
        started = float(started_at)
    except ValueError:
        started = 0.0
    if time.time() - started < 3:
        return jsonify(success=False, message="Please take a moment and try again."), 400

    # Skip Turnstile validation if keys are not configured (for development)
    if TURNSTILE_SECRET and app.config["TURNSTILE_SITE_KEY"]:
        if not token:
            return jsonify(success=False, message="Verification failed."), 400
        try:
            r = requests.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": TURNSTILE_SECRET, "response": token, "remoteip": request.remote_addr},
                timeout=5
            )
            if not r.json().get("success", False):
                return jsonify(success=False, message="Verification failed."), 400
        except Exception:
            return jsonify(success=False, message="Verification failed."), 400

    url_count = len(URL_RE.findall(msg))
    if url_count > 2:
        return jsonify(success=False, message="Too many links in message."), 400
    if url_count >= 1 and len(msg.split()) < 6:
        return jsonify(success=False, message="Message looks like spam."), 400

    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify(success=False, message="Enter a valid email."), 400
    domain = email.split("@")[-1]
    if domain in DISPOSABLE:
        return jsonify(success=False, message="Use a real email address."), 400

    if not name or len(msg) < 6:
        return jsonify(success=False, message="Please complete all fields."), 400

    # Send email
    try:
        send_contact_email(name, email, msg)
        return jsonify(success=True, message="Thanks — we'll get back to you"), 200
    except Exception:
        return jsonify(success=False, message="Error sending message. Please try again."), 500

def send_contact_email(name, email, message):
    """Send contact form email using SendGrid"""
    # SendGrid configuration
    sg = sendgrid.SendGridAPIClient(api_key='SG.REDACTED_ROTATE_ME')
    
    # Email content
    subject = f"New Contact Form Submission from {name}"
    body = f"""
    New contact form submission:
    
    Name: {name}
    Email: {email}
    Message: {message}
    
    ---
    This message was sent from the MeTiger Inc. website contact form.
    """
    
    # Create SendGrid mail object
    mail = Mail(
        from_email='info@metiger.ca',  # Sender (must be verified in SendGrid)
        to_emails='info@metiger.ca',   # Recipient
        subject=subject,
        plain_text_content=body
    )
    
    # Send email
    response = sg.send(mail)
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
