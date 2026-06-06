from flask import (
    Blueprint,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_content
from .resources import TOPIC_ORDER

# Language-prefixed content pages (mounted under /<lang_code>/ in the app factory).
bp = Blueprint("main", __name__)

# Root-level, language-agnostic endpoints (no /<lang_code>/ prefix).
root_bp = Blueprint("root", __name__)


@bp.route("/")
def index():
    content = get_content()
    elections = list(content.elections.values())
    return render_template("index.html", elections=elections)


@bp.route("/about")
def about():
    return render_template("about.html")


@root_bp.route("/")
def root():
    """Send the bare domain to a language: remembered choice, then the browser's
    preference, then the default."""
    lang = session.get("lang")
    if lang not in SUPPORTED_LANGUAGES:
        lang = request.accept_languages.best_match(SUPPORTED_LANGUAGES) or DEFAULT_LANGUAGE
    return redirect(url_for("main.index", lang_code=lang))


@root_bp.route("/robots.txt")
def robots():
    sitemap_url = url_for("root.sitemap", _external=True)
    body = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    resp = make_response(body)
    resp.headers["Content-Type"] = "text/plain"
    return resp


@root_bp.route("/sitemap.xml")
def sitemap():
    # English content defines the canonical structure; emit every URL once per
    # supported language prefix.
    content = get_content()
    resources_dir = current_app.config["CONTENT_DIR"] / "resources"

    urls = []
    for lang in SUPPORTED_LANGUAGES:
        urls.append(url_for("main.index", lang_code=lang, _external=True))
        urls.append(url_for("main.about", lang_code=lang, _external=True))
        urls.append(url_for("resources.index", lang_code=lang, _external=True))
        for topic in TOPIC_ORDER:
            if (resources_dir / f"{topic}.md").exists():
                urls.append(
                    url_for("resources.topic", topic=topic, lang_code=lang, _external=True)
                )
        for election in content.elections.values():
            urls.append(
                url_for("elections.election", slug=election.slug, lang_code=lang, _external=True)
            )
        for election_slug, candidates in content.candidates.items():
            for candidate in candidates:
                urls.append(
                    url_for(
                        "elections.candidate",
                        election_slug=election_slug,
                        candidate_id=candidate.id,
                        lang_code=lang,
                        _external=True,
                    )
                )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        lines.append(f"  <url><loc>{url}</loc></url>")
    lines.append("</urlset>")

    resp = make_response("\n".join(lines))
    resp.headers["Content-Type"] = "application/xml"
    return resp
