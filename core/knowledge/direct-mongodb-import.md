# Direct MongoDB Import Guide for EasyChamp

## When to Use
When the production API (`api.easychamp.com`) is down (HTTP 522) or the import endpoint
has issues with fixture deserialization, you can use the local `sw-easychamp` repo to
run the API locally (connects to production MongoDB) or write directly to MongoDB.

## Architecture Overview

### Database: `Fixtures-db` on MongoDB (5.161.49.75:27017)
Connection string is in `appsettings.Development.json`.

### Key Collections
| Collection | Purpose | Key Fields |
|---|---|---|
| `champs` | Tournament/competition | `_id`, `Name`, `TeamRefs[]`, `StagesRefs[]`, `ChampLeagueRef` |
| `champLeagues` | League (parent of champs) | `_id`, `Name`, `SubDomain` |
| `stages` | Group stage / Playoff stage | `_id`, `GroupRefs[]`, `FixturesRefs[]`, `ChampRef` |
| `groups` | Groups within a stage | `_id`, `TeamRefs[]`, `FixtureRefs[]`, `StageRef`, `ChampRef` |
| `fixtures` | Match results | `_id`, `HomeTeam`, `AwayTeam`, `HomeTeamScore`, `AwayTeamScore`, `Status`, `HomeSquad[]`, `AwaySquad[]` |
| `events` | Goals, cards, etc | `_id`, `EventType`, `PlayerRef`, `FixtureRef`, `IsHomeEvent`, `ChampTeamPlayerId`, `Minute` (STRING!) |
| `champGroupStandings` | Group standings (computed) | `_id`, `Standings[]`, `GroupRef`, `ChampRef`, `StageRef` |
| `champTeamPlayers` | Player registrations per champ | `_id`, `Player`, `ChampTeamId`, `ChampRef` |
| `players` | Global player records | `_id`, `FullName`, `ExternalId` |
| `teams` | Global team records | `_id`, `Name`, `ExternalId`, `ImageUrl` |
| `news` | News articles | `_id`, `Title`, `Description` (HTML), `Categories[]`, `IsPublished` |

### ID Format
All IDs are **string GUIDs** (not BSON ObjectId). Use `str(uuid.uuid4())` for new records.

### References Pattern
Documents use embedded "Ref" objects, NOT foreign key IDs:
```json
{
  "ChampRef": {"_id": "guid-here", "Version": 0, "Name": "Champ Name"},
  "ChampLeagueRef": {"_id": "guid-here", "Version": 0, "Name": "League Name"}
}
```

## Running the Local API

```bash
cd /Users/antonabyzov/Projects/sw-easychamp/repositories/ec-standings-api
dotnet run --project ec-standings-api --no-launch-profile \
  --urls "http://0.0.0.0:5010" 2>&1 | tee /tmp/ec-standings-api.log &
```

Environment: `ASPNETCORE_ENVIRONMENT=Development` (auto from `launchSettings.json`).
Base URL: `http://127.0.0.1:5010/ec-standings-api/`

**Note**: The API connects to PRODUCTION MongoDB. All changes are live immediately.

## Proven End-to-End Workflow (Tested 2026-02-22)

This workflow was validated by deleting C108 and re-creating from scratch. Every step is confirmed working.

**What the import endpoint handles:** League, Champ, Teams (with ExternalId matching), Players/CTPs, Stage, Group (with teamIds). It also creates an empty `champGroupStandings` document.

**What must be done via MongoDB:** Fixtures, Squads, Events, News (with HTML body).

**What must be recalculated via API:** Standings, Player Stats, Team Stats. Then zero-stat standings entries must be added for teams without fixtures.

### Phase 1: Import via API (handles teams + players + champ)
```bash
curl -s -X POST "http://127.0.0.1:5010/ec-standings-api/import/league" \
  -H "Content-Type: application/json" \
  -d @import.json
```

Import JSON structure (use `Teams` NOT `ChampTeams`):
```json
{
  "ImportSource": 99,
  "ImportMode": 0,
  "League": {
    "Name": "PS23 Soccer League",
    "Country": "USA",
    "SportKindName": "Soccer",
    "Id": "PS23 Soccer League",
    "Champs": [{
      "Name": "Master 30 8v8 - C108",
      "Id": "unique-external-id",
      "LeagueName": "PS23 Soccer League",
      "StartDate": "2026-02-17",
      "EndDate": "2026-06-30",
      "SportKindName": "Soccer",
      "Teams": [
        {
          "Name": "EasyChamp",
          "Id": "EasyChamp",
          "ImageUrl": "https://ps23soccer.com/webfiles/ps23/escudos/319.png",
          "SportKindName": "Soccer",
          "TeamMembers": [
            {"Player": {"FullName": "Anton Abyzov", "Id": "A. Abyzov", "SportKindName": "Soccer"}}
          ]
        }
      ],
      "Stages": [{"Name": "Group Stage", "Type": "League", "Order": 1, "Groups": []}]
    }]
  }
}
```

