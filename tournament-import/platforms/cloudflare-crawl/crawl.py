#!/usr/bin/env python3
"""
Cloudflare /crawl-based tournament scraper for EasyChamp imports.

Universal scraper that uses Cloudflare's Browser Rendering API to crawl
any tournament website and extract structured fixture data.

Usage:
    # Start a crawl job
    python crawl.py start --url "https://league-site.com/season" \
        --account-id "$CF_ACCOUNT_ID" --api-token "$CF_API_TOKEN" \
        --limit 50 --depth 3 --render

    # Poll for results
    python crawl.py poll --job-id "abc-123" \
        --account-id "$CF_ACCOUNT_ID" --api-token "$CF_API_TOKEN" \
        --output raw_crawl.json

    # Transform crawl results to EasyChamp import format
    python crawl.py transform --input raw_crawl.json --output import.json \
        --league-name "My League" --country "USA" --sport "Soccer"

Environment variables (alternative to CLI args):
    CF_ACCOUNT_ID   - Cloudflare account ID
    CF_API_TOKEN    - Cloudflare API token with Browser Rendering permission
"""

import argparse
import hashlib
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API_BASE = "https://api.cloudflare.com/client/v4/accounts"

# AI extraction prompt for tournament pages
EXTRACTION_PROMPT = """Extract tournament fixture/match data from this page. For each match found, return:
- home_team: home team name (string)
- away_team: away team name (string)
- home_score: home team score (integer or null if not played)
- away_score: away team score (integer or null if not played)
- date: match date in YYYY-MM-DD format (string or null)
- round: round/matchday number or name (string)
- stage: "group" or "playoff" (string)
- playoff_round: if playoff, one of: "round_of_16", "quarterfinal", "semifinal", "final", "3rd_place_playoff" (string or null)
- home_scorers: list of scorer names for home team (array of strings)
- away_scorers: list of scorer names for away team (array of strings)
- home_penalty_score: penalty shootout score for home team (integer or null)
- away_penalty_score: penalty shootout score for away team (integer or null)
- competition_name: name of the competition/tournament (string)

Return as JSON: { "matches": [...], "teams": [...], "standings": [...] }

For teams, return: { "name": string, "logo_url": string or null }
For standings (if visible), return: { "team": string, "played": int, "wins": int, "draws": int, "losses": int, "goals_for": int, "goals_against": int, "points": int, "position": int }

If the page has no match data, return { "matches": [], "teams": [], "standings": [] }."""


def api_request(method, url, token, data=None):
    """Make an authenticated request to Cloudflare API."""
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        print(f"API error {e.code}: {error_body}", file=sys.stderr)
        sys.exit(1)


def start_crawl(args):
    """Start a Cloudflare crawl job."""
    account_id = args.account_id or os.environ.get("CF_ACCOUNT_ID")
    api_token = args.api_token or os.environ.get("CF_API_TOKEN")

    if not account_id or not api_token:
        print("Error: CF_ACCOUNT_ID and CF_API_TOKEN required", file=sys.stderr)
        sys.exit(1)

    url = f"{API_BASE}/{account_id}/browser-rendering/crawl"

    payload = {
        "url": args.url,
        "limit": args.limit,
        "depth": args.depth,
        "render": args.render,
        "formats": ["json", "markdown"],
        "jsonOptions": {
            "prompt": EXTRACTION_PROMPT,
            "response_format": {"type": "json_object"},
        },
        "rejectResourceTypes": ["image", "media", "font", "stylesheet"],
    }

    if args.include:
        payload.setdefault("options", {})["includePatterns"] = args.include
    if args.exclude:
        payload.setdefault("options", {})["excludePatterns"] = args.exclude

    result = api_request("POST", url, api_token, payload)

    if result.get("success"):
        job_id = result["result"]
        print(f"Crawl job started: {job_id}")
        print(f"\nPoll with:\n  python crawl.py poll --job-id {job_id}")
        return job_id
    else:
        print(f"Failed to start crawl: {result}", file=sys.stderr)
        sys.exit(1)


