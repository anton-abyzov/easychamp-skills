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
| `champTeamPlayers` | Player registrations per champ | `_id`, `Player`, `ChampTeamId`, `ChampRef` |
| `players` | Global player records | `_id`, `FullName`, `ExternalId` |
| `teams` | Global team records | `_id`, `Name`, `ExternalId`, `ImageUrl` |

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

## Step-by-Step: Creating a New Competition

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
fixture = {
    "_id": str(uuid.uuid4()),
    "Version": 0,
    "AddedAtUtc": now,
    "UpdatedAtUtc": now,
    "CreatedBy": "IntegrationWorker",
    "ExternalId": "unique-fixture-id",
    "Date": datetime(2026, 2, 17, 5, 0, 0),
    "HomeTeamScore": "3",   # STRING!
    "AwayTeamScore": "1",   # STRING!
    "Status": 2,            # 2 = Finished
    "MatchDay": 1,
    "MatchDayName": "1",    # STRING!
    "HomeTeam": make_team_ref("Team Name"),  # Full embedded object
    "AwayTeam": make_team_ref("Other Team"),
    "GroupRef": {"_id": "group-guid", "Version": 0},
    "StageRef": {"_id": "stage-guid", "Version": 0, "Name": "Group Stage"},
    "ChampRef": {"_id": "champ-guid", "Version": 0, "Name": "Champ Name"},
    "ChampLeagueRef": league_ref,
    "HomeSquad": [],  # Squad entries from ChampTeamPlayers
    "AwaySquad": [],
    "RefereeRefs": [],
    "IsImportCompleted": True,
    "IsProcessing": False,
}
```

**After inserting fixtures**, update refs:
```python
# Update group
groups_coll.update_one({"_id": GROUP_ID}, {"$set": {"FixtureRefs": [{"_id": fix_id, "Version": 0}]}})
# Update stage
stages_coll.update_one({"_id": STAGE_ID}, {"$set": {"FixturesRefs": [{"_id": fix_id, "Version": 0}]}})
```

### Phase 4: Recalculate Standings
```bash
curl -X POST "http://127.0.0.1:5010/ec-standings-api/recalculate/champ/{champId}/standings"
```
This is **critical** — standings are NOT auto-calculated from MongoDB inserts. The API must recalculate them.

### Phase 5: Create Events (Goals)
```python
event = {
    "_id": str(uuid.uuid4()),
    "Minute": "0",          # STRING, not int!
    "EventType": "scorer",
    "Type": 2,               # Goal
    "Points": 1,
    "IsHomeEvent": True,
    "FixtureRef": {"_id": fixture_id, "Version": 0},
    "ChampRef": {"_id": champ_id, "Version": 0, "Name": "..."},
    "ChampLeagueRef": league_ref,
    "PlayerRef": {"_id": player_id, "Version": 0, "FullName": "Player Name"},
    "ChampTeamPlayerId": "ctp-guid",
    # ... other fields
}
```

### Phase 6: Create News
```python
news = {
    "_id": str(uuid.uuid4()),
    "Title": "Match Day 1: ...",
    "Description": "<html content>",
    "ContentType": 1,
    "IsPublic": True,
    "IsPublished": True,
    "Categories": [
        {"EntityId": champ_id, "Type": 0},
        {"EntityId": league_id, "Type": 2}
    ],
    "SportKindRef": {"_id": "05684792-9662-4e9f-a163-8545e5736c3d", "Version": 0, "Name": "Soccer"},
    "Date": datetime(2026, 2, 17),
}
```

## Common Pitfalls
1. **Minute must be STRING** — `"0"` not `0`. Causes BsonType deserialization error.
2. **Scores must be STRING** — `"3"` not `3`.
3. **Team ExternalIds** — Existing teams use their NAME as ExternalId.
4. **Import uses `Teams` not `ChampTeams`** — The swagger shows `teams`, the import model field is `Teams`.
5. **Group.Fixtures not deserialized** — The import endpoint doesn't process fixtures inside groups.
6. **After MongoDB inserts, recalculate standings** — `POST /recalculate/champ/{id}/standings`
7. **Dev auth bypass** — The middleware uses "Admin" role but the validator checks "Administrator" and "SystemAdmin".
8. **UUID representation** — Use `UuidRepresentation.STANDARD` when connecting with pymongo.

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
