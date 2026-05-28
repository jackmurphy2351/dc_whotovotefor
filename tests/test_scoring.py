from datetime import date

import pytest

from helpmevote.models import Candidate, Issue, Position, Source
from helpmevote.scoring import ScoredCandidate, match_score, rank_candidates


def make_source() -> Source:
    return Source(url="https://example.com", title="Test", publisher="test", accessed=date.today())


def make_candidate(positions: list[tuple[str, int | None]]) -> Candidate:
    return Candidate(
        id="test-cand",
        name="Test Candidate",
        election_slug="test",
        short_bio="",
        long_bio="",
        campaign_url=None,
        endorsements=(),
        in_fair_elections=False,
        positions=tuple(
            Position(
                question_id=qid,
                stance=stance,
                explanation="",
                sources=(make_source(),) if stance else (),
            )
            for qid, stance in positions
        ),
        advisories=(),
        sources=(),
    )


def make_questions(ids: list[str], issue: str = "housing") -> list:
    from helpmevote.models import Question
    return [
        Question(
            id=qid,
            issue=issue,
            prompt=f"Question {qid}",
            applies_to_elections=("test",),
            explanation="",
            sources=(),
        )
        for qid in ids
    ]


def make_issues(*ids: str) -> dict:
    return {i: Issue(id=i, label=i.title(), description="") for i in ids}


class TestMatchScore:
    def test_perfect_match(self):
        candidate = make_candidate([("q1", 2)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (2, 3)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent == pytest.approx(100.0)

    def test_opposite_match(self):
        candidate = make_candidate([("q1", 2)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (-2, 3)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent == pytest.approx(0.0)

    def test_importance_zero_excluded(self):
        candidate = make_candidate([("q1", 2), ("q2", -2)])
        questions = make_questions(["q1", "q2"])
        issues = make_issues("housing")
        # q1: perfect match (user=2, cand=2), importance=0 → excluded
        # q2: opposite   (user=2, cand=-2), importance=3 → 0% match
        user_answers = {"q1": (2, 0), "q2": (2, 3)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent == pytest.approx(0.0)

    def test_no_opinion_excluded(self):
        candidate = make_candidate([("q1", 2)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (None, 3)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent is None

    def test_unknown_candidate_stance_excluded(self):
        candidate = make_candidate([("q1", None)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (2, 3)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent is None

    def test_all_importance_zero_returns_none(self):
        candidate = make_candidate([("q1", 2)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (2, 0)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent is None

    def test_partial_importance_weighting(self):
        candidate = make_candidate([("q1", 2), ("q2", -2)])
        questions = make_questions(["q1", "q2"])
        issues = make_issues("housing")
        # q1: perfect (user=2, cand=2, weight=1)
        # q2: opposite (user=2, cand=-2, weight=3) → agreement=0
        user_answers = {"q1": (2, 1), "q2": (2, 3)}

        result = match_score(user_answers, candidate, questions, issues)
        # numerator: 1.0*1 + 0.0*3 = 1; denominator: 1+3 = 4 → 25%
        assert result.match_percent == pytest.approx(25.0)

    def test_coverage_warning(self):
        candidate = make_candidate([("q1", None)])  # no known stance
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (2, 3)}  # importance=3 → high-importance

        result = match_score(user_answers, candidate, questions, issues)
        assert result.total_high_importance == 1
        assert result.covered_high_importance == 0
        assert result.coverage_warning is True

    def test_no_coverage_warning_when_all_covered(self):
        candidate = make_candidate([("q1", 2)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (2, 3)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.coverage_warning is False

    def test_intermediate_distance(self):
        candidate = make_candidate([("q1", 1)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": (2, 1)}

        result = match_score(user_answers, candidate, questions, issues)
        # distance=1, agreement=0.75, weight=1 → 75%
        assert result.match_percent == pytest.approx(75.0)


class TestRankCandidates:
    def _sc(self, name: str, pct: float | None, covered: int = 1, total: int = 1) -> ScoredCandidate:
        from helpmevote.models import Candidate
        c = Candidate(
            id=name.lower().replace(" ", "-"),
            name=name,
            election_slug="test",
            short_bio="",
            long_bio="",
            campaign_url=None,
            endorsements=(),
            in_fair_elections=False,
            positions=(),
            advisories=(),
            sources=(),
        )
        return ScoredCandidate(
            candidate=c,
            match_percent=pct,
            issue_scores=[],
            covered_high_importance=covered,
            total_high_importance=total,
        )

    def test_higher_pct_first(self):
        a = self._sc("Alice", 80.0)
        b = self._sc("Bob", 60.0)
        ranked = rank_candidates([b, a])
        assert ranked[0].candidate.name == "Alice"

    def test_none_last(self):
        a = self._sc("Alice", 80.0)
        b = self._sc("Bob", None)
        ranked = rank_candidates([b, a])
        assert ranked[0].candidate.name == "Alice"
        assert ranked[1].candidate.name == "Bob"

    def test_alphabetical_tiebreak(self):
        a = self._sc("Zelda", 80.0)
        b = self._sc("Alice", 80.0)
        ranked = rank_candidates([a, b])
        assert ranked[0].candidate.name == "Alice"
