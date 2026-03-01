# EasyChamp Tournament Import Guide

## CRITICAL JSON STRUCTURE RULES (2026-03-01)

⚠️ **`Champs` array MUST be INSIDE the `League` object**, not at root level:
```json
// ✅ CORRECT
{"League": {"Id": "...", "Champs": [...]}}

// ❌ WRONG — Champs will deserialize as empty list
{"League": {"Id": "..."}, "Champs": [...]}
```

⚠️ **Fixtures MUST use `HomeTeam`/`AwayTeam` objects**, not string IDs:
```json
// ✅ CORRECT
"HomeTeam": {"Id": "#10 FC", "Name": "#10 FC", "SportKindName": "Soccer"}

// ❌ WRONG — causes NullReferenceException at ImportLeagueService.cs:286
"HomeTeamId": "#10 FC"
```

## News Article Creation via MongoDB

When creating news directly in MongoDB, these fields are REQUIRED (the API returns 500 without them):
- `SportKindRef._id` must be a UUID string (e.g. `"05684792-9662-4e9f-a163-8545e5736c3d"` for Soccer), NOT an integer
- `ContentType` must be `NumberInt(1)` (not 0)
- `AddedAtUtc`, `UpdatedAtUtc`, `Date` — ISODate objects
- `IsPublic: true`, `IsPublished: true`
- `Categories` — array of `{EntityId: "<champ-or-league-id>", Type: <0=champ, 1=league, 2=team>}`

News URL format: `https://easychamp.com/news/<news-id>` (NOT under `/observe/competition/`)

## The Import Endpoint Works! (Validated 2026-02-22, re-validated 2026-03-01)

The `/import/league` endpoint handles **everything** — fixtures, squads, events, standings, and player stats are all auto-calculated. The Swagger documentation is misleading because it hides the `Fixtures` property on the Group model, but the property exists (confirmed via reflection on `Sc.ApiCore.Lib` v3.0.19).

### What the import auto-calculates:
- ✅ Standings (for teams with fixtures)
- ✅ Player stats (Goals, Games from events + squads)
- ✅ Stage player stats
- ✅ Team stats

### What still needs manual handling:
- ❌ Zero-stat standings entries for teams WITHOUT fixtures (bye week teams)
- ❌ News articles with HTML body (import requires non-empty `Description` field, but `Body` field maps to `Description`)

## Complete Import JSON Template

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
      "Id": "C108",
      "LeagueName": "PS23 Soccer League",
      "StartDate": "2026-02-17",
      "EndDate": "2026-06-30",
      "SportKindName": "Soccer",
      "Teams": [
        {
          "Name": "EasyChamp", "Id": "EasyChamp",
          "ImageUrl": "https://...",
          "SportKindName": "Soccer",
          "TeamMembers": [
            {"Player": {"FullName": "Anton Abyzov", "Id": "A. Abyzov", "SportKindName": "Soccer"}}
          ]
        }
      ],
      "Stages": [{
        "Name": "Group Stage",
        "Type": "League",
        "Order": 1,
        "RoundCount": 2,
        "TeamCount": 6,
        "GroupCount": 1,
        "Groups": [{
          "Name": "Group A",
          "TeamIds": ["EasyChamp", "Atenas Pocito", "#10 FC", "Miami All Stars"],
          "Fixtures": [
            {
              "Id": "unique-fixture-external-id",
              "Date": "2026-02-17T05:00:00",
              "Status": 2,
              "MatchDay": 1,
              "MatchDayName": "1",
              "HomeTeamScore": "3",
              "AwayTeamScore": "1",
              "HomeTeam": {"Name": "#10 FC", "Id": "#10 FC", "SportKindName": "Soccer"},
              "AwayTeam": {"Name": "Miami All Stars", "Id": "Miami All Stars", "SportKindName": "Soccer"},
              "HomeSquad": [
                {"Player": {"FullName": "E. Lopez", "Id": "E. Lopez", "SportKindName": "Soccer"}, "IsPlayed": true}
              ],
              "AwaySquad": [
                {"Player": {"FullName": "S. Garcia", "Id": "S. Garcia", "SportKindName": "Soccer"}, "IsPlayed": true}
              ],
              "Events": [
                {
                  "EventType": "scorer",
                  "IsHomeEvent": true,
                  "Player": {"Id": "E. Lopez", "FullName": "E. Lopez", "SportKindName": "Soccer"},
                  "Minute": "0",
                  "Points": 1,
                  "Id": "unique-event-id"
                }
              ]
            }
          ]
        }]
      }]
    }]
  }
}
```

### Key Rules for Import JSON:
1. **Team `Id`** must match existing team `ExternalId` (usually the team name)
2. **Player `Id`** must match existing player `ExternalId` — this is how players are matched
3. **Event Player** requires `FullName` AND `Id` AND `SportKindName` — all three are validated
4. **Fixture `Status`**: 2 = Finished
5. **Scores are strings**: `"3"` not `3`
6. **Each Event needs a unique `Id`** to prevent duplicates on re-import
7. **Each Fixture needs a unique `Id`** for the same reason
8. **Squad items** need `IsPlayed: true` for the stats engine to count "Games"
9. **`ImportSource: 99`** = custom import, **`ImportMode: 0`** = full import

## Running the Local API

```bash
cd /Users/antonabyzov/Projects/sw-easychamp/repositories/ec-standings-api
dotnet run --project ec-standings-api --no-launch-profile \
  --urls "http://0.0.0.0:5010" 2>&1 | tee /tmp/ec-standings-api.log &
