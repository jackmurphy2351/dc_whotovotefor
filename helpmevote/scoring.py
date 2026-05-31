from dataclasses import dataclass, field

from .models import Candidate, Question, Source


@dataclass
class IssueScore:
    issue_id: str
    issue_label: str
    match_percent: float | None
    answered: int
    total: int


@dataclass
class AnswerDetail:
    """One answered question, comparing the user's answer to the candidate's stance."""
    question_id: str
    prompt: str
    issue_label: str
    user_stance: int  # user always has a stance in the answered set
    candidate_stance: int | None  # None = candidate has no known position
    agreement: float | None  # 0..1; None when candidate stance is unknown
    explanation: str
    quote: str
    sources: tuple[Source, ...]


@dataclass
class ScoredCandidate:
    candidate: Candidate
    match_percent: float | None
    issue_scores: list[IssueScore]
    details: list[AnswerDetail] = field(default_factory=list)

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
    details: list[AnswerDetail] = []

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

        issue_label = issues[issue_id].label if issue_id in issues else issue_id
        position = positions_by_qid.get(qid)

        if position is None or position.stance is None:
            # User answered, but the candidate has no known stance.
            details.append(AnswerDetail(
                question_id=qid,
                prompt=question.prompt,
                issue_label=issue_label,
                user_stance=user_stance,
                candidate_stance=None,
                agreement=None,
                explanation=position.explanation if position else "",
                quote=position.quote if position else "",
                sources=position.sources if position else (),
            ))
            continue

        distance = abs(user_stance - position.stance)
        agreement = 1.0 - (distance / 4.0)

        details.append(AnswerDetail(
            question_id=qid,
            prompt=question.prompt,
            issue_label=issue_label,
            user_stance=user_stance,
            candidate_stance=position.stance,
            agreement=agreement,
            explanation=position.explanation,
            quote=position.quote,
            sources=position.sources,
        ))

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
        details=details,
    )


def rank_candidates(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Sort by match_percent desc (None last), then name asc."""
    def sort_key(sc: ScoredCandidate):
        pct = sc.match_percent if sc.match_percent is not None else -1.0
        return (-pct, sc.candidate.name)

    return sorted(scored, key=sort_key)
