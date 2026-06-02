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
SELECTION_KEY = "quiz_selected"


def _session_key(slug: str) -> str:
    return f"{SESSION_KEY}_{slug}"


def _selection_key(slug: str) -> str:
    return f"{SELECTION_KEY}_{slug}"


def _active_questions(content, slug: str) -> list:
    """Election questions filtered to the user's saved selection.

    When no selection is stored (e.g. a direct link to the quiz), all of the
    election's questions are returned — backward-compatible with the old flow.
    """
    questions = content.questions_by_election.get(slug, [])
    selected = session.get(_selection_key(slug))
    if selected is None:
        return questions
    chosen = set(selected)
    return [q for q in questions if q.id in chosen]


def _grouped_questions(content, slug: str) -> list:
    """Ordered ``[(Issue, [Question, ...]), ...]`` for the selection screen.

    Preserves questions.yaml order and first-seen issue order.
    """
    groups: list = []
    index: dict[str, int] = {}
    for q in content.questions_by_election.get(slug, []):
        if q.issue not in index:
            index[q.issue] = len(groups)
            groups.append((content.issues.get(q.issue), []))
        groups[index[q.issue]][1].append(q)
    return groups


@bp.route("/quiz/<slug>/start")
def start(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = content.questions_by_election.get(slug, [])
    if not questions:
        return render_template("quiz_no_questions.html", election=elec)

    saved_selection = session.get(_selection_key(slug))
    # No selection stored yet → everything pre-checked.
    selected = set(saved_selection) if saved_selection is not None else {q.id for q in questions}

    return render_template(
        "quiz_start.html",
        election=elec,
        groups=_grouped_questions(content, slug),
        selected=selected,
        total=len(questions),
        error=False,
    )


@bp.post("/quiz/<slug>/start")
def start_post(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = content.questions_by_election.get(slug, [])
    valid_ids = {q.id for q in questions}
    selected = [qid for qid in request.form.getlist("selected") if qid in valid_ids]

    if not selected:
        return render_template(
            "quiz_start.html",
            election=elec,
            groups=_grouped_questions(content, slug),
            selected=set(),
            total=len(questions),
            error=True,
        )

    session[_selection_key(slug)] = selected
    return redirect(url_for("quiz.quiz", slug=slug, step=0, fresh=1))


@bp.route("/quiz/<slug>")
def quiz(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = _active_questions(content, slug)
    if not questions:
        return render_template("quiz_no_questions.html", election=elec)

    step = request.args.get("step", 0, type=int)
    step = max(0, min(step, len(questions) - 1))
    question = questions[step]
    issue = content.issues.get(question.issue)

    saved = session.get(_session_key(slug), {})
    saved_stance = saved.get(question.id)
    if request.args.get("fresh"):
        saved_stance = None

    return render_template(
        "quiz.html",
        election=elec,
        question=question,
        issue=issue,
        step=step,
        total=len(questions),
        saved_stance=saved_stance,
    )


@bp.post("/quiz/<slug>")
def quiz_post(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = _active_questions(content, slug)
    step = request.form.get("step", 0, type=int)

    if step < len(questions):
        qid = questions[step].id
        raw_stance = request.form.get("stance")

        saved = session.get(_session_key(slug), {})
        stance = int(raw_stance) if raw_stance not in (None, "", "skip") else None
        saved[qid] = stance
        session[_session_key(slug)] = saved

    next_step = step + 1
    if next_step < len(questions):
        return redirect(url_for("quiz.quiz", slug=slug, step=next_step, fresh=1))
    return redirect(url_for("quiz.results", slug=slug))


@bp.route("/results/<slug>")
def results(slug: str):
    content = current_app.config["CONTENT"]
    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = _active_questions(content, slug)
    candidates = content.candidates.get(slug, [])
    issues = content.issues
    saved: dict = session.get(_session_key(slug), {})

    all_zero = not saved or all(s is None for s in saved.values())

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
    session.pop(_selection_key(slug), None)
    return redirect(url_for("quiz.start", slug=slug))
