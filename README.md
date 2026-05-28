# Help Me Vote DC 2026!

An open-source, interactive voter guide for Washington, DC's **June 16, 2026 Democratic Primary** (and the At-Large special general election on the same day). It helps voters find their best-matched candidates across five races using an OKCupid-style weighted questionnaire.

> **Why the primary matters:** In DC local politics, the Democratic Primary is effectively the general election. The District has not elected a Republican mayor since 1954. Winning the June 16 primary is, for most races, winning the seat.

---

## What it does

1. You pick a race (Mayor, Non-Voting Delegate, two At-Large Council seats, or Ward 1 Council).
2. You answer a series of issue questions — stance *and* how much you care about each issue.
3. The app scores every candidate against your answers using a weighted alignment algorithm and ranks them from most to least aligned.
4. Each result shows per-issue breakdowns and links every claim to a primary source.

### The five races

| Slug | Race | Type |
|---|---|---|
| `mayor` | Mayoral Election | Democratic Primary (7 candidates) |
| `delegate` | Non-Voting Delegate to Congress | Democratic Primary (5 candidates) |
| `at_large_mcduffie` | At-Large Council — Special Election | **Non-partisan** general election (3 candidates) |
| `at_large_bonds` | At-Large Council — Regular (2 seats) | Democratic Primary (9 candidates) |
| `ward1` | Ward 1 Councilmember | Democratic Primary (5 candidates) |

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

All 21 tests should pass. The test suite covers:
- Scoring algorithm edge cases (importance weighting, null stances, coverage warnings)
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
└── tests/
    ├── test_scoring.py
    ├── test_data_loader.py
    └── test_routes.py
```

---

## Scoring algorithm

The match percentage is calculated per candidate using a weighted alignment formula inspired by OKCupid:

```
For each question where:
  - user importance > 0  (not "doesn't matter to me")
  - user answered with a stance  (not "no opinion")
  - candidate has a known stance  (not null/unknown)

  distance  = abs(user_stance - candidate_stance)   # 0..4
  agreement = 1 - (distance / 4.0)                 # 1.0 = perfect, 0.0 = opposite
  weight    = user_importance                        # 1..3

match_percent = 100 × Σ(agreement × weight) / Σ(weight)
```

Stances run from **−2** (strongly opposes) to **+2** (strongly supports). A candidate with no known stances on any of your weighted questions is shown as "Insufficient data" rather than scored at 0%.

A **coverage warning** appears when a candidate is missing stances on questions you rated as high-importance (≥ 2).

---

## Content — all claims must link to sources

This app enforces a "no unsourced claims" policy at startup:

- Any `Position` with a non-zero, non-null `stance` **must** include at least one `Source` with a URL.
- If this rule is violated, `data_loader.py` raises a `ValueError` and the app **refuses to start**.
- Every source is rendered as a numbered superscript citation on the candidate page, with a hover tooltip showing the title and publisher.

Acceptable sources: dc.gov, dccouncil.gov, dcboe.org, candidate campaign sites, Ballotpedia, and established local news (The 51st, Washington City Paper, WAMU/DCist archive, Washington Post).

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

- Why the Democratic Primary = the General Election in DC
- Ranked Choice Voting (Initiative 83)
- TOPA & DOPA (tenant purchase rights)
- The DC Fair Elections Program
- How the DC Council works (wards vs. at-large)
- The Non-Voting Delegate role & DC Statehood

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

## Contributing

Pull requests welcome. The most useful contributions right now are:

1. **Candidate positions** — if you find a sourced position we've missed, add it to the relevant `content/candidates/*.yaml` file with a URL.
2. **Bug reports** — open an issue.
3. **Other cities/elections** — the content is fully data-driven; a different city's election would only require new YAML files and a new `elections.yaml`.

Please run `python -m pytest` before submitting a PR. All claims must have source URLs — the CI will reject any position without one.
