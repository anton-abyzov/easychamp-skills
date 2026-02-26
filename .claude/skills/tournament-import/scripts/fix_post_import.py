#!/usr/bin/env python3
"""
Post-import fixes for EasyChamp tournaments.

Applies common fixes that the import API doesn't handle correctly:
- Bracket order values (API silently ignores Order field)
- Team logos across all 3 user-facing collections
- Penalty score data types
- Standings recalculation

Usage:
    python fix_post_import.py fix-brackets --champ-id <id>
    python fix_post_import.py fix-logos --champ-id <id>
    python fix_post_import.py fix-penalties --fixture-id <id>
    python fix_post_import.py recalculate --champ-id <id>
    python fix_post_import.py verify --champ-id <id>

Requires:
    MONGODB_URI environment variable
    API_BASE_URL environment variable (default: https://api.easychamp.com)
    API_TOKEN environment variable (for API calls)
"""

import os
import sys
import json
import argparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def get_db():
    """Connect to MongoDB. NEVER falls back to hardcoded credentials."""
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        print("ERROR: MONGODB_URI environment variable is required.")
        print("Set it with: export MONGODB_URI='mongodb://...'")
        sys.exit(1)

    # Production safety guard
    prod_hosts = ["easychamp", "production", "prod"]
    for host in prod_hosts:
        if host in uri.lower() and "ALLOW_PRODUCTION" not in os.environ:
            print(f"ERROR: Production MongoDB detected ('{host}' in URI).")
            print("Set ALLOW_PRODUCTION=1 to confirm you want to modify production data.")
            sys.exit(1)

    try:
        from pymongo import MongoClient
    except ImportError:
        print("ERROR: pymongo is required. Install with: pip install pymongo")
        sys.exit(1)

    client = MongoClient(uri)
    return client["ec-standings-db"]


def api_call(method, path, data=None):
    """Make API call to EasyChamp standings API."""
    base_url = os.environ.get("API_BASE_URL", "https://api.easychamp.com")
    token = os.environ.get("API_TOKEN", "")
    url = f"{base_url}{path}"

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode()) if resp.read() else None
    except HTTPError as e:
        print(f"API Error: {e.code} {e.reason}")
        try:
            print(f"Response: {e.read().decode()}")
        except Exception:
            pass
        return None


