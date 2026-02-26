#!/usr/bin/env python3
"""
Pre-import validation for EasyChamp tournament data.

Validates an import JSON file against all known rules and pitfalls
before sending to the API. Catches issues that would cause silent
failures or 500 errors.

Usage:
    python validate_import.py import.json
    python validate_import.py import.json --strict
"""

import json
import sys
import re
from collections import defaultdict
from pathlib import Path


VALID_MATCHDAY_NAMES = {
    "quarterfinal", "semifinal", "final", "third_place",
    "round_of_16", "round_of_32",
}
VALID_EVENT_TYPES = {"scorer", "yellowcard", "redcard", "substitution", "owngoal", "missedpenalty"}
VALID_STAGE_TYPES = {"League", "Playoff"}
SKIP_SCORER_ENTRIES = {"walk over", "forfeit", "w/o", "wo", ""}


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, path, msg):
        self.errors.append(f"ERROR [{path}]: {msg}")

    def warn(self, path, msg):
        self.warnings.append(f"WARN  [{path}]: {msg}")

    @property
    def ok(self):
        return len(self.errors) == 0

    def summary(self):
        lines = []
        if self.errors:
            lines.append(f"\n{'='*60}")
            lines.append(f"ERRORS ({len(self.errors)}):")
            lines.append(f"{'='*60}")
            for e in self.errors:
                lines.append(f"  {e}")
        if self.warnings:
            lines.append(f"\n{'='*60}")
            lines.append(f"WARNINGS ({len(self.warnings)}):")
            lines.append(f"{'='*60}")
            for w in self.warnings:
                lines.append(f"  {w}")
        if self.ok and not self.warnings:
            lines.append("\nAll checks passed.")
        elif self.ok:
            lines.append(f"\nNo errors. {len(self.warnings)} warning(s).")
        else:
            lines.append(f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s). Fix errors before import.")
        return "\n".join(lines)


def validate_score_field(val, field_name, path, result):
    """Scores MUST be strings. Int causes 500."""
    if val is None:
        return
    if not isinstance(val, str):
        result.error(path, f"{field_name} must be string, got {type(val).__name__}: {val}")


def validate_player(player, path, result):
    """Validate player object has required fields."""
    if not player:
        result.error(path, "Player object is null/empty")
        return
    if not player.get("FullName") and not player.get("fullName"):
        result.error(path, "Player missing FullName")
    # OtherFullName is REQUIRED by API (can be empty string but must exist)
    name_key = "OtherFullName" if "OtherFullName" in player else "otherFullName"
    if name_key not in player:
        result.error(path, "Player missing OtherFullName (required, can be empty string)")
    if not player.get("SportKindName") and not player.get("sportKindName"):
        result.warn(path, "Player missing SportKindName")


