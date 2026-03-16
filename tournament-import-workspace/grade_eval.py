#!/usr/bin/env python3
"""
Programmatic grader for tournament-import evals.
Checks assertions against output JSON files.
"""

import json
import sys
import os
import re
from pathlib import Path


def find_json_outputs(outputs_dir):
    """Find all JSON output files in the outputs directory."""
    results = {}
    for f in Path(outputs_dir).rglob("*.json"):
        if f.name == "metrics.json":
            continue
        results[f.name] = f
    return results


def load_json_safe(path):
    """Load JSON, return None on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def collect_all_values(obj, key):
    """Recursively collect all values for a given key in nested dicts/lists."""
    values = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                values.append(v)
            values.extend(collect_all_values(v, key))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(collect_all_values(item, key))
    return values


def collect_all_objects(obj, key):
    """Recursively collect all objects that have a given key."""
    results = []
    if isinstance(obj, dict):
        if key in obj:
            results.append(obj)
        for v in obj.values():
            results.extend(collect_all_objects(v, key))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(collect_all_objects(item, key))
    return results


def grade_eval1(data):
    """Grade PS23 parse with penalties eval."""
    results = []

    # 1. All HomeTeamScore and AwayTeamScore are strings
    home_scores = collect_all_values(data, "HomeTeamScore")
    away_scores = collect_all_values(data, "AwayTeamScore")
    all_scores = home_scores + away_scores
    all_strings = all(isinstance(s, str) for s in all_scores) if all_scores else False
    results.append({
        "text": "All HomeTeamScore and AwayTeamScore values are strings",
        "passed": all_strings,
        "evidence": f"Found {len(all_scores)} score values. Types: {set(type(s).__name__ for s in all_scores)}" if all_scores else "No score fields found"
    })

    # 2. HomePenaltyScore and AwayPenaltyScore are strings
    hp = collect_all_values(data, "HomePenaltyScore")
    ap = collect_all_values(data, "AwayPenaltyScore")
    pen_scores = hp + ap
    pen_strings = all(isinstance(s, str) for s in pen_scores) if pen_scores else False
    results.append({
        "text": "HomePenaltyScore and AwayPenaltyScore are strings",
        "passed": pen_strings,
        "evidence": f"Found {len(pen_scores)} penalty scores. Types: {set(type(s).__name__ for s in pen_scores)}" if pen_scores else "No penalty score fields found"
    })

    # 3. PeriodScores uses Home_score/Away_score (snake_case)
    period_scores = collect_all_values(data, "PeriodScores")
    has_snake = False
    has_camel = False
    for ps_list in period_scores:
        if isinstance(ps_list, list):
            for ps in ps_list:
                if isinstance(ps, dict):
                    if "Home_score" in ps or "Away_score" in ps:
                        has_snake = True
                    if "HomeScore" in ps or "AwayScore" in ps:
                        has_camel = True
    results.append({
        "text": "PeriodScores uses Home_score and Away_score (snake_case)",
        "passed": has_snake and not has_camel,
        "evidence": f"snake_case found: {has_snake}, camelCase found: {has_camel}"
    })

    # 4. PeriodScores Type is lowercase 'penalties'
    ps_types = []
    for ps_list in period_scores:
        if isinstance(ps_list, list):
            for ps in ps_list:
                if isinstance(ps, dict) and "Type" in ps:
                    ps_types.append(ps["Type"])
    type_ok = any(t == "penalties" for t in ps_types) if ps_types else False
    results.append({
        "text": "PeriodScores Type is lowercase 'penalties'",
        "passed": type_ok,
        "evidence": f"PeriodScore Type values: {ps_types}" if ps_types else "No PeriodScores Type found"
    })

    # 5. EventType is 'scorer' not 'goal'
    event_types = collect_all_values(data, "EventType")
    has_scorer = any(t == "scorer" for t in event_types)
    has_goal = any(t == "goal" for t in event_types)
    results.append({
        "text": "EventType is 'scorer' for goals, not 'goal'",
        "passed": has_scorer and not has_goal,
        "evidence": f"Event types found: {set(event_types)}" if event_types else "No EventType fields found"
    })

    # 6. Every Player has OtherFullName
    players = collect_all_objects(data, "FullName")
    players_with_ofn = [p for p in players if "OtherFullName" in p]
    results.append({
        "text": "Every Player object has an OtherFullName field",
        "passed": len(players) > 0 and len(players_with_ofn) == len(players),
        "evidence": f"{len(players_with_ofn)}/{len(players)} players have OtherFullName"
    })

    # 7. Champs inside League
    league = data.get("League", {})
    champs_in_league = "Champs" in league if isinstance(league, dict) else False
    champs_at_root = "Champs" in data
    results.append({
        "text": "Champs array is nested inside League object",
        "passed": champs_in_league and not champs_at_root,
        "evidence": f"Champs in League: {champs_in_league}, Champs at root: {champs_at_root}"
    })

    # 8. R. Gutierrez x2 creates 2 events
    events = collect_all_values(data, "Events")
    gutierrez_events = 0
    for evt_list in events:
        if isinstance(evt_list, list):
            for evt in evt_list:
                if isinstance(evt, dict):
                    player = evt.get("Player", {})
                    if isinstance(player, dict) and "Gutierrez" in player.get("FullName", ""):
                        gutierrez_events += 1
    # In week 1: R. Gutierrez x2 = 2 events. Total across all matches: should be more
    # Week 1: x2, Week 2: 1, Week 3: x2 = 5 total for R. Gutierrez, plus semifinals 1, final 1 = 7
    # Just check that at least 2 exist for the x2 pattern
    results.append({
        "text": "The 'R. Gutierrez x2' scorer creates exactly 2 separate goal events",
        "passed": gutierrez_events >= 2,
        "evidence": f"Found {gutierrez_events} R. Gutierrez goal events total across all fixtures"
    })

    # 9. Both stages exist
    stages = []
    champs = league.get("Champs", []) if isinstance(league, dict) else []
    for champ in champs:
        if isinstance(champ, dict):
            for stage in champ.get("Stages", []):
                if isinstance(stage, dict):
                    stages.append(stage.get("Type", ""))
    has_league_stage = "League" in stages
    has_playoff_stage = "Playoff" in stages
    results.append({
        "text": "Output contains both Group Stage (Type: League) and Playoffs (Type: Playoff)",
        "passed": has_league_stage and has_playoff_stage,
        "evidence": f"Stage types found: {stages}"
    })

    # 10. All scorers in squad
    fixtures = collect_all_objects(data, "HomeSquad")
    scorers_in_squad = True
    missing = []
    for fix in fixtures:
        home_squad_ids = set()
        for sq in fix.get("HomeSquad", []):
            p = sq.get("Player", {})
            if isinstance(p, dict):
                home_squad_ids.add(p.get("Id", ""))
        away_squad_ids = set()
        for sq in fix.get("AwaySquad", []):
            p = sq.get("Player", {})
            if isinstance(p, dict):
                away_squad_ids.add(p.get("Id", ""))
        for evt in fix.get("Events", []):
            if isinstance(evt, dict):
                player = evt.get("Player", {})
                pid = player.get("Id", "") if isinstance(player, dict) else ""
                is_home = evt.get("IsHomeEvent", True)
                if is_home and pid and pid not in home_squad_ids and home_squad_ids:
                    scorers_in_squad = False
                    missing.append(f"Home scorer {pid} not in HomeSquad")
                elif not is_home and pid and pid not in away_squad_ids and away_squad_ids:
                    scorers_in_squad = False
                    missing.append(f"Away scorer {pid} not in AwaySquad")
    results.append({
        "text": "All scorers appear in their team's squad",
        "passed": scorers_in_squad,
        "evidence": f"No missing scorers in squads" if scorers_in_squad else f"Missing: {missing[:5]}"
    })

    return results


def grade_eval2(data):
    """Grade knockout bracket eval."""
    results = []

    league = data.get("League", {})
    champs = league.get("Champs", []) if isinstance(league, dict) else []

    # Collect all fixtures
    all_fixtures = []
    for champ in champs:
        if isinstance(champ, dict):
            for stage in champ.get("Stages", []):
                if isinstance(stage, dict):
                    for group in stage.get("Groups", []):
                        if isinstance(group, dict):
                            all_fixtures.extend(group.get("Fixtures", []))

    # Categorize by matchDayName
    qf = [f for f in all_fixtures if isinstance(f, dict) and f.get("MatchDayName") == "quarterfinal"]
    sf = [f for f in all_fixtures if isinstance(f, dict) and f.get("MatchDayName") == "semifinal"]
    final = [f for f in all_fixtures if isinstance(f, dict) and f.get("MatchDayName") == "final"]
    third = [f for f in all_fixtures if isinstance(f, dict) and f.get("MatchDayName") == "3rd_place_playoff"]

    # 1. QF Order values 4-7
    qf_orders = sorted([f.get("Order") for f in qf if f.get("Order") is not None])
    results.append({
        "text": "Quarterfinal fixtures have Order values from 4-7",
        "passed": set(qf_orders) == {4, 5, 6, 7} if qf_orders else False,
        "evidence": f"QF Order values: {qf_orders}"
    })

    # 2. SF Order values 2-3
    sf_orders = sorted([f.get("Order") for f in sf if f.get("Order") is not None])
    results.append({
        "text": "Semifinal fixtures have Order values 2 and 3",
        "passed": set(sf_orders) == {2, 3} if sf_orders else False,
        "evidence": f"SF Order values: {sf_orders}"
    })

    # 3. Final Order = 1
    final_orders = [f.get("Order") for f in final if f.get("Order") is not None]
    results.append({
        "text": "Final fixture has Order value 1",
        "passed": 1 in final_orders if final_orders else False,
        "evidence": f"Final Order values: {final_orders}"
    })

    # 4. All matchDayName lowercase without hyphens
    all_mdns = [f.get("MatchDayName", "") for f in all_fixtures if isinstance(f, dict)]
    valid_mdns = {"quarterfinal", "semifinal", "final", "3rd_place_playoff"}
    all_valid = all(m in valid_mdns for m in all_mdns) if all_mdns else False
    results.append({
        "text": "All matchDayName values are lowercase without hyphens",
        "passed": all_valid,
        "evidence": f"matchDayName values: {set(all_mdns)}"
    })

    # 5. 3rd place playoff exists
    results.append({
        "text": "A 3rd place playoff fixture exists",
        "passed": len(third) >= 1,
        "evidence": f"Found {len(third)} 3rd place playoff fixture(s)"
    })

    # 6. Champs inside League
    champs_in_league = "Champs" in league if isinstance(league, dict) else False
    champs_at_root = "Champs" in data
    results.append({
        "text": "Champs array is nested inside League object",
        "passed": champs_in_league and not champs_at_root,
        "evidence": f"Champs in League: {champs_in_league}, Champs at root: {champs_at_root}"
    })

    # 7. All scores are strings
    home_scores = collect_all_values(data, "HomeTeamScore")
    away_scores = collect_all_values(data, "AwayTeamScore")
    all_scores = home_scores + away_scores
    all_strings = all(isinstance(s, str) for s in all_scores) if all_scores else False
    results.append({
        "text": "All scores are strings ('0' not 0)",
        "passed": all_strings,
        "evidence": f"Score types: {set(type(s).__name__ for s in all_scores)}" if all_scores else "No scores found"
    })

    # 8. Exactly 8 fixtures (4 QF + 2 SF + 1 F + 1 3rd)
    total = len(qf) + len(sf) + len(final) + len(third)
    results.append({
        "text": "Exactly 8 total playoff fixtures (4+2+1+1)",
        "passed": len(qf) == 4 and len(sf) == 2 and len(final) == 1 and len(third) == 1,
        "evidence": f"QF: {len(qf)}, SF: {len(sf)}, Final: {len(final)}, 3rd: {len(third)} = {total} total"
    })

    # 9. HomeTeam/AwayTeam are objects
    teams_ok = True
    for f in all_fixtures:
        if isinstance(f, dict):
            ht = f.get("HomeTeam")
            at = f.get("AwayTeam")
            if not isinstance(ht, dict) or not isinstance(at, dict):
                teams_ok = False
                break
            if "Id" not in ht or "Name" not in ht:
                teams_ok = False
                break
    results.append({
        "text": "HomeTeam and AwayTeam are objects with Id and Name",
        "passed": teams_ok and len(all_fixtures) > 0,
        "evidence": f"Checked {len(all_fixtures)} fixtures" if teams_ok else "Found non-object or missing Id/Name in teams"
    })

    return results


def grade_eval3(data, diagnosis_text=""):
    """Grade diagnose-fix broken import eval."""
    results = []

    # Check diagnosis identification (from diagnosis.md or from the fixed JSON)
    diag = diagnosis_text.lower() if diagnosis_text else ""

    # 1. Identifies numeric scores
    results.append({
        "text": "Identifies that scores are numbers and must be strings",
        "passed": ("string" in diag and ("score" in diag or "number" in diag or "integer" in diag)) or "HomeTeamScore" in diag,
        "evidence": "Diagnosis mentions score type issue" if "string" in diag else "Score type issue not mentioned in diagnosis"
    })

    # 2. Identifies Quarter-Final -> quarterfinal
    results.append({
        "text": "Identifies 'Quarter-Final' must be 'quarterfinal'",
        "passed": "quarter" in diag and ("lowercase" in diag or "hyphen" in diag or "quarterfinal" in diag),
        "evidence": "Quarter-Final format issue mentioned" if "quarter" in diag else "Not mentioned"
    })

    # 3. Identifies Semi-Final -> semifinal
    results.append({
        "text": "Identifies 'Semi-Final' must be 'semifinal'",
        "passed": "semi" in diag and ("lowercase" in diag or "hyphen" in diag or "semifinal" in diag),
        "evidence": "Semi-Final format issue mentioned" if "semi" in diag else "Not mentioned"
    })

    # 4. Identifies PeriodScores casing
    results.append({
        "text": "Identifies PeriodScores must use Home_score/Away_score",
        "passed": ("home_score" in diag or "snake" in diag or "snake_case" in diag) and "period" in diag,
        "evidence": "PeriodScores casing issue mentioned" if "home_score" in diag or "snake" in diag else "Not mentioned"
    })

    # 5. Identifies PeriodScores Type casing
    results.append({
        "text": "Identifies PeriodScores Type must be lowercase 'penalties'",
        "passed": "penalties" in diag and ("lowercase" in diag or "type" in diag or "Penalties" in diag),
        "evidence": "PeriodScores Type casing mentioned" if "penalties" in diag else "Not mentioned"
    })

    # 6. Identifies EventType
    results.append({
        "text": "Identifies EventType 'goal' must be 'scorer'",
        "passed": "scorer" in diag and ("goal" in diag or "event" in diag),
        "evidence": "EventType issue mentioned" if "scorer" in diag else "Not mentioned"
    })

    # 7. Identifies Champs at root
    results.append({
        "text": "Identifies Champs at root must be inside League",
        "passed": "champs" in diag and ("league" in diag or "root" in diag or "inside" in diag or "nested" in diag),
        "evidence": "Champs location issue mentioned" if "champs" in diag else "Not mentioned"
    })

    # 8. Identifies missing OtherFullName
    results.append({
        "text": "Identifies missing OtherFullName on Players",
        "passed": "otherfullname" in diag or "other_full_name" in diag or "OtherFullName" in diagnosis_text,
        "evidence": "OtherFullName issue mentioned" if "otherfullname" in diag else "Not mentioned"
    })

    # 9. Identifies penalty score types
    results.append({
        "text": "Identifies penalty scores must be strings",
        "passed": "penalty" in diag and ("string" in diag or "type" in diag),
        "evidence": "Penalty score type mentioned" if "penalty" in diag else "Not mentioned"
    })

    # 10. Fixed output has all corrections
    if data:
        scores = collect_all_values(data, "HomeTeamScore") + collect_all_values(data, "AwayTeamScore")
        scores_ok = all(isinstance(s, str) for s in scores) if scores else False

        mdns = collect_all_values(data, "MatchDayName")
        valid_mdns = {"1", "2", "3", "quarterfinal", "semifinal", "final", "3rd_place_playoff"}
        mdns_ok = all(m in valid_mdns or m.isdigit() for m in mdns) if mdns else False

        league = data.get("League", {})
        champs_ok = "Champs" in league if isinstance(league, dict) else False

        events = collect_all_values(data, "EventType")
        events_ok = all(e == "scorer" for e in events) if events else True

        all_fixed = scores_ok and mdns_ok and champs_ok and events_ok
        results.append({
            "text": "The fixed output file has all issues corrected",
            "passed": all_fixed,
            "evidence": f"scores_strings={scores_ok}, mdns_valid={mdns_ok}, champs_in_league={champs_ok}, events_scorer={events_ok}"
        })
    else:
        results.append({
            "text": "The fixed output file has all issues corrected",
            "passed": False,
            "evidence": "No fixed output JSON found"
        })

    return results


def grade_run(eval_id, outputs_dir):
    """Grade a single run."""
    json_files = find_json_outputs(outputs_dir)

    if eval_id in (1, 2):
        # Find the main output JSON (not metrics, not diagnosis)
        main_json = None
        for name, path in json_files.items():
            if "import" in name.lower() or "output" in name.lower() or "copa" in name.lower() or "bracket" in name.lower():
                main_json = load_json_safe(path)
                break
        if main_json is None and json_files:
            # Try first non-metrics JSON
            for name, path in json_files.items():
                if name != "metrics.json":
                    main_json = load_json_safe(path)
                    if main_json and ("League" in main_json or "ImportSource" in main_json):
                        break
                    main_json = None

        if main_json is None:
            return [{"text": f"Output JSON exists", "passed": False, "evidence": f"No valid import JSON found in {outputs_dir}. Files: {list(json_files.keys())}"}]

        if eval_id == 1:
            return grade_eval1(main_json)
        else:
            return grade_eval2(main_json)

    elif eval_id == 3:
        # Find fixed JSON and diagnosis
        fixed_json = None
        diagnosis_text = ""

        for name, path in json_files.items():
            if "fix" in name.lower():
                fixed_json = load_json_safe(path)

        # Check for diagnosis.md
        for f in Path(outputs_dir).rglob("*.md"):
            if "diagnos" in f.name.lower():
                diagnosis_text = f.read_text()

        # Also check for any text file with diagnosis
        if not diagnosis_text:
            for f in Path(outputs_dir).rglob("*.txt"):
                if "diagnos" in f.name.lower():
                    diagnosis_text = f.read_text()

        # If no separate diagnosis file, check if there's a text output
        if not diagnosis_text and fixed_json is None:
            # Try any JSON
            for name, path in json_files.items():
                if name != "metrics.json":
                    fixed_json = load_json_safe(path)
                    if fixed_json:
                        break

        return grade_eval3(fixed_json, diagnosis_text)


def main():
    if len(sys.argv) < 4:
        print("Usage: grade_eval.py <eval_id> <outputs_dir> <output_file>")
        sys.exit(1)

    eval_id = int(sys.argv[1])
    outputs_dir = sys.argv[2]
    output_file = sys.argv[3]

    results = grade_run(eval_id, outputs_dir)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    grading = {
        "expectations": results,
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": round(passed / total, 2) if total > 0 else 0
        }
    }

    with open(output_file, "w") as f:
        json.dump(grading, f, indent=2)

    print(f"Graded eval {eval_id}: {passed}/{total} passed ({grading['summary']['pass_rate']:.0%})")


if __name__ == "__main__":
    main()