```

Base URL: `http://127.0.0.1:5010/ec-standings-api/`

**Note**: Connects to PRODUCTION MongoDB. All changes are live immediately.

## Step-by-Step Procedure

### Step 1: Import via API
```bash
curl -s -X POST "http://127.0.0.1:5010/ec-standings-api/import/league?ownerId=37f8d338-a9e8-45f1-9efe-477575f155c5" \
  -H "Content-Type: application/json" \
  -d @import.json
```

⚠️ **CRITICAL: Always pass `ownerId`!** Without it, the import uses `ImportConstants.DefaultOwnerId` which creates duplicate teams and assigns the wrong manager. For PS23 Soccer League, the owner is `37f8d338-a9e8-45f1-9efe-477575f155c5` (anton.abyzov@gmail.com).

Expected response: `{"success":true,"message":"League imported successfully","champsImported":1}`

This creates: league, champ, teams, players, CTPs, stage, group, fixtures, squads, events.
Auto-calculates: standings (for teams with fixtures), player stats, team stats.

### Step 2: Add Zero-Stat Standings for Bye-Week Teams
Teams without fixtures don't appear in standings. Add them manually:

```python
from pymongo import MongoClient
from bson.codec_options import CodecOptions
from bson.binary import UuidRepresentation

MONGO_URI = os.environ["EASYCHAMP_MONGO_URI"]  # Set from appsettings.Development.json — NEVER hardcode credentials
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client['Fixtures-db']
opts = CodecOptions(uuid_representation=UuidRepresentation.STANDARD)

champ = db.get_collection('champs', codec_options=opts).find_one({"ExternalId": "C108"})
CHAMP_ID = champ['_id']
team_map = {t['Name']: t for t in champ['TeamRefs']}

cgs = db.get_collection('champGroupStandings', codec_options=opts)
doc = cgs.find_one({"ChampRef._id": CHAMP_ID})
existing = {s['ChampTeam']['Name'] for s in doc['Standings']}

missing = []
for name in ["3 Toques FC", "Junior Miami"]:  # Teams without fixtures
    if name not in existing:
        t = team_map[name]
        missing.append({
            "Place": len(doc['Standings']) + 1,
            "Scores": 0, "Played": 0, "Win": 0, "Draw": 0, "Lose": 0,
            "TotalScored": 0, "TotalConceded": 0,
            "PersonalScores": 0, "PersonalScored": 0, "PersonalConceded": 0, "PersonalAwayGoals": 0,
            "ChampTeam": {
                "_id": t['_id'], "Version": 0, "Name": t['Name'],
                "OwnerId": "37f8d338-a9e8-45f1-9efe-477575f155c5",
                "SportKind": None, "League": None, "TeamShortName": None,
                "IsInternational": False, "ImageUrl": t.get('ImageUrl', ''),
                "IsVirtual": False, "ChampTeamId": t['ChampTeamId']
            },
            "LastFixtureResults": []
        })

if missing:
    cgs.update_one({"_id": doc['_id']}, {"$push": {"Standings": {"$each": missing}}})
```

### Step 3: Create News Article (MongoDB)
```python
news = {
    "_id": str(uuid.uuid4()),
    "Version": 0, "AddedAtUtc": now, "UpdatedAtUtc": now,
    "CreatedBy": "IntegrationWorker",
    "ExternalId": "c108-matchday1-recap",
    "Title": "Match Day 1: EasyChamp Falls 4-5 in Thriller",
    "Description": "<html>...</html>",  # Rich HTML with inline styles
    "ContentType": 1,
    "IsPublic": True, "IsPublished": True,
    "Categories": [
        {"EntityId": champ_id, "Type": 0},   # 0 = Champ
        {"EntityId": league_id, "Type": 2}    # 2 = League
    ],
    "SportKindRef": {"_id": "05684792-9662-4e9f-a163-8545e5736c3d", "Version": 0, "Name": "Soccer"},
    "Keywords": ["EasyChamp", "PS23", "match report"],
    "Date": datetime(2026, 2, 17)
}
db.get_collection('news', codec_options=opts).insert_one(news)
```

