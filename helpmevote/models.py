from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    publisher: str
    accessed: date


@dataclass(frozen=True)
class Position:
    question_id: str
    # -2=strongly opposes, -1=opposes, 0=neutral, 1=supports, 2=strongly supports, None=unknown
    stance: int | None
    explanation: str
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class Advisory:
    """A named third-party endorsement advisory, e.g. 'Free DC: do not rank X'."""
    organization: str
    year: int
    text: str
    source: Source


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    election_slug: str
    short_bio: str
    long_bio: str
    campaign_url: str | None
    endorsements: tuple[str, ...]
    in_fair_elections: bool
    positions: tuple[Position, ...]
    advisories: tuple[Advisory, ...]
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class Question:
    id: str
    issue: str
    prompt: str
    applies_to_elections: tuple[str, ...]
    explanation: str
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class Issue:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class Election:
    slug: str
    title: str
    short_description: str
    whats_at_stake: str
    election_date: date
    sources: tuple[Source, ...]


@dataclass
class AppContent:
    """All loaded content, assembled at startup."""
    elections: dict[str, Election] = field(default_factory=dict)
    issues: dict[str, Issue] = field(default_factory=dict)
    questions: dict[str, Question] = field(default_factory=dict)
    # election_slug -> list of candidates
    candidates: dict[str, list[Candidate]] = field(default_factory=dict)
    # all candidates by id
    candidates_by_id: dict[str, Candidate] = field(default_factory=dict)
    # election_slug -> ordered list of question ids
    questions_by_election: dict[str, list[Question]] = field(default_factory=dict)
