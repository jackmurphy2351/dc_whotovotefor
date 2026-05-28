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
    covered_high_importance: int
    total_high_importance: int

    @property
    def insufficient_data(self) -> bool:
        return self.match_percent is None

    @property
    def coverage_warning(self) -> bool:
        return (
            self.total_high_importance > 0
            and self.covered_high_importance < self.total_high_importance
        )


def match_score(
    user_answers: dict[str, tuple[int | None, int]],
    candidate: Candidate,
    questions: list[Question],
    issues: dict,
) -> ScoredCandidate:
    """
    Compute a candidate's match score against user answers.

    user_answers: {question_id: (user_stance, importance)}
      user_stance: -2..+2, or None = "no opinion"
      importance:  0..3  (0 = excluded)
    """
    positions_by_qid = {p.question_id: p for p in candidate.positions}

    numerator = 0.0
    denominator = 0.0
    covered_high = 0
    total_high = 0

    issue_data: dict[str, dict] = {}

    for question in questions:
        qid = question.id
        if qid not in user_answers:
            continue

        user_stance, importance = user_answers[qid]
        issue_id = question.issue
        if issue_id not in issue_data:
            issue_data[issue_id] = {"num": 0.0, "den": 0.0, "answered": 0, "total": 0}

        if importance >= 2:
            total_high += 1

        if importance == 0 or user_stance is None:
            continue

        position = positions_by_qid.get(qid)
        if position is None or position.stance is None:
            continue

        if importance >= 2:
            covered_high += 1

        distance = abs(user_stance - position.stance)
        agreement = 1.0 - (distance / 4.0)
        weight = float(importance)

        numerator += agreement * weight
        denominator += weight

        issue_data[issue_id]["num"] += agreement * weight
        issue_data[issue_id]["den"] += weight
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
        covered_high_importance=covered_high,
        total_high_importance=total_high,
    )


def rank_candidates(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Sort by match_percent desc (None last), then coverage desc, then name asc."""
    def sort_key(sc: ScoredCandidate):
        pct = sc.match_percent if sc.match_percent is not None else -1.0
        coverage = sc.covered_high_importance / max(sc.total_high_importance, 1)
        return (-pct, -coverage, sc.candidate.name)

    return sorted(scored, key=sort_key)