### Step 4: Verify (MANDATORY)
Run verification checks on ALL tabs — see Verification Checklist below.

## Deleting a Tournament (Full Cleanup)

⚠️ **This deletes from PRODUCTION MongoDB. Double-check the CHAMP_ID.**

```python
CHAMP_ID = "the-champ-guid-to-delete"

for coll_name, field in [
    ('events', 'ChampRef._id'),
    ('fixtures', 'ChampRef._id'),
    ('champGroupStandings', 'ChampRef._id'),
    ('champTeamPlayers', 'ChampRef._id'),
    ('groups', 'ChampRef._id'),
    ('stages', 'ChampRef._id'),
    ('stagePlayerStats', 'ChampRef._id'),
]:
    r = db.get_collection(coll_name, codec_options=opts).delete_many({field: CHAMP_ID})
    print(f"Deleted {r.deleted_count} from {coll_name}")

# Delete news linked to this champ
r = db.get_collection('news', codec_options=opts).delete_many(
    {"Categories": {"$elemMatch": {"EntityId": CHAMP_ID, "Type": 0}}}
)
print(f"Deleted {r.deleted_count} from news")

# Delete the champ itself
r = db.get_collection('champs', codec_options=opts).delete_one({"_id": CHAMP_ID})
print(f"Deleted {r.deleted_count} from champs")
```

**Collections cleaned**: events, fixtures, champGroupStandings, champTeamPlayers, groups, stages, stagePlayerStats, news, champs.

**NOT cleaned** (shared data): teams, players, champLeagues. These are reused across competitions.

**⚠️ CRITICAL: Clean up player histories after deletion!**
The import adds history entries with `appendHistory: true`. Deleting the champ doesn't remove them.

```python
# Remove history entries pointing to deleted champ(s)
DEAD_CHAMPS = ["champ-id-1", "champ-id-2"]  # All deleted champ IDs
players = db.get_collection('players', codec_options=opts)
for p in players.find({"History.ChampId": {"$in": DEAD_CHAMPS}}):
    clean = [h for h in p.get('History', []) if h.get('ChampId') not in DEAD_CHAMPS]
    players.update_one({"_id": p['_id']}, {"$set": {"History": clean}})
    print(f"  {p.get('FullName','?')}: {len(p['History'])} -> {len(clean)}")
```

## Verification Checklist (MANDATORY after every import)

### 1. Participants
```bash
curl -s "$BASE/champs/{champId}" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
teams = d.get('teams', []); print(f'Teams: {len(teams)}')
for t in teams: print(f'  {t.get(\"name\",\"?\")}')"
```
✅ Expected: All teams listed (e.g., 6 for C108)

### 2. Standings
```bash
curl -s "$BASE/champs/{champId}/standings" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
for stage in d.get('stages', []):
  for group in stage.get('groups', []):
    for s in group.get('standings', []):
      t = s.get('team', {})
      print(f'{s[\"place\"]}. {t.get(\"name\",\"?\"):20s} P:{s[\"played\"]} GF:{s[\"totalScored\"]} GA:{s[\"totalConceded\"]} Pts:{s[\"scores\"]}')"
```
✅ Expected: **ALL group teams** (including 0-game teams)

### 3. Schedule
```bash
curl -s "$BASE/fixture/champ/{champId}" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
for f in d:
    print(f'MD{f.get(\"matchDay\",\"?\")} {f.get(\"homeTeam\",{}).get(\"name\",\"?\")} {f.get(\"homeTeamScore\",\"?\")} - {f.get(\"awayTeamScore\",\"?\")} {f.get(\"awayTeam\",{}).get(\"name\",\"?\")}')"
```
✅ Expected: Fixtures with correct scores

### 4. Stats
```bash
curl -s "$BASE/champs/{champId}/stats?pageSize=20" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
for item in d.get('items', []):
    p = item.get('playerRef', {}).get('fullName', '?')
    stats = {s['name']: s['value'] for s in item.get('allStats', [])}
    print(f'{p:25s} Goals:{stats.get(\"Goals\",0)} Games:{stats.get(\"Games\",0)}')"
```
✅ Expected: All squad players appear (scorers with goals, non-scorers with Games:1)

### 5. Events
```bash
curl -s "$BASE/fixture/{fixtureId}/events" | python3 -c "
import sys, json; d=json.loads(sys.stdin.read())
items = d.get('items', [])
home = len([e for e in items if e.get('isHomeEvent')]); away = len(items) - home
print(f'Events: {len(items)} (Home:{home} Away:{away})')"
```
✅ Expected: Event count matches score

