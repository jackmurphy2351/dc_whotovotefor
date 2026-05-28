from dataclasses import dataclass

from .models import Candidate, Question


@dataclass
class IssueScore:
    issue_id: str
    issue_label: str
    match_percent: float | None
    answered: int
    total: int


@dataclass
class ScoredCandidate:
    candidate: Candidate
    match_percent: float | None
    issue_scores: list[IssueScore]

    @property
    def insufficient_data(self) -> bool:
        return self.match_percent is None


def match_score(
    user_answers: dict[str, int | None],
    candidate: Candidate,
    questions: list[Question],
    issues: dict,
) -> ScoredCandidate:
    """
    Compute a candidate's match score against user answers.

    user_answers: {question_id: user_stance}
      user_stance: -2..+2, or None = skipped / no opinion
    """
    positions_by_qid = {p.question_id: p for p in candidate.positions}

    numerator = 0.0
    denominator = 0.0

    issue_data: dict[str, dict] = {}

    for question in questions:
        qid = question.id
        if qid not in user_answers:
            continue

        user_stance = user_answers[qid]
        issue_id = question.issue
        if issue_id not in issue_data:
            issue_data[issue_id] = {"num": 0.0, "den": 0.0, "answered": 0, "total": 0}

        if user_stance is None:
            continue

        position = positions_by_qid.get(qid)
        if position is None or position.stance is None:
            continue

        distance = abs(user_stance - position.stance)
        agreement = 1.0 - (distance / 4.0)

        numerator += agreement
        denominator += 1.0

        issue_data[issue_id]["num"] += agreement
        issue_data[issue_id]["den"] += 1.0
        issue_data[issue_id]["answered"] += 1
        issue_data[issue_id]["total"] += 1

    match_percent = (100.0 * numerator / denominator) if denominator > 0 else None

    issue_scores = []
    for question in questions:
        issue_id = question.issue
        if issue_id in issue_data and issue_id not in [s.issue_id for s in issue_scores]:
            d = issue_data[issue_id]
            label = issues[issue_id].label if issue_id in issues else issue_id
            pct = (100.0 * d["num"] / d["den"]) if d["den"] > 0 else None
            issue_scores.append(IssueScore(
                issue_id=issue_id,
                issue_label=label,
                match_percent=pct,
                answered=d["answered"],
                total=d["total"],
            ))

    return ScoredCandidate(
        candidate=candidate,
        match_percent=match_percent,
        issue_scores=issue_scores,
    )


def rank_candidates(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Sort by match_percent desc (None last), then name asc."""
    def sort_key(sc: ScoredCandidate):
        pct = sc.match_percent if sc.match_percent is not None else -1.0
        return (-pct, sc.candidate.name)

    return sorted(scored, key=sort_key)
