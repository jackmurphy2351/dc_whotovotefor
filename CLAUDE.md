# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run dev server (http://127.0.0.1:5000)
FLASK_ENV=development .venv/bin/python app.py

# Run all tests (21 tests; data_loader + scoring)
.venv/bin/python -m pytest

# Run a single test
.venv/bin/python -m pytest tests/test_scoring.py::TestMatchScore::test_perfect_match

# Lint
.venv/bin/ruff check .
```

Python 3.13 is required (`pyproject.toml`). Install dev deps with `pip install -e ".[dev]"`.

## Architecture

**Flask app factory + content-at-startup.** `helpmevote/__init__.py` calls `load_all_content()` once and stashes the result on `app.config["CONTENT"]` as an `AppContent` dataclass. Routes read from `current_app.config["CONTENT"]`. There is no database — quiz state lives in a signed-cookie Flask session keyed `quiz_answers_<election_slug>`.

**Content is data, not code.** Everything voter-facing lives under `content/`:
- `elections.yaml`, `issues.yaml`, `questions.yaml` — top-level taxonomy
- `candidates/<election_slug>.yaml` — one file per race
- `resources/*.md` — explainer pages (Markdown + YAML front-matter, rendered via `python-frontmatter`)

Adding a candidate or question is a YAML edit, not a code change.

**Fail-closed validation at startup.** `helpmevote/data_loader.py` (`validate_content`) raises `ValueError` and the app refuses to start if:
- A `Position` has a non-zero, non-null `stance` but no `sources` (the "no unsourced claims" policy)
- A candidate references an unknown `question_id`
- A question references an unknown `issue` or `applies_to_elections` slug
- Two candidates share an `id` (must be unique *across all races*)

When editing YAML, run the dev server or `pytest` to catch violations immediately — failure messages name the offending record.

**Domain model is frozen dataclasses.** `helpmevote/models.py` — `Election`, `Candidate`, `Position`, `Question`, `Issue`, `Source`, `Advisory` are all `@dataclass(frozen=True)`. Treat them as immutable: build new instances, never mutate. The mutable assembly container is `AppContent`.

**Scoring is a pure function.** `helpmevote/scoring.py` (`match_score`) takes user answers + a candidate + questions + issues and returns a `ScoredCandidate`. No Flask, no globals. Stances are integers `-2..+2` or `None` (unknown). User-skipped questions and unknown candidate stances are both excluded from the denominator; a candidate with zero overlap returns `match_percent=None` ("insufficient data") rather than 0%.

**Routes are split into four blueprints** under `helpmevote/routes/`:
- `main.py` — `/`, `/about`
- `elections.py` — `/election/<slug>`, `/candidate/<election_slug>/<candidate_id>`
- `quiz.py` — `/quiz/<slug>` (GET stepped, POST advances), `/results/<slug>`, `/quiz/<slug>/reset`
- `resources.py` — `/resources`, `/resources/<topic>` (hardcoded topic allowlist in `TOPIC_ORDER` / `TOPIC_TITLES`)

## Content conventions

- **Stance scale:** `-2` strongly opposes, `-1` opposes, `0` neutral, `1` supports, `2` strongly supports, `null` unknown. `0` and `null` do **not** require sources; everything else does.
- **Candidate IDs are kebab-case and globally unique** across all `candidates/*.yaml` files — not just within one race.
- **Advisories** are named third-party voter-guidance quotes (e.g. "Free DC: do not rank X"), always attributed to an organization, never editorial.
- **Source dates** (`accessed:`) parse via `date.fromisoformat`. Quote them as `YYYY-MM-DD`.

## Deployment

`Procfile` + `render.yaml` target Render's free tier (`gunicorn app:app`). `SECRET_KEY` and `FLASK_ENV=production` must be set in production env.