### 6. Website Visual Check
- `https://easychamp.com/observe/competition/{champId}?tabs=participants`
- `https://easychamp.com/observe/competition/{champId}?tabs=standings`
- `https://easychamp.com/observe/competition/{champId}?tabs=schedule`
- `https://easychamp.com/observe/competition/{champId}?tabs=stats`
- `https://easychamp.com/observe/league/{leagueId}?tabs=news`

## Common Pitfalls
1. **Event Player needs FullName + Id + SportKindName** — API returns 400 validation error without all three
2. **Scores must be STRING** — `"3"` not `3`
3. **MatchDayName must be STRING** — `"1"` not `1`
4. **Team ExternalIds = team names** — Existing teams use their NAME as ExternalId
5. **Swagger hides Fixtures on Group** — The property exists (confirmed via reflection), Swagger just doesn't show it
6. **Standings only includes teams with fixtures** — Must manually add zero-stat entries for bye-week teams
7. **Each fixture and event needs a unique Id** — Prevents duplicates on re-import
8. **Squad `IsPlayed: true`** required for "Games" stat to count
9. **News with HTML** — Import validation requires non-empty `Body`/`Description`. Easier to insert directly into MongoDB.
10. **UUID representation** — Use `UuidRepresentation.STANDARD` when connecting with pymongo
11. **`fixturesProcessed: 0` in response** — This is misleading. Fixtures ARE processed; the counter just doesn't track them.
12. **Always pass `ownerId` query parameter** — Without it, import uses `ImportConstants.DefaultOwnerId` (`f9fe7636...`) which creates duplicate teams and assigns wrong ManagerIds. The champ won't appear under the correct league on the website.
13. **Clean up duplicate teams** after failed imports — Check `db.teams.find({Name: "TeamName"})` for duplicates. Keep the one with the correct OwnerId.
14. **Player history duplicates on reimport** — The import calls `AddManyHistoryAsync` with `appendHistory: true`, adding a new history entry EVERY time. If you reimport a champ multiple times, players get duplicate history entries. **Must clean up player History[] after deleting a champ** (see Deletion procedure below).

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

## News Article Guide

### VideoUrl Field
Set the `VideoUrl` field on the news document to the game highlights YouTube URL (e.g., `https://youtu.be/UZmmD6TzHDA`). EasyChamp uses this as the news thumbnail/preview. **Always set this when highlights are available** — it's better than a blank image.

```python
news["VideoUrl"] = "https://youtu.be/VIDEO_ID"  # Highlights URL
```

### HTML Style Guide (Light + Dark Theme Compatible)

⚠️ **CRITICAL: Use `color:inherit` for all text, NEVER hardcoded dark colors like `#333` or `#1a1a2e`.**
The EasyChamp website supports light and dark themes. Hardcoded dark text colors become invisible on dark backgrounds.

**Rules:**
- **All text**: `color:inherit` (inherits from theme)
- **Reduced emphasis text**: `color:inherit;opacity:0.85` (body), `opacity:0.5` (captions)
- **Backgrounds**: Use `rgba()` with low alpha, NOT solid colors like `#f0f4ff` — those look wrong on dark theme
  - Scorer cards: `background:rgba(49,95,211,0.12)` (blue), `background:rgba(211,47,47,0.12)` (red)
  - Neutral sections: `background:rgba(128,128,128,0.1)`
  - Borders: `border:1px solid rgba(128,128,128,0.2)`
- **Links**: `color:#5b8af5` (works on both themes)
- **Accent text** (team headers): `color:#315FD3` (blue) or `color:#d32f2f` (red) — these are bright enough for both
- **Header banner**: Dark gradient is fine — it's self-contained with white text
- **YouTube embed**: responsive iframe `padding-bottom:56.25%`
- **Section title**: Change "Full Game" to "Game Highlights" when using highlights URL

**DON'T use:**
- `color:#333` — invisible on dark theme ❌
- `color:#1a1a2e` — invisible on dark theme ❌
- `background:#f0f4ff` — looks jarring on dark theme ❌
- `background:#fff5f5` — looks jarring on dark theme ❌
- `background:white` — breaks dark theme ❌
- `border:1px solid #ddd` — barely visible on dark theme ❌

**DO use:**
- `color:inherit` — adapts to theme ✅
- `color:inherit;opacity:0.85` — subtle body text ✅
- `background:rgba(128,128,128,0.1)` — theme-neutral ✅
- `border:1px solid rgba(128,128,128,0.2)` — works on both ✅
