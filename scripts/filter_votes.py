#!/usr/bin/env python3
"""
filter_votes.py — map FastDemocracy voting records to quiz questions.

Reads scripts/output/voting_records.csv (produced by fastdemocracy_scraper.py)
and emits two files:

  scripts/output/filtered_votes.csv
      One row per (quiz_question × candidate × matching vote), tagged with
      the question ID and issue. Use this to quickly see every council vote
      relevant to a given quiz question.

  scripts/output/vote_summary.csv
      One row per (quiz_question × candidate_name), with yes_count, no_count,
      other_count, and total. A quick scorecard for whether a candidate has a
      voting record that leans for or against each question.

Candidates with two FastDemocracy IDs (McDuffie: DCL000004/DCL000025,
Robert White: DCL000019/DCL000024) are merged under a single display name
before summarising so their votes aren't double-counted.

Usage:
    python scripts/filter_votes.py
    python scripts/filter_votes.py --question housing_topa_restore
    python scripts/filter_votes.py --candidate "Charles Allen"
"""
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Candidate name normalisation
# Candidates with two FastDemocracy entries are merged to a single display name.
# ---------------------------------------------------------------------------

# DCL000013 (Anita Bonds) is excluded — she is retiring and not on the ballot.
ID_TO_DISPLAY: dict[str, str] = {
    "DCL000002": "Vincent Orange",
    "DCL000004": "Kenyan McDuffie",
    "DCL000017": "Elissa Silverman",
    "DCL000019": "Robert White",
    "DCL000020": "Charles Allen",
    "DCL000024": "Robert White",        # alt entry → same display name
    "DCL000025": "Kenyan McDuffie",     # alt entry → same display name
    "DCL000026": "Brooke Pinto",
    "DCL000027": "Janeese Lewis George",
    "DCL000031": "Zachary Parker",
}

EXCLUDED_IDS = {"DCL000013"}  # Anita Bonds — retiring, not on ballot

# ---------------------------------------------------------------------------
# Quiz question → FastDemocracy topic slugs + keyword hints.
#
# A vote row matches a question when:
#   1. Its `topic` column is in the question's `topics` list.
#   2. At least one keyword appears (case-insensitive) in `description`
#      OR `bill_number`.  (If `keywords` is empty, topic match alone suffices.)
# ---------------------------------------------------------------------------

