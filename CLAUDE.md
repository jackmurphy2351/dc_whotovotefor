# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run dev server (http://127.0.0.1:5000)
FLASK_ENV=development .venv/bin/python app.py

# Run all tests (45 tests; data_loader + scoring + quiz selection)
.venv/bin/python -m pytest

# Run a single test
.venv/bin/python -m pytest tests/test_scoring.py::TestMatchScore::test_perfect_match

# Lint
.venv/bin/ruff check .
```

Python 3.13 is required (`pyproject.toml`). Install dev deps with `pip install -e ".[dev]"`.

## Research scripts

`scripts/fastdemocracy_scraper.py` pulls DC Council sponsored-bill and voting-record data from fastdemocracy.com for candidates who have (or had) a council seat. Uses only stdlib (`urllib`, `re`, `csv`) — no extra dependencies. Output lands in `scripts/output/`.

```bash
# Scrape all known candidates (bills + votes, ~20 min due to rate-limit delays)
python scripts/fastdemocracy_scraper.py

# Bills only (faster)
python scripts/fastdemocracy_scraper.py --bills-only

# Single legislator
python scripts/fastdemocracy_scraper.py --id DCL000027   # Janeese Lewis George

# Print a discovered name→ID table for all DC legislators
python scripts/fastdemocracy_scraper.py --discover
```

**Known FastDemocracy legislator IDs** (defined in `CANDIDATES` dict at top of script):

| ID | Candidate | Race |
|---|---|---|
| DCL000002 | Vincent Orange | Mayor |
| DCL000004 / DCL000025 | Kenyan McDuffie | Mayor (two session entries) |
| DCL000017 | Elissa Silverman | At-Large (McDuffie seat) |
| DCL000019 / DCL000024 | Robert White | Delegate (two session entries) |
| DCL000020 | Charles Allen | Ward 6 |
| DCL000026 | Brooke Pinto | Delegate |
| DCL000027 | Janeese Lewis George | Mayor |
| DCL000031 | Zachary Parker | Ward 5 |

The AJAX endpoint pattern is:
- Sponsored bills: `https://fastdemocracy.com/ajax/?sponsoredbills-state=dc&sponsoredbills-legislator={ID}`
- Voting records: `https://fastdemocracy.com/ajax/?voterecord-state=dc&voterecord-topic-id={topic}&voterecord-chamber=upper&voterecord-legislator={ID}`

Both require the header `X-Requested-With: XMLHttpRequest`. The scraper tries 45 topic slugs per legislator and skips ones that return empty results. `scripts/output/` is gitignored (raw scraped data, not checked in).

### Mapping the record to quiz questions

