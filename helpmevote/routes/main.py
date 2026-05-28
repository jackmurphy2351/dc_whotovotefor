from flask import Blueprint, current_app, render_template

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    content = current_app.config["CONTENT"]
    elections = list(content.elections.values())
    return render_template("index.html", elections=elections)


@bp.route("/about")
def about():
    return render_template("about.html")
