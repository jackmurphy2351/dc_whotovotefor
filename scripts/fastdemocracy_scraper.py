#!/usr/bin/env python3
"""
FastDemocracy DC Council Scraper
Pulls sponsored bills and voting records for DC Council candidates from fastdemocracy.com.

Usage:
    python scripts/fastdemocracy_scraper.py                  # scrape all known candidates
    python scripts/fastdemocracy_scraper.py --bills-only     # sponsored bills only
    python scripts/fastdemocracy_scraper.py --votes-only     # voting records only
    python scripts/fastdemocracy_scraper.py --id DCL000027   # single legislator

Output: scripts/output/ (sponsored_bills.csv, voting_records.csv)

Discovery: running --discover probes DCL000001–DCL000040 and prints a name→ID table.
"""
import argparse
import csv
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AJAX_URL = "https://fastdemocracy.com/ajax/"
BASE_REFERER = "https://fastdemocracy.com/bill-search/dc/legislators/"
HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE_REFERER,
    "Accept": "*/*",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.5 Safari/605.1.15"
    ),
}

# DC candidates from the 2026 primary ballot who have (or had) DC Council seats.
# Key = FastDemocracy legislator ID; Value = (display_name, race)
# Duplicate IDs exist for some members who appear in multiple sessions — include both.
CANDIDATES: dict[str, tuple[str, str]] = {
    "DCL000002": ("Vincent Orange",       "Mayor"),
    "DCL000004": ("Kenyan McDuffie",       "Mayor (Session 19–22)"),
    "DCL000013": ("Anita Bonds",           "At-Large (Bonds seat)"),
    "DCL000017": ("Elissa Silverman",      "At-Large (McDuffie seat)"),
    "DCL000019": ("Robert White",          "Delegate (Session 23+)"),
    "DCL000020": ("Charles Allen",         "Ward 6"),
    "DCL000024": ("Robert White",          "Delegate (alt entry)"),
    "DCL000025": ("Kenyan McDuffie",       "Mayor (alt entry / Session 23+)"),
    "DCL000026": ("Brooke Pinto",          "Delegate"),
    "DCL000027": ("Janeese Lewis George",  "Mayor"),
    "DCL000031": ("Zachary Parker",        "Ward 5"),
}

# All topic slugs used by FastDemocracy's voting-history filter.
# Slugs that return no data for a given legislator are silently skipped.
TOPICS = [
    "agriculture", "animals", "arts", "banks", "benefits", "budget",
    "business", "children", "civil-rights", "communications", "crime",
    "cryptocurrency", "defense", "drugs", "education", "energy",
    "environment", "finance", "fire", "food", "government", "guns",
    "healthcare", "housing", "immigration", "infrastructure", "internet",
    "jobs", "labor", "land", "manufacturing", "media", "military",
    "police", "poverty", "prisons", "public-health", "religion",
    "retirement", "schools", "science", "social-services", "taxes",
    "technology", "trade", "transportation", "veterans", "water", "welfare",
]

REQUEST_DELAY = 0.6  # seconds between requests — be polite to the server

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch(params: dict, retries: int = 3) -> str:
    url = AJAX_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                print(f"  Rate-limited, sleeping 5s…", file=sys.stderr)
                time.sleep(5)
            else:
                raise
    return ""


def fetch_with_delay(params: dict) -> str:
    time.sleep(REQUEST_DELAY)
    return _fetch(params)

# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------