def poll_crawl(args):
    """Poll a crawl job until completion and save results."""
    account_id = args.account_id or os.environ.get("CF_ACCOUNT_ID")
    api_token = args.api_token or os.environ.get("CF_API_TOKEN")

    if not account_id or not api_token:
        print("Error: CF_ACCOUNT_ID and CF_API_TOKEN required", file=sys.stderr)
        sys.exit(1)

    base_url = f"{API_BASE}/{account_id}/browser-rendering/crawl/{args.job_id}"

    all_pages = []
    cursor = None

    while True:
        url = base_url
        if cursor:
            url += f"?cursor={cursor}"

        result = api_request("GET", url, api_token)

        if not result.get("success"):
            print(f"Poll error: {result}", file=sys.stderr)
            sys.exit(1)

        data = result["result"]
        status = data.get("status", "unknown")
        total = data.get("total", 0)
        finished = data.get("finished", 0)

        print(f"Status: {status} ({finished}/{total} pages)")

        if "pages" in data:
            all_pages.extend(data["pages"])

        if status == "completed":
            # Check for more pages via cursor
            if data.get("cursor"):
                cursor = data["cursor"]
                continue
            break
        elif status in ("failed", "cancelled"):
            print(f"Job {status}", file=sys.stderr)
            sys.exit(1)
        else:
            # Still running — wait and retry
            time.sleep(5)
            continue

    output = {
        "job_id": args.job_id,
        "total_pages": len(all_pages),
        "pages": all_pages,
    }

    output_path = args.output or "raw_crawl.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_pages)} pages to {output_path}")
    print(f"Next: python crawl.py transform --input {output_path} --output import.json")


def make_id(prefix, name):
    """Generate deterministic ID from name."""
    h = hashlib.md5(name.encode()).hexdigest()[:12]
    return f"cf:{prefix}:{h}"


