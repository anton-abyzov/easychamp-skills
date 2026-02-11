#!/usr/bin/env python3
"""
Generic tournament parser for EasyChamp imports.

Transforms tournament data from external platforms into EasyChamp's
POST /import/league format. Supports PS23 Soccer JSON and generic CSV.

Usage:
    python parse_tournament.py --platform ps23 --input data.json --output import.json
    python parse_tournament.py --platform csv --input games.csv --output import.json

PS23 Soccer JSON format:
    See knowledge/platform-ps23.md for expected structure.

Generic CSV format:
    Required columns: date, home_team, away_team, home_score, away_score, week
    Optional: home_scorers, away_scorers, home_logo, away_logo, stage
"""

import json
import csv
import re
import hashlib
import sys
import argparse
from pathlib import Path
from collections import defaultdict


def slugify(name):
    """Convert name to URL-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def md5_short(val):
    """Short MD5 hash for ID generation."""
    return hashlib.md5(val.encode()).hexdigest()[:12]


def parse_score(score_str):
    """Parse score string like '5-3' into (home, away) as strings."""
    if not score_str or score_str.strip() in ("", "-", "vs", "TBD"):
        return None, None
    parts = score_str.strip().split("-")
    if len(parts) != 2:
        return None, None
    try:
        h, a = parts[0].strip(), parts[1].strip()
        int(h)  # validate numeric
        int(a)
        return h, a
    except ValueError:
        return None, None


def parse_penalty_score(score_str):
    """Parse penalty score like '(2-3)' or 'pen 2-3'."""
    if not score_str:
        return None, None
    m = re.search(r"(?:pen|penalties?|pk)[\s:]*(\d+)\s*[-–]\s*(\d+)", score_str, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"\((\d+)\s*[-–]\s*(\d+)\)", score_str)
    if m:
        return m.group(1), m.group(2)
    return None, None


def parse_scorers(scorers_str, team_id, platform_prefix):
    """
    Parse scorer string into list of (player_name, player_id, goal_count).
    Handles: semicolons, commas, multipliers (5x Name, Name x5).
    """
    if not scorers_str:
        return []

    skip = {"walk over", "forfeit", "w/o", "wo", ""}
    results = []

    # Split by semicolons first, then by commas
    parts = re.split(r"[;]", scorers_str)
    if len(parts) == 1:
        parts = re.split(r",", scorers_str)

    for part in parts:
        part = part.strip()
        if not part or part.lower() in skip:
            continue

        # Check multiplier prefix: "5x K. Moosa"
        m = re.match(r"(\d+)\s*x\s+(.+)", part, re.IGNORECASE)
        if m:
            count = int(m.group(1))
            name = m.group(2).strip()
        else:
            # Check multiplier suffix: "K. Moosa x5"
            m = re.match(r"(.+?)\s+x\s*(\d+)", part, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                count = int(m.group(2))
            else:
                name = part
                count = 1

        if name.lower() in skip:
            continue

        pid = f"{platform_prefix}:player:{md5_short(name)}"
        results.append((name, pid, count))

    return results


def make_player(name, pid, sport="Soccer"):
    """Create player object with all required fields."""
    return {
        "FullName": name,
        "Id": pid,
        "OtherFullName": "",
        "SportKindName": sport,
    }


def make_team(name, team_id, logo_url=None, sport="Soccer", members=None):
    """Create team object."""
    team = {
        "Id": team_id,
        "Name": name,
        "ImageUrl": logo_url,
        "SportKindName": sport,
    }
    if members:
        team["TeamMembers"] = [{"Player": make_player(m["name"], m["id"], sport)} for m in members]
    else:
        team["TeamMembers"] = []
    return team


def make_events(home_scorers, away_scorers, team_id_home, team_id_away, prefix):
    """Create events list from scorer strings."""
    events = []
    for name, pid, count in parse_scorers(home_scorers, team_id_home, prefix):
        for _ in range(count):
            events.append({
                "IsHomeEvent": True,
                "Minute": "",
                "EventType": "scorer",
                "Player": make_player(name, pid),
                "Description": f"Goal by {name}",
            })
    for name, pid, count in parse_scorers(away_scorers, team_id_away, prefix):
        for _ in range(count):
            events.append({
                "IsHomeEvent": False,
                "Minute": "",
                "EventType": "scorer",
                "Player": make_player(name, pid),
                "Description": f"Goal by {name}",
            })
    return events


def build_squads(scorers_str, team_id, prefix, roster=None):
    """
    Build squad list. If roster provided, use full roster.
    Otherwise fall back to scorers only.
    """
    squad = []
    seen = set()

    if roster:
        for player in roster:
            pid = player.get("id") or f"{prefix}:player:{md5_short(player['name'])}"
            if pid not in seen:
                seen.add(pid)
                squad.append({
                    "Player": make_player(player["name"], pid),
                    "SquadType": 0,
                    "IsPlayed": player.get("played", True),
                })

    # Add scorers not already in roster
    for name, pid, _ in parse_scorers(scorers_str, team_id, prefix):
        if pid not in seen:
            seen.add(pid)
            squad.append({
                "Player": make_player(name, pid),
                "SquadType": 0,
                "IsPlayed": True,
            })

    return squad


# ─────────────────────────────────────────────
# PS23 Soccer Parser
# ─────────────────────────────────────────────

def parse_ps23(data, sport="Soccer"):
    """Parse PS23 Soccer JSON export into EasyChamp import format."""
    prefix = "ps23"
    comp = data.get("competition", {})
    league_name = comp.get("league_name") or comp.get("name", "Unknown League")
    comp_name = comp.get("name", league_name)
    country = comp.get("country", "")
    start_date = comp.get("start_date", "")
    end_date = comp.get("end_date", "")

    # Build team registry from all games
    teams = {}  # team_name -> {id, logo, members}
    all_games = data.get("all_games", [])
    player_stats = data.get("all_player_stats", [])

    # Collect player-team mappings from stats
    team_rosters = defaultdict(list)
    for ps in player_stats:
        team_name = ps.get("team", "")
        player_name = ps.get("player", "")
        if team_name and player_name:
            pid = f"{prefix}:player:{md5_short(player_name)}"
            team_rosters[team_name].append({"name": player_name, "id": pid, "played": True})

    # Build team info from games
    for game in all_games:
        for side in ("home", "away"):
            name = game.get(side, "")
            if name and name not in teams:
                tid = f"{prefix}:team:{md5_short(name)}"
                logo = game.get(f"{side}_logo") or game.get(f"{side}_image")
                # PS23 logo pattern
                if not logo and game.get(f"{side}_id"):
                    logo = f"https://ps23soccer.com/webfiles/ps23/escudos/{game[f'{side}_id']}.png"
                teams[name] = {"id": tid, "logo": logo, "members": team_rosters.get(name, [])}

    # Group stage fixtures
    group_fixtures = []
    for game in all_games:
        home_name = game.get("home", "")
        away_name = game.get("away", "")
        if not home_name or not away_name:
            continue

        home_info = teams.get(home_name, {"id": f"{prefix}:team:{md5_short(home_name)}", "logo": None, "members": []})
        away_info = teams.get(away_name, {"id": f"{prefix}:team:{md5_short(away_name)}", "logo": None, "members": []})

        score = game.get("score", "")
        h_score, a_score = parse_score(score)
        week = game.get("week") or game.get("matchday") or game.get("round") or 1
        date = game.get("date", start_date)

        fixture_id = f"{prefix}:fixture:{slugify(home_name)}-vs-{slugify(away_name)}-{week}"

        home_scorers = game.get("home_scorers", "")
        away_scorers = game.get("away_scorers", "")

        fixture = {
            "Id": fixture_id,
            "Date": date,
            "HomeTeamScore": h_score or "0",
            "AwayTeamScore": a_score or "0",
            "MatchDay": int(week),
            "MatchDayName": str(week),
            "Status": 2 if h_score is not None else 0,
            "HomeTeam": make_team(home_name, home_info["id"], home_info["logo"], sport),
            "AwayTeam": make_team(away_name, away_info["id"], away_info["logo"], sport),
            "HomeSquad": build_squads(home_scorers, home_info["id"], prefix, home_info["members"]),
            "AwaySquad": build_squads(away_scorers, away_info["id"], prefix, away_info["members"]),
            "Events": make_events(home_scorers, away_scorers, home_info["id"], away_info["id"], prefix),
        }
        group_fixtures.append(fixture)

    # Playoff fixtures
    playoff_fixtures = []
    playoffs = data.get("playoffs") or comp.get("playoffs") or {}
    stage_order = {"quarterfinals": "quarterfinal", "semifinals": "semifinal",
                   "final": "final", "third_place": "third_place"}
    node_base = {"quarterfinal": 4, "semifinal": 2, "final": 1}

    for stage_key, mdn in stage_order.items():
        games = playoffs.get(stage_key, [])
        if isinstance(games, dict):
            games = [games]
        for gi, game in enumerate(games):
            if not game:
                continue
            home_name = game.get("home", "")
            away_name = game.get("away", "")
            if not home_name or not away_name:
                continue

            home_info = teams.get(home_name, {"id": f"{prefix}:team:{md5_short(home_name)}", "logo": None, "members": []})
            away_info = teams.get(away_name, {"id": f"{prefix}:team:{md5_short(away_name)}", "logo": None, "members": []})

            score = game.get("score", "")
            h_score, a_score = parse_score(score)
            date = game.get("date", end_date)
            fixture_id = f"{prefix}:fixture:{slugify(home_name)}-vs-{slugify(away_name)}-{mdn}{gi+1}"
            order_val = node_base.get(mdn, 1) + gi

            fixture = {
                "Id": fixture_id,
                "Date": date,
                "HomeTeamScore": h_score or "0",
                "AwayTeamScore": a_score or "0",
                "MatchDay": gi + 1,
                "MatchDayName": mdn,
                "Status": 2 if h_score is not None else 0,
                "Order": order_val,
                "HomeTeam": make_team(home_name, home_info["id"], home_info["logo"], sport),
                "AwayTeam": make_team(away_name, away_info["id"], away_info["logo"], sport),
                "HomeSquad": [],
                "AwaySquad": [],
                "Events": make_events(
                    game.get("home_scorers", ""),
                    game.get("away_scorers", ""),
                    home_info["id"], away_info["id"], prefix
                ),
            }

            # Handle penalties
            pen_score = game.get("penalty_score") or game.get("penalties")
            hp, ap = parse_penalty_score(str(pen_score)) if pen_score else (None, None)
            if hp and ap:
                fixture["HomePenaltyScore"] = hp
                fixture["AwayPenaltyScore"] = ap
                fixture["HasPenalties"] = True
                fixture["HasOvertime"] = False
                fixture["PeriodScores"] = [{"Home_score": hp, "Away_score": ap, "Type": "penalties"}]
                # Determine winner
                if int(hp) > int(ap):
                    fixture["WinnerTeamId"] = home_info["id"]
                else:
                    fixture["WinnerTeamId"] = away_info["id"]

            playoff_fixtures.append(fixture)

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

    # Build final import
    is_complete = all(f.get("Status") == 2 for f in group_fixtures + playoff_fixtures)

    return {
        "ImportSource": 99,
        "ImportMode": 0,
        "League": {
            "Name": league_name,
            "Country": country,
            "SportKindName": sport,
            "ImageUrl": None,
            "Champs": [{
                "Name": comp_name,
                "ExternalId": f"{prefix}:comp:{slugify(comp_name)}",
                "StartDate": start_date,
                "EndDate": end_date,
                "IsComplete": is_complete,
                "SportKindName": sport,
                "LeagueName": league_name,
                "Stages": stages,
            }],
        },
    }


# ─────────────────────────────────────────────
# Generic CSV Parser
# ─────────────────────────────────────────────

def parse_csv(filepath, sport="Soccer", league_name="Imported League", prefix="csv"):
    """Parse generic CSV into EasyChamp import format."""
    fixtures = []
    teams = {}

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            home_name = row.get("home_team", "").strip()
            away_name = row.get("away_team", "").strip()
            if not home_name or not away_name:
                continue

            for name in (home_name, away_name):
                if name not in teams:
                    teams[name] = {"id": f"{prefix}:team:{md5_short(name)}", "logo": row.get(f"{'home' if name == home_name else 'away'}_logo")}

            h_score = str(row.get("home_score", "0")).strip()
            a_score = str(row.get("away_score", "0")).strip()
            week = int(row.get("week", row.get("round", row.get("matchday", "1"))))
            date = row.get("date", "")
            stage = row.get("stage", "group").strip().lower()

            fixture_id = f"{prefix}:fixture:{slugify(home_name)}-vs-{slugify(away_name)}-{week}"
            home_id = teams[home_name]["id"]
            away_id = teams[away_name]["id"]

            fixture = {
                "Id": fixture_id,
                "Date": date,
                "HomeTeamScore": h_score,
                "AwayTeamScore": a_score,
                "MatchDay": week,
                "MatchDayName": str(week) if stage == "group" else stage,
                "Status": 2,
                "HomeTeam": make_team(home_name, home_id, teams[home_name]["logo"], sport),
                "AwayTeam": make_team(away_name, away_id, teams[away_name]["logo"], sport),
                "HomeSquad": build_squads(row.get("home_scorers", ""), home_id, prefix),
                "AwaySquad": build_squads(row.get("away_scorers", ""), away_id, prefix),
                "Events": make_events(
                    row.get("home_scorers", ""),
                    row.get("away_scorers", ""),
                    home_id, away_id, prefix
                ),
            }

            if stage in ("quarterfinal", "semifinal", "final", "third_place"):
                node_base = {"quarterfinal": 4, "semifinal": 2, "final": 1, "third_place": 1}
                fixture["Order"] = node_base.get(stage, 1)

            fixtures.append(fixture)

    # Split into group stage and playoffs
    group_fixtures = [f for f in fixtures if f["MatchDayName"].isdigit()]
    playoff_fixtures = [f for f in fixtures if not f["MatchDayName"].isdigit()]

    stages = []
    if group_fixtures:
        stages.append({"Name": "Group Stage", "Type": "League", "Groups": [{"Name": "Group A", "Fixtures": group_fixtures}]})
    if playoff_fixtures:
        stages.append({"Name": "Playoffs", "Type": "Playoff", "Groups": [{"Name": "Playoffs", "Fixtures": playoff_fixtures}]})

    return {
        "ImportSource": 99,
        "ImportMode": 0,
        "League": {
            "Name": league_name,
            "Country": "",
            "SportKindName": sport,
            "ImageUrl": None,
            "Champs": [{
                "Name": league_name,
                "ExternalId": f"{prefix}:comp:{slugify(league_name)}",
                "StartDate": "",
                "EndDate": "",
                "IsComplete": True,
                "SportKindName": sport,
                "LeagueName": league_name,
                "Stages": stages,
            }],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Parse tournament data for EasyChamp import")
    parser.add_argument("--platform", required=True, choices=["ps23", "csv"], help="Source platform")
    parser.add_argument("--input", required=True, help="Input file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--sport", default="Soccer", help="Sport kind name (default: Soccer)")
    parser.add_argument("--league", default="Imported League", help="League name (CSV only)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {args.input}")
        sys.exit(1)

    if args.platform == "ps23":
        with open(input_path) as f:
            data = json.load(f)
        result = parse_ps23(data, sport=args.sport)
    elif args.platform == "csv":
        result = parse_csv(args.input, sport=args.sport, league_name=args.league)
    else:
        print(f"Unknown platform: {args.platform}")
        sys.exit(1)

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Count what we generated
    champs = result.get("League", {}).get("Champs", [])
    total_fixtures = 0
    total_teams = set()
    for champ in champs:
        for stage in champ.get("Stages", []):
            for group in stage.get("Groups", []):
                fixtures = group.get("Fixtures", [])
                total_fixtures += len(fixtures)
                for fix in fixtures:
                    for tk in ("HomeTeam", "AwayTeam"):
                        team = fix.get(tk) or {}
                        tid = team.get("Id")
                        if tid:
                            total_teams.add(tid)

    print(f"Parsed {total_fixtures} fixtures, {len(total_teams)} teams")
    print(f"Output written to: {args.output}")
    print(f"\nNext step: python validate_import.py {args.output}")


if __name__ == "__main__":
    main()
