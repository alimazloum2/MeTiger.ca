# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Development server (auto-reload, binds 0.0.0.0:8000):
```bash
source venv/bin/activate
python app.py
```

Production (gunicorn, 2 workers on 127.0.0.1:8000, backgrounded):
```bash
./start_app.sh
```
Note: `start_app.sh` `export`s production secrets inline and overrides whatever is in `.env`. If you change SMTP/Turnstile keys, update both places.

Install/update deps:
```bash
venv/bin/pip install -r requirements.txt
```

There is no test suite, no linter, and no build step.

## Architecture

Single-file Flask app (`app.py`) serving Jinja2 templates from `templates/` with one shared layout (`base.html`). Pages are `index.html`, `services.html`, `projects.html`, `contact.html` — all static content. There is no database; the only dynamic surface is the contact form.

### Contact form pipeline
The form posts to `POST /send_message` (not `/contact` — that route exists but only flashes a message and is effectively legacy). The endpoint runs a layered anti-spam check before sending mail; **all four layers must stay in place** because each catches a different attacker class:

1. **Honeypot** — a hidden `company` field; any value → 400.
2. **Time gate** — form must be open ≥ 3s (client sends `started_at` from `START_TS` injected by the index route).
3. **Cloudflare Turnstile** — server-side `siteverify` against `TURNSTILE_SECRET`. Skipped only if both keys are empty (dev mode).
4. **Content checks** — URL count in message, disposable-email domain blocklist (`DISPOSABLE` set), basic email-shape validation, min message length.

Rate limiting via `flask-limiter`: 3/min on `/send_message`, 100/hour global default, keyed by remote IP.

Mail goes out via `send_contact_email()` using Office365 SMTP (`smtp.office365.com:587`, STARTTLS) authenticating as `info@metiger.ca`. The `From` address must match the authenticated `SMTP_USER` or Office365 will reject. `Reply-To` is set to the visitor's email so direct replies work. `requirements.txt` still pins `sendgrid` — it is unused; SMTP is the live path.

### Configuration
Loaded from `.env` via `python-dotenv` at import time. Required env vars:
- `SECRET_KEY` — Flask session signing
- `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET` — Cloudflare Turnstile (defaults in code are real, not placeholders)
- `SMTP_USER`, `SMTP_PASSWORD` — Office365 mailbox creds for `info@metiger.ca`

`SENDGRID_API_KEY`, `FROM_EMAIL`, `TO_EMAIL` appear in `start_app.sh` and `/debug` but are not used by the send path.

### Notes
- `GET /debug` echoes config (truncated secrets) and is wired up in production. Treat as a known footgun — don't expand what it leaks.
- `static/images/` and `app.log` are present locally but gitignored / untracked.
- Brand colors live as Tailwind config in `base.html`: `metiger-blue #004c97`, `metiger-orange #ff6b35`. Tailwind is loaded via CDN, not built.

See `DEPLOYMENT.md` for the full Nginx + gunicorn + systemd setup used in production.
