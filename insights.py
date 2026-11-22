"""Insights section for metiger.ca: public article pages plus a small
password-protected admin area for adding, editing and deleting posts.

Storage is one JSON file per post under data/insights/ (no database). The
data/ directory is gitignored so posts written through the admin page are
never touched by a deploy; on first run it is seeded from content/insights_seed/.

Admin access uses a single password read from ADMIN_PASSWORD in .env. If that
variable is empty the admin routes return 404.
"""
import hmac
import json
import os
import re
import secrets
import tempfile
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Blueprint, abort, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from markupsafe import Markup, escape

bp = Blueprint("insights", __name__)

_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_ROOT, "data", "insights")
SEED_DIR = os.path.join(_ROOT, "content", "insights_seed")
# Photos uploaded through the admin page. Lives under data/ (gitignored) so it
# is backed up with the posts and never touched by a deploy.
MEDIA_DIR = os.path.join(_ROOT, "data", "insights_media")
MEDIA_NAME_RE = re.compile(r"^[a-f0-9]{20}\.(?:jpg|png)$")
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_SIDE = 1600

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_TITLE, MAX_DESC, MAX_BODY, MAX_TAGS = 160, 320, 60000, 8
ADMIN_SESSION_HOURS = 12


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
def _ensure_data_dir():
    """Create data/insights/, seeding it once from the committed seed posts."""
    if os.path.isdir(DATA_DIR):
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.isdir(SEED_DIR):
        for name in sorted(os.listdir(SEED_DIR)):
            if name.endswith(".json"):
                with open(os.path.join(SEED_DIR, name), encoding="utf-8") as src:
                    _write_json(os.path.join(DATA_DIR, name), json.load(src))