def transform_crawl(args):
    """Transform raw crawl results into EasyChamp import JSON."""
    with open(args.input) as f:
        raw = json.load(f)

    # Collect all matches, teams, standings from all crawled pages
    all_matches = []
    all_teams = {}
    all_standings = []

    for page in raw.get("pages", []):
        page_json = page.get("json")
        if not page_json:
            continue

        # Handle both direct dict and string JSON
        if isinstance(page_json, str):
            try:
                page_json = json.loads(page_json)
            except json.JSONDecodeError:
                continue

        for match in page_json.get("matches", []):
            all_matches.append(match)

        for team in page_json.get("teams", []):
            name = team.get("name", "")
            if name and name not in all_teams:
                all_teams[name] = team

        for standing in page_json.get("standings", []):
            all_standings.append(standing)

    if not all_matches:
        print("Warning: No matches found in crawl data", file=sys.stderr)
        print("Consider using the two-pass strategy (see guide.md)", file=sys.stderr)

    print(f"Found: {len(all_matches)} matches, {len(all_teams)} teams, {len(all_standings)} standings")

    # Deduplicate matches by (home, away, round)
    seen = set()
    unique_matches = []
    for m in all_matches:
        key = (m.get("home_team", ""), m.get("away_team", ""), str(m.get("round", "")))
        if key not in seen:
            seen.add(key)
            unique_matches.append(m)

    print(f"After dedup: {len(unique_matches)} unique matches")

    # Build team registry with IDs
    team_registry = {}
    for match in unique_matches:
        for side in ["home_team", "away_team"]:
            name = match.get(side, "")
            if name and name not in team_registry:
                team_registry[name] = {
                    "Id": make_id("team", name),
                    "Name": name,
                    "ImageUrl": all_teams.get(name, {}).get("logo_url"),
                    "SportKindName": args.sport,
                }

    # Collect all players
    player_registry = {}

    def get_player(name, team_name):
        key = f"{name}|{team_name}"
        if key not in player_registry:
            player_registry[key] = {
                "FullName": name,
                "Id": make_id("player", key),
                "OtherFullName": "",
                "SportKindName": args.sport,
            }
        return player_registry[key]

    # Separate group and playoff fixtures
    group_fixtures = []
    playoff_fixtures = []

    for match in unique_matches:
        home_name = match.get("home_team", "Unknown")
        away_name = match.get("away_team", "Unknown")
        home_team = team_registry.get(home_name, {"Id": make_id("team", home_name), "Name": home_name})
        away_team = team_registry.get(away_name, {"Id": make_id("team", away_name), "Name": away_name})

        # Build events from scorers
        events = []
        home_members = []
        away_members = []

        for scorer_name in match.get("home_scorers", []):
            player = get_player(scorer_name, home_name)
            events.append({
                "IsHomeEvent": True,
                "Minute": str(5 + len(events) * 5),
                "EventType": "scorer",
                "Player": dict(player),
                "Description": f"Goal by {scorer_name}",
            })
            home_members.append({"Player": dict(player)})

        for scorer_name in match.get("away_scorers", []):
            player = get_player(scorer_name, away_name)
            events.append({
                "IsHomeEvent": False,
                "Minute": str(5 + len(events) * 5),
                "EventType": "scorer",
                "Player": dict(player),
                "Description": f"Goal by {scorer_name}",
            })
            away_members.append({"Player": dict(player)})

        # Determine round info
        round_str = str(match.get("round", "1"))
        try:
            match_day = int(round_str)
            match_day_name = round_str
        except ValueError:
            match_day = 1
            match_day_name = round_str

        home_score = match.get("home_score")
        away_score = match.get("away_score")

        fixture = {
            "Id": make_id("fixture", f"{home_name}-{away_name}-{round_str}"),
            "Date": match.get("date"),
            "HomeTeamScore": str(home_score) if home_score is not None else None,
            "AwayTeamScore": str(away_score) if away_score is not None else None,
            "MatchDay": match_day,
            "MatchDayName": match_day_name,
            "Status": 2 if home_score is not None else 0,
            "HomeTeam": {
                **home_team,
                "TeamMembers": _dedupe_members(home_members),
            },
            "AwayTeam": {
                **away_team,
                "TeamMembers": _dedupe_members(away_members),
            },
            "HomeSquad": [{"Player": m["Player"], "SquadType": 0, "IsPlayed": True} for m in _dedupe_members(home_members)],
            "AwaySquad": [{"Player": m["Player"], "SquadType": 0, "IsPlayed": True} for m in _dedupe_members(away_members)],
            "Events": events,
        }

        # Handle penalties
        hp = match.get("home_penalty_score")
        ap = match.get("away_penalty_score")
        if hp is not None and ap is not None:
            fixture["HomePenaltyScore"] = str(hp)
            fixture["AwayPenaltyScore"] = str(ap)
            fixture["PeriodScores"] = [
                {"type": "regular_period", "Home_score": str(home_score), "Away_score": str(away_score)},
                {"type": "penalties", "Home_score": str(hp), "Away_score": str(ap)},
            ]

        stage = match.get("stage", "group")
        if stage == "playoff":
            playoff_round = match.get("playoff_round", "quarterfinal")
            fixture["MatchDayName"] = playoff_round
            playoff_fixtures.append(fixture)
        else:
            group_fixtures.append(fixture)

    # Assign bracket Order to playoff fixtures
    _assign_bracket_order(playoff_fixtures)

    # Determine dates
    dates = [m.get("date") for m in unique_matches if m.get("date")]
    start_date = min(dates) if dates else None
    end_date = max(dates) if dates else None

    # Detect competition name
    comp_names = [m.get("competition_name") for m in unique_matches if m.get("competition_name")]
    comp_name = comp_names[0] if comp_names else args.league_name

    # Build stages
    stages = []
    if group_fixtures:
        stages.append({
            "Name": "Group Stage",
            "Type": "League",
            "Groups": [{"Name": "Group A", "Fixtures": group_fixtures}],
        })
    if playoff_fixtures:
        stages.append({
            "Name": "Playoffs",
            "Type": "Playoff",
            "Groups": [{"Name": "Playoffs", "Fixtures": playoff_fixtures}],
        })

    # Build champ-level team list with ALL players
    champ_teams = []
    for name, team in team_registry.items():
        members = []
        for key, player in player_registry.items():
            pname, tname = key.rsplit("|", 1)
            if tname == name:
                members.append({"Player": dict(player)})
        champ_teams.append({
            **team,
            "TeamMembers": members,
        })

    # Assemble import JSON
    import_json = {
        "ImportSource": 99,
        "ImportMode": 0,
        "League": {
            "Name": args.league_name,
            "Country": args.country,
            "SportKindName": args.sport,
            "ImageUrl": None,
            "Champs": [
                {
                    "Name": comp_name,
                    "ExternalId": make_id("comp", comp_name),
                    "StartDate": start_date,
                    "EndDate": end_date,
                    "IsComplete": True,
                    "SportKindName": args.sport,
                    "LeagueName": args.league_name,
                    "Teams": champ_teams,
                    "Stages": stages,
                }
            ],
        },
    }

    output_path = args.output or "import.json"
    with open(output_path, "w") as f:
        json.dump(import_json, f, indent=2, ensure_ascii=False)

    print(f"\nOutput: {output_path}")
    print(f"Teams: {len(team_registry)}, Fixtures: {len(group_fixtures) + len(playoff_fixtures)}, Players: {len(player_registry)}")
    print(f"\nNext: python scripts/validate_import.py {output_path} --strict")