class _TableParser(HTMLParser):
    """Minimal table parser that returns a list of rows (each row = list of cell texts)."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []
        self._in_cell = False
        self._links: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "tr":
            self._row = []
            self._links = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell = []
        elif tag == "a" and self._in_cell:
            href = attrs_d.get("href", "")
            if href:
                self._links.append(href)

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._in_cell = False
            self._row.append("".join(self._cell).strip())
        elif tag == "tr" and self._row:
            self.rows.append(self._row[:])

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def _parse_table(html: str) -> list[list[str]]:
    p = _TableParser()
    p.feed(html)
    return p.rows


def parse_sponsored_bills(html: str, leg_id: str, leg_name: str) -> list[dict]:
    """Return list of dicts for every bill row in the sponsored-bills response."""
    records = []
    for row in _parse_table(html)[1:]:  # skip header
        if len(row) < 2:
            continue
        cell0 = row[0]
        # cell0 looks like "21\nB 21-0708" — split on whitespace
        parts = cell0.split()
        session = parts[0] if parts else ""
        bill_number = " ".join(parts[1:]) if len(parts) > 1 else ""
        # extract URL from raw HTML snippet
        url_match = re.search(r'href="(https://fastdemocracy\.com/bill/[^"]+)"', html)
        # We'll re-parse for URLs per row below — for now use empty string
        title = row[1]
        records.append({
            "legislator_id": leg_id,
            "candidate_name": leg_name,
            "session": session,
            "bill_number": bill_number,
            "title": title,
            "bill_url": "",
        })
    return records


def parse_sponsored_bills_full(html: str, leg_id: str, leg_name: str) -> list[dict]:
    """More accurate bill parser that extracts URLs from the raw HTML."""
    records = []
    # Each <tr> contains two <td>s: (session+bill+link) and (title)
    row_pattern = re.compile(
        r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
        re.DOTALL,
    )
    link_pattern = re.compile(r'href="(https://fastdemocracy\.com/bill/[^"]+)"[^>]*>([^<]+)</a>')
    for m in row_pattern.finditer(html):
        cell0_html, cell1_html = m.group(1), m.group(2)
        # Session number is raw text before the <a>
        raw_text = re.sub(r'<[^>]+>', ' ', cell0_html)
        parts = raw_text.split()
        session = parts[0] if parts else ""
        link_m = link_pattern.search(cell0_html)
        bill_url = link_m.group(1) if link_m else ""
        bill_number = link_m.group(2).strip() if link_m else (" ".join(parts[1:]) if len(parts) > 1 else "")
        title = re.sub(r'<[^>]+>', '', cell1_html).strip()
        if not bill_number and not title:
            continue
        records.append({
            "legislator_id": leg_id,
            "candidate_name": leg_name,
            "session": session,
            "bill_number": bill_number,
            "title": title,
            "bill_url": bill_url,
        })
    return records


def parse_vote_records(html: str, topic: str, leg_id: str, leg_name: str) -> list[dict]:
    """Parse voting-record HTML for a single topic, returning list of vote dicts."""
    records = []
    row_pattern = re.compile(
        r'<tr[^>]*class="action[^"]*"[^>]*>(.*?)</tr>',
        re.DOTALL,
    )
    cell_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
    bill_link_pat = re.compile(r'href="(https://fastdemocracy\.com/bill/[^"]+)"[^>]*>([^<]+)</a>')
    leg_link_pat = re.compile(r'href="https://fastdemocracy\.com/legislator/dc/legislators/(DCL\d+)"[^>]*>([^<;]+)')
    vote_pat = re.compile(r'<font[^>]+color="([^"]+)"[^>]*>([^<]+)</font>')

    for row_m in row_pattern.finditer(html):
        row_html = row_m.group(1)
        cells = cell_pattern.findall(row_html)
        if len(cells) < 4:
            continue

        # Cell 0: session + bill number + link
        c0 = cells[0]
        raw0 = re.sub(r'<[^>]+>', ' ', c0).split()
        session = raw0[0] if raw0 else ""
        bill_m = bill_link_pat.search(c0)
        bill_url = bill_m.group(1) if bill_m else ""
        bill_number = bill_m.group(2).strip() if bill_m else " ".join(raw0[1:])

        # Cell 1: sponsors
        sponsors = [name.strip().rstrip(";").strip() for _, name in leg_link_pat.findall(cells[1])]

        # Cell 2: description
        description = re.sub(r'<[^>]+>', '', cells[2]).strip()

        # Cell 3: motion + vote
        vote_m = vote_pat.search(cells[3])
        vote = vote_m.group(2).strip() if vote_m else ""
        motion_raw = re.sub(r'<[^>]+>', ' ', cells[3]).strip()
        motion = motion_raw.replace(vote, "").strip()

        records.append({
            "legislator_id": leg_id,
            "candidate_name": leg_name,
            "topic": topic,
            "session": session,
            "bill_number": bill_number,
            "bill_url": bill_url,
            "description": description,
            "motion": motion,
            "vote": vote,
            "sponsors": "; ".join(sponsors),
        })
    return records


# ---------------------------------------------------------------------------
# Legislator ID discovery
# ---------------------------------------------------------------------------

def discover_legislators(id_range: range = range(1, 41)) -> dict[str, str]:
    """
    Probe legislator IDs and return {leg_id: name} by extracting sponsor links
    from one topic's voting records for each candidate.
    """
    print("Discovering legislator names by probing voting records…")
    known: dict[str, str] = {}

    # Seed with a known active legislator to get the co-sponsor network
    seed_params = {
        "voterecord-state": "dc",
        "voterecord-topic-id": "fire",
        "voterecord-chamber": "upper",
        "voterecord-legislator": "DCL000002",
    }
    html = fetch_with_delay(seed_params)
    for lid, name in re.findall(
        r'href="https://fastdemocracy\.com/legislator/dc/legislators/(DCL\d+)"[^>]*>\s*([^<;]+)',
        html,
    ):
        name = name.strip()
        if name:
            known[lid] = name

    # Try additional seeds for more recent sessions
    for extra_id in ["DCL000020", "DCL000027", "DCL000025"]:
        if extra_id not in known:
            continue
        for topic in ("housing", "budget", "crime"):
            p = {
                "voterecord-state": "dc",
                "voterecord-topic-id": topic,
                "voterecord-chamber": "upper",
                "voterecord-legislator": extra_id,
            }
            html = fetch_with_delay(p)
            for lid, name in re.findall(
                r'href="https://fastdemocracy\.com/legislator/dc/legislators/(DCL\d+)"[^>]*>\s*([^<;]+)',
                html,
            ):
                name = name.strip()
                if name and lid not in known:
                    known[lid] = name

    return {k: v for k, v in sorted(known.items())}


# ---------------------------------------------------------------------------
# Core scrape functions
# ---------------------------------------------------------------------------

def scrape_sponsored_bills(leg_id: str, leg_name: str) -> list[dict]:
    print(f"  Fetching sponsored bills for {leg_name} ({leg_id})…")
    html = fetch_with_delay({
        "sponsoredbills-state": "dc",
        "sponsoredbills-legislator": leg_id,
    })
    records = parse_sponsored_bills_full(html, leg_id, leg_name)
    print(f"    → {len(records)} bills")
    return records


def scrape_voting_records(leg_id: str, leg_name: str, topics: list[str] = TOPICS) -> list[dict]:
    print(f"  Fetching voting records for {leg_name} ({leg_id})…")
    all_records: list[dict] = []
    for topic in topics:
        html = fetch_with_delay({
            "voterecord-state": "dc",
            "voterecord-topic-id": topic,
            "voterecord-chamber": "upper",
            "voterecord-legislator": leg_id,
        })
        if len(html.strip()) <= 20:
            continue
        records = parse_vote_records(html, topic, leg_id, leg_name)
        if records:
            print(f"    {topic}: {len(records)} votes")
            all_records.extend(records)
    print(f"    → {len(all_records)} total votes across all topics")
    return all_records


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

BILLS_FIELDS = ["candidate_name", "legislator_id", "session", "bill_number", "title", "bill_url"]
VOTES_FIELDS = [
    "candidate_name", "legislator_id", "topic", "session",
    "bill_number", "description", "motion", "vote", "sponsors", "bill_url",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows → {path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape DC candidate legislative records from FastDemocracy")
    parser.add_argument("--bills-only", action="store_true", help="Only fetch sponsored bills")
    parser.add_argument("--votes-only", action="store_true", help="Only fetch voting records")
    parser.add_argument("--id", metavar="DCL_ID", help="Scrape a single legislator ID")
    parser.add_argument("--discover", action="store_true", help="Discover & print all DC legislator IDs")
    args = parser.parse_args()

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    if args.discover:
        known = discover_legislators()
        print("\nDiscovered legislators:")
        for lid, name in known.items():
            print(f"  {lid}: {name}")
        return

    candidates = CANDIDATES
    if args.id:
        if args.id not in CANDIDATES:
            print(f"Unknown ID {args.id}. Add it to CANDIDATES or use --discover.")
            print(f"Proceeding with ID only (no display name lookup).")
            candidates = {args.id: (args.id, "unknown")}
        else:
            candidates = {args.id: CANDIDATES[args.id]}

    all_bills: list[dict] = []
    all_votes: list[dict] = []

    for leg_id, (leg_name, race) in candidates.items():
        print(f"\n{'='*60}")
        print(f"{leg_name} ({leg_id}) — {race}")

        if not args.votes_only:
            bills = scrape_sponsored_bills(leg_id, leg_name)
            all_bills.extend(bills)

        if not args.bills_only:
            votes = scrape_voting_records(leg_id, leg_name)
            all_votes.extend(votes)

    print(f"\n{'='*60}")
    if all_bills:
        write_csv(output_dir / "sponsored_bills.csv", BILLS_FIELDS, all_bills)
    if all_votes:
        write_csv(output_dir / "voting_records.csv", VOTES_FIELDS, all_votes)

    if not all_bills and not all_votes:
        print("No data scraped. Try --discover to check available IDs.")


if __name__ == "__main__":
    main()