def fix_brackets(champ_id):
    """
    Fix playoff bracket order values in MongoDB.

    The PUT /fixture/{id}/score endpoint silently ignores the Order field.
    This fixes Order and MatchDayName directly in MongoDB.
    """
    db = get_db()
    from bson import ObjectId

    # Get all fixtures for this champ
    fixtures = list(db.fixtures.find({"champRef._id": ObjectId(champ_id)}))
    print(f"Found {len(fixtures)} fixtures for champ {champ_id}")

    playoff_fixtures = [f for f in fixtures if not (f.get("matchDayName") or "").isdigit()]
    print(f"  {len(playoff_fixtures)} playoff fixtures")

    if not playoff_fixtures:
        print("No playoff fixtures found. Nothing to fix.")
        return

    # Check which need fixing
    needs_fix = []
    for f in playoff_fixtures:
        issues = []
        mdn = f.get("matchDayName", "")
        order = f.get("order") or f.get("Order")

        if mdn != mdn.lower():
            issues.append(f"matchDayName '{mdn}' -> '{mdn.lower()}'")
        if "-" in mdn:
            issues.append(f"matchDayName contains hyphens: '{mdn}'")
        if order is None:
            issues.append("Order is null (bracket won't render)")

        if issues:
            needs_fix.append((f, issues))

    if not needs_fix:
        print("All playoff fixtures have correct Order and MatchDayName.")
        return

    print(f"\n{len(needs_fix)} fixtures need fixing:")
    for f, issues in needs_fix:
        fid = f["_id"]
        print(f"  {fid}: {', '.join(issues)}")

    confirm = input("\nApply fixes? (y/N): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    fixed = 0
    for f, _ in needs_fix:
        fid = f["_id"]
        updates = {}
        mdn = f.get("matchDayName", "")
        normalized = mdn.lower().replace("-", "")
        if mdn != normalized:
            updates["matchDayName"] = normalized

        if f.get("order") is None and f.get("Order") is None:
            # Auto-assign order based on stage
            node_base = {"quarterfinal": 4, "semifinal": 2, "final": 1, "third_place": 1}
            base = node_base.get(normalized, 1)
            # Count how many fixtures of this stage we've already processed
            same_stage = [x for x, _ in needs_fix if (x.get("matchDayName") or "").lower().replace("-", "") == normalized]
            idx = same_stage.index(f)
            updates["Order"] = base + idx

        if updates:
            db.fixtures.update_one({"_id": fid}, {"$set": updates})
            fixed += 1
            print(f"  Fixed {fid}: {updates}")

    print(f"\nFixed {fixed} fixtures.")


def fix_logos(champ_id):
    """
    Fix team logos across all 3 user-facing collections.

    After import, logos may be missing or wrong in:
    1. champs.TeamRefs (Participants tab)
    2. groups.TeamRefs (Standings tab)
    3. fixtures.HomeTeam/AwayTeam (Fixture cards)
    """
    db = get_db()
    from bson import ObjectId

    oid = ObjectId(champ_id)

    # Get champ document
    champ = db.champs.find_one({"_id": oid})
    if not champ:
        print(f"Champ {champ_id} not found")
        return

    print(f"Champ: {champ.get('name', 'Unknown')}")

    # Get authoritative team data (from teams collection)
    team_refs = champ.get("teamRefs") or champ.get("TeamRefs") or []
    print(f"TeamRefs in champ: {len(team_refs)}")

    # Build team logo map from teams collection
    team_ids = set()
    for tr in team_refs:
        tid = tr.get("Id") or tr.get("id")
        if tid:
            team_ids.add(tid)

    team_logos = {}
    for tid in team_ids:
        team = db.teams.find_one({"_id": tid})
        if team:
            logo = team.get("imageUrl") or team.get("ImageUrl")
            if logo:
                team_logos[tid] = logo

    if not team_logos:
        print("No team logos found in teams collection.")
        # Fall back to fixture data
        fixtures = list(db.fixtures.find({"champRef._id": oid}).limit(5))
        for f in fixtures:
            for tk in ("homeTeam", "awayTeam"):
                team = f.get(tk) or {}
                tid = team.get("id") or team.get("champTeamId")
                logo = team.get("imageUrl")
                if tid and logo:
                    team_logos[tid] = logo
        print(f"Found {len(team_logos)} logos from fixture data")

    if not team_logos:
        print("No logos to fix.")
        return

    print(f"\nLogos to apply: {len(team_logos)} teams")
    for tid, logo in team_logos.items():
        print(f"  {tid}: {logo[:60]}...")

    confirm = input("\nApply logo fixes? (y/N): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    fixed = 0

    # 1. Fix champs.TeamRefs
    for tid, logo in team_logos.items():
        r = db.champs.update_one(
            {"_id": oid, "TeamRefs.Id": tid},
            {"$set": {"TeamRefs.$.ImageUrl": logo}}
        )
        if r.modified_count:
            fixed += 1
            print(f"  champs.TeamRefs: {tid}")

    # 2. Fix groups.TeamRefs
    groups = list(db.groups.find({"champRef._id": oid}))
    for group in groups:
        for tid, logo in team_logos.items():
            r = db.groups.update_one(
                {"_id": group["_id"], "TeamRefs.Id": tid},
                {"$set": {"TeamRefs.$.ImageUrl": logo}}
            )
            if r.modified_count:
                fixed += 1
                print(f"  groups.TeamRefs ({group.get('name', '?')}): {tid}")

    # 3. Fix fixtures.HomeTeam / AwayTeam
    for tid, logo in team_logos.items():
        r = db.fixtures.update_many(
            {"champRef._id": oid, "homeTeam.id": tid},
            {"$set": {"homeTeam.imageUrl": logo}}
        )
        if r.modified_count:
            fixed += r.modified_count
            print(f"  fixtures.homeTeam: {tid} ({r.modified_count} fixtures)")

        r = db.fixtures.update_many(
            {"champRef._id": oid, "awayTeam.id": tid},
            {"$set": {"awayTeam.imageUrl": logo}}
        )
        if r.modified_count:
            fixed += r.modified_count
            print(f"  fixtures.awayTeam: {tid} ({r.modified_count} fixtures)")

    print(f"\nApplied {fixed} logo updates across all collections.")


def fix_penalties(fixture_id):
    """
    Fix penalty score data for a specific fixture.

    Ensures all penalty-related fields are correct:
    - HomePenaltyScore/AwayPenaltyScore as strings
    - HasPenalties = true
    - WinnerTeamId set correctly
    - PeriodScores entry with Type="penalties"
    """
    db = get_db()

    fixture = db.fixtures.find_one({"_id": fixture_id})
    if not fixture:
        print(f"Fixture {fixture_id} not found (remember: _id is a string, not UUID)")
        return

    home = fixture.get("homeTeam", {}).get("name", "Home")
    away = fixture.get("awayTeam", {}).get("name", "Away")
    print(f"Fixture: {home} vs {away}")
    print(f"  Score: {fixture.get('homeTeamScore')}-{fixture.get('awayTeamScore')}")
    print(f"  Penalties: {fixture.get('homePenaltyScore')}-{fixture.get('awayPenaltyScore')}")
    print(f"  HasPenalties: {fixture.get('hasPenalties')}")
    print(f"  WinnerTeamId: {fixture.get('winnerTeamId')}")

    updates = {}

    # Check types
    for field in ("homePenaltyScore", "awayPenaltyScore"):
        val = fixture.get(field)
        if val is not None and not isinstance(val, str):
            updates[field] = str(val)
            print(f"  FIX: {field} {type(val).__name__} -> string '{val}'")

    for field in ("homeTeamScore", "awayTeamScore"):
        val = fixture.get(field)
        if val is not None and not isinstance(val, str):
            updates[field] = str(val)
            print(f"  FIX: {field} {type(val).__name__} -> string '{val}'")

    hp = fixture.get("homePenaltyScore")
    ap = fixture.get("awayPenaltyScore")

    if hp and ap:
        if not fixture.get("hasPenalties"):
            updates["hasPenalties"] = True
            print("  FIX: hasPenalties -> true")

        if not fixture.get("winnerTeamId"):
            hp_int = int(hp) if isinstance(hp, (int, str)) and str(hp).isdigit() else 0
            ap_int = int(ap) if isinstance(ap, (int, str)) and str(ap).isdigit() else 0
            if hp_int > ap_int:
                winner = fixture.get("homeTeam", {}).get("id") or fixture.get("homeTeam", {}).get("champTeamId")
            else:
                winner = fixture.get("awayTeam", {}).get("id") or fixture.get("awayTeam", {}).get("champTeamId")
            if winner:
                updates["winnerTeamId"] = winner
                print(f"  FIX: winnerTeamId -> {winner}")

        # Check PeriodScores
        period_scores = fixture.get("periodScores") or []
        has_pen_period = any((ps.get("Type") or ps.get("type") or "").lower() == "penalties" for ps in period_scores)
        if not has_pen_period:
            hp_str = str(hp) if hp else "0"
            ap_str = str(ap) if ap else "0"
            new_ps = period_scores + [{"Home_score": hp_str, "Away_score": ap_str, "Type": "penalties"}]
            updates["periodScores"] = new_ps
            print(f"  FIX: Added PeriodScores penalties entry")

    if not updates:
        print("\nNo fixes needed.")
        return

    confirm = input(f"\nApply {len(updates)} fix(es)? (y/N): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    db.fixtures.update_one({"_id": fixture_id}, {"$set": updates})
    print("Fixes applied.")


def recalculate(champ_id):
    """Trigger standings recalculation via API."""
    print(f"Recalculating standings for champ {champ_id}...")
    result = api_call("POST", f"/recalculate/champ/{champ_id}/standings")
    if result is not None:
        print("Standings recalculated successfully.")
    else:
        print("Recalculation may have failed. Check API logs.")


def verify(champ_id):
    """Run post-import verification checks."""
    db = get_db()
    from bson import ObjectId

    oid = ObjectId(champ_id)
    issues = []

    # 1. Check champ exists
    champ = db.champs.find_one({"_id": oid})
    if not champ:
        print(f"ERROR: Champ {champ_id} not found")
        return
    print(f"Champ: {champ.get('name', 'Unknown')}")

    # 2. Count fixtures
    fixtures = list(db.fixtures.find({"champRef._id": oid}))
    print(f"Fixtures: {len(fixtures)}")

    # 3. Check fixture statuses
    status_counts = {}
    for f in fixtures:
        s = f.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
    print(f"Status distribution: {status_counts}")
    if status_counts.get(0):
        issues.append(f"{status_counts[0]} fixtures still Scheduled (status=0)")

    # 4. Check score types
    bad_scores = 0
    for f in fixtures:
        for field in ("homeTeamScore", "awayTeamScore", "homePenaltyScore", "awayPenaltyScore"):
            val = f.get(field)
            if val is not None and not isinstance(val, str):
                bad_scores += 1
    if bad_scores:
        issues.append(f"{bad_scores} score fields with wrong type (should be string)")

    # 5. Check team logos in champs.TeamRefs
    team_refs = champ.get("teamRefs") or champ.get("TeamRefs") or []
    missing_logos = [tr for tr in team_refs if not (tr.get("ImageUrl") or tr.get("imageUrl"))]
    if missing_logos:
        issues.append(f"{len(missing_logos)} teams missing logos in champs.TeamRefs (Participants tab)")

    # 6. Check playoff brackets
    playoff_fixtures = [f for f in fixtures if not (f.get("matchDayName") or "").isdigit()]
    missing_order = [f for f in playoff_fixtures if f.get("order") is None and f.get("Order") is None]
    if missing_order:
        issues.append(f"{len(missing_order)} playoff fixtures missing Order (bracket won't render)")

    bad_mdn = [f for f in playoff_fixtures if (f.get("matchDayName") or "") != (f.get("matchDayName") or "").lower()]
    if bad_mdn:
        issues.append(f"{len(bad_mdn)} fixtures with non-lowercase matchDayName")

    # 7. Check groups exist
    groups = list(db.groups.find({"champRef._id": oid}))
    print(f"Groups: {len(groups)}")
    if not groups:
        issues.append("No groups found for this champ")

    # 8. Check stages exist
    stages = list(db.stages.find({"champRef._id": oid}))
    print(f"Stages: {len(stages)}")
    if not stages:
        issues.append("No stages found for this champ")

    # 9. Check for duplicate fixtures
    ext_ids = [f.get("id") for f in fixtures if f.get("id")]
    dupes = [eid for eid in set(ext_ids) if ext_ids.count(eid) > 1]
    if dupes:
        issues.append(f"{len(dupes)} duplicate fixture ExternalIds: {dupes[:5]}")

    # 10. Check standings exist
    standings = db.champGroupStandings.find_one({"champRef._id": oid})
    if not standings:
        issues.append("No standings calculated - run recalculate")

    # Summary
    print(f"\n{'='*60}")
    if issues:
        print(f"ISSUES FOUND ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("ALL CHECKS PASSED")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Post-import fixes for EasyChamp")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    p_brackets = subparsers.add_parser("fix-brackets", help="Fix playoff bracket order values")
    p_brackets.add_argument("--champ-id", required=True, help="Championship ObjectId")

    p_logos = subparsers.add_parser("fix-logos", help="Fix team logos across all collections")
    p_logos.add_argument("--champ-id", required=True, help="Championship ObjectId")

    p_pen = subparsers.add_parser("fix-penalties", help="Fix penalty score data types")
    p_pen.add_argument("--fixture-id", required=True, help="Fixture _id (string)")

    p_recalc = subparsers.add_parser("recalculate", help="Trigger standings recalculation")
    p_recalc.add_argument("--champ-id", required=True, help="Championship ObjectId")

    p_verify = subparsers.add_parser("verify", help="Run post-import verification")
    p_verify.add_argument("--champ-id", required=True, help="Championship ObjectId")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "fix-brackets":
        fix_brackets(args.champ_id)
    elif args.command == "fix-logos":
        fix_logos(args.champ_id)
    elif args.command == "fix-penalties":
        fix_penalties(args.fixture_id)
    elif args.command == "recalculate":
        recalculate(args.champ_id)
    elif args.command == "verify":
        verify(args.champ_id)


if __name__ == "__main__":
    main()