def _dedupe_members(members):
    """Deduplicate team members by player ID."""
    seen = set()
    result = []
    for m in members:
        pid = m["Player"]["Id"]
        if pid not in seen:
            seen.add(pid)
            result.append(m)
    return result


BRACKET_ORDER = {
    "final": [1],
    "3rd_place_playoff": [],
    "semifinal": [2, 3],
    "quarterfinal": [4, 5, 6, 7],
    "round_of_16": list(range(8, 16)),
    "round_of_32": list(range(16, 32)),
}


def _assign_bracket_order(playoff_fixtures):
    """Assign Order values to playoff fixtures based on bracket position."""
    by_round = {}
    for f in playoff_fixtures:
        rd = f.get("MatchDayName", "quarterfinal")
        by_round.setdefault(rd, []).append(f)

    for round_name, fixtures in by_round.items():
        orders = BRACKET_ORDER.get(round_name, [])
        for i, f in enumerate(fixtures):
            if i < len(orders):
                f["Order"] = orders[i]
            else:
                f["Order"] = i + 1


def main():
    parser = argparse.ArgumentParser(
        description="Cloudflare /crawl tournament scraper for EasyChamp"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    start_p = subparsers.add_parser("start", help="Start a crawl job")
    start_p.add_argument("--url", required=True, help="URL to crawl")
    start_p.add_argument("--account-id", help="Cloudflare account ID (or CF_ACCOUNT_ID env)")
    start_p.add_argument("--api-token", help="Cloudflare API token (or CF_API_TOKEN env)")
    start_p.add_argument("--limit", type=int, default=50, help="Max pages to crawl")
    start_p.add_argument("--depth", type=int, default=3, help="Max link depth")
    start_p.add_argument("--render", action="store_true", help="Use headless Chrome")
    start_p.add_argument("--include", nargs="+", help="URL patterns to include")
    start_p.add_argument("--exclude", nargs="+", help="URL patterns to exclude")

    # poll
    poll_p = subparsers.add_parser("poll", help="Poll a crawl job for results")
    poll_p.add_argument("--job-id", required=True, help="Crawl job ID")
    poll_p.add_argument("--account-id", help="Cloudflare account ID")
    poll_p.add_argument("--api-token", help="Cloudflare API token")
    poll_p.add_argument("--output", default="raw_crawl.json", help="Output file")

    # transform
    transform_p = subparsers.add_parser("transform", help="Transform crawl results to EasyChamp format")
    transform_p.add_argument("--input", required=True, help="Raw crawl JSON file")
    transform_p.add_argument("--output", default="import.json", help="Output import JSON")
    transform_p.add_argument("--league-name", required=True, help="League name")
    transform_p.add_argument("--country", default="USA", help="Country")
    transform_p.add_argument("--sport", default="Soccer", help="Sport kind")

    args = parser.parse_args()

    if args.command == "start":
        start_crawl(args)
    elif args.command == "poll":
        poll_crawl(args)
    elif args.command == "transform":
        transform_crawl(args)


if __name__ == "__main__":
    main()