`scripts/filter_votes.py` maps the scraped record to quiz questions via the `QUESTION_FILTERS` table (per-question FastDemocracy topic slugs + title/description keywords). It writes into `scripts/output/`:
- `filtered_votes.csv` — one row per (question × candidate × matching vote); **weak** evidence
- `vote_summary.csv` — yes/no/other tallies per (question × candidate)
- `filtered_sponsorships.csv` — one row per (question × candidate × authored bill whose title matches the question's keywords); **strong** evidence

Both filtered files carry a `lims_url` (authoritative DC Council LIMS link) and a `council_period` (parsed from the bill number — period 24 began Jan 2021). Keyword matching against bill titles is **word-boundary-anchored** so short/ambiguous terms (`ice`, `rat`, `sanctuary values`) don't match inside larger words; dual legislator IDs are merged and retiring Anita Bonds (DCL000013) is excluded.

`scripts/corroborate.py` joins those CSVs against the published positions (via `load_all_content`) and writes `scripts/output/corroboration_report.md`, classifying each (council candidate × question) as **CORROBORATES** (supportive stance + an authored on-topic bill → add a LIMS source to the existing position), **CONFLICT**, or **NEW** (authored a bill but no published position). When acting on the report:
- The **campaign page stays authoritative** for a candidate's stance; the council record only corroborates.
- A bill corroborates only if its **subject matches the question's specific claim** — not just a keyword (e.g. a TOPA *exemption* does not support "strengthen TOPA"; a "Human Rights Sanctuary" reproductive-rights bill is not about ICE; Circulator funding is not about bus *lanes*).
- Sponsorships are strong evidence; **votes are noisy context only** and can be semantically inverted.
- Prefer bills from **council period ≥ 24 (2021+)**; older bills are used only as a flagged fallback when a candidate has no in-window record (e.g. former members like Vincent Orange).

## Architecture

**Flask app factory + content-at-startup.** `helpmevote/__init__.py` calls `load_all_content()` once and stashes the result on `app.config["CONTENT"]` as an `AppContent` dataclass. Routes read from `current_app.config["CONTENT"]`. There is no database — quiz state lives in signed-cookie Flask session keys: `quiz_answers_<election_slug>` (the `{question_id: stance}` map) and `quiz_selected_<election_slug>` (the list of question IDs the user chose to answer; absent means "all questions").

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

`ScoredCandidate` also reports **coverage**: `answered_count` (questions the user answered with an opinion) and `compared_count` (the subset where the candidate also had a known stance), plus a `coverage` ratio and a `sufficient_data` flag. A candidate is "sufficient" only with `compared_count >= MIN_COMPARED` (8) **and** `coverage >= MIN_COVERAGE` (0.40) — both module-level constants in `scoring.py`. `rank_candidates` sorts well-documented candidates first (by match% desc), then limited-data candidates (by match% desc), then `None` last. Low coverage never alters a candidate's percentage or imputes missing positions — it only demotes them into the limited tier, which `results.html` renders under a "Limited information available" heading with per-card "based on N of M questions" labels.

**Routes are split into four blueprints** under `helpmevote/routes/`:
- `main.py` — `/`, `/about`
- `elections.py` — `/election/<slug>`, `/candidate/<election_slug>/<candidate_id>`
- `quiz.py` — `/quiz/<slug>/start` (GET/POST question-selection screen, grouped by issue with per-category + per-question checkboxes; stores `quiz_selected_<slug>`), `/quiz/<slug>` (GET stepped, POST advances), `/results/<slug>`, `/quiz/<slug>/reset`. The stepped quiz, progress, and results scoring all run over `_active_questions()` — the election's questions filtered to the user's selection (or all questions when none is stored). The selection screen is the quiz's entry point from the election page.
- `resources.py` — `/resources`, `/resources/<topic>` (hardcoded topic allowlist in `TOPIC_ORDER` / `TOPIC_TITLES`; one entry is `methodology`, the public stance-grading explainer)

## Content conventions

- **Stance scale:** `-2` strongly opposes, `-1` opposes, `0` neutral, `1` supports, `2` strongly supports, `null` unknown. `0` and `null` do **not** require sources; everything else does.
- **Stance-grading rubric:** The criteria for assigning a stance — especially when a position earns a strong **±2** (on-topic to the question's specific claim *and* backed by emphatic framing or a concrete commitment) versus an ordinary **±1** — are written up in `content/resources/methodology.md`, published at `/resources/methodology`. Sponsorship is strong evidence; a lone vote is weak; the campaign page stays authoritative. Keep that page in sync when the grading bar changes.
- **Candidate IDs are kebab-case and globally unique** across all `candidates/*.yaml` files — not just within one race.
- **Advisories** are named third-party voter-guidance quotes (e.g. "Free DC: do not rank X"), always attributed to an organization, never editorial.
- **Source dates** (`accessed:`) parse via `date.fromisoformat`. Quote them as `YYYY-MM-DD`.

## Deployment

`Procfile` + `render.yaml` target Render's free tier (`gunicorn app:app`). `SECRET_KEY` and `FLASK_ENV=production` must be set in production env.
