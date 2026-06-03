# Help Me Vote DC 2026!

An open-source, interactive voter guide for Washington, DC's **June 16, 2026 Democratic Primary** (and the At-Large special general election on the same day). It helps voters find their best-matched candidates across five races.

> **Why the primary matters:** In DC local politics, the Democratic Primary is effectively the general election. The District has not elected a Republican mayor since 1954. Winning the June 16 primary is, for most races, winning the seat.

---

## What it does

1. You pick a race (Mayor, Non-Voting Delegate, two At-Large Council seats, or Ward 1 Council).
2. You answer a series of issue questions on a 5-point scale (strongly oppose → strongly support), or skip any you don't care about.
3. The app scores every candidate by averaging your agreement on the questions where both you and the candidate have a stated position, then ranks them from most to least aligned — surfacing how much data backs each score so well-documented candidates aren't outranked by thinly-sourced ones (see [Scoring algorithm](#scoring-algorithm)).
4. Each result shows per-issue breakdowns and links every claim to a primary source.

### The five races

| Slug | Race                                | Type |
|---|-------------------------------------|---|
| `mayor` | Mayoral Election                    | Democratic Primary (7 candidates) |
| `delegate` | Non-Voting Delegate to Congress     | Democratic Primary (5 candidates) |
| `at_large_mcduffie` | At-Large Council — Special Election | **Non-partisan** general election (3 candidates) |
| `at_large_bonds` | At-Large Council — Regular          | Democratic Primary (9 candidates) |
| `ward1` | Ward 1 Councilmember                | Democratic Primary (5 candidates) |

---

## Tech stack

- **Python 3.13** · **Flask 3.x** · **Jinja2** (server-rendered, no frontend build step)
- **PyYAML** for all candidate/question/election content
- **python-frontmatter + Markdown** for resource/explainer pages
- **Flask session** (signed cookie) for quiz state — no database
- Vanilla JS for quiz UX enhancements (progress bar, radio highlight)
- **pytest** for unit + integration tests

---

## Running locally

```bash
# 1. Clone
git clone https://github.com/jackmurphy2351/dc_whotovotefor.git
cd dc_whotovotefor

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Start the dev server
FLASK_ENV=development python app.py
```

The app will be available at **http://127.0.0.1:5000**.

### Running tests

```bash
python -m pytest
```

All 31 tests should pass. The test suite covers:
- Scoring algorithm edge cases (null stances, skipped questions, agreement calculation)
- Coverage tracking and the limited-data ranking tier (thresholds, tiered sort order)
- Data loader validation (duplicate IDs, missing sources, unknown question references)
- Flask route smoke tests (all routes return 200)

---

## Project structure

```
dc_whotovotefor/
├── app.py                        # Flask entry point
├── pyproject.toml
├── helpmevote/
│   ├── __init__.py               # App factory; loads content at startup
│   ├── config.py
│   ├── data_loader.py            # YAML loader + startup validation
│   ├── models.py                 # Frozen dataclasses (Election, Candidate, Position, …)
│   ├── scoring.py                # Weighted match algorithm (pure function)
│   ├── routes/
│   │   ├── main.py               # /, /about
│   │   ├── elections.py          # /election/<slug>
│   │   ├── quiz.py               # /quiz/<slug>, POST, /results/<slug>
│   │   └── resources.py          # /resources, /resources/<topic>
│   ├── templates/                # Jinja2 templates
│   └── static/                   # CSS + JS
├── content/
│   ├── elections.yaml
│   ├── issues.yaml
│   ├── questions.yaml
│   ├── candidates/
│   │   ├── mayor.yaml            # 7 candidates
│   │   ├── delegate.yaml         # 5 candidates
│   │   ├── at_large_mcduffie.yaml  # 3 candidates
│   │   ├── at_large_bonds.yaml   # 9 candidates
│   │   └── ward1.yaml            # 5 candidates
│   └── resources/                # Markdown explainer pages
├── scripts/
│   └── fastdemocracy_scraper.py  # DC Council voting-record scraper (see below)
└── tests/
    ├── test_scoring.py
    ├── test_data_loader.py
    └── test_routes.py
```

---

## Scoring algorithm

