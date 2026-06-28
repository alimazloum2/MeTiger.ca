from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, Response
import io, os, re, time, requests
from collections import OrderedDict
from threading import Lock
from dotenv import load_dotenv
import segno

# Load environment variables from .env file
load_dotenv()

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Anti-spam configuration
app.config["TURNSTILE_SITE_KEY"] = os.getenv("TURNSTILE_SITE_KEY", "0x4AAAAAAB8Wgm9wM6xbP-yW")
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
limiter = Limiter(get_remote_address, app=app, default_limits=["100/hour"])
URL_RE = re.compile(r'https?://', re.I)
DISPOSABLE = {"mailinator.com","guerrillamail.com","10minutemail.com","tempmail.dev","yopmail.com","getnada.com","trashmail.com"}

# Crypto payment info — only served after Turnstile passes.
PAYMENT_INFO = {
    "qrAddress": "0x011796f4f6DF20cee9Da15d5127E5d77ED0e4743",
    "ensName": "metiger.eth",
    "contractAddress": "0xa79d3083a7e303Db38e013C54135F178834Ccb1B",
    "network": "Base",
}

# Cache verified Turnstile tokens so /send_message can reuse the same token
# that /api/reveal-payment already redeemed (siteverify only accepts each
# token once).
_VERIFIED_TOKENS = OrderedDict()
_VERIFIED_TOKENS_LOCK = Lock()
_VERIFIED_TOKEN_TTL = 300  # seconds


def verify_turnstile(token, remote_ip):
    if not TURNSTILE_SECRET or not app.config["TURNSTILE_SITE_KEY"]:
        return True
    if not token:
        return False
    now = time.time()
    with _VERIFIED_TOKENS_LOCK:
        while _VERIFIED_TOKENS:
            first = next(iter(_VERIFIED_TOKENS))
            if _VERIFIED_TOKENS[first] > now:
                break
            _VERIFIED_TOKENS.popitem(last=False)
        if token in _VERIFIED_TOKENS:
            return True
    try:
        r = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": TURNSTILE_SECRET, "response": token, "remoteip": remote_ip},
            timeout=5,
        )
        if r.json().get("success", False):
            with _VERIFIED_TOKENS_LOCK:
                _VERIFIED_TOKENS[token] = now + _VERIFIED_TOKEN_TTL
            return True
    except Exception:
        pass
    return False

@app.route("/")
def index():
    return render_template("index.html", 
                         TURNSTILE_SITE_KEY=app.config["TURNSTILE_SITE_KEY"],
                         START_TS=int(time.time()))

BASE_URL = "https://metiger.ca"

# Crawlers / answer engines explicitly welcomed. Standard search bots are
# already covered by the wildcard rule; these are named so AI crawlers see an
# explicit Allow.
_AI_USER_AGENTS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "ClaudeBot", "Claude-Web", "anthropic-ai",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Applebot-Extended",
    "CCBot", "Amazonbot", "Bytespider", "meta-externalagent",
]


@app.route("/robots.txt")
@limiter.exempt
def robots_txt():
    lines = [
        "# robots.txt for metiger.ca",
        "User-agent: *",
        "Allow: /",
        "Disallow: /debug",
        "",
    ]
    for ua in _AI_USER_AGENTS:
        lines += [f"User-agent: {ua}", "Allow: /", ""]
    lines.append(f"Sitemap: {BASE_URL}/sitemap.xml")
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@app.route("/sitemap.xml")
@limiter.exempt
def sitemap_xml():
    pages = ["/", "/services", "/projects", "/estimate-calculator", "/electrical-budget-guide", "/contact"]
    urls = "".join(
        f"<url><loc>{BASE_URL}{p}</loc>"
        f"<changefreq>monthly</changefreq>"
        f"<priority>{'1.0' if p == '/' else '0.8'}</priority></url>"
        for p in pages
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )
    return Response(xml, mimetype="application/xml")


