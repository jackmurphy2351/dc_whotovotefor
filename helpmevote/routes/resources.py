from pathlib import Path

import frontmatter
import markdown as md
from flask import Blueprint, abort, current_app, render_template

bp = Blueprint("resources", __name__)

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

TOPIC_TITLES = {
    "primary_vs_general": "Why the Democratic Primary Is Effectively the General Election in DC",
    "ranked_choice": "Ranked Choice Voting / Initiative 83",
    "topa": "TOPA & DOPA: Tenant Purchase Rights",
    "fair_elections": "The DC Fair Elections Program",
    "dc_council": "How the DC Council Works",
    "delegate_statehood": "The Non-Voting Delegate & DC Statehood",
    "special_elections": "How Special Elections Work",
    "methodology": "How We Assign Candidate Stances",
    "privacy": "Privacy & Your Data",
}


def _load_resource(resources_dir: Path, topic: str):
    path = resources_dir / f"{topic}.md"
    if not path.exists():
        return None
    post = frontmatter.load(str(path))
    body_html = md.markdown(post.content, extensions=["tables", "attr_list"])
    return {"meta": post.metadata, "html": body_html, "topic": topic,
            "title": TOPIC_TITLES.get(topic, topic)}


@bp.route("/resources")
def index():
    resources_dir = current_app.config["CONTENT_DIR"] / "resources"
    topics = []
    for t in TOPIC_ORDER:
        path = resources_dir / f"{t}.md"
        if path.exists():
            topics.append({"slug": t, "title": TOPIC_TITLES.get(t, t)})
    return render_template("resources/index.html", topics=topics)


@bp.route("/resources/<topic>")
def topic(topic: str):
    if topic not in TOPIC_TITLES:
        abort(404)
    resources_dir = current_app.config["CONTENT_DIR"] / "resources"
    resource = _load_resource(resources_dir, topic)
    if not resource:
        abort(404)
    return render_template("resources/topic.html", resource=resource)
