from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, Response
import io, os, re, time, requests, hmac, hashlib
from datetime import datetime
from collections import OrderedDict
from threading import Lock
from dotenv import load_dotenv
import segno
import pages as page_registry
import insights as insights_module
import chat as chat_module

# Load environment variables from .env file (explicit path so it loads no
# matter what CWD the service starts in).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Anti-spam configuration
app.config["TURNSTILE_SITE_KEY"] = os.getenv("TURNSTILE_SITE_KEY", "0x4AAAAAAB8Wgm9wM6xbP-yW")
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
EL_WEBHOOK_SECRET = os.getenv("EL_WEBHOOK_SECRET", "")


def client_ip():
    """Visitor IP for per-visitor rate limits and Turnstile.

    gunicorn only listens on 127.0.0.1 behind nginx (behind Cloudflare), so
    request.remote_addr is always 127.0.0.1. Prefer Cloudflare's header, then
    the one nginx sets. These headers can be forged by anyone who reaches the
    origin directly, so the strict limits below (form posts, admin login) do
    NOT use this function; they stay keyed on the socket address, i.e. site-wide.
    """
    return (request.headers.get("CF-Connecting-IP")
            or request.headers.get("X-Real-IP")
            or request.remote_addr or "unknown")


# Page views: per visitor. Static files are exempt (see below).
limiter = Limiter(client_ip, app=app, default_limits=["600/hour"])


@limiter.request_filter
def _exempt_static():
    return request.endpoint == "static"


# Drawing uploads on the quote form. Files are emailed as attachments (there is
# no object store), so the total is capped well under typical 25 MB mailbox
# limits — base64 inflates attachments ~33%. Larger sets use the plan-link field.
MAX_ATTACH_TOTAL = 15 * 1024 * 1024      # 15 MB combined, raw bytes
MAX_ATTACH_FILES = 10
ALLOWED_ATTACH_EXT = {
    "pdf", "dwg", "dxf", "dwf", "rvt", "zip",
    "png", "jpg", "jpeg", "gif", "tif", "tiff",
    "csv", "xls", "xlsx", "doc", "docx", "txt",
}
# Hard request ceiling (> MAX_ATTACH_TOTAL to leave room for the other fields).
# Exceeding it raises 413 before the view runs; see the handler below.
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


@app.errorhandler(413)
def _too_large(_e):
    return jsonify(
        success=False,
        message="Files too large. Keep attachments under 15 MB total, "
                "or share a plan link instead.",
    ), 413


@app.context_processor
def inject_globals():
    """Make Turnstile key + a fresh form-open timestamp available to every
    template, so any page can include the shared quote form."""
    return {
        "TURNSTILE_SITE_KEY": app.config["TURNSTILE_SITE_KEY"],
        "START_TS": int(time.time()),
        "ASSET_V": ASSET_V,
    }


def _asset_version():
    """Cache-buster for CSS/JS: newest mtime under static/css and static/js."""
    newest = 0
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    for sub in ("css", "js"):
        folder = os.path.join(base, sub)
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                newest = max(newest, int(os.path.getmtime(os.path.join(folder, name))))
    return str(newest)


ASSET_V = _asset_version()


@app.errorhandler(404)
def _not_found(_e):
    return render_template("404.html"), 404


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
    payload = {"secret": TURNSTILE_SECRET, "response": token}
    if remote_ip and not remote_ip.startswith("127.") and remote_ip != "unknown":
        payload["remoteip"] = remote_ip
    try:
        r = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=payload,
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
    return render_template("home.html")

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
        "Disallow: /admin",
        "",
    ]
    for ua in _AI_USER_AGENTS:
        lines += [f"User-agent: {ua}", "Allow: /", ""]
    lines.append(f"Sitemap: {BASE_URL}/sitemap.xml")
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def _template_lastmod(template_rel):
    """ISO date (YYYY-MM-DD) of a template's last modification, for <lastmod>."""
    try:
        mtime = os.path.getmtime(os.path.join(_TEMPLATE_DIR, template_rel))
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except OSError:
        return None