**CRITICAL**: Team `Id` must match existing team `ExternalId` (usually the team name).

### Phase 2: Add Group via PUT /stage/{id}
```bash
curl -s -X PUT "http://127.0.0.1:5010/ec-standings-api/stage/{stageId}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Group Stage",
    "type": {"name": "League", "id": "f2f7e59e-6d65-461c-9f75-011172b2f7d8"},
    "roundCount": 2, "order": 1, "teamsCount": 6, "groupCount": 1,
    "groups": [{"name": "Group A", "teams": ["team-guid-1", "team-guid-2"]}]
  }'
```

### Phase 3: Create Fixtures via MongoDB

```python
from pymongo import MongoClient
from bson.codec_options import CodecOptions
from bson.binary import UuidRepresentation
import uuid
from datetime import datetime, timezone

MONGO_URI = "REDACTED_MONGO_URI"
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client['Fixtures-db']
opts = CodecOptions(uuid_representation=UuidRepresentation.STANDARD)
# Get collection: db.get_collection('fixtures', codec_options=opts)
```

Fixture document:
```python
fixture = {
    "_id": str(uuid.uuid4()),
    "Version": 0,
    "AddedAtUtc": now,
    "UpdatedAtUtc": now,
    "CreatedBy": "IntegrationWorker",
    "UpdatedBy": "IntegrationWorker",
    "ExternalId": "unique-fixture-id",
    "Date": datetime(2026, 2, 17, 5, 0, 0),
    "HomeTeamScore": "3",   # ⚠️ STRING!
    "AwayTeamScore": "1",   # ⚠️ STRING!
    "Status": 2,            # 2 = Finished
    "MatchDay": 1,
    "MatchDayName": "1",    # ⚠️ STRING!
    "HomeTeam": {            # Full embedded TeamRef
        "_id": "team-guid", "Version": 0, "Name": "Team Name",
        "ImageUrl": "...", "IsInternational": False, "ChampTeamId": "champ-team-guid"
    },
    "AwayTeam": { ... },     # Same structure
    "GroupRef": {"_id": "group-guid", "Version": 0},
    "StageRef": {"_id": "stage-guid", "Version": 0, "Name": "Group Stage"},
    "ChampRef": {"_id": "champ-guid", "Version": 0, "Name": "Champ Name"},
    "ChampLeagueRef": { ... },
    "HomeSquad": [],         # Player entries from ChampTeamPlayers
    "AwaySquad": [],
    "RefereeRefs": [],
    "IsImportCompleted": True,
    "IsProcessing": False,
}
```

**After inserting fixtures**, update refs in group AND stage:
```python
# Update group
groups_coll.update_one({"_id": GROUP_ID}, {"$set": {"FixtureRefs": fixture_refs_list}})
# Update stage
stages_coll.update_one({"_id": STAGE_ID}, {"$set": {"FixturesRefs": fixture_refs_list}})
# Each ref: {"_id": fixture_id, "Version": 0}
```

### Phase 4: Recalculate Standings
```bash
curl -X POST "http://127.0.0.1:5010/ec-standings-api/recalculate/champ/{champId}/standings"
```

**⚠️ CRITICAL**: This endpoint only creates standings entries for teams that appear in fixtures.
Teams with no fixtures (e.g., bye week) will be MISSING from the standings table.

**Fix**: After recalculation, manually add zero-stat entries to `champGroupStandings.Standings[]`
for any teams in the group that don't have fixtures yet:

```python
# Standing entry structure for a team with 0 games:
zero_standing = {
    "Place": 5,  # After all teams with games
    "Scores": 0, "Played": 0, "Win": 0, "Draw": 0, "Lose": 0,
    "TotalScored": 0, "TotalConceded": 0,
    "PersonalScores": 0, "PersonalScored": 0, "PersonalConceded": 0,
    "PersonalAwayGoals": 0,
    "ChampTeam": {
        "_id": "team-id",          # From champ.TeamRefs[]._id
        "Version": 0,
        "Name": "Team Name",
        "OwnerId": "owner-guid",
        "SportKind": None, "League": None, "TeamShortName": None,
        "IsInternational": False,
        "ImageUrl": "https://...",
        "IsVirtual": False,
        "ChampTeamId": "champ-team-id"  # From champ.TeamRefs[].ChampTeamId
    },
    "LastFixtureResults": []
}
# Push to standings:
cgs.update_one({"ChampRef._id": champ_id}, {"$push": {"Standings": {"$each": [zero_standing]}}})
```