def _write_json(path, payload):
    """Atomic write so a crash or two workers never leave a half-written post."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _path(slug):
    if not SLUG_RE.match(slug or "") or len(slug) > 80:
        return None
    return os.path.join(DATA_DIR, slug + ".json")


def load_post(slug):
    _ensure_data_dir()
    path = _path(slug)
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            post = json.load(fh)
    except (OSError, ValueError):
        return None
    post["slug"] = slug
    return post


def all_posts(include_drafts=False):
    """Newest first."""
    _ensure_data_dir()
    posts = []
    for name in os.listdir(DATA_DIR):
        if name.endswith(".json"):
            post = load_post(name[:-5])
            if post and (include_drafts or post.get("published", True)):
                posts.append(post)
    posts.sort(key=lambda p: (p.get("date", ""), p.get("slug", "")), reverse=True)
    return posts


def sitemap_entries():
    """(path, lastmod) for every published post."""
    return [("/insights/%s/" % p["slug"], p.get("updated") or p.get("date")) for p in all_posts()]


# --------------------------------------------------------------------------
# Body formatting: a small, safe subset of Markdown. Everything is HTML-escaped
# first, so nothing typed in the admin form can inject markup or script.
# --------------------------------------------------------------------------
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(((?:https?://|/)[^\s)]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_ITAL_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
# A photo is a paragraph on its own: ![caption](/insights/media/<file>).
# Only files uploaded through the admin page are accepted as a source.
_IMAGE_RE = re.compile(r"^!\[([^\]\n]*)\]\((/insights/media/[a-f0-9]{20}\.(?:jpg|png))\)$")


def _inline(text):
    out = str(escape(text))

    def link(m):
        label, url = m.group(1), m.group(2)
        ext = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
        return '<a href="%s"%s>%s</a>' % (url, ext, label)

    out = _LINK_RE.sub(link, out)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = _ITAL_RE.sub(r"<em>\1</em>", out)
    return out


def render_body(body):
    blocks = re.split(r"\n\s*\n", (body or "").replace("\r\n", "\n").strip())
    html = []
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        image = _IMAGE_RE.match(lines[0]) if len(lines) == 1 else None
        if image:
            caption = str(escape(image.group(1).strip()))
            html.append('<figure class="article-figure"><img src="%s" alt="%s" loading="lazy">%s</figure>'
                        % (image.group(2), caption,
                           "<figcaption>%s</figcaption>" % caption if caption else ""))
        elif lines[0].startswith("### "):
            html.append("<h3>%s</h3>" % _inline(lines[0][4:]))
        elif lines[0].startswith("## "):
            html.append("<h2>%s</h2>" % _inline(lines[0][3:]))
        elif all(ln.startswith("- ") for ln in lines):
            html.append("<ul>%s</ul>" % "".join("<li>%s</li>" % _inline(ln[2:]) for ln in lines))
        else:
            html.append("<p>%s</p>" % _inline(" ".join(lines)))
    return Markup("\n".join(html))


def pretty_date(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return "%s %d, %d" % (d.strftime("%B"), d.day, d.year)
    except (TypeError, ValueError):
        return iso or ""


@bp.app_template_filter("pretty_date")
def _pretty_date_filter(value):
    return pretty_date(value)


# --------------------------------------------------------------------------
# Public pages
# --------------------------------------------------------------------------
@bp.route("/insights/")
def insights_index():
    return render_template("insights_index.html", posts=all_posts())


@bp.route("/insights/<slug>/")
def insights_post(slug):
    post = load_post(slug)
    if not post or not post.get("published", True):
        abort(404)
    related = [p for p in all_posts() if p["slug"] != slug][:3]
    return render_template("insights_post.html", post=post,
                           body_html=render_body(post.get("body", "")), related=related)


@bp.route("/insights/media/<name>")
def insights_media(name):
    if not MEDIA_NAME_RE.match(name):
        abort(404)
    return send_from_directory(MEDIA_DIR, name, max_age=31536000)


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------
def _admin_password():
    return os.environ.get("ADMIN_PASSWORD", "")


def _csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _check_csrf():
    sent = request.form.get("csrf", "")
    if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
        abort(400)


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _admin_password():
            abort(404)
        if not session.get("admin"):
            return redirect(url_for("insights.admin_login"))
        return view(*args, **kwargs)
    return wrapper


@bp.after_request
def _no_index_admin(resp):
    if request.path.startswith("/admin"):
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/admin/", methods=["GET"])
def admin_home():
    return redirect(url_for("insights.admin_insights"))


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not _admin_password():
        abort(404)
    error = None
    if request.method == "POST":
        _check_csrf()
        supplied = request.form.get("password", "")
        if hmac.compare_digest(supplied.encode(), _admin_password().encode()):
            session.clear()
            session["admin"] = True
            session.permanent = True
            _csrf_token()
            return redirect(url_for("insights.admin_insights"))
        error = "Wrong password."
    return render_template("admin/login.html", csrf=_csrf_token(), error=error), (401 if error else 200)


@bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    _check_csrf()
    session.clear()
    return redirect(url_for("insights.admin_login"))


@bp.route("/admin/insights")
@admin_required
def admin_insights():
    return render_template("admin/insights.html", posts=all_posts(include_drafts=True),
                           csrf=_csrf_token(), saved=request.args.get("saved"))


def _slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:80].strip("-")


def _form_to_post(existing=None):
    """Validate the edit form. Returns (post_dict, errors)."""
    f = request.form
    title = f.get("title", "").strip()
    slug = (existing or {}).get("slug") or _slugify(f.get("slug", "").strip() or title)
    post = {
        "slug": slug,
        "title": title,
        "date": f.get("date", "").strip() or date.today().isoformat(),
        "description": f.get("description", "").strip(),
        "tags": [t.strip() for t in f.get("tags", "").split(",") if t.strip()][:MAX_TAGS],
        "body": f.get("body", "").replace("\r\n", "\n").strip(),
        "published": f.get("published") == "yes",
    }
    errors = []
    if not title:
        errors.append("Add a title.")
    if len(title) > MAX_TITLE:
        errors.append("Title is too long (max %d characters)." % MAX_TITLE)
    if not SLUG_RE.match(slug or ""):
        errors.append("The web address may only use lowercase letters, numbers and dashes.")
    try:
        datetime.strptime(post["date"], "%Y-%m-%d")
    except ValueError:
        errors.append("Date must look like 2026-11-22.")
    if len(post["description"]) > MAX_DESC:
        errors.append("Summary is too long (max %d characters)." % MAX_DESC)
    if not post["body"]:
        errors.append("Write the article text.")
    if len(post["body"]) > MAX_BODY:
        errors.append("Article text is too long.")
    return post, errors


@bp.route("/admin/insights/new", methods=["GET", "POST"])
@admin_required
def admin_insight_new():
    post, errors = {"date": date.today().isoformat(), "published": True, "tags": []}, []
    if request.method == "POST":
        _check_csrf()
        post, errors = _form_to_post()
        if not errors and load_post(post["slug"]):
            errors.append("An article with that web address already exists.")
        if not errors:
            post["updated"] = date.today().isoformat()
            _write_json(_path(post["slug"]), post)
            return redirect(url_for("insights.admin_insights", saved=post["slug"]))
    return render_template("admin/edit.html", post=post, errors=errors, is_new=True,
                           csrf=_csrf_token(),
                           preview=render_body(post.get("body", "")) if errors else None)


@bp.route("/admin/insights/<slug>/edit", methods=["GET", "POST"])
@admin_required
def admin_insight_edit(slug):
    post = load_post(slug)
    if not post:
        abort(404)
    errors = []
    if request.method == "POST":
        _check_csrf()
        post, errors = _form_to_post(existing=post)
        if not errors:
            post["updated"] = date.today().isoformat()
            _write_json(_path(slug), post)
            return redirect(url_for("insights.admin_insights", saved=slug))
    return render_template("admin/edit.html", post=post, errors=errors, is_new=False,
                           csrf=_csrf_token(), preview=None)


def _store_image(upload):
    """Check an uploaded photo and save a clean copy. Returns (name, error).

    The picture is re-encoded rather than stored as sent: that proves it really
    is an image, shrinks phone-sized photos, and drops embedded data such as the
    GPS location a phone camera records.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        img = Image.open(upload.stream)
        if img.format not in ("JPEG", "PNG", "WEBP"):
            return None, "Use a JPG, PNG or WebP picture."
        if img.width * img.height > 60_000_000:
            return None, "That picture is too large."
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        transparent = img.mode in ("RGBA", "LA") or "transparency" in img.info
        os.makedirs(MEDIA_DIR, exist_ok=True)
        if transparent:
            name = secrets.token_hex(10) + ".png"
            img.convert("RGBA").save(os.path.join(MEDIA_DIR, name), "PNG", optimize=True)
        else:
            name = secrets.token_hex(10) + ".jpg"
            img.convert("RGB").save(os.path.join(MEDIA_DIR, name), "JPEG",
                                    quality=85, optimize=True, progressive=True)
        return name, None
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None, "That file could not be read as a picture."