@app.route("/sitemap.xml")
@limiter.exempt
def sitemap_xml():
    urls = "\n".join(
        f"<url><loc>{BASE_URL}{path}</loc>"
        + (f"<lastmod>{lastmod}</lastmod>" if (lastmod := _template_lastmod(tmpl)) else "")
        + "</url>"
        for path, tmpl in page_registry.sitemap_entries()
    )
    posts = "\n".join(
        f"<url><loc>{BASE_URL}{path}</loc>"
        + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
        + "</url>"
        for path, lastmod in insights_module.sitemap_entries()
    )
    if posts:
        urls = urls + "\n" + posts
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )
    return Response(xml, mimetype="application/xml")


# Plain-language summary for LLMs / answer engines (https://llmstxt.org/).
_LLMS_TXT = """# MeTiger Inc. — Canadian Electrical Estimating

> MeTiger Inc. is a commercial and industrial electrical estimating consultancy
> based in Bedford, Nova Scotia, Canada, serving electrical contractors and
> general contractors across Canada. Tagline: "Canadian electrical estimating,
> delivered without drama." (For USA estimating, see https://metiger.us.)

## About

MeTiger turns Canadian tender drawings, specifications, and addenda into clean
electrical takeoffs, material lists, labour summaries, colour-coded marked-up
drawings, and scope notes built for review. Estimating support is informed by
CSA C22.1 / the Canadian Electrical Code, provincial practices, project
specifications, local utility requirements, and bid documents. Final compliance
remains subject to the project engineer, the authority having jurisdiction, and
applicable provincial/territorial requirements. MeTiger provides estimating and
coordination support, not sealed or stamped engineering.

- Founded: 2022
- Office: 620 Nine Mile Drive, Bedford, NS B4A 0H4, Canada
- Email: info@metiger.ca
- Phone: +1 (838) 638-4437 (answered by an AI assistant; an estimator follows up)
- Area served: Canada (remote delivery across all provinces and territories)
- NDA available on request

## Services

- Canadian Electrical Estimating: Takeoffs and labour summaries built from your
  PDF or DWG tender set, delivered as a reviewable estimate package.
- Electrical Takeoffs: Standalone quantity takeoffs by system and marked-up plans.
- Commercial & Industrial Estimating: Tenant improvements, retail, warehouses,
  and heavier industrial/utility electrical scopes.
- Electrical Bid Review: An independent second set of eyes on drawings,
  quantities, exclusions, and scope gaps before you submit.
- Construction Documentation Support and Electrical Design Coordination Support,
  working alongside the engineer of record where required.

## Project types

Commercial tenant improvements, retail fit-outs, restaurants and hospitality,
warehouses and light industrial, multi-family residential, municipal facilities,
pump stations and utility infrastructure, schools and institutional, office and
mixed-use, and service upgrades / distribution work.

## Links

- Website: https://metiger.ca/
- Electrical Estimating Services: https://metiger.ca/canada-electrical-estimating-services/
- Electrical Takeoffs: https://metiger.ca/electrical-takeoff-services-canada/
- Bid Review: https://metiger.ca/electrical-bid-review-canada/
- Pricing: https://metiger.ca/pricing/
- Calculator: https://metiger.ca/estimate-calculator
- Technology: https://metiger.ca/technology/
- Insights: https://metiger.ca/insights/
- Samples: https://metiger.ca/samples/
- Case Studies: https://metiger.ca/case-studies/
- Contact / Quote: https://metiger.ca/contact/
- Privacy: https://metiger.ca/privacy/
- Terms: https://metiger.ca/terms/
- USA estimating: https://metiger.us
- LinkedIn: https://www.linkedin.com/company/metiger
- YouTube: https://www.youtube.com/@MeTigerCa
"""