### Phase 5: Create Events (Goals)
```python
event = {
    "_id": str(uuid.uuid4()),
    "Version": 0,
    "AddedAtUtc": now,
    "UpdatedAtUtc": now,
    "CreatedBy": "IntegrationWorker",
    "UpdatedBy": "IntegrationWorker",
    "ExternalId": str(uuid.uuid4())[:8],
    "Minute": "0",          # ⚠️ STRING, not int!
    "EventType": "scorer",
    "VARRefereeDecision": None,
    "Type": 2,               # Goal
    "Value": None,
    "Note": None,
    "Description": None,
    "BodyPart": None,
    "GoalType": None,
    "FixtureRef": {"_id": fixture_id, "Version": 0},
    "ChampRef": {"_id": champ_id, "Version": 0, "Name": "..."},
    "ChampLeagueRef": league_ref,   # Copy from champ document
    "PlayerRef": {"_id": player_id, "Version": 0, "FullName": "Player Name"},
    "AssistantPlayerRef": None,
    "ChampTeamPlayerId": "ctp-guid", # From champTeamPlayers._id
    "ChampTeamPlayerAssistantId": None,
    "IsHomeEvent": True,             # True = home team scorer
    "Points": 1
}
```

**Finding CTP (ChampTeamPlayer) IDs**: Query `champTeamPlayers` by `ChampRef._id` and `Player.FullName`.

### Phase 6: Create News Article

News is stored in the `news` collection:
```python
news = {
    "_id": str(uuid.uuid4()),
    "Version": 0,
    "AddedAtUtc": now,
    "UpdatedAtUtc": now,
    "CreatedBy": "IntegrationWorker",
    "ExternalId": "c108-matchday1-recap",
    "Title": "Match Day 1: EasyChamp Falls 4-5 in Thriller",
    "Description": "<html content here>",  # Rich HTML with inline styles
    "ContentType": 1,                       # 1 = Article
    "IsPublic": True,
    "IsPublished": True,
    "Categories": [
        {"EntityId": champ_id, "Type": 0},   # 0 = Champ category
        {"EntityId": league_id, "Type": 2}    # 2 = League category
    ],
    "SportKindRef": {
        "_id": "05684792-9662-4e9f-a163-8545e5736c3d",
        "Version": 0,
        "Name": "Soccer"
    },
    "Keywords": ["EasyChamp", "PS23", "match report"],
    "ImageUrl": None,               # Or "News/filename.png" for uploaded images
    "ImageInitialFileName": None,
    "ImageContentType": None,
    "Date": datetime(2026, 2, 17)   # Match date
}
```

**News HTML Style Guide** (matches existing articles):
- Use **inline CSS** only (no external stylesheets)
- Dark gradient header with team logos, score, and match info
- Body text: `font-size:15px; line-height:1.7; color:#333`
- Section headers: `font-size:22px; color:#1a1a2e`
- Tag pills: `background:#315FD3; color:white; border-radius:20px`
- YouTube embed: responsive iframe with `padding-bottom:56.25%`
- Goal scorers in colored cards: blue for home (`#f0f4ff`), red for away (`#fff5f5`)
- Lineup as pill badges
- "Stats powered by EasyChamp" footer link

**Categories Type values**: `0` = Champ, `2` = League (champLeague)

## Complete Checklist for Match Day Import

- [ ] 1. Create/update competition via `/import/league` (teams, players, stages)
- [ ] 2. Create group via `PUT /stage/{id}` with all teams
- [ ] 3. Insert fixtures into MongoDB `fixtures` collection
- [ ] 4. Update `groups.FixtureRefs` and `stages.FixturesRefs` with new fixture IDs
- [ ] 5. Insert events (goals) into `events` collection
- [ ] 6. Populate `HomeSquad`/`AwaySquad` in fixture documents
- [ ] 7. Recalculate standings: `POST /recalculate/champ/{id}/standings`
- [ ] 8. **Add zero-stat standings entries** for teams without fixtures (⚠️ recalc wipes these every time!)
- [ ] 9. Recalculate player/team stats (ALL of these, in order):
  ```bash
  CHAMP="{champId}" STAGE="{stageId}" LEAGUE="{leagueId}"
  curl -X POST ".../stage/$STAGE/recalcstageplayerstats"
  curl -X POST ".../champs/$CHAMP/recalcstageplayerstats"
  curl -X POST ".../champs/$CHAMP/recalcoverallplayerstats"
  curl -X POST ".../stage/$STAGE/recalcstageuserteamstats"
  curl -X POST ".../champ-leagues/$LEAGUE/recalcstageplayerstats"
  # For each team with fixtures:
  curl -X POST ".../teams/$TEAM_ID/recalctotalstats"
  ```
  ⚠️ **League-level recalc** (`/champ-leagues/{id}/recalcoverallplayerstats`) can take 60s+ — run it but don't wait.
