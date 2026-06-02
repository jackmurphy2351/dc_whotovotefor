#!/usr/bin/env python3
"""
corroborate.py — cross-reference the published candidate positions against the
DC Council legislative record mined by filter_votes.py.

Reads:
  content/                          (via helpmevote.data_loader.load_all_content)
  scripts/output/filtered_sponsorships.csv   (strong evidence — authored bills)
  scripts/output/filtered_votes.csv          (weak evidence — roll-call votes)
  scripts/output/sponsored_bills.csv         (for the new-question theme appendix)

Writes:
  scripts/output/corroboration_report.md

The report never edits content. It classifies each (council candidate x question)
with evidence as:
  CORROBORATES — published stance agrees with the record → queue a source addition
  CONFLICT     — published stance contradicts the record → flag for manual review
  NEW          — strong evidence but no published position on that question

Nothing here decides relevance on its own: every bill is listed with its title and
LIMS URL so a human (or the curator applying §1) makes the final call.

Usage:
    python scripts/corroborate.py
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from helpmevote.data_loader import load_all_content  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

# Council candidates with a legislative record (display name as it appears in the
# mined CSVs). Each maps to the candidate `name` field in content/candidates/*.yaml.
COUNCIL_NAMES = {
    "Kenyan McDuffie", "Janeese Lewis George", "Vincent Orange", "Robert White",
    "Brooke Pinto", "Elissa Silverman", "Zachary Parker", "Charles Allen",
}

# "Last ~5 years": DC Council period 24 began January 2021. Sponsorships from
# period >= 24 are preferred; older bills are used only as a fallback when a
# candidate has no in-window record on a question.
MIN_PERIOD = 24

STANCE_LABEL = {
    -2: "strongly opposes (-2)", -1: "opposes (-1)", 0: "neutral (0)",
    1: "supports (+1)", 2: "strongly supports (+2)", None: "unknown (null)",
}


def load_rows(name: str) -> list[dict]:
    path = OUTPUT_DIR / name
    if not path.exists():
        print(f"ERROR: {path} not found — run filter_votes.py first.")
        raise SystemExit(1)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_candidate_index(content):
    """name -> Candidate, restricted to the council members in scope."""
    by_name = {}
    for cand in content.candidates_by_id.values():
        if cand.name in COUNCIL_NAMES:
            by_name[cand.name] = cand
    missing = COUNCIL_NAMES - set(by_name)
    if missing:
        print(f"WARNING: council names with no candidate entry: {sorted(missing)}")
    return by_name


def published_stance(cand, qid):
    """Return (has_position, stance) for a candidate's position on a question."""
    for pos in cand.positions:
        if pos.question_id == qid:
            return True, pos.stance
    return False, None


def classify(has_pos, stance, has_sponsor, bills_yes, bills_no):
    """Tentative, human-reviewable verdict, driven by SPONSORSHIP (strong evidence).

    Votes are too noisy and can be semantically inverted (a Yes on a "Sanctuary
    Values Act" supports *limiting* ICE cooperation), so they are NOT used to decide
    a verdict — they appear only as compact context. Sponsoring a topic bill is
    treated as supportive action on that issue.
    """
    if not has_pos:
        return "NEW" if has_sponsor else "—"
    if not has_sponsor:
        return "VOTE-ONLY"  # context only, not an action item
    if stance is None or stance == 0:
        return "REVIEW (no editorial lean to compare)"
    return "CORROBORATES" if stance > 0 else "CONFLICT"