For each question you answer, the app computes an agreement score between your stance and the candidate's:

```
For each question where:
  - user answered with a stance  (not skipped / no opinion)
  - candidate has a known stance  (not null/unknown)

  distance  = abs(user_stance - candidate_stance)   # 0..4
  agreement = 1 - (distance / 4.0)                 # 1.0 = perfect, 0.0 = opposite

match_percent = 100 × Σ(agreement) / n
```

Stances run from **−2** (strongly opposes) to **+2** (strongly supports). A candidate with no known stances on any of your answered questions is shown as "Insufficient data" rather than scored at 0%.

### Coverage and the limited-data tier

A percentage built from only a handful of questions can be misleading, so every result also reports its **coverage** — `compared_count` of `answered_count`, shown on the card as *"based on N of M questions."*

A candidate counts as well-documented only when it clears **both** thresholds (`MIN_COMPARED` / `MIN_COVERAGE` at the top of `scoring.py`):

```
sufficient_data = compared_count >= 8  AND  compared_count / answered_count >= 0.40
```

`rank_candidates` ranks well-documented candidates first (by match % desc), then the rest (by match % desc), with "Insufficient data" candidates last. Candidates that fall short are grouped under a **"Limited information available"** heading and flagged with a "Limited data" badge — but their real percentage is shown unchanged. **Missing positions are never guessed or imputed**; a thinly-sourced candidate is simply ranked with less confidence until more sourced positions are added.

---

## Content — all claims must link to sources

This app enforces a "no unsourced claims" policy at startup:

- Any `Position` with a non-zero, non-null `stance` **must** include at least one `Source` with a URL.
- If this rule is violated, `data_loader.py` raises a `ValueError` and the app **refuses to start**.
- Every source is rendered as a numbered superscript citation on the candidate page, with a hover tooltip showing the title and publisher.

Acceptable sources: dc.gov, dccouncil.gov, dcboe.org, candidate campaign sites, Ballotpedia, and established local news (The 51st, Washington City Paper, WAMU/DCist archive, Washington Post).

How each stance is graded — and specifically when a position earns a strong **±2** rather than an ordinary **±1** — is documented in [`content/resources/methodology.md`](content/resources/methodology.md), published in-app at `/resources/methodology`.

---

## Adding or updating candidate data

All content lives in `content/candidates/<race>.yaml`. The schema for a candidate entry:

```yaml
- id: first-last                  # kebab-case, unique across all races
  name: "First Last"
  election_slug: mayor            # must match a slug in elections.yaml
  in_fair_elections: true         # DC Fair Elections Program participant?
  campaign_url: https://...       # or null
  endorsements:
    - "Organization Name"
  short_bio: >
    One or two sentence summary shown on cards.
  long_bio: |
    Full paragraph bio shown on the candidate profile page.
  advisories:                     # named third-party warnings, quoted verbatim
    - organization: "Free DC"
      year: 2026
      text: "Do not rank Kenyan McDuffie."
      source:
        url: https://freedcproject.org/news/our-2026-endorsements-guide
        title: "Our 2026 Endorsements Guide — Free DC"
        publisher: "Free DC Project"
        accessed: 2026-05-27
  sources:                        # general sources for the bio
    - url: https://...
      title: "Page title"
      publisher: publisher.org
      accessed: 2026-05-27
  positions:
    - question_id: housing_topa_restore   # must match an id in questions.yaml
      stance: 2                           # -2 to +2, or null for unknown
      explanation: "Why this stance."
      sources:
        - url: https://...                # REQUIRED for non-zero, non-null stance
          title: "..."
          publisher: "..."
          accessed: 2026-05-27
```

After editing any YAML file, run `python -m pytest` to validate. The data loader will catch unknown question IDs, duplicate candidate IDs, and any sourcing violations before the tests even hit the routes.

---

## Named advisories

Organizations (not the site itself) that have issued public voter guidance are displayed verbatim on candidate profiles and result pages, with a link to the source:

> ⚠ **Free DC (2026):** "Do not rank Kenyan McDuffie." — [freedcproject.org]

These are always attributed to the named organization and never presented as the site's own editorial stance.

---

## DC Fair Elections Program

