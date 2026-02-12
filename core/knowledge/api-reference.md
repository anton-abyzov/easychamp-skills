# EasyChamp API Reference - Import Related Endpoints

Base URL: `https://api.easychamp.com` (or `https://easychamp.com/sc-standing-api`)

## Import Endpoints

### POST /import/league
Full atomic league import. Creates entire hierarchy in one operation.

**Payload:**
```json
{
  "ImportSource": 99,
  "ImportMode": 0,
  "League": {
    "Name": "League Name",
    "Country": "USA",
    "SportKindName": "Soccer",
    "Champs": [{
      "Name": "Tournament Name",
      "StartDate": "2024-10-29",
      "EndDate": "2025-01-28",
      "Stages": [{
        "Name": "Group Stage",
        "Type": "League",
        "Groups": [{
          "Name": "Group A",
          "Fixtures": [...]
        }]
      }]
    }]
  }
}
```

ImportSource values: 99 = ExternalJson
ImportMode values: 0 = Full

### POST /import/fixtures
Batch fixture import. Idempotent - existing fixtures updated, not duplicated.

**Payload:** Array of fixtures with embedded Group.Stage.Champ.League hierarchy.

## Fixture Endpoints

### GET /fixture/{id}
Get single fixture by ID.

### GET /fixture/champ/{champId}
Get all fixtures for a championship.

### PUT /fixture/{id}/score
Update fixture scores. Uses UpdateFixtureDto.

**WARNING**: Does NOT save `Order` field. Use MongoDB directly for order updates.

**Payload (UpdateFixtureDto extends SaveFixtureDto):**
```json
{
  "HomeTeamScore": "5",
  "AwayTeamScore": "3",
  "HomePenaltyScore": "2",
  "AwayPenaltyScore": "3",
  "Status": 2,
  "HasPenalties": true,
  "HasOvertime": false,
  "WinnerTeamId": "guid-string",
  "PeriodScores": [{
    "Home_score": "2",
    "Away_score": "3",
    "Type": "penalties"
  }],
  "Referees": [],
  "Proofs": []
}
```

### POST /fixture/{id}/event/bulk
Bulk add player events with advanced metrics.

## Team Endpoints

### PUT /teams/{id}
Update team details. Publishes RabbitMQ UpdateImage message.

**Collections updated by TriggerService.UpdateTeamImage():**
- champs.TeamRefs, groups.TeamRefs, fixtures.HomeTeam/AwayTeam
- champGroupStandings, players, stagePlayerStats, stageUserTeamStats
- stageTeamStats, champTeamRating

### GET /teams/{id}
Get team details.

## Championship Endpoints

### GET /champs/{id}
Get competition details including TeamRefs (used by Participants tab).

### POST /recalculate/champ/{id}/standings
Trigger standings recalculation. Run after score changes.

## Image Upload

### POST /image
Upload image to Minio S3 storage. Returns relative path.

**Parameters (query string):**
- `entity`: Category - `Teams`, `Players`, `Others`
- `sportKind`: Sport name - `Soccer`, `Basketball`, etc.

**Request:** multipart/form-data with `file` field.

**Response:** Relative path string, e.g., `Teams/Soccer/logo_guid.png`

Full URL: `https://minio.easychamp.com/sportchamp-prod/{relative_path}`

**Image Pipeline (`scripts/image_pipeline.py`):**
```python
from image_pipeline import ImagePipeline

pipeline = ImagePipeline(api_url="http://localhost:15010", sport_kind="Soccer")
updated_json = pipeline.process_import_json(import_data)  # Replaces external URLs with Minio paths
```

Or via CLI flag: `python ps23_data_import.py --upload-images`

## Player History (Transfer History)

Players can have `Histories` array in import JSON for team attachment tracking.

**Import JSON format:**
```json
{
  "FullName": "John Doe",
  "Histories": [{
    "TeamId": "ps23:team:abc123",
    "TeamName": "Team A",
    "StartDate": "2024-04-30",
    "EndDate": "2024-10-15",
    "IsActive": true,
    "ChampId": "ps23:champ:def456",
    "ChampName": "Tournament Name",
    "Type": 0
  }]
}
```

**Fields:** TeamId (required, matches team ExternalId), StartDate (required), EndDate (optional), IsActive (required), Type (0=Player, 1=OnLoan)

ImportPlayersService resolves TeamId and ChampId from external strings to internal GUIDs during import.

## Delete (Force)

### DELETE /champs/{champId}?forceDelete=true
Cascade delete: stages, groups, fixtures, events, stats, ratings, news, favorites, permissions.

### DELETE /champ-leagues/{leagueId}
Delete league (must delete champs first or use separate forceDelete).

## Authentication

Most write endpoints require Bearer token:
```bash
curl -X POST "https://api.easychamp.com/import/league" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d @import.json
```

## MongoDB Direct Access

For fields the API doesn't save (like Order), use pymongo:

```python
from pymongo import MongoClient

client = MongoClient(MONGODB_URI)
db = client['ec-standings-db']

# Update fixture order
db.fixtures.update_one(
    {"_id": "fixture-id-string"},  # _id is STRING, not UUID
    {"$set": {"Order": 4, "MatchDayName": "quarterfinal"}}
)

# Update team logo in champs collection
db.champs.update_one(
    {"_id": ObjectId("champId"), "TeamRefs.Id": "teamId"},
    {"$set": {"TeamRefs.$.ImageUrl": "new-url"}}
)
```