def validate_fixture(fixture, path, result, all_player_ids):
    """Validate a single fixture."""
    # Score types
    validate_score_field(fixture.get("HomeTeamScore"), "HomeTeamScore", path, result)
    validate_score_field(fixture.get("AwayTeamScore"), "AwayTeamScore", path, result)
    validate_score_field(fixture.get("HomePenaltyScore"), "HomePenaltyScore", path, result)
    validate_score_field(fixture.get("AwayPenaltyScore"), "AwayPenaltyScore", path, result)

    # Status must be int enum
    status = fixture.get("Status")
    if status is not None:
        if isinstance(status, str):
            result.error(path, f"Status must be int (0/1/2), got string: '{status}'")
        elif status not in (0, 1, 2):
            result.warn(path, f"Status value {status} not in expected range (0=Scheduled, 1=InProgress, 2=Finished)")

    # MatchDay must be int
    md = fixture.get("MatchDay")
    if md is not None and not isinstance(md, int):
        result.error(path, f"MatchDay must be int, got {type(md).__name__}: {md}")

    # MatchDayName validation
    mdn = fixture.get("MatchDayName")
    if mdn is not None:
        if not isinstance(mdn, str):
            result.error(path, f"MatchDayName must be string, got {type(mdn).__name__}: {mdn}")
        elif not mdn.isdigit() and mdn not in VALID_MATCHDAY_NAMES:
            result.warn(path, f"MatchDayName '{mdn}' not in known values. Group stage should be numeric string '1', '2', etc.")
        if isinstance(mdn, str) and mdn != mdn.lower():
            result.error(path, f"MatchDayName must be lowercase: '{mdn}' -> '{mdn.lower()}'")
        if isinstance(mdn, str) and "-" in mdn:
            result.error(path, f"MatchDayName must not contain hyphens: '{mdn}' -> '{mdn.replace('-', '')}'")

    # Order field for playoffs
    order = fixture.get("Order")
    if mdn and isinstance(mdn, str) and not mdn.isdigit():
        if order is None:
            result.error(path, "Playoff fixture missing Order field (required for bracket rendering)")
        elif not isinstance(order, int):
            result.error(path, f"Order must be int, got {type(order).__name__}: {order}")

    # Penalty fields consistency
    has_pen = fixture.get("HasPenalties")
    hp_score = fixture.get("HomePenaltyScore")
    ap_score = fixture.get("AwayPenaltyScore")
    winner = fixture.get("WinnerTeamId")
    period_scores = fixture.get("PeriodScores") or []

    if hp_score or ap_score:
        if not has_pen:
            result.error(path, "Penalty scores set but HasPenalties is not true")
        if not winner:
            result.error(path, "Penalty scores set but WinnerTeamId is missing")
        pen_period = [ps for ps in period_scores if (ps.get("Type") or "").lower() == "penalties"]
        if not pen_period:
            result.error(path, "Penalty scores set but PeriodScores missing entry with Type='penalties'")

    # PeriodScores validation
    for i, ps in enumerate(period_scores):
        ps_path = f"{path}.PeriodScores[{i}]"
        ps_type = ps.get("Type")
        if ps_type and ps_type != ps_type.lower():
            result.warn(ps_path, f"Type should be lowercase: '{ps_type}' (API auto-lowercases)")
        # Check snake_case field names
        if "HomeScore" in ps or "AwayScore" in ps:
            result.error(ps_path, "Use Home_score/Away_score (snake_case), not HomeScore/AwayScore")
        hs = ps.get("Home_score")
        aws = ps.get("Away_score")
        validate_score_field(hs, "Home_score", ps_path, result)
        validate_score_field(aws, "Away_score", ps_path, result)

    # Team validation
    for team_key in ("HomeTeam", "AwayTeam"):
        team = fixture.get(team_key)
        if not team:
            result.error(path, f"{team_key} is missing or null")
            continue
        if not team.get("Id") and not team.get("id"):
            result.error(f"{path}.{team_key}", "Missing Id")
        if not team.get("Name") and not team.get("name"):
            result.error(f"{path}.{team_key}", "Missing Name")
        # Check team members
        members = team.get("TeamMembers") or []
        for j, tm in enumerate(members):
            player = tm.get("Player") or {}
            p_id = player.get("Id") or player.get("id")
            if p_id:
                team_id = team.get("Id") or team.get("id") or "unknown"
                all_player_ids[p_id].add(team_id)
            validate_player(player, f"{path}.{team_key}.TeamMembers[{j}]", result)

    # Squad validation
    for squad_key in ("HomeSquad", "AwaySquad"):
        squad = fixture.get(squad_key) or []
        for j, entry in enumerate(squad):
            player = entry.get("Player") or {}
            p_id = player.get("Id") or player.get("id")
            if p_id:
                team_key_for_squad = "HomeTeam" if squad_key == "HomeSquad" else "AwayTeam"
                team = fixture.get(team_key_for_squad) or {}
                team_id = team.get("Id") or team.get("id") or "unknown"
                all_player_ids[p_id].add(team_id)
            validate_player(player, f"{path}.{squad_key}[{j}]", result)

    # Events validation
    events = fixture.get("Events") or []
    event_player_ids = set()
    for j, event in enumerate(events):
        ev_path = f"{path}.Events[{j}]"
        ev_type = event.get("EventType") or event.get("eventType")
        if ev_type and ev_type not in VALID_EVENT_TYPES:
            result.error(ev_path, f"EventType '{ev_type}' not valid. Use 'scorer' not 'goal'")
        minute = event.get("Minute") or event.get("minute")
        if minute is not None:
            validate_score_field(minute, "Minute", ev_path, result)
        player = event.get("Player") or event.get("player") or {}
        p_id = player.get("Id") or player.get("id")
        if p_id:
            event_player_ids.add(p_id)
            is_home = event.get("IsHomeEvent") or event.get("isHomeEvent")
            team_key_for_event = "HomeTeam" if is_home else "AwayTeam"
            team = fixture.get(team_key_for_event) or {}
            team_id = team.get("Id") or team.get("id") or "unknown"
            all_player_ids[p_id].add(team_id)
        validate_player(player, f"{ev_path}.Player", result)
        # Check scorer names against skip list
        full_name = (player.get("FullName") or player.get("fullName") or "").strip().lower()
        if full_name in SKIP_SCORER_ENTRIES:
            result.error(ev_path, f"Player name '{full_name}' looks like a forfeit marker, not a real player")

    # Cross-check: event players should be in squads
    home_squad = fixture.get("HomeSquad") or []
    away_squad = fixture.get("AwaySquad") or []
    squad_player_ids = set()
    for entry in home_squad + away_squad:
        p = entry.get("Player") or {}
        pid = p.get("Id") or p.get("id")
        if pid:
            squad_player_ids.add(pid)
    for pid in event_player_ids:
        if pid not in squad_player_ids and (home_squad or away_squad):
            result.warn(path, f"Event player {pid} not found in any squad")

    # Date validation
    date = fixture.get("Date")
    if date:
        if "T" in str(date):
            result.warn(path, f"Date contains time component: '{date}'. Use date-only format 'YYYY-MM-DD'")
        if not re.match(r"^\d{4}-\d{2}-\d{2}", str(date)):
            result.error(path, f"Date format invalid: '{date}'. Expected 'YYYY-MM-DD'")


