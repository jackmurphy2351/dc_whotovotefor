import re
from pathlib import Path

import frontmatter
import markdown as md
from flask import Blueprint, abort, current_app, render_template

from ..i18n import current_lang, translate_ui

# Root-relative links inside resource markdown (e.g. /resources/ranked_choice) are
# authored without a language prefix; rewrite them to the active language so they
# don't 404 under the /<lang_code>/ routing. Skips protocol-relative (//) links.
_INTERNAL_HREF = re.compile(r'href="/(?!/)')

bp = Blueprint("resources", __name__)

# Display order and the allowlist of valid resource topics. Titles are
# translated via ui.yaml under the "resources.title.<topic>" key.
TOPIC_ORDER = [
    "primary_vs_general",
    "ranked_choice",
    "topa",
    "fair_elections",
    "dc_council",
    "delegate_statehood",
    "special_elections",
    "methodology",
    "privacy",
]
TOPIC_SLUGS = set(TOPIC_ORDER)


def _topic_title(topic: str) -> str:
    return translate_ui(f"resources.title.{topic}")


def _resources_dir() -> Path:
    return current_app.config["CONTENT_DIR"] / "resources"


def _load_resource(topic: str):
    """Load a resource page, preferring the active language's translated markdown
    (content/<lang>/resources/<topic>.md) and falling back to English."""
    base = current_app.config["CONTENT_DIR"]
    candidates = [base / current_lang() / "resources" / f"{topic}.md",
                  base / "resources" / f"{topic}.md"]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return None
    post = frontmatter.load(str(path))
    body_html = md.markdown(post.content, extensions=["tables", "attr_list"])
    body_html = _INTERNAL_HREF.sub(f'href="/{current_lang()}/', body_html)
    return {"meta": post.metadata, "html": body_html, "topic": topic,
            "title": _topic_title(topic)}


@bp.route("/resources")
def index():
    resources_dir = _resources_dir()
    topics = []
    for t in TOPIC_ORDER:
        if (resources_dir / f"{t}.md").exists():
            topics.append({"slug": t, "title": _topic_title(t)})
    return render_template("resources/index.html", topics=topics)


@bp.route("/resources/<topic>")
def topic(topic: str):
    if topic not in TOPIC_SLUGS:
        abort(404)
    resource = _load_resource(topic)
    if not resource:
        abort(404)
    return render_template("resources/topic.html", resource=resource)
