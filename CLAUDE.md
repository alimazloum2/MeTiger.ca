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

## Design (November 2026 redesign)

metiger.ca mirrors the look and wording of metiger.us. `static/css/site.css` is the metiger.us stylesheet with only its colours changed (see Colours below); `static/css/ca.css` adds the Canadian coverage map, the restyle of the older pages (`main.legacy-page`), and the admin screens. `static/js/site.js` handles the menu and the quote form. No build step, no Tailwind.

Colours (chosen November 2026 so the Canadian site looks different from the US one): "Glacier blue and orange". Dark `#0f3550` (darker `#0a2538`), mid `#1a5078`, accent orange `#f28c28` (hover `#f6a24c`, orange text on light `#a3560a`), link/secondary-button blue `#0f6aa0` (hover `#0b4a70`), page `#f2f7fb`. The US navy/copper hex values were replaced one-for-one across `site.css`, `ca.css`, the templates and `static/brand/*`; when copying new CSS from metiger.us, apply the same swap.

Hard rules for client-visible content:
- Company name is "MeTiger Inc." only. No personal names anywhere.
- The only phone number is +1 (838) 638-4437, printed only in the top strip (`partials/site_header.html`). The mobile bar's "Call" button links to it without printing it. On computers, clicking a phone link opens the "Call MeTiger" box (built in `site.js`, same as metiger.us), which shows that same number with a Copy button.
- Email is info@metiger.ca. Footer cross-link reads "US projects → metiger.us".
- Fees are published in CAD plus GST/HST in `partials/fee_table.html` (used by the estimating page and `/pricing/`).
- Credentials wording lives only in `partials/credentials.html`.
- Never invent facts (prices, response times, counts, testimonials, legal text).

Routes added: `/technology/`, `/privacy/`, `/terms/`, `/insights/`, `/insights/<slug>/`, a styled 404. `/calculator/` and `/electrical-estimating/` (the metiger.us paths) 301 to the existing `/estimate-calculator` and `/canada-electrical-estimating-services/`. `/debug` was removed.

### Insights + admin (`insights.py`)
Posts are JSON files in `data/insights/` (gitignored, seeded once from `content/insights_seed/`). Back up `data/` with `.env`. Admin is at `/admin/` and uses the single `ADMIN_PASSWORD` from `.env` (admin returns 404 if unset). Post bodies use a small escaped Markdown subset (see `render_body`). Photos: the editor's "Insert photo" button uploads to `data/insights_media/` (re-encoded with Pillow, max 1600px, EXIF removed) and writes `![caption](/insights/media/<file>)` as its own paragraph; only that path is accepted as an image source.

### Website chat assistant (`chat.py`)
Corner chat widget (`partials/chat_widget.html`, `static/js/chat.js`) posting to `POST /api/chat`, which forwards to an OpenAI-compatible server. Off until `.env` has `CHAT_API_BASE` (ending in `/v1`) and `CHAT_MODEL` (optional `CHAT_API_KEY`, `CHAT_DAILY_CAP` default 400): while unset, the widget is not rendered and the endpoint 404s. The assistant may only use `content/chat_knowledge.md` — keep that file in step with the site, and keep the rules in `chat.RULES` (no invented prices/times, no phone number, no personal names, not engineering advice). Conversations are not stored. Safeguards: same-origin check, honeypot, per-visitor limits (8/min, 40/hour, 80/day), site-wide daily cap, capped message and reply length. An AI call can hold a gunicorn worker for up to 25 s.

### Rate limits
gunicorn sits behind nginx behind Cloudflare, so `request.remote_addr` is always 127.0.0.1. Page views are limited per visitor via `client_ip()` (CF-Connecting-IP); static files are exempt; `/send_message` and admin login stay keyed on the socket address, i.e. site-wide.

## Market positioning

