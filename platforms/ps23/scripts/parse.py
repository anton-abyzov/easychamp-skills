#!/usr/bin/env python3
"""
PS23 Soccer tournament parser for EasyChamp imports.

Transforms PS23 Soccer JSON exports into EasyChamp's POST /import/league format.

Usage:
    python parse.py --input data.json --output import.json
    python parse.py --input data.json --output import.json --sport Soccer

PS23 Soccer JSON format:
    See platforms/ps23/knowledge/platform-guide.md for expected structure.
"""

import json
import re
import hashlib
import sys
import argparse
from pathlib import Path
from collections import defaultdict

PREFIX = "ps23"


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
        int(h)
        int(a)
        return h, a
    except ValueError:
        return None, None


def parse_penalty_score(score_str):
    """Parse penalty score like '(2-3)' or 'pen 2-3'."""
    if not score_str:
        return None, None
    m = re.search(r"(?:pen|penalties?|pk)[\s:]*(\d+)\s*[-\u2013]\s*(\d+)", score_str, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"\((\d+)\s*[-\u2013]\s*(\d+)\)", score_str)
    if m:
        return m.group(1), m.group(2)
    return None, None


def parse_scorers(scorers_str):
    """
    Parse PS23 scorer string into list of (player_name, goal_count).

    PS23 formats:
      - Semicolon: "K. Moosa; L. Peralta"
      - Comma: "K. Moosa, L. Peralta"
      - Prefix multiplier: "5x K. Moosa"
      - Suffix multiplier: "K. Moosa x5"
      - Skip: "walk over", "forfeit", "", "w/o"
    """
    if not scorers_str:
        return []

    skip = {"walk over", "forfeit", "w/o", "wo", ""}
    results = []

    parts = re.split(r"[;]", scorers_str)
    if len(parts) == 1:
        parts = re.split(r",", scorers_str)

    for part in parts:
        part = part.strip()
        if not part or part.lower() in skip:
            continue

        m = re.match(r"(\d+)\s*x\s+(.+)", part, re.IGNORECASE)
        if m:
            count = int(m.group(1))
            name = m.group(2).strip()
        else:
            m = re.match(r"(.+?)\s+x\s*(\d+)", part, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                count = int(m.group(2))
            else:
                name = part
                count = 1

        if name.lower() in skip:
            continue

        results.append((name, count))

    return results


def make_player(name, sport="Soccer"):
    """Create player object with all required EasyChamp fields."""
    pid = f"{PREFIX}:player:{md5_short(name)}"
    return {
        "FullName": name,
        "Id": pid,
        "OtherFullName": "",
        "SportKindName": sport,
    }


def make_team(name, logo_url=None, sport="Soccer", members=None):
    """Create team object."""
    tid = f"{PREFIX}:team:{md5_short(name)}"
    team = {
        "Id": tid,
        "Name": name,
        "ImageUrl": logo_url,
        "SportKindName": sport,
    }
    if members:
        team["TeamMembers"] = [{"Player": make_player(m["name"], sport)} for m in members]
    else:
        team["TeamMembers"] = []
    return team


def make_events(home_scorers_str, away_scorers_str, sport="Soccer"):
    """Create events list from PS23 scorer strings."""
    events = []
    for name, count in parse_scorers(home_scorers_str):
        for _ in range(count):
            events.append({
                "IsHomeEvent": True,
                "Minute": "",
                "EventType": "scorer",
                "Player": make_player(name, sport),
                "Description": f"Goal by {name}",
            })
    for name, count in parse_scorers(away_scorers_str):
        for _ in range(count):
            events.append({
                "IsHomeEvent": False,
                "Minute": "",
                "EventType": "scorer",
                "Player": make_player(name, sport),
                "Description": f"Goal by {name}",
            })
    return events


def build_squad(scorers_str, roster=None, sport="Soccer"):
    """Build squad list from roster + scorers."""
    squad = []
    seen = set()

    if roster:
        for player in roster:
            pid = f"{PREFIX}:player:{md5_short(player['name'])}"
            if pid not in seen:
                seen.add(pid)
                squad.append({
                    "Player": make_player(player["name"], sport),
                    "SquadType": 0,
                    "IsPlayed": player.get("played", True),
                })

    for name, _ in parse_scorers(scorers_str):
        pid = f"{PREFIX}:player:{md5_short(name)}"
        if pid not in seen:
            seen.add(pid)
            squad.append({
                "Player": make_player(name, sport),
                "SquadType": 0,
                "IsPlayed": True,
            })

    return squad


def parse_ps23(data, sport="Soccer"):
    """Parse PS23 Soccer JSON export into EasyChamp import format."""
    comp = data.get("competition", {})
    league_name = comp.get("league_name") or comp.get("name", "Unknown League")
    comp_name = comp.get("name", league_name)
    country = comp.get("country", "")
    start_date = comp.get("start_date", "")
    end_date = comp.get("end_date", "")

    # Build team registry
    teams = {}
    all_games = data.get("all_games", [])
    player_stats = data.get("all_player_stats", [])

    # Collect rosters from player stats
    team_rosters = defaultdict(list)
    for ps in player_stats:
        team_name = ps.get("team", "")
        player_name = ps.get("player", "")
        if team_name and player_name:
            team_rosters[team_name].append({"name": player_name, "played": True})

    # Build team info from games
    for game in all_games:
        for side in ("home", "away"):
            name = game.get(side, "")
            if name and name not in teams:
                logo = game.get(f"{side}_logo") or game.get(f"{side}_image")
                if not logo and game.get(f"{side}_id"):
                    logo = f"https://ps23soccer.com/webfiles/ps23/escudos/{game[f'{side}_id']}.png"
                teams[name] = {"logo": logo, "members": team_rosters.get(name, [])}

    # Group stage fixtures
    group_fixtures = []
    for game in all_games:
        home_name = game.get("home", "")
        away_name = game.get("away", "")
        if not home_name or not away_name:
            continue

        home_info = teams.get(home_name, {"logo": None, "members": []})
        away_info = teams.get(away_name, {"logo": None, "members": []})

        score = game.get("score", "")
        h_score, a_score = parse_score(score)
        week = game.get("week") or game.get("matchday") or game.get("round") or 1
        date = game.get("date", start_date)

        fixture_id = f"{PREFIX}:fixture:{slugify(home_name)}-vs-{slugify(away_name)}-{week}"
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
            "HomeTeam": make_team(home_name, home_info["logo"], sport),
            "AwayTeam": make_team(away_name, away_info["logo"], sport),
            "HomeSquad": build_squad(home_scorers, home_info["members"], sport),
            "AwaySquad": build_squad(away_scorers, away_info["members"], sport),
            "Events": make_events(home_scorers, away_scorers, sport),
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

            home_info = teams.get(home_name, {"logo": None, "members": []})
            away_info = teams.get(away_name, {"logo": None, "members": []})

            score = game.get("score", "")
            h_score, a_score = parse_score(score)
            date = game.get("date", end_date)
            fixture_id = f"{PREFIX}:fixture:{slugify(home_name)}-vs-{slugify(away_name)}-{mdn}{gi+1}"
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
                "HomeTeam": make_team(home_name, home_info["logo"], sport),
                "AwayTeam": make_team(away_name, away_info["logo"], sport),
                "HomeSquad": [],
                "AwaySquad": [],
                "Events": make_events(
                    game.get("home_scorers", ""),
                    game.get("away_scorers", ""),
                    sport
                ),
            }

            pen_score = game.get("penalty_score") or game.get("penalties")
            hp, ap = parse_penalty_score(str(pen_score)) if pen_score else (None, None)
            if hp and ap:
                home_tid = f"{PREFIX}:team:{md5_short(home_name)}"
                away_tid = f"{PREFIX}:team:{md5_short(away_name)}"
                fixture["HomePenaltyScore"] = hp
                fixture["AwayPenaltyScore"] = ap
                fixture["HasPenalties"] = True
                fixture["HasOvertime"] = False
                fixture["PeriodScores"] = [{"Home_score": hp, "Away_score": ap, "Type": "penalties"}]
                fixture["WinnerTeamId"] = home_tid if int(hp) > int(ap) else away_tid

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
                "ExternalId": f"{PREFIX}:comp:{slugify(comp_name)}",
                "StartDate": start_date,
                "EndDate": end_date,
                "IsComplete": is_complete,
                "SportKindName": sport,
                "LeagueName": league_name,
                "Stages": stages,
            }],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Parse PS23 Soccer tournament data for EasyChamp import")
    parser.add_argument("--input", required=True, help="Input JSON file from PS23 export")
    parser.add_argument("--output", required=True, help="Output JSON file (EasyChamp import format)")
    parser.add_argument("--sport", default="Soccer", help="Sport kind name (default: Soccer)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {args.input}")
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    result = parse_ps23(data, sport=args.sport)

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Summary
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
                        tid = (fix.get(tk) or {}).get("Id")
                        if tid:
                            total_teams.add(tid)

    print(f"Parsed {total_fixtures} fixtures, {len(total_teams)} teams")
    print(f"Output: {args.output}")
    print(f"\nNext: python ../../core/scripts/validate_import.py {args.output}")


if __name__ == "__main__":
    main()