# Plain-language summary for LLMs / answer engines (https://llmstxt.org/).
_LLMS_TXT = """# MeTiger Inc.

> MeTiger Inc. is a construction project management and electrical engineering
> consulting firm registered in Nova Scotia, Canada, serving clients across the
> United States. Tagline: "Delivering complex construction projects without drama."

## About

MeTiger Inc. partners with clients to plan, engineer, and construct resilient
infrastructure. We work behind the scenes to de-risk construction, keep trades
moving, and protect the schedule with senior engineering oversight and disciplined
project management. Engineered in Nova Scotia, built across the U.S.

- Founded: 2022
- Office: 620 Nine Mile Drive, Bedford, NS B4A 0H4, Canada
- Email: info@metiger.ca
- Phone: +1 (782) 640-5557
- Area served: United States (firm registered in Canada)
- Certified Procore partner

## Services

- Electrical Engineering: Coordinated, code-compliant electrical solutions that
  bridge engineering intent with construction execution, improving safety, energy
  efficiency, and reliability.
- Project Management: Scope review, RFIs and submittals, subcontract negotiation,
  cost forecasting, progress claims, and budget/cash-flow control.
- Construction Documentation: RFQs, tender front-end packages, and addenda before
  award; CDs, CCNs, and CCOs after award to keep scope, cost, and drawings aligned.
- Tender Review & Cost Estimating: Drawing review, quantity verification, and
  organized trade packages for builders and clients.

## Selected projects

- Retail Remodel — Walmart Supercenter, Pembroke Pines, FL: electrical estimating
  and engineering for an interior remodel coordinated around live store operations.
- Restaurant Tenant Improvement — CAVA, Doral, FL: electrical estimating and
  coordination for a new restaurant build-out, supporting an on-time opening.
- Utility Infrastructure — Lift Station Electrical, Hernando County, FL:
  engineering and estimating for municipal wastewater lift station packages.

## Links

- Website: https://metiger.ca/
- Services: https://metiger.ca/services
- Projects: https://metiger.ca/projects
- Contact: https://metiger.ca/contact
- LinkedIn: https://www.linkedin.com/company/metiger
- YouTube: https://www.youtube.com/@MeTigerCa
"""


@app.route("/llms.txt")
@limiter.exempt
def llms_txt():
    return Response(_LLMS_TXT, mimetype="text/plain")


@app.route("/debug")
def debug():
    sendgrid_key = os.getenv('SENDGRID_API_KEY', 'Not set')
    from_email = os.getenv('FROM_EMAIL', 'Not set')
    to_email = os.getenv('TO_EMAIL', 'Not set')
    
    return f"""
    <html>
    <head><title>Debug Info</title></head>
    <body>
        <h1>Debug Information</h1>
        <p>Turnstile Site Key: {app.config['TURNSTILE_SITE_KEY']}</p>
        <p>Turnstile Secret: {TURNSTILE_SECRET[:10] if TURNSTILE_SECRET else 'Not set'}...</p>
        <p>SendGrid API Key: {sendgrid_key[:10] if sendgrid_key != 'Not set' else 'Not set'}...</p>
        <p>From Email: {from_email}</p>
        <p>To Email: {to_email}</p>
        <div class="cf-turnstile" data-sitekey="{app.config['TURNSTILE_SITE_KEY']}"></div>
        <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
    </body>
    </html>
    """

@app.route("/services")
def services():
    return render_template("services.html")

@app.route("/projects")
def projects():
    return render_template("projects.html")

@app.route("/estimate-calculator")
def estimate_calculator():
    return render_template("estimate_calculator.html")

@app.route("/electrical-budget-guide")
def electrical_budget_guide():
    return render_template("budget_guide.html")

@app.route("/test_turnstile")
def test_turnstile():
    return render_template("test_turnstile.html")

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

def _build_qr_svg(text):
    qr = segno.make(text, error="m")
    buf = io.BytesIO()
    qr.save(
        buf,
        kind="svg",
        scale=5,
        border=2,
        dark="#000000",
        light="#ffffff",
        xmldecl=False,
    )
    return buf.getvalue().decode("ascii")


@app.post("/api/reveal-payment")
@limiter.limit("10/minute")
def reveal_payment():
    token = request.form.get("cf-turnstile-response", "").strip()
    if not token:
        payload = request.get_json(silent=True) or {}
        token = (payload.get("token") or "").strip()
    if not verify_turnstile(token, request.remote_addr):
        return jsonify(success=False, message="Verification required."), 403
    return jsonify(
        success=True,
        qrSvg=_build_qr_svg(PAYMENT_INFO["qrAddress"]),
        **PAYMENT_INFO,
    )


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

    if not verify_turnstile(token, request.remote_addr):
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
        # Temporarily hardcode SendGrid for testing
        send_contact_email(name, email, msg)
        return jsonify(success=True, message="Thanks — we'll get back to you"), 200
    except Exception as e:
        print(f"Email error: {e}")
        return jsonify(success=False, message="Error sending message. Please try again."), 500

def send_contact_email(name, email, message):
    """Send contact form email using Microsoft SMTP"""
    
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    sender_email = "info@metiger.ca"  # Must match the authenticated account
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        raise ValueError("SMTP credentials not configured")

    # Email content
    msg = MIMEMultipart()
    msg['From'] = f"MeTiger Website <{sender_email}>"
    msg['To'] = "info@metiger.ca"
    msg['Subject'] = f"New Contact Form Submission from {name}"
    msg['Reply-To'] = email  # Allow direct reply to the visitor

    body = f"""
    New contact form submission:
    
    Name: {name}
    Email: {email}
    
    Message:
    {message}
    
    ---
    This message was sent from the MeTiger Inc. website contact form.
    """
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Send email
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Secure the connection
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"SMTP Error: {e}")
        raise e

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
