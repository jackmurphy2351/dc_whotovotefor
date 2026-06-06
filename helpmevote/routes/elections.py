from flask import Blueprint, abort, render_template

from ..i18n import get_content

bp = Blueprint("elections", __name__)


@bp.route("/election/<slug>")
def election(slug: str):
    content = get_content()
    elec = content.elections.get(slug)
    if not elec:
        abort(404)
    candidates = content.candidates.get(slug, [])
    return render_template("election.html", election=elec, candidates=candidates)


@bp.route("/candidate/<election_slug>/<candidate_id>")
def candidate(election_slug: str, candidate_id: str):
    content = get_content()
    elec = content.elections.get(election_slug)
    if not elec:
        abort(404)
    cand = content.candidates_by_id.get(candidate_id)
    if not cand or cand.election_slug != election_slug:
        abort(404)
    questions = {q.id: q for q in content.questions_by_election.get(election_slug, [])}
    issues = content.issues
    return render_template(
        "candidate.html", election=elec, candidate=cand, questions=questions, issues=issues
    )