QUESTION_FILTERS: dict[str, dict] = {
    # ── HOUSING ──────────────────────────────────────────────────────────────
    "housing_topa_restore": {
        "issue": "tenants_rights",
        "topics": ["housing", "land"],
        "keywords": ["topa", "tenant opportunity", "tenant purchase"],
    },
    "housing_rent_stabilization": {
        "issue": "housing",
        "topics": ["housing", "land"],
        "keywords": ["rent stabiliz", "rent control", "rent increase", "rent supplement"],
    },
    "housing_dopa": {
        "issue": "housing",
        "topics": ["housing", "land"],
        "keywords": ["dopa", "district opportunity to purchase", "affordable housing"],
    },
    "housing_production_trust_fund": {
        "issue": "housing",
        "topics": ["housing", "budget", "finance"],
        "keywords": ["housing production trust", "hptf", "affordable housing fund"],
    },
    "housing_social_model": {
        "issue": "housing",
        "topics": ["housing"],
        "keywords": ["social housing", "public housing", "community land trust", "new communities"],
    },
    "housing_upzoning": {
        "issue": "housing",
        "topics": ["housing", "land"],
        "keywords": ["zoning", "upzone", "multifamily", "density", "comprehensive plan",
                     "missing middle", "accessory dwelling", "single family"],
    },
    # ── TRANSIT ──────────────────────────────────────────────────────────────
    "transit_bike_bus_lanes": {
        "issue": "transit",
        "topics": ["transportation", "infrastructure"],
        "keywords": ["bike", "bicycle", "bus lane", "dedicated lane", "protected lane",
                     "circulator", "streetcar"],
    },
    "transit_fare_free_buses": {
        "issue": "transit",
        "topics": ["transportation"],
        "keywords": ["fare", "fare-free", "free bus", "metro for dc", "metrobus"],
    },
    "transit_congestion_pricing": {
        "issue": "transit",
        "topics": ["transportation"],
        "keywords": ["congestion", "toll", "road pricing", "vehicle fee", "commuter tax"],
    },
    # ── MPD & ICE ────────────────────────────────────────────────────────────
    "mpd_ice_cooperation": {
        "issue": "mpd_ice",
        "topics": ["immigration", "police"],
        "keywords": ["ice", "immigration enforcement", "sanctuary", "deportation",
                     "cooperative agreement", "federal immigration", "immigration detain"],
    },
    # ── EDUCATION ────────────────────────────────────────────────────────────
    "education_community_schools": {
        "issue": "education",
        "topics": ["education", "schools"],
        "keywords": ["community school", "wraparound", "school-based service",
                     "community school incentive"],
    },
    "education_mental_health_schools": {
        "issue": "education",
        "topics": ["education", "schools", "healthcare", "public-health"],
        "keywords": ["mental health", "behavioral health", "school counselor",
                     "school health", "school-based behavioral", "clinician"],
    },
    "education_mayoral_control": {
        "issue": "education",
        "topics": ["education", "schools"],
        "keywords": ["mayoral control", "state board of education", "dcps governance",
                     "school governance", "education reform amendment"],
    },
    # ── COMMUNITY SAFETY & VIOLENCE PREVENTION ───────────────────────────────
    "crime_public_health": {
        "issue": "community_safety",
        "topics": ["crime", "police", "public-health"],
        "keywords": ["near act", "violence interrupt", "public health approach",
                     "community violence", "violence prevention", "trauma"],
    },
    # ── POLICING & CRIMINAL JUSTICE ──────────────────────────────────────────
    "crime_secure_dc": {
        "issue": "policing",
        "topics": ["crime", "police"],
        "keywords": ["secure dc", "pretrial detention", "pre-trial detention",
                     "criminal penalty", "omnibus", "crime omnibus"],
    },
    "crime_more_police": {
        "issue": "policing",
        "topics": ["police"],
        "keywords": ["police officer", "mpd officer", "officer hiring", "police recruit",
                     "cadet program", "police staffing", "police force"],
    },
    "crime_police_in_schools": {
        "issue": "policing",
        "topics": ["police", "crime", "education"],
        "keywords": ["school resource officer", " sro ", "police in school",
                     "officer in school", "safety officer school"],
    },
    # ── YOUTH CURFEWS ────────────────────────────────────────────────────────
    "youth_curfew_support": {
        "issue": "youth_curfew",
        "topics": ["crime", "children"],
        "keywords": ["curfew", "juvenile curfew", "youth curfew"],
    },
    "youth_curfew_programming": {
        "issue": "youth_curfew",
        "topics": ["children", "education"],
        "keywords": ["summer youth employment", "marion barry summer", "youth program",
                     "out-of-school", "recreation center", "youth job", "youth employment"],
    },
    # ── ECONOMIC DEVELOPMENT ─────────────────────────────────────────────────
    "fiscal_progressive_taxation": {
        "issue": "economic_development",
        "topics": ["taxes", "finance", "budget"],
        "keywords": ["income tax", "corporate tax", "wealth tax", "millionaire",
                     "progressive tax", "revenue", "tax increase", "surtax"],
    },
    "econ_small_business_tax_relief": {
        "issue": "economic_development",
        "topics": ["taxes", "business"],
        "keywords": ["small business", "small retailer", "business tax", "entrepreneur",
                     "business license fee", "business improvement"],
    },
    # ── ENVIRONMENT ──────────────────────────────────────────────────────────
    "environment_renewable_energy": {
        "issue": "environment",
        "topics": ["energy", "environment"],
        "keywords": ["renewable", "solar", "wind energy", "clean energy", "geothermal",
                     "green new deal", "renewable portfolio"],
    },
    "environment_data_centers": {
        "issue": "environment",
        "topics": ["energy", "environment", "internet"],
        "keywords": ["data center", "colocation", "server farm"],
    },
    "environment_public_power": {
        "issue": "environment",
        "topics": ["energy", "environment"],
        "keywords": ["pepco", "public power", "public utility", "municipal utility",
                     "electric utility", "electricity rate"],
    },
    # ── PARKS & RECREATION ───────────────────────────────────────────────────
    "parks_rec_funding": {
        "issue": "parks_recreation",
        "topics": ["children", "government"],
        "keywords": ["parks and recreation", "recreation center", "rec center",
                     "department of parks", "dpr ", "youth programming", "senior program"],
    },
    # ── SANITATION ───────────────────────────────────────────────────────────
    "sanitation_rats": {
        "issue": "sanitation",
        "topics": ["public-health", "government"],
        "keywords": ["rodent", "rat ", "rats ", "sanitation", "trash container",
                     "garbage", "solid waste", "dpw"],
    },
    # ── HARM REDUCTION ───────────────────────────────────────────────────────
    "harm_reduction_safe_injection": {
        "issue": "harm_reduction",
        "topics": ["drugs", "healthcare", "public-health"],
        "keywords": ["safe injection", "overdose prevention", "opioid", "harm reduction",
                     "needle exchange", "syringe", "drug treatment"],
    },
    # ── CHILDCARE ────────────────────────────────────────────────────────────
    "childcare_universal": {
        "issue": "childcare",
        "topics": ["children", "education", "benefits"],
        "keywords": ["childcare", "child care", "pre-k", "pkeep", "early childhood",
                     "child development"],
    },
    "childcare_birth_to_three": {
        "issue": "childcare",
        "topics": ["children", "education", "benefits"],
        "keywords": ["birth to three", "birth-to-three", "infant care", "toddler",
                     "early childhood", "child care subsidy"],
    },
    # ── DC STATEHOOD ─────────────────────────────────────────────────────────
    "statehood_top_priority": {
        "issue": "dc_statehood",
        "topics": ["government", "civil-rights"],
        "keywords": ["statehood", "new columbia", "dc statehood", "voting rights",
                     "51st state", "end taxation without representation"],
    },
    "statehood_tax_exemption": {
        "issue": "dc_statehood",
        "topics": ["taxes", "government"],
        "keywords": ["statehood", "dc resident", "taxation without representation",
                     "dc tax"],
    },
    "statehood_strategy_bipartisan": {
        "issue": "dc_statehood",
        "topics": ["government", "civil-rights"],
        "keywords": ["statehood", "new columbia", "dc statehood"],
    },
    # ── FEDERAL WORKERS ──────────────────────────────────────────────────────
    "federal_workers_advocate": {
        "issue": "federal_workers",
        "topics": ["government", "labor", "jobs"],
        "keywords": ["federal worker", "federal employee", "government employee",
                     "federal workforce", "doge", "workforce reduction"],
    },
    # ── HOME RULE ────────────────────────────────────────────────────────────
    "delegate_budget_autonomy": {
        "issue": "home_rule",
        "topics": ["government", "budget"],
        "keywords": ["home rule", "budget autonomy", "congressional review",
                     "local budget", "budget control"],
    },
    "home_rule_dc_resist": {
        "issue": "home_rule",
        "topics": ["government", "civil-rights"],
        "keywords": ["home rule", "federal interference", "home rule act",
                     "congressional interference"],
    },
    "delegate_oppose_federal_mpd": {
        "issue": "home_rule",
        "topics": ["police", "government"],
        "keywords": ["national guard", "federal police", "federal law enforcement",
                     "section 740", "federal takeover", "military in dc"],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def display_name(row: dict) -> str:
    return ID_TO_DISPLAY.get(row["legislator_id"], row["candidate_name"])


def matches_question(row: dict, q_filter: dict) -> bool:
    if row["topic"] not in q_filter["topics"]:
        return False
    keywords = q_filter.get("keywords", [])
    if not keywords:
        return True
    haystack = (row["description"] + " " + row["bill_number"]).lower()
    return any(kw.lower() in haystack for kw in keywords)


def normalise_vote(vote: str) -> str:
    v = vote.strip().lower()
    if v in ("yes", "yea", "aye"):
        return "Yes"
    if v in ("no", "nay"):
        return "No"
    if v:
        return "Other"
    return ""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FILTERED_FIELDS = [
    "quiz_question", "issue", "candidate_name", "legislator_id",
    "session", "bill_number", "description", "motion", "vote",
    "topic", "sponsors", "bill_url",
]

SUMMARY_FIELDS = [
    "quiz_question", "issue", "candidate_name",
    "yes_count", "no_count", "other_count", "total",
]


def main():
    parser = argparse.ArgumentParser(description="Filter voting records by quiz question")
    parser.add_argument("--question", metavar="QID", help="Limit output to one question ID")
    parser.add_argument("--candidate", metavar="NAME", help="Limit output to one candidate display name")
    args = parser.parse_args()

    output_dir = Path(__file__).parent / "output"
    votes_path = output_dir / "voting_records.csv"
    if not votes_path.exists():
        print(f"ERROR: {votes_path} not found — run fastdemocracy_scraper.py first.")
        raise SystemExit(1)

    # Load all vote rows
    with open(votes_path, newline="", encoding="utf-8") as f:
        all_votes = list(csv.DictReader(f))

    print(f"Loaded {len(all_votes):,} vote records.")

    questions = QUESTION_FILTERS
    if args.question:
        if args.question not in questions:
            print(f"Unknown question ID '{args.question}'. Valid IDs:")
            for qid in sorted(questions):
                print(f"  {qid}")
            raise SystemExit(1)
        questions = {args.question: questions[args.question]}

    filtered_rows: list[dict] = []
    # summary: (question, candidate_display_name) → {yes, no, other}
    summary: dict[tuple, dict] = defaultdict(lambda: {"yes": 0, "no": 0, "other": 0})

    for qid, q_filter in questions.items():
        for row in all_votes:
            if row["legislator_id"] in EXCLUDED_IDS:
                continue
            cname = display_name(row)
            if args.candidate and cname.lower() != args.candidate.lower():
                continue
            if not matches_question(row, q_filter):
                continue

            vote_norm = normalise_vote(row.get("vote", ""))
            key = (qid, cname)
            if vote_norm == "Yes":
                summary[key]["yes"] += 1
            elif vote_norm == "No":
                summary[key]["no"] += 1
            elif vote_norm:
                summary[key]["other"] += 1

            filtered_rows.append({
                "quiz_question": qid,
                "issue": q_filter["issue"],
                "candidate_name": cname,
                "legislator_id": row["legislator_id"],
                "session": row["session"],
                "bill_number": row["bill_number"],
                "description": row["description"],
                "motion": row["motion"],
                "vote": vote_norm or row.get("vote", ""),
                "topic": row["topic"],
                "sponsors": row["sponsors"],
                "bill_url": row["bill_url"],
            })

    # Write filtered votes
    filtered_path = output_dir / "filtered_votes.csv"
    with open(filtered_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FILTERED_FIELDS)
        writer.writeheader()
        writer.writerows(filtered_rows)
    print(f"Wrote {len(filtered_rows):,} filtered rows → {filtered_path}")

    # Write summary
    summary_rows = []
    for (qid, cname), counts in sorted(summary.items()):
        total = counts["yes"] + counts["no"] + counts["other"]
        summary_rows.append({
            "quiz_question": qid,
            "issue": QUESTION_FILTERS[qid]["issue"],
            "candidate_name": cname,
            "yes_count": counts["yes"],
            "no_count": counts["no"],
            "other_count": counts["other"],
            "total": total,
        })

    summary_path = output_dir / "vote_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Wrote {len(summary_rows):,} summary rows → {summary_path}")

    # Print a quick human-readable table
    if args.question:
        print(f"\nSummary for '{args.question}':")
        print(f"  {'Candidate':<30} {'Yes':>5} {'No':>5} {'Other':>6} {'Total':>6}")
        print(f"  {'-'*30} {'---':>5} {'---':>5} {'-----':>6} {'-----':>6}")
        for row in summary_rows:
            print(f"  {row['candidate_name']:<30} {row['yes_count']:>5} {row['no_count']:>5} {row['other_count']:>6} {row['total']:>6}")


if __name__ == "__main__":
    main()
