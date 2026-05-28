from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from helpmevote.scoring import match_score, rank_candidates

bp = Blueprint("quiz", __name__)

SESSION_KEY = "quiz_answers"


def _session_key(slug: str) -> str:
    return f"{SESSION_KEY}_{slug}"


@bp.route("/quiz/<slug>")
def quiz(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = content.questions_by_election.get(slug, [])
    if not questions:
        return render_template("quiz_no_questions.html", election=elec)

    step = request.args.get("step", 0, type=int)
    step = max(0, min(step, len(questions) - 1))
    question = questions[step]
    issue = content.issues.get(question.issue)

    saved = session.get(_session_key(slug), {})
    saved_stance, saved_importance = saved.get(question.id, (None, None))

    return render_template(
        "quiz.html",
        election=elec,
        question=question,
        issue=issue,
        step=step,
        total=len(questions),
        saved_stance=saved_stance,
        saved_importance=saved_importance,
    )


@bp.post("/quiz/<slug>")
def quiz_post(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = content.questions_by_election.get(slug, [])
    step = request.form.get("step", 0, type=int)

    if step < len(questions):
        qid = questions[step].id
        raw_stance = request.form.get("stance")
        raw_importance = request.form.get("importance", 0, type=int)

        saved = session.get(_session_key(slug), {})
        stance = int(raw_stance) if raw_stance not in (None, "", "skip") else None
        saved[qid] = (stance, raw_importance)
        session[_session_key(slug)] = saved

    next_step = step + 1
    if next_step < len(questions):
        return redirect(url_for("quiz.quiz", slug=slug, step=next_step))
    return redirect(url_for("quiz.results", slug=slug))


@bp.route("/results/<slug>")
def results(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = content.questions_by_election.get(slug, [])
    candidates = content.candidates.get(slug, [])
    issues = content.issues
    saved: dict = session.get(_session_key(slug), {})

    all_zero = all(imp == 0 for (_, imp) in saved.values()) if saved else True

    scored = [
        match_score(saved, c, questions, issues)
        for c in candidates
    ]
    ranked = rank_candidates(scored)

    return render_template(
        "results.html",
        election=elec,
        ranked=ranked,
        all_zero=all_zero,
        questions={q.id: q for q in questions},
        issues=issues,
    )


@bp.route("/quiz/<slug>/reset")
def reset(slug: str):
    session.pop(_session_key(slug), None)
    return redirect(url_for("quiz.quiz", slug=slug))