@bp.route("/admin/insights/upload", methods=["POST"])
@admin_required
def admin_insight_upload():
    _check_csrf()
    upload = request.files.get("photo")
    if not upload or not upload.filename:
        return jsonify(ok=False, message="Choose a picture first."), 400
    if (request.content_length or 0) > MAX_IMAGE_BYTES:
        return jsonify(ok=False, message="That picture is over 12 MB. Use a smaller one."), 413
    name, error = _store_image(upload)
    if error:
        return jsonify(ok=False, message=error), 400
    return jsonify(ok=True, url="/insights/media/" + name)


@bp.route("/admin/insights/<slug>/delete", methods=["POST"])
@admin_required
def admin_insight_delete(slug):
    _check_csrf()
    path = _path(slug)
    if not path or not os.path.isfile(path):
        abort(404)
    if request.form.get("confirm") != slug:
        abort(400)
    os.unlink(path)
    return redirect(url_for("insights.admin_insights"))


def init_app(app, limiter=None, strict_key=None):
    """Register the blueprint and harden the admin session cookie."""
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=ADMIN_SESSION_HOURS))
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Strict")
    # Secure cookies everywhere except an explicit local dev run over http.
    app.config.setdefault("SESSION_COOKIE_SECURE", os.environ.get("METIGER_DEV") != "1")
    app.register_blueprint(bp)
    if limiter is not None:
        # Password guessing: 5 tries a minute, counted site-wide (not per IP).
        name = "insights.admin_login"
        app.view_functions[name] = limiter.limit(
            "5/minute", key_func=strict_key, methods=["POST"])(app.view_functions[name])