def validate_league_import(data, result):
    """Validate a full league import payload (POST /import/league)."""
    league = data.get("League") or data.get("league")
    if not league:
        result.error("root", "Missing 'League' object")
        return

    if not league.get("Name"):
        result.error("League", "Missing Name")
    if not league.get("SportKindName"):
        result.warn("League", "Missing SportKindName")

    champs = league.get("Champs") or []
    if not champs:
        result.error("League", "No Champs (tournaments) defined")

    all_player_ids = defaultdict(set)  # player_id -> set of team_ids
    fixture_ids = set()
    team_ids_seen = set()

    for ci, champ in enumerate(champs):
        c_path = f"League.Champs[{ci}]"
        if not champ.get("Name"):
            result.error(c_path, "Missing Name")
        if not champ.get("StartDate"):
            result.warn(c_path, "Missing StartDate")

        stages = champ.get("Stages") or []
        if not stages:
            result.error(c_path, "No Stages defined")

        for si, stage in enumerate(stages):
            s_path = f"{c_path}.Stages[{si}]"
            stage_type = stage.get("Type")
            if stage_type and stage_type not in VALID_STAGE_TYPES:
                result.warn(s_path, f"Stage Type '{stage_type}' not in known values: {VALID_STAGE_TYPES}")

            groups = stage.get("Groups") or []
            if not groups:
                result.error(s_path, "No Groups defined")

            for gi, group in enumerate(groups):
                g_path = f"{s_path}.Groups[{gi}]"
                fixtures = group.get("Fixtures") or []
                if not fixtures:
                    result.warn(g_path, "No Fixtures in group")

                for fi, fixture in enumerate(fixtures):
                    f_path = f"{g_path}.Fixtures[{fi}]"
                    f_id = fixture.get("Id") or fixture.get("id")
                    if f_id:
                        if f_id in fixture_ids:
                            result.error(f_path, f"Duplicate fixture Id: '{f_id}'")
                        fixture_ids.add(f_id)

                    # Track teams
                    for tk in ("HomeTeam", "AwayTeam"):
                        team = fixture.get(tk) or {}
                        tid = team.get("Id") or team.get("id")
                        if tid:
                            team_ids_seen.add(tid)

                    validate_fixture(fixture, f_path, result, all_player_ids)

    # Check for players appearing on multiple teams with same ID
    for pid, teams in all_player_ids.items():
        if len(teams) > 1:
            result.error("cross-check",
                         f"Player ID '{pid}' appears on {len(teams)} teams: {teams}. "
                         "Use unique IDs per team (e.g., append team name).")


def validate_fixture_import(data, result):
    """Validate a fixture array import payload (POST /import/fixtures)."""
    if not isinstance(data, list):
        result.error("root", f"Expected array of fixtures, got {type(data).__name__}")
        return

    all_player_ids = defaultdict(set)
    fixture_ids = set()

    for fi, fixture in enumerate(data):
        f_path = f"fixtures[{fi}]"
        f_id = fixture.get("Id") or fixture.get("id")
        if f_id:
            if f_id in fixture_ids:
                result.error(f_path, f"Duplicate fixture Id: '{f_id}'")
            fixture_ids.add(f_id)
        validate_fixture(fixture, f_path, result, all_player_ids)

    for pid, teams in all_player_ids.items():
        if len(teams) > 1:
            result.error("cross-check",
                         f"Player ID '{pid}' on {len(teams)} teams: {teams}. Use unique IDs per team.")


def validate_file(filepath, strict=False):
    """Load and validate a JSON import file."""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    result = ValidationResult()

    # Detect format
    if isinstance(data, list):
        print(f"Detected: Fixture array import ({len(data)} fixtures)")
        validate_fixture_import(data, result)
    elif "League" in data or "league" in data:
        print("Detected: Full league import (POST /import/league)")
        validate_league_import(data, result)
    elif "Fixtures" in data or "fixtures" in data:
        fixtures = data.get("Fixtures") or data.get("fixtures") or []
        print(f"Detected: Fixture object import ({len(fixtures)} fixtures)")
        validate_fixture_import(fixtures, result)
    else:
        result.error("root", "Unknown import format. Expected league import or fixture array.")

    print(result.summary())

    if strict and not result.ok:
        sys.exit(1)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_import.py <import.json> [--strict]")
        sys.exit(1)

    filepath = sys.argv[1]
    strict = "--strict" in sys.argv
    validate_file(filepath, strict=strict)
