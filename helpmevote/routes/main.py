from flask import Blueprint, current_app, make_response, render_template, url_for

from .resources import TOPIC_TITLES

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    content = current_app.config["CONTENT"]
    elections = list(content.elections.values())
    return render_template("index.html", elections=elections)


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.route("/robots.txt")
def robots():
    sitemap_url = url_for("main.sitemap", _external=True)
    body = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    resp = make_response(body)
    resp.headers["Content-Type"] = "text/plain"
    return resp


@bp.route("/sitemap.xml")
def sitemap():
    content = current_app.config["CONTENT"]
    resources_dir = current_app.config["CONTENT_DIR"] / "resources"

    urls = [
        url_for("main.index", _external=True),
        url_for("main.about", _external=True),
        url_for("resources.index", _external=True),
    ]

    for topic in TOPIC_TITLES:
        if (resources_dir / f"{topic}.md").exists():
            urls.append(url_for("resources.topic", topic=topic, _external=True))

    for election in content.elections.values():
        urls.append(url_for("elections.election", slug=election.slug, _external=True))

    for election_slug, candidates in content.candidates.items():
        for candidate in candidates:
            urls.append(
                url_for(
                    "elections.candidate",
                    election_slug=election_slug,
                    candidate_id=candidate.id,
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
