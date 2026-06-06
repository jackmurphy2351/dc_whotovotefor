"""Regression sweeps over the *real* loaded content (content/).

These are belt-and-suspenders over `validate_content` in data_loader.py: they
pin the content policies to named, greppable tests rather than relying solely on
app startup. They run against the actual content shipped in `content/`, so a bad
YAML edit fails here even if startup validation is ever loosened.
"""

import pytest

from helpmevote import create_app


@pytest.fixture(scope="module")
def content():
    return create_app("development").config["CONTENT"]


def _positions(content):
    for candidates in content.candidates.values():
        for cand in candidates:
            for pos in cand.positions:
                yield cand, pos


def test_no_unsourced_nonzero_stance(content):
    """Every non-zero, non-null stance must carry at least one source."""
    offenders = [
        f"{cand.id}:{pos.question_id} (stance={pos.stance})"
        for cand, pos in _positions(content)
        if pos.stance not in (0, None) and not pos.sources
    ]
    assert not offenders, "unsourced non-zero stances: " + ", ".join(offenders)


def test_candidate_ids_globally_unique(content):
    """Candidate ids must be unique across all races, not just within one."""
    seen = {}
    dupes = []
    for candidates in content.candidates.values():
        for cand in candidates:
            if cand.id in seen:
                dupes.append(cand.id)
            seen[cand.id] = cand
    assert not dupes, f"duplicate candidate ids: {dupes}"


def test_positions_reference_known_questions(content):
    """Each position's question_id must be a known question (the invariant the
    loader enforces). A position may reference a question outside the race's
    applies_to_elections — that data is simply dormant for that race — so this
    checks global existence, not per-election membership."""
    offenders = [
        f"{cand.id}:{pos.question_id}"
        for cand, pos in _positions(content)
        if pos.question_id not in content.questions
    ]
    assert not offenders, "positions on unknown questions: " + ", ".join(offenders)
