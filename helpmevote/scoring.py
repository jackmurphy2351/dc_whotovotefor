from dataclasses import dataclass, field

from .models import Candidate, Question, Source

# A candidate's score is only as trustworthy as the number of questions it rests
# on. To stay in the "confident" ranking tier, a candidate must have a known
# stance on at least MIN_COMPARED of the user's answered questions AND cover at
# least MIN_COVERAGE of them. Below either bar the candidate is flagged
# "limited data" and sorted beneath every well-documented candidate — its real
# percentage is kept, never fabricated or imputed.
MIN_COMPARED = 8
MIN_COVERAGE = 0.40


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
    distance: int | None  # steps apart on the -2..+2 scale; None when stance unknown
    explanation: str
    quote: str
    sources: tuple[Source, ...]

    @property
    def agreement_label(self) -> str | None:
        """Coarse headline label for the pill, driven by step distance (not the
        continuous agreement value used for the percentage):
          - identical position (0 steps) -> "agree"
          - one step apart (same side, differing intensity) -> "partial"
          - two or more steps apart -> "disagree"
        Returns None when the candidate has no known stance (no pill shown).
        """
        if self.distance is None:
            return None
        if self.distance == 0:
            return "agree"
        if self.distance == 1:
            return "partial"
        return "disagree"


@dataclass
class ScoredCandidate:
    candidate: Candidate
    match_percent: float | None
    issue_scores: list[IssueScore]
    details: list[AnswerDetail] = field(default_factory=list)
    # Questions the user answered with a real opinion (the scope for this user).
    answered_count: int = 0
    # Subset of answered_count where the candidate also has a known stance.
    compared_count: int = 0

    @property
    def insufficient_data(self) -> bool:
        return self.match_percent is None

    @property
    def coverage(self) -> float:
        """Fraction of the user's answered questions the candidate has a stance on."""
        if self.answered_count == 0:
            return 0.0
        return self.compared_count / self.answered_count

    @property
    def sufficient_data(self) -> bool:
        """True when the score rests on enough of the user's questions to trust the ranking."""
        return self.compared_count >= MIN_COMPARED and self.coverage >= MIN_COVERAGE


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
    answered_count = 0  # user questions with a real opinion

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

        answered_count += 1
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
                distance=None,
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
            distance=distance,
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
        answered_count=answered_count,
        compared_count=int(denominator),
    )


def rank_candidates(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Sort into two tiers: well-documented candidates first (by match% desc),
    then limited-data candidates (by match% desc). None last, name asc tiebreak.

    A low-coverage candidate keeps its real percentage; it simply sorts below
    every candidate whose score rests on enough of the user's questions.
    """
    def sort_key(sc: ScoredCandidate):
        pct = sc.match_percent if sc.match_percent is not None else -1.0
        return (not sc.sufficient_data, -pct, sc.candidate.name)

    return sorted(scored, key=sort_key)
