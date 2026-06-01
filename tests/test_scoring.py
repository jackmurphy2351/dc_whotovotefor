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
        user_answers = {"q1": 2}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent == pytest.approx(100.0)

    def test_opposite_match(self):
        candidate = make_candidate([("q1", 2)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": -2}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent == pytest.approx(0.0)

    def test_skipped_question_excluded(self):
        candidate = make_candidate([("q1", 2), ("q2", -2)])
        questions = make_questions(["q1", "q2"])
        issues = make_issues("housing")
        # q1: skipped → excluded; q2: opposite → 0%
        user_answers = {"q1": None, "q2": 2}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent == pytest.approx(0.0)

    def test_all_skipped_returns_none(self):
        candidate = make_candidate([("q1", 2)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": None}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent is None

    def test_unknown_candidate_stance_excluded(self):
        candidate = make_candidate([("q1", None)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": 2}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent is None

    def test_multiple_questions_averaged(self):
        candidate = make_candidate([("q1", 2), ("q2", -2)])
        questions = make_questions(["q1", "q2"])
        issues = make_issues("housing")
        # q1: perfect (agreement=1.0); q2: opposite (agreement=0.0) → avg 50%
        user_answers = {"q1": 2, "q2": 2}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.match_percent == pytest.approx(50.0)

    def test_intermediate_distance(self):
        candidate = make_candidate([("q1", 1)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": 2}

        result = match_score(user_answers, candidate, questions, issues)
        # distance=1, agreement=0.75 → 75%
        assert result.match_percent == pytest.approx(75.0)


class TestAgreementLabel:
    """The pill label is coarse and gap-driven, independent of the continuous
    agreement value that feeds the percentage."""

    @pytest.mark.parametrize(
        "user, cand, expected",
        [
            (2, 2, "agree"),       # 0 steps
            (-1, -1, "agree"),     # 0 steps
            (2, 1, "partial"),     # 1 step, same side
            (-2, -1, "partial"),   # 1 step, same side
            (1, -1, "disagree"),   # 2 steps
            (2, -1, "disagree"),   # 3 steps
            (2, -2, "disagree"),   # 4 steps, opposite
            (2, 0, "disagree"),    # 2 steps, committed vs neutral
        ],
    )
    def test_label_by_gap(self, user, cand, expected):
        candidate = make_candidate([("q1", cand)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")

        result = match_score({"q1": user}, candidate, questions, issues)
        assert result.details[0].agreement_label == expected

    def test_label_none_when_candidate_stance_unknown(self):
        candidate = make_candidate([("q1", None)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")

        result = match_score({"q1": 2}, candidate, questions, issues)
        assert result.details[0].agreement_label is None
        assert result.details[0].distance is None


class TestAnswerDetails:
    def test_detail_per_answered_question(self):
        candidate = make_candidate([("q1", 2), ("q2", -2)])
        questions = make_questions(["q1", "q2"])
        issues = make_issues("housing")
        user_answers = {"q1": 2, "q2": 2}

        result = match_score(user_answers, candidate, questions, issues)
        assert [d.question_id for d in result.details] == ["q1", "q2"]
        # q1: perfect agreement; q2: opposite
        assert result.details[0].agreement == pytest.approx(1.0)
        assert result.details[0].candidate_stance == 2
        assert result.details[0].user_stance == 2
        assert result.details[1].agreement == pytest.approx(0.0)

    def test_skipped_question_has_no_detail(self):
        candidate = make_candidate([("q1", 2), ("q2", -2)])
        questions = make_questions(["q1", "q2"])
        issues = make_issues("housing")
        user_answers = {"q1": None, "q2": 2}

        result = match_score(user_answers, candidate, questions, issues)
        assert [d.question_id for d in result.details] == ["q2"]

    def test_unknown_candidate_stance_still_detailed(self):
        candidate = make_candidate([("q1", None)])
        questions = make_questions(["q1"])
        issues = make_issues("housing")
        user_answers = {"q1": 2}

        result = match_score(user_answers, candidate, questions, issues)
        # Candidate has no known position, but the answered question still appears.
        assert len(result.details) == 1
        assert result.details[0].candidate_stance is None
        assert result.details[0].agreement is None
        assert result.details[0].user_stance == 2

    def test_quote_carried_through(self):
        from helpmevote.models import Candidate, Position
        candidate = Candidate(
            id="quoter",
            name="Quoter",
            election_slug="test",
            short_bio="",
            long_bio="",
            campaign_url=None,
            endorsements=(),
            in_fair_elections=False,
            positions=(
                Position(
                    question_id="q1",
                    stance=2,
                    explanation="exp",
                    sources=(make_source(),),
                    quote="I strongly support this.",
                ),
            ),
            advisories=(),
            sources=(),
        )
        questions = make_questions(["q1"])
        issues = make_issues("housing")

        result = match_score({"q1": 2}, candidate, questions, issues)
        assert result.details[0].quote == "I strongly support this."
        assert result.details[0].explanation == "exp"


class TestCoverage:
    def test_counts_track_answered_and_compared(self):
        candidate = make_candidate([(f"q{i}", 2) for i in range(10)])
        questions = make_questions([f"q{i}" for i in range(10)])
        issues = make_issues("housing")
        user_answers = {f"q{i}": 2 for i in range(10)}

        result = match_score(user_answers, candidate, questions, issues)
        assert result.answered_count == 10
        assert result.compared_count == 10
        assert result.coverage == pytest.approx(1.0)

    def test_skipped_user_questions_excluded_from_answered(self):
        candidate = make_candidate([("q0", 2), ("q1", 2)])
        questions = make_questions(["q0", "q1"])
        issues = make_issues("housing")
        result = match_score({"q0": 2, "q1": None}, candidate, questions, issues)
        assert result.answered_count == 1
        assert result.compared_count == 1

    def test_unknown_candidate_stance_counts_toward_answered_not_compared(self):
        candidate = make_candidate([("q0", 2), ("q1", None), ("q2", None)])
        questions = make_questions(["q0", "q1", "q2"])
        issues = make_issues("housing")
        result = match_score({"q0": 2, "q1": 2, "q2": 2}, candidate, questions, issues)
        assert result.answered_count == 3
        assert result.compared_count == 1
        assert result.coverage == pytest.approx(1 / 3)

    def test_sufficient_data_true_when_above_thresholds(self):
        candidate = make_candidate([(f"q{i}", 2) for i in range(10)])
        questions = make_questions([f"q{i}" for i in range(10)])
        issues = make_issues("housing")
        result = match_score({f"q{i}": 2 for i in range(10)}, candidate, questions, issues)
        assert result.sufficient_data is True

    def test_sufficient_data_false_below_absolute_floor(self):
        # 5 compared questions < MIN_COMPARED=8, even at 100% coverage.
        candidate = make_candidate([(f"q{i}", 2) for i in range(5)])
        questions = make_questions([f"q{i}" for i in range(5)])
        issues = make_issues("housing")
        result = match_score({f"q{i}": 2 for i in range(5)}, candidate, questions, issues)
        assert result.compared_count == 5
        assert result.sufficient_data is False

    def test_sufficient_data_false_below_coverage(self):
        # 10 compared meets the floor, but user answered 30 → coverage 0.33 < 0.40.
        candidate = make_candidate([(f"q{i}", 2) for i in range(10)])
        questions = make_questions([f"q{i}" for i in range(30)])
        issues = make_issues("housing")
        user_answers = {f"q{i}": 2 for i in range(30)}
        result = match_score(user_answers, candidate, questions, issues)
        assert result.compared_count == 10
        assert result.answered_count == 30
        assert result.sufficient_data is False

    def test_coverage_zero_when_no_answers(self):
        candidate = make_candidate([("q0", 2)])
        questions = make_questions(["q0"])
        issues = make_issues("housing")
        result = match_score({"q0": None}, candidate, questions, issues)
        assert result.coverage == 0.0
        assert result.sufficient_data is False


class TestRankCandidates:
    def _sc(
        self,
        name: str,
        pct: float | None,
        answered: int = 20,
        compared: int = 20,
    ) -> ScoredCandidate:
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
            answered_count=answered,
            compared_count=compared,
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

    def test_limited_data_sorts_below_well_documented(self):
        thin = self._sc("Johnson", 100.0, answered=29, compared=5)
        solid = self._sc("Bowser", 70.0, answered=29, compared=27)
        ranked = rank_candidates([thin, solid])
        assert ranked[0].candidate.name == "Bowser"
        assert ranked[1].candidate.name == "Johnson"
        assert ranked[0].sufficient_data is True
        assert ranked[1].sufficient_data is False

    def test_limited_tier_ordered_by_pct(self):
        a = self._sc("Aaa", 90.0, answered=29, compared=3)
        b = self._sc("Bbb", 100.0, answered=29, compared=4)
        ranked = rank_candidates([a, b])
        assert ranked[0].candidate.name == "Bbb"
        assert ranked[1].candidate.name == "Aaa"