def main():
    content = load_all_content(REPO_ROOT / "content")
    cand_by_name = build_candidate_index(content)

    sponsorships = load_rows("filtered_sponsorships.csv")
    votes = load_rows("filtered_votes.csv")
    all_votes_raw = load_rows("voting_records.csv")
    all_bills = load_rows("sponsored_bills.csv")

    # sponsorships[(name, qid)] -> {bill_number: (title, lims_url, period)}
    spon = defaultdict(dict)
    for r in sponsorships:
        period = int(r["council_period"]) if r.get("council_period") else 0
        spon[(r["candidate_name"], r["quiz_question"])][r["bill_number"]] = (
            r["title"], r["lims_url"], period,
        )

    # votes[(name, qid)][bill_number] -> {"votes": set, "title", "lims_url"}
    def _vote_slot():
        return {"votes": set(), "title": "", "lims_url": ""}
    vote_idx = defaultdict(lambda: defaultdict(_vote_slot))
    for r in votes:
        slot = vote_idx[(r["candidate_name"], r["quiz_question"])][r["bill_number"]]
        slot["votes"].add(r["vote"])
        slot["title"] = r["description"]
        slot["lims_url"] = r["lims_url"]

    q_prompt = {q.id: q.prompt for q in content.questions.values()}

    # ---- assemble per (candidate, question) records ----
    keys = set(spon) | set(vote_idx)
    records = []
    for (name, qid) in sorted(keys):
        cand = cand_by_name.get(name)
        if cand is None:
            continue
        has_pos, stance = published_stance(cand, qid)
        all_spon = spon.get((name, qid), {})
        spon_recent = {b: v for b, v in all_spon.items() if v[2] >= MIN_PERIOD}
        spon_old = {b: v for b, v in all_spon.items() if v[2] < MIN_PERIOD}
        # In-window record wins; older bills only count as a fallback when there is
        # no in-window sponsorship for this candidate/question.
        fallback = not spon_recent and bool(spon_old)
        spon_bills = spon_recent if spon_recent else (spon_old if fallback else {})
        bills_yes = bills_no = 0
        vote_bills = []
        for bno, slot in sorted(vote_idx.get((name, qid), {}).items()):
            vs = slot["votes"]
            if "Yes" in vs and "No" not in vs:
                lean = "Yes"
                bills_yes += 1
            elif "No" in vs and "Yes" not in vs:
                lean = "No"
                bills_no += 1
            else:
                lean = "/".join(sorted(vs)) or "?"
            vote_bills.append((bno, slot["title"], slot["lims_url"], lean))
        verdict = classify(has_pos, stance, bool(spon_bills), bills_yes, bills_no)
        records.append({
            "name": name, "cand": cand, "qid": qid, "has_pos": has_pos,
            "stance": stance, "spon_bills": spon_bills, "vote_bills": vote_bills,
            "bills_yes": bills_yes, "bills_no": bills_no, "verdict": verdict,
            "fallback": fallback,
        })

    # ---- vote-filter diagnostic ----
    vote_topics = Counter(r["topic"] for r in all_votes_raw)

    # ---- new-question theme appendix: council-sponsored bills matching NO
    #      existing question filter, by frequent title words ----
    matched_bill_nos = {r["bill_number"] for r in sponsorships}
    stop = set("the of and to for in a an act amendment temporary emergency "
               "declaration resolution congressional review of 2015 2016 2017 2018 "
               "2019 2020 2021 2022 2023 2024 2025 2026 establishment clarification "
               "second sense council aka now known as".split())
    word_freq = Counter()
    unmatched_examples = defaultdict(list)
    for b in all_bills:
        # council membership: the mined sponsored_bills.csv already covers only the
        # tracked legislators; Anita Bonds is the only excluded id.
        if b["legislator_id"] == "DCL000013":
            continue
        if b["bill_number"] in matched_bill_nos:
            continue
        title = b["title"]
        words = re.findall(r"[a-z]{4,}", title.lower())
        for w in words:
            if w in stop:
                continue
            word_freq[w] += 1
            if len(unmatched_examples[w]) < 4:
                unmatched_examples[w].append(title.split(" (")[0])

    # ---- write report ----
    lines = []
    A = lines.append
    A("# Council-record corroboration report\n")
    A("_Generated by `scripts/corroborate.py`. Strong evidence = sponsored bills; "
      "weak evidence = roll-call votes. No content was edited by this script._\n")

    A("## Vote-filter diagnostic\n")
    A(f"`voting_records.csv` holds {len(all_votes_raw):,} vote rows. Distinct `topic` "
      "values present (top 25), to confirm the filters line up with the scrape:\n")
    A("| topic | rows |\n|---|---|")
    for topic, n in vote_topics.most_common(25):
        A(f"| {topic or '(blank)'} | {n:,} |")
    A("\nA full run of `filter_votes.py` matches votes across many questions "
      f"({len(votes):,} filtered vote rows), so the earlier TOPA-only file was a "
      "single-question (`--question`) export, not a broken filter. Votes are kept as "
      "weak/supplementary evidence per plan.\n")

    sec1 = [r for r in records if r["verdict"] == "CORROBORATES"]
    sec2 = [r for r in records if r["verdict"] == "CONFLICT"]
    secnew = [r for r in records if r["verdict"] == "NEW"]
    secvote = [r for r in records if r["verdict"] == "VOTE-ONLY"]
    secrev = [r for r in records if r["verdict"].startswith("REVIEW")]

    def fmt_sponsored(r):
        tag = " — ⚠️ pre-2021 fallback (no in-window record)" if r["fallback"] else ""
        out = [f"    - **Sponsored (strong){tag}:**"]
        for bno, (title, url, period) in sorted(r["spon_bills"].items()):
            out.append(f"      - {bno} (period {period}) — {title} — {url}")
        return out

    def vote_summary(r):
        n = len(r["vote_bills"])
        if not n:
            return "no related votes"
        ex = "; ".join(t for _, t, _, _ in r["vote_bills"][:3])
        return (f"{n} related vote(s) — Yes={r['bills_yes']} No={r['bills_no']}; "
                f"e.g. {ex}")

    A("## §1 — Source additions to apply (CORROBORATES — sponsorship-backed)\n")
    A("The candidate **authored** a bill on-topic for a question they already take a "
      "supportive stance on. Append the listed LIMS source(s) to the existing position; "
      "do **not** change the stance. Confirm bill↔question polarity before adding.\n")
    by_cand = defaultdict(list)
    for r in sec1:
        by_cand[r["name"]].append(r)
    for name in sorted(by_cand):
        A(f"### {name} (`{cand_by_name[name].id}`)")
        for r in by_cand[name]:
            A(f"- **{r['qid']}** — published: {STANCE_LABEL[r['stance']]} — "
              f"prompt: _{q_prompt.get(r['qid'], '')}_")
            lines.extend(fmt_sponsored(r))
            A(f"      - _vote context:_ {vote_summary(r)}")
        A("")

    A("## §2 — Conflicts to review (sponsored a bill but published stance opposes)\n")
    if not sec2:
        A("_None flagged._\n")
    for r in sec2:
        A(f"- **{r['name']}** / **{r['qid']}** — published: {STANCE_LABEL[r['stance']]} "
          f"yet authored a bill on this topic. Verify polarity.")
        lines.extend(fmt_sponsored(r))
    A("")

    A("## §3 — New-question / position-gap signals (sponsored, no published position)\n")
    A("Strong evidence on a question the candidate has **no** published position on. "
      "Consider adding a position (after manual confirmation). These map to existing "
      "question IDs — brand-new question ideas are in §4.\n")
    bynew = defaultdict(list)
    for r in secnew:
        bynew[r["qid"]].append(r)
    for qid in sorted(bynew):
        A(f"- **{qid}** — _{q_prompt.get(qid, '')}_")
        for r in sorted(bynew[qid], key=lambda x: x["name"]):
            tag = " ⚠️ pre-2021 fallback" if r["fallback"] else ""
            A(f"    - {r['name']}{tag}:")
            for bno, (title, url, period) in sorted(r["spon_bills"].items()):
                A(f"      - {bno} (period {period}) — {title} — {url}")
    A("")

    A("## §4 — Brand-new question ideas (evidence appendix)\n")
    A("Most frequent meaningful words among council-sponsored bills that matched **no** "
      "existing question filter. Use this to hand-author proposed new questions "
      "(proposal only — not written to `questions.yaml`).\n")
    A("| word | bills | example titles |\n|---|---|---|")
    for word, n in word_freq.most_common(40):
        if n < 4:
            continue
        ex = "; ".join(unmatched_examples[word][:3])
        A(f"| {word} | {n} | {ex} |")
    A("")

    A("## Appendix A — Vote-only context (weak; no sponsorship)\n")
    A("Questions where the candidate has no authored bill but did cast related votes. "
      "Weak/noisy evidence (routine budget votes, broad reform omnibuses, possible "
      "polarity inversion) — informational only, not an action list.\n")
    for r in sorted(secvote, key=lambda x: (x["name"], x["qid"])):
        A(f"- {r['name']} / {r['qid']} — published: {STANCE_LABEL[r['stance']]} — "
          f"{vote_summary(r)}")
    A("")

    A("## Appendix B — REVIEW (neutral / no editorial lean, sponsored)\n")
    for r in secrev:
        A(f"- {r['name']} / {r['qid']} — published: {STANCE_LABEL[r['stance']]} "
          f"(sponsored={len(r['spon_bills'])})")
    A("")

    report_path = OUTPUT_DIR / "corroboration_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote report → {report_path}")
    print(f"  §1 corroborates: {len(sec1)}  §2 conflicts: {len(sec2)}  "
          f"§3 new/gap: {len(secnew)}  vote-only: {len(secvote)}  review: {len(secrev)}")


if __name__ == "__main__":
    main()