@app.route("/llms.txt")
@limiter.exempt
def llms_txt():
    return Response(_LLMS_TXT, mimetype="text/plain")


@app.route("/services")
def services():
    # Legacy USA-era route → Canada estimating hub (preserve inbound links).
    return redirect("/canada-electrical-estimating-services/", code=301)

@app.route("/projects")
def projects():
    # Legacy USA-era route → Canada case studies.
    return redirect("/case-studies/", code=301)

@app.route("/estimate-calculator")
def estimate_calculator():
    return render_template("estimate_calculator.html")

@app.route("/electrical-budget-guide")
def electrical_budget_guide():
    return render_template("budget_guide.html")

@app.route("/technology/")
def technology():
    return render_template("technology.html")


@app.route("/privacy/")
def privacy():
    return render_template("privacy.html")


@app.route("/terms/")
def terms():
    return render_template("terms.html")


# metiger.us paths -> the existing metiger.ca URLs (kept for ranking).
@app.route("/calculator/")
@app.route("/calculator")
def calculator_alias():
    return redirect("/estimate-calculator", code=301)


@app.route("/electrical-estimating/")
@app.route("/electrical-estimating")
def estimating_alias():
    return redirect("/canada-electrical-estimating-services/", code=301)


@app.route("/test_turnstile")
def test_turnstile():
    return render_template("test_turnstile.html")

@app.route("/contact/")
def contact():
    # Quote-request page. The form posts to /send_message (the live SMTP path);
    # this route only renders. Flask 308-redirects /contact -> /contact/.
    return render_template("quote.html")


def _verify_elevenlabs_signature(raw_body, sig_header):
    """Verify the ElevenLabs HMAC signature (header 'ElevenLabs-Signature:
    t=<ts>,v0=<hex>'). Requests without a valid signature are rejected (401)."""
    if not sig_header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in sig_header.split(","))
        ts, v0 = parts.get("t"), parts.get("v0")
        if not ts or not v0:
            return False
        signed = f"{ts}.{raw_body}"
        expected = hmac.new(EL_WEBHOOK_SECRET.encode(), signed.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, v0)
    except Exception:
        return False


