from datetime import date
from pathlib import Path

import yaml

from .models import (
    Advisory,
    AppContent,
    Candidate,
    Election,
    EndorsementGroup,
    Issue,
    Position,
    Question,
    Source,
)

# Fixed, controlled vocabulary for endorsement group categories. Adding a new
# label here is the only way to introduce a new category; validate_content
# rejects anything else.
ALLOWED_ENDORSEMENT_CATEGORIES = (
    "Labor unions",
    "Elected/Appointed Officials",
    "Advocacy & community organizations",
    "Individuals & public figures",
    "Newspapers & editorial boards",
)


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_source(raw: dict) -> Source:
    return Source(
        url=raw["url"],
        title=raw["title"],
        publisher=raw["publisher"],
        accessed=_parse_date(raw["accessed"]),
    )


def _parse_sources(raw_list: list | None) -> tuple[Source, ...]:
    if not raw_list:
        return ()
    return tuple(_parse_source(s) for s in raw_list)


def _parse_position(raw: dict) -> Position:
    stance = raw.get("stance")
    sources = _parse_sources(raw.get("sources"))
    if stance is not None and stance != 0 and not sources:
        raise ValueError(
            f"Position '{raw['question_id']}' has stance={stance} but no sources. "
            "Every non-neutral stance requires at least one source."
        )
    return Position(
        question_id=raw["question_id"],
        stance=stance,
        explanation=raw.get("explanation", ""),
        sources=sources,
        quote=raw.get("quote", ""),
    )


def _parse_advisory(raw: dict) -> Advisory:
    return Advisory(
        organization=raw["organization"],
        year=int(raw["year"]),
        text=raw["text"],
        source=_parse_source(raw["source"]),
    )


def _parse_endorsement_group(raw: dict) -> EndorsementGroup:
    return EndorsementGroup(
        category=raw["category"],
        items=tuple(raw.get("items", [])),
    )


def _parse_candidate(raw: dict, election_slug: str) -> Candidate:
    return Candidate(
        id=raw["id"],
        name=raw["name"],
        election_slug=election_slug,
        short_bio=raw.get("short_bio", ""),
        long_bio=raw.get("long_bio", ""),
        campaign_url=raw.get("campaign_url"),
        endorsements=tuple(
            _parse_endorsement_group(g) for g in raw.get("endorsements", [])
        ),
        in_fair_elections=bool(raw.get("in_fair_elections", False)),
        positions=tuple(_parse_position(p) for p in raw.get("positions", [])),
        advisories=tuple(_parse_advisory(a) for a in raw.get("advisories", [])),
        sources=_parse_sources(raw.get("sources")),
    )


def load_elections(path: Path) -> dict[str, Election]:
    raw = yaml.safe_load(path.read_text())
    elections = {}
    for item in raw:
        slug = item["slug"]
        elections[slug] = Election(
            slug=slug,
            title=item["title"],
            short_description=item["short_description"],
            whats_at_stake=item["whats_at_stake"],
            election_date=_parse_date(item["election_date"]),
            sources=_parse_sources(item.get("sources")),
        )
    return elections


def load_issues(path: Path) -> dict[str, Issue]:
    raw = yaml.safe_load(path.read_text())
    return {item["id"]: Issue(id=item["id"], label=item["label"], description=item["description"])
            for item in raw}


def load_questions(path: Path) -> dict[str, Question]:
    raw = yaml.safe_load(path.read_text())
    questions = {}
    for item in raw:
        qid = item["id"]
        questions[qid] = Question(
            id=qid,
            issue=item["issue"],
            prompt=item["prompt"],
            applies_to_elections=tuple(item.get("applies_to_elections", [])),
            explanation=item.get("explanation", ""),
            sources=_parse_sources(item.get("sources")),
        )
    return questions


def load_candidates(candidates_dir: Path, election_slug: str) -> list[Candidate]:
    path = candidates_dir / f"{election_slug}.yaml"
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text())
    return [_parse_candidate(item, election_slug) for item in raw]


def validate_content(content: AppContent) -> None:
    """Raise ValueError on any referential integrity violation."""
    seen_ids: set[str] = set()
    for slug, candidates in content.candidates.items():
        if slug not in content.elections:
            raise ValueError(f"Candidates file for '{slug}' has no matching election slug.")
        for c in candidates:
            if c.id in seen_ids:
                raise ValueError(f"Duplicate candidate id: '{c.id}'")
            seen_ids.add(c.id)
            for pos in c.positions:
                if pos.question_id not in content.questions:
                    raise ValueError(
                        f"Candidate '{c.id}' references unknown question '{pos.question_id}'"
                    )
            for group in c.endorsements:
                if group.category not in ALLOWED_ENDORSEMENT_CATEGORIES:
                    raise ValueError(
                        f"Candidate '{c.id}' has endorsement group with unknown "
                        f"category '{group.category}'. Allowed categories: "
                        f"{', '.join(ALLOWED_ENDORSEMENT_CATEGORIES)}"
                    )

    for qid, q in content.questions.items():
        if q.issue not in content.issues:
            raise ValueError(
                f"Question '{qid}' references unknown issue '{q.issue}'"
            )
        for slug in q.applies_to_elections:
            if slug not in content.elections:
                raise ValueError(
                    f"Question '{qid}' applies_to_elections includes unknown slug '{slug}'"
                )


def load_all_content(content_dir: Path) -> AppContent:
    content = AppContent()

    content.elections = load_elections(content_dir / "elections.yaml")
    content.issues = load_issues(content_dir / "issues.yaml")
    content.questions = load_questions(content_dir / "questions.yaml")

    candidates_dir = content_dir / "candidates"
    for slug in content.elections:
        cands = load_candidates(candidates_dir, slug)
        content.candidates[slug] = cands
        for c in cands:
            content.candidates_by_id[c.id] = c

    for slug in content.elections:
        content.questions_by_election[slug] = [
            q for q in content.questions.values()
            if slug in q.applies_to_elections
        ]

    validate_content(content)
    return content