- [ ] 10. Create news article in `news` collection
- [ ] 11. **Verify everything** (see Verification section below)

## Verification Checklist (MANDATORY after every import)

After completing all import steps, verify each of these via the API or website.
Do NOT skip this — every issue we've had came from missing a verification step.

### 1. Participants Tab
```bash
# All teams must appear
curl -s "http://127.0.0.1:5010/ec-standings-api/champs/{champId}" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
teams = d.get('teams', d.get('teamRefs', []))
print(f'Teams: {len(teams)}')
for t in teams: print(f'  {t.get(\"name\",\"?\")}')
"
```
✅ Expected: All teams in the competition listed (e.g., 6 for C108)

### 2. Standings Tab
```bash
curl -s "http://127.0.0.1:5010/ec-standings-api/champs/{champId}/standings" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
for stage in d.get('stages', []):
  for group in stage.get('groups', []):
    standings = group.get('standings', [])
    print(f'Teams in standings: {len(standings)}')
    for s in standings:
      t = s.get('team', {})
      print(f'  {s[\"place\"]}. {t.get(\"name\",\"?\")} P:{s[\"played\"]} GF:{s[\"totalScored\"]} GA:{s[\"totalConceded\"]} Pts:{s[\"scores\"]}')
"
```
✅ Expected: **ALL group teams** appear (including those with 0 games)
✅ Expected: Points correct (W=3, D=1, L=0)
✅ Expected: GF/GA match fixture scores

### 3. Schedule Tab
```bash
curl -s "http://127.0.0.1:5010/ec-standings-api/fixture/champ/{champId}" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
for f in d:
    home = f.get('homeTeam',{}).get('name','?')
    away = f.get('awayTeam',{}).get('name','?')
    print(f'MD{f.get(\"matchDay\",\"?\")} {home} {f.get(\"homeTeamScore\",\"?\")} - {f.get(\"awayTeamScore\",\"?\")} {away} | events:{len(f.get(\"events\",[]))}')
"
```
✅ Expected: All fixtures listed with correct scores
✅ Expected: Match day numbers correct

### 4. Stats Tab (Player Stats)
```bash
curl -s "http://127.0.0.1:5010/ec-standings-api/champs/{champId}/stats?pageSize=20" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
for item in d.get('items', []):
    player = item.get('playerRef', {}).get('fullName', '?')
    stats = {s['name']: s['value'] for s in item.get('allStats', [])}
    print(f'  {player}: {stats.get(\"Goals\",0)} goals, {stats.get(\"Games\",0)} games')
"
```
✅ Expected: All scorers appear with correct goal tallies
✅ Expected: Games played = number of fixtures they appeared in

### 5. Events per Fixture
```bash
# Check each fixture individually
curl -s "http://127.0.0.1:5010/ec-standings-api/fixture/{fixtureId}/events" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
items = d.get('items', [])
print(f'Events: {len(items)}')
home = [e for e in items if e.get('isHomeEvent')]
away = [e for e in items if not e.get('isHomeEvent')]
print(f'Home goals: {len(home)}, Away goals: {len(away)}')
for e in items:
    side = 'HOME' if e.get('isHomeEvent') else 'AWAY'
    print(f'  [{side}] {e.get(\"player\",{}).get(\"fullName\",\"?\")}')
"
```
✅ Expected: Event count matches score (home events = home score, away events = away score)

### 6. News
```bash
curl -s "http://127.0.0.1:5010/ec-standings-api/news?champLeagueId={leagueId}&pageSize=5" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
for n in d.get('items', []):
    print(f'{n.get(\"title\",\"?\")} | published: {n.get(\"isPublished\")}')
"
```
✅ Expected: New article appears, `isPublished: true`