The [DC Fair Elections Program](https://ocf.dc.gov/page/fair-elections-program) provides a 5-to-1 public match on small-dollar contributions (≤ $200) from DC residents. Candidates who opt in cannot accept corporate or PAC money. Participation status is shown on every candidate card and is one of the quiz questions.

---

## Resources / explainer pages

The `/resources` section contains dc.gov-linked explainer pages on:

- Why the Democratic Primary ≈ the General Election in DC
- Ranked Choice Voting (Initiative 83)
- TOPA & DOPA (tenant purchase rights)
- The DC Fair Elections Program
- How the DC Council works (wards vs. at-large)
- The Non-Voting Delegate role & DC Statehood
- **How we assign candidate stances** — the grading rubric, including when a position earns a strong **±2** vs an ordinary **±1**

These are Markdown files in `content/resources/` with YAML front-matter declaring their sources.

---

## License

**AGPL-3.0.** If you fork this and deploy it as a web service, you must make your modified source code available. This ensures that any version of this app running anywhere — including forks covering other cities or elections — remains open and auditable.

---

## Deploying to Render (free tier)

This is a Flask/WSGI app — it **cannot** be deployed on Streamlit. Use [Render](https://render.com), [Fly.io](https://fly.io), or [Railway](https://railway.app) instead.

### Render (recommended — free, no credit card required)

1. Go to [render.com](https://render.com) and sign in with GitHub.
2. Click **New → Web Service** and connect the `dc_whotovotefor` repository.
3. Render will auto-detect the `Procfile`. Confirm these settings:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
4. Under **Environment Variables**, add:
   - `FLASK_ENV` = `production`
   - `SECRET_KEY` = *(generate a random string, e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"` )*
5. Click **Deploy**. Render will build and serve the app on a `*.onrender.com` URL.

On every `git push` to `main`/`master`, Render will automatically redeploy.

> **Note:** On Render's free tier the app will spin down after 15 minutes of inactivity and take ~30 seconds to cold-start on the next request. This is fine for a civic-tech app that sees bursty election-season traffic.

---

## Research tools

`scripts/fastdemocracy_scraper.py` scrapes DC Council sponsored-bill and voting-record data from [fastdemocracy.com](https://fastdemocracy.com) for candidates who currently hold or previously held a council seat. It uses only Python stdlib — no extra dependencies beyond what the app already requires.

```bash
# Scrape all known candidates (~20 min)
python scripts/fastdemocracy_scraper.py

# Bills only, or a single legislator
python scripts/fastdemocracy_scraper.py --bills-only
python scripts/fastdemocracy_scraper.py --id DCL000027   # Janeese Lewis George
```

Output CSVs (`sponsored_bills.csv`, `voting_records.csv`) are written to `scripts/output/` (gitignored). The data covers sponsored bills and yes/no votes across ~45 policy topic categories, and is useful for researching candidate positions to add to the YAML files.

Two follow-on scripts turn that raw data into reviewable evidence:

```bash
# Map the scraped record to quiz questions (writes filtered_votes.csv,
# vote_summary.csv, filtered_sponsorships.csv to scripts/output/)
python scripts/filter_votes.py

# Cross-reference the record against published positions and write a
# corroboration report (scripts/output/corroboration_report.md)
python scripts/corroborate.py
```

`filter_votes.py` matches each authored bill / vote to a quiz question and tags it with the bill's DC Council **LIMS** link and council period. `corroborate.py` flags where a candidate's authored bills **corroborate** the stance we already publish (so we can attach the LIMS record as a source), where they **conflict**, and where there is a **position gap**. Treat sponsored bills as strong evidence and votes as weak context; the candidate's campaign page remains the authoritative source for their stance, and a bill only counts as corroboration when its subject genuinely matches the question.

---

## Contributing

Pull requests welcome. The most useful contributions right now are:

1. **Candidate positions** — if you find a sourced position we've missed, add it to the relevant `content/candidates/*.yaml` file with a URL.
2. **Bug reports** — open an issue.
3. **Other cities/elections** — the content is fully data-driven; a different city's election would only require new YAML files and a new `elections.yaml`.

Please run `python -m pytest` before submitting a PR. All claims must have source URLs — the CI will reject any position without one.
