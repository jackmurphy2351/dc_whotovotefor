import types
from datetime import date

from flask import (
    Blueprint,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from helpmevote.i18n import get_content, translate_ui
from helpmevote.scoring import match_score, rank_candidates

bp = Blueprint("quiz", __name__)

# Answers live in a single, election-agnostic store keyed by question id, so a
# stance given in one race automatically counts in every other race the question
# applies to. Only "which questions to present" stays per-race (the selection).
GLOBAL_ANSWERS_KEY = "quiz_answers"
SELECTION_KEY = "quiz_selected"

# Pseudo-slug for the "answer everything, see every race" flow.
ALL_SLUG = "all"


def _selection_key(slug: str) -> str:
    return f"{SELECTION_KEY}_{slug}"


def _answers() -> dict:
    return session.get(GLOBAL_ANSWERS_KEY, {})


def _save_answers(answers: dict) -> None:
    session[GLOBAL_ANSWERS_KEY] = answers


def _resolve_election(content, slug: str):
    """Return the Election for ``slug``, or a synthetic stand-in for ALL_SLUG."""
    if slug == ALL_SLUG:
        return types.SimpleNamespace(slug=ALL_SLUG, title=translate_ui("quiz.all_races"))
    return content.elections.get(slug)


def _base_questions(content, slug: str) -> list:
    """All questions in scope for a flow: the union for ALL_SLUG, else the race's."""
    if slug == ALL_SLUG:
        return list(content.questions.values())
    return content.questions_by_election.get(slug, [])


def _active_questions(content, slug: str) -> list:
    """In-scope questions filtered to the user's saved selection.

    When no selection is stored (e.g. a direct link to the quiz), all of the
    in-scope questions are returned — backward-compatible with the old flow.
    """
    questions = _base_questions(content, slug)
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
    for q in _base_questions(content, slug):
        if q.issue not in index:
            index[q.issue] = len(groups)
            groups.append((content.issues.get(q.issue), []))
        groups[index[q.issue]][1].append(q)
    return groups


@bp.route("/quiz/<slug>/start")
def start(slug: str):
    content = get_content()
    elec = _resolve_election(content, slug)
    if not elec:
        abort(404)

    questions = _base_questions(content, slug)
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
    content = get_content()
    elec = _resolve_election(content, slug)
    if not elec:
        abort(404)

    questions = _base_questions(content, slug)
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
    return redirect(url_for("quiz.quiz", slug=slug, step=0))


@bp.route("/quiz/<slug>")
def quiz(slug: str):
    content = get_content()
    elec = _resolve_election(content, slug)
    if not elec:
        abort(404)

    questions = _active_questions(content, slug)
    if not questions:
        return render_template("quiz_no_questions.html", election=elec)

    step = request.args.get("step", 0, type=int)
    step = max(0, min(step, len(questions) - 1))
    question = questions[step]
    issue = content.issues.get(question.issue)

    saved_stance = _answers().get(question.id)

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
    content = get_content()
    elec = _resolve_election(content, slug)
    if not elec:
        abort(404)

    questions = _active_questions(content, slug)
    step = request.form.get("step", 0, type=int)

    if step < len(questions):
        qid = questions[step].id
        raw_stance = request.form.get("stance")

        answers = _answers()
        answers[qid] = int(raw_stance) if raw_stance not in (None, "", "skip") else None
        _save_answers(answers)

    next_step = step + 1
    if next_step < len(questions):
        return redirect(url_for("quiz.quiz", slug=slug, step=next_step))
    return redirect(url_for("quiz.results", slug=slug))


@bp.route("/results/<slug>")
def results(slug: str):
    content = get_content()
    if slug == ALL_SLUG:
        return _results_all(content)

    elec = content.elections.get(slug)
    if not elec:
        abort(404)

    questions = _active_questions(content, slug)
    candidates = content.candidates.get(slug, [])
    issues = content.issues
    saved = _answers()

    all_zero = not saved or all(s is None for s in saved.values())

    scored = [match_score(saved, c, questions, issues) for c in candidates]
    ranked = rank_candidates(scored)

    return render_template(
        "results.html",
        election=elec,
        ranked=ranked,
        all_zero=all_zero,
        questions={q.id: q for q in questions},
        issues=issues,
    )


def _results_all(content):
    """Combined results: each race scored over its full question set from the
    one shared answer store."""
    saved = _answers()
    all_zero = not saved or all(s is None for s in saved.values())
    issues = content.issues

    race_results = []
    for slug, elec in content.elections.items():
        questions = content.questions_by_election.get(slug, [])
        candidates = content.candidates.get(slug, [])
        if not questions or not candidates:
            continue
        scored = [match_score(saved, c, questions, issues) for c in candidates]
        race_results.append((elec, rank_candidates(scored)))

    return render_template(
        "results_all.html",
        race_results=race_results,
        all_zero=all_zero,
    )


@bp.route("/results/<slug>/download")
def download(slug: str):
    """Self-contained HTML report of the user's results, served as a download.

    Mirrors the results pages but never truncates: the ALL_SLUG report carries
    every candidate in every race (the on-screen version shows only the top 3
    per race) with the full question-by-question breakdown.
    """
    content = get_content()
    if slug != ALL_SLUG and slug not in content.elections:
        abort(404)

    # Nothing to report without answers — send the user to the results page,
    # which explains how to take the quiz.
    saved = _answers()
    if not saved or all(s is None for s in saved.values()):
        return redirect(url_for("quiz.results", slug=slug))

    issues = content.issues
    if slug == ALL_SLUG:
        race_results = []
        for race_slug, elec in content.elections.items():
            questions = content.questions_by_election.get(race_slug, [])
            candidates = content.candidates.get(race_slug, [])
            if not questions or not candidates:
                continue
            scored = [match_score(saved, c, questions, issues) for c in candidates]
            race_results.append((elec, rank_candidates(scored)))
    else:
        elec = content.elections[slug]
        questions = _active_questions(content, slug)
        candidates = content.candidates.get(slug, [])
        scored = [match_score(saved, c, questions, issues) for c in candidates]
        race_results = [(elec, rank_candidates(scored))]

    today = date.today()
    html = render_template(
        "report.html",
        race_results=race_results,
        generated=today,
    )
    filename = f"help-me-vote-dc-results-{slug}-{today.isoformat()}.html"
    return Response(
        html,
        mimetype="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/quiz/<slug>/reset")
def reset(slug: str):
    # Answers are shared across races, so "start over" clears the whole store
    # (and every saved question selection).
    session.pop(GLOBAL_ANSWERS_KEY, None)
    for key in list(session.keys()):
        if key.startswith(SELECTION_KEY + "_"):
            session.pop(key, None)
    return redirect(url_for("quiz.start", slug=slug))