def _send_call_summary_email(subject, body):
    """Email an ElevenLabs post-call summary to the business inbox via SMTP.

    Reads the same SMTP_SERVER/SMTP_PORT/SMTP_SECURITY/SMTP_FROM env vars as
    send_contact_email() so both paths follow the mailbox host.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.office365.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    if not smtp_user or not smtp_password:
        raise ValueError("SMTP credentials not configured")
    sender_email = os.environ.get("SMTP_FROM") or smtp_user or "info@metiger.ca"
    msg = MIMEMultipart()
    msg["From"] = f"MeTiger Website <{sender_email}>"
    msg["To"] = os.environ.get("EMAIL_TO") or "info@metiger.ca"
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    if smtp_security == "ssl":
        server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=20)
    else:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=20)
        server.starttls()
    server.login(smtp_user, smtp_password)
    server.send_message(msg)
    server.quit()


@app.route("/elevenlabs/post-call", methods=["POST"])
@limiter.exempt
def elevenlabs_post_call():
    """Receiver for ElevenLabs post-call webhooks: verify signature, email a
    call summary + transcript to info@metiger.ca, and ack with 200."""
    raw = request.get_data(as_text=True)
    if not _verify_elevenlabs_signature(raw, request.headers.get("ElevenLabs-Signature", "")):
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    data = payload.get("data", {}) or {}
    analysis = data.get("analysis", {}) or {}
    conv_id = data.get("conversation_id", "unknown")
    summary = analysis.get("transcript_summary") or "(no summary provided)"
    turns = []
    for t in (data.get("transcript") or []):
        text = t.get("message") or t.get("text") or ""
        if text:
            turns.append(f"{t.get('role', '?')}: {text}")
    transcript = "\n".join(turns) or "(no transcript)"
    body = (
        f"ElevenLabs AI call\n\nConversation: {conv_id}\n"
        f"Agent: {data.get('agent_id', '')}\n\n"
        f"Summary:\n{summary}\n\nTranscript:\n{transcript}\n"
    )
    try:
        _send_call_summary_email(f"AI call summary — {conv_id}", body)
        print(f"ElevenLabs webhook: emailed summary for {conv_id} to {os.environ.get('EMAIL_TO') or 'info@metiger.ca'}", flush=True)
    except Exception as e:
        print(f"ElevenLabs webhook email error: {e}", flush=True)  # ack anyway so EL doesn't retry-storm
    return jsonify({"status": "ok"}), 200


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
@limiter.limit("10/minute", key_func=get_remote_address)
def reveal_payment():
    token = request.form.get("cf-turnstile-response", "").strip()
    if not token:
        payload = request.get_json(silent=True) or {}
        token = (payload.get("token") or "").strip()
    if not verify_turnstile(token, client_ip()):
        return jsonify(success=False, message="Verification required."), 403
    return jsonify(
        success=True,
        qrSvg=_build_qr_svg(PAYMENT_INFO["qrAddress"]),
        **PAYMENT_INFO,
    )


@app.post("/send_message")
@limiter.limit("3/minute", key_func=get_remote_address)
def send_message():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    msg = (request.form.get("message") or "").strip()
    # Honeypot renamed from 'company' -> 'website' so 'company' can be a real
    # quote field. Do NOT check 'company' here or legit submissions get blocked.
    honeypot = request.form.get("website", "")
    started_at = request.form.get("started_at", "0")
    token = request.form.get("cf-turnstile-response", "")

    print(f"Form data: name={name}, email={email}, started_at={started_at}, honeypot={'yes' if honeypot else 'no'}, token={'present' if token else 'missing'}", flush=True)

    if honeypot:
        return jsonify(success=False, message="Bad request"), 400

    try:
        started = float(started_at)
    except ValueError:
        started = 0.0
    if time.time() - started < 3:
        return jsonify(success=False, message="Please take a moment and try again."), 400

    if not verify_turnstile(token, client_ip()):
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

    plan_link = (request.form.get("plan_link") or "").strip()
    if len(msg) < 6 and len(plan_link) > 5:
        msg = (msg + "\n" if msg else "") + "(No message entered; drawings shared by plan link.)"
    if not name or len(msg) < 6:
        return jsonify(success=False, message="Please add your name and a drawing link or a short message."), 400

    # Collect optional quote-form fields. All optional — the required name /
    # email / message above keep the simple contact path working unchanged.
    details = {
        "Company": request.form.get("company", "").strip(),
        "Phone": request.form.get("phone", "").strip(),
        "Province": request.form.get("province", "").strip(),
        "Project type": request.form.get("project_type", "").strip(),
        "Service needed": request.form.get("service", "").strip(),
        "Bid due date": request.form.get("bid_date", "").strip(),
        "Plan link": request.form.get("plan_link", "").strip(),
        "NDA": request.form.get("nda", "").strip(),
        "Consent to contact": "Yes" if request.form.get("consent") else "No",
        "Submitted from": request.form.get("source", "").strip(),
    }

    # Collect optional drawing uploads. Field name "attachments" (multiple).
    uploads = [f for f in request.files.getlist("attachments") if f and f.filename]
    if len(uploads) > MAX_ATTACH_FILES:
        return jsonify(success=False, message=f"Please attach at most {MAX_ATTACH_FILES} files."), 400
    attachments = []
    total = 0
    for f in uploads:
        safe = secure_filename(f.filename) or "attachment"
        ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
        if ext not in ALLOWED_ATTACH_EXT:
            return jsonify(success=False, message=f"File type not allowed: {f.filename}"), 400
        data = f.read()
        total += len(data)
        if total > MAX_ATTACH_TOTAL:
            return jsonify(success=False, message="Attachments exceed 15 MB total. Share a plan link for larger sets."), 400
        attachments.append((safe, data))
    if attachments:
        details["Attachments"] = ", ".join(n for n, _ in attachments)

    # Send email
    try:
        send_contact_email(name, email, msg, details, attachments=attachments)
        return jsonify(success=True, message="Thanks — we'll review your request and get back to you."), 200
    except Exception as e:
        print(f"Email error: {e}", flush=True)
        return jsonify(success=False, message="Error sending message. Please try again."), 500

def send_contact_email(name, email, message, details=None, attachments=None):
    """Send a contact/quote email over SMTP.

    `details` is an optional dict of extra quote fields; only non-empty values
    are included in the body. `attachments` is an optional list of
    (filename, bytes) tuples attached to the message (drawing uploads). The
    From address must match the authenticated SMTP user on most providers or
    the message is rejected; Reply-To is the visitor so replies reach them
    directly.

    Server/port/security/sender are read from the environment so the mailbox
    can move hosts (e.g. Office365 -> mail.oqumail.com) without a code change:
      SMTP_SERVER   (default smtp.office365.com)
      SMTP_PORT     (default 587)
      SMTP_SECURITY starttls | ssl  (default starttls)
      SMTP_FROM     (default: SMTP_USER, else info@metiger.ca)
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.office365.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    # From must match the authenticated account on most hosts.
    sender_email = os.environ.get("SMTP_FROM") or smtp_user or "info@metiger.ca"
    recipient = os.environ.get("TO_EMAIL") or "info@metiger.ca"

    if not smtp_user or not smtp_password:
        raise ValueError("SMTP credentials not configured")

    details = details or {}
    project_type = details.get("Project type") or "General"
    province = details.get("Province") or "Canada"

    from_name = os.environ.get("SMTP_FROM_NAME", "MeTiger Inc.")
    msg = MIMEMultipart()
    msg['From'] = f"{from_name} <{sender_email}>"
    msg['To'] = recipient
    msg['Subject'] = f"metiger.ca Quote Request – {project_type} – {province}"
    msg['Reply-To'] = email  # Allow direct reply to the visitor

    lines = [
        "New quote / contact request from metiger.ca",
        "",
        f"Name:  {name}",
        f"Email: {email}",
    ]
    for label, value in details.items():
        if value:
            lines.append(f"{label}: {value}")
    lines += ["", "Message / scope notes:", message, "",
              "---", "Sent from the MeTiger Inc. (metiger.ca) website."]
    body = "\n".join(lines)

    msg.attach(MIMEText(body, 'plain'))

    for fname, data in (attachments or []):
        part = MIMEApplication(data, Name=fname)
        part['Content-Disposition'] = f'attachment; filename="{fname}"'
        msg.attach(part)

    # Send email. SSL (port 465) opens an encrypted socket directly; STARTTLS
    # (port 587) upgrades a plaintext connection. mail.oqumail.com-style hosts
    # typically use one of these two.
    try:
        if smtp_security == "ssl":
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=20)
            server.starttls()  # Secure the connection
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"SMTP Error: {e}")
        raise e

# ---------------------------------------------------------------------------
# Register CA marketing / service / province pages from the registry. Each
# renders a self-contained template (templates/pages/*) that carries its own
# SEO metadata + JSON-LD via template blocks.
# ---------------------------------------------------------------------------
def _make_page_view(template_name):
    def _view():
        return render_template(template_name)
    return _view


for _path, _template, _endpoint, _prio in page_registry.ALL_REGISTRY_PAGES:
    app.add_url_rule(_path, _endpoint, _make_page_view(_template))


@app.route("/payments")
def payments():
    # Crypto / TigerCoin consultation payments, kept off the main estimating
    # funnel. Still served by the Turnstile-gated /api/reveal-payment endpoint.
    return render_template("payments.html")


insights_module.init_app(app, limiter=limiter, strict_key=get_remote_address)
chat_module.init_app(app, limiter=limiter, visitor_key=client_ip)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