### 7. Website Visual Check
Open these URLs and confirm visually:
- `https://easychamp.com/observe/competition/{champId}?tabs=participants` — all teams with logos
- `https://easychamp.com/observe/competition/{champId}?tabs=standings` — full table, all teams
- `https://easychamp.com/observe/competition/{champId}?tabs=schedule` — fixtures with scores
- `https://easychamp.com/observe/competition/{champId}?tabs=stats` — player stats (goals, games)
- `https://easychamp.com/observe/league/{leagueId}?tabs=news` — news article visible

## Common Pitfalls
1. **Minute must be STRING** — `"0"` not `0`. Causes `BsonType deserialization error`.
2. **Scores must be STRING** — `"3"` not `3`.
3. **MatchDayName must be STRING** — `"1"` not `1`.
4. **Team ExternalIds** — Existing teams use their NAME as ExternalId.
5. **Import uses `Teams` not `ChampTeams`** — The swagger shows `teams`, the import model field is `Teams`.
6. **Group.Fixtures not deserialized** — The import endpoint doesn't process fixtures inside groups.
7. **Standings recalculation only covers teams with fixtures** — Must manually add entries for teams with 0 games played. Without this, teams appear in "Participants" but NOT in "Standings". **AND**: Every time you re-run standings recalc, it OVERWRITES the Standings array, wiping the zero-stat entries. Always re-add them AFTER recalculation.
8. **Squads required for "Games" stat** — The stats engine counts "Games Played" from `HomeSquad`/`AwaySquad` entries (where `IsPlayed: true`). If a fixture has empty squads, only scorers (from events) appear in stats. Non-scoring players will be invisible. Always populate squads BEFORE running stats recalculation.
9. **Dev auth bypass doesn't work** — The middleware uses "Admin" role but the validator checks "Administrator" and "SystemAdmin". Use direct MongoDB writes as workaround.
9. **UUID representation** — Use `UuidRepresentation.STANDARD` when connecting with pymongo.
10. **After inserting fixtures, update BOTH group and stage refs** — Missing refs means the fixture won't appear in the schedule.
11. **Events are queried by `FixtureRef._id`** — The API joins events to fixtures via this field, not via an `EventRefs` array in the fixture document.

## Key IDs for PS23 Soccer League
- **League**: `8f541539-9752-4d5b-a39d-78361dedf092`
- **SportKind (Soccer)**: `05684792-9662-4e9f-a163-8545e5736c3d`
- **StageType (League)**: `f2f7e59e-6d65-461c-9f75-011172b2f7d8`
- **Owner (anton.abyzov)**: `37f8d338-a9e8-45f1-9efe-477575f155c5`

## Existing Teams (PS23 Soccer League)
| Team | ID | ExternalId |
|---|---|---|
| EasyChamp | 94098a5f-54c7-46f1-a2d5-fc2c1aae373d | EasyChamp |
| Atenas Pocito | 93b7bc07-83e1-4482-8356-1a4a1df278f4 | Atenas Pocito |
| #10 FC | d7aa9c6d-34f0-443a-99f2-93b58de11d2c | #10 FC |
| Miami All Stars | bf3120e4-1fd9-4509-b291-c2f10243dde3 | Miami All Stars |
| 3 Toques FC | 63b362f7-b588-46c9-8394-af06fb8f44da | 3 Toques FC |
| Junior Miami | f13d3871-d9f4-44ae-86d9-fef445ab3f65 | Junior Miami |

## C108 Specific IDs (Re-imported 2026-02-22)
| Entity | ID |
|---|---|
| Champ | `3f4ae5f9-55ca-4f64-8e17-cdf80d8c0231` |
| Stage (Group Stage) | `6e89cd49-7743-4270-8b2b-e13220cd2586` |
| Group A | `a3f2f9a1-20fe-48bd-933c-0b7a7073bda9` |
| ChampTeam: EasyChamp | `3cdc478e-7671-405c-9933-a5d8af9e27fd` |
| ChampTeam: #10 FC | `b6dc027a-5477-4d45-970f-963a24f8c94b` |
| ChampTeam: Miami All Stars | `569aaa76-6d86-462e-8a1f-de871872da52` |
| ChampTeam: Atenas Pocito | `db90f405-3d98-4430-bc8d-36f4e8868f9a` |
| ChampTeam: 3 Toques FC | `6e1603e1-3660-401d-a94d-76a50cd2256d` |
| ChampTeam: Junior Miami | `380271be-5628-4430-af3f-6b754fc70c99` |

**Note**: ChampTeamIds change every time you re-import. Always query fresh after import.