`metiger.ca` is the **Canada** market site (this repo). `metiger.us` is a **separate** USA site. Keep USA-only language (Florida/Texas/NEC/NECA/"United States") OFF metiger.ca except the single "Looking for USA estimating? Visit metiger.us" cross-link. Use Canadian positioning: CSA C22.1 / Canadian Electrical Code, "CEC-aware", labour/colour/centre spelling. MeTiger provides **estimating and coordination support, not stamped/sealed engineering** — never claim otherwise.

## Architecture

Flask app (`app.py`) serving Jinja2 templates from `templates/`. Two shared layouts:
- **`base_page.html`** — the premium dark layout used by the homepage and all CA marketing/service/province pages. Provides SEO/canonical/OG/hreflang blocks, a per-page `head_schema` block, and pulls in the shared header/footer. Pages extend it and compose sections with macros from **`partials/ui.html`** (`trust_bar`, `checks`, `process_steps`, `systems`, `faq_list`, `faq_schema`, `breadcrumb`, `breadcrumb_schema`, `service_schema`, `cta_band`). NOTE: inside macro args use a raw `&` (macros autoescape); in literal template text use `&amp;`.
- **`base.html`** — legacy light layout, still used only by `estimate_calculator.html` and `budget_guide.html`.

Shared chrome partials: `partials/site_header.html` (Canada nav + mobile menu + USA cross-link + "Request a Quote" CTA), `partials/site_footer.html` (Canada footer + USA link + Privacy/Vision/Mission modals), `partials/structured_data.html` (global Org/WebSite/ProfessionalService JSON-LD, Canada), `partials/quote_form.html` (the shared multi-field quote form).

**Page registry:** `pages.py` maps every CA URL → template (under `templates/pages/`) → endpoint. `app.py` registers a render view for each in a loop and builds `/sitemap.xml` from `pages.sitemap_entries()`. To add a page: create the template extending `base_page.html`, add a line to `pages.py`. Key routes: `/` (home.html), `/contact/` (quote.html), `/canada-electrical-estimating-services/` (main SEO landing), 7 service pages, `/pricing/` `/samples/` `/case-studies/`, 10 province pages, `/payments` (crypto, off-funnel). `/services`→landing and `/projects`→`/case-studies/` are 301s. There is no database; the only dynamic surface is the quote/contact form.

A global `context_processor` injects `TURNSTILE_SITE_KEY` and a fresh `START_TS` into every template so any page can include `quote_form.html`.

### Quote / contact form pipeline
The homepage and `/contact/` both include `partials/quote_form.html`, which posts via `fetch` to `POST /send_message`. (`/contact/` is GET-only now — it renders the quote page; the old flash-only `/contact` POST is gone.) The endpoint runs a layered anti-spam check before sending mail; **all four layers must stay in place** because each catches a different attacker class:

1. **Honeypot** — a hidden `website` field (renamed from `company`, which is now a REAL quote field); any value → 400.
2. **Time gate** — form must be open ≥ 3s (client sends `started_at` from `START_TS` injected by the index route).
3. **Cloudflare Turnstile** — server-side `siteverify` against `TURNSTILE_SECRET`. Skipped only if both keys are empty (dev mode).
4. **Content checks** — URL count in message, disposable-email domain blocklist (`DISPOSABLE` set), basic email-shape validation, min message length.

Rate limiting via `flask-limiter`: 3/min on `/send_message`, 100/hour global default, keyed by remote IP.

Mail goes out via `send_contact_email(name, email, message, details)` using Office365 SMTP (`smtp.office365.com:587`, STARTTLS) authenticating as `info@metiger.ca`. The `From` address must match the authenticated `SMTP_USER` or Office365 will reject. `Reply-To` is set to the visitor's email so direct replies work. `details` is an optional dict of the extra quote fields (company, phone, province, project type, service, bid date, plan link, NDA, consent, source); non-empty values are appended to the body and the subject is built dynamically as `metiger.ca Quote Request – [Project Type] – [Province]`. Recipient is `TO_EMAIL` (defaults `info@metiger.ca`). The required fields are still just name/email/message, so the simple path keeps working. `requirements.txt` still pins `sendgrid` — it is unused; SMTP is the live path.

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
