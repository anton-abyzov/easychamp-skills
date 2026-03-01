# Common Pitfalls - EasyChamp Tournament Import

All pitfalls discovered during production imports. Each has been encountered at least once and caused real issues.

## 1. Score Field Types

Scores MUST be strings in MongoDB. Using integers causes serialization errors (HTTP 500).

```json
// WRONG
"HomeTeamScore": 5

// CORRECT
"HomeTeamScore": "5"
```

## 2. Penalty Score Types

Penalty scores follow the same rule - MUST be strings.

```json
// WRONG - causes HTTP 500
"HomePenaltyScore": 2,
"AwayPenaltyScore": 3

// CORRECT
"HomePenaltyScore": "2",
"AwayPenaltyScore": "3"
```

Also requires:
- `HasPenalties: true`
- `WinnerTeamId: "guid-string"` (winner of the penalty shootout)
- `PeriodScores: [{ Type: "penalties", Home_score: "2", Away_score: "3" }]`

## 3. MatchDayName Format (Playoffs)

Must be lowercase, no hyphens, must match PlayoffStage enum exactly.

```json
// WRONG
"MatchDayName": "Quarter-Final"
"MatchDayName": "SEMIFINAL"
"MatchDayName": "Semi-Finals"

// CORRECT
"MatchDayName": "quarterfinal"
"MatchDayName": "semifinal"
"MatchDayName": "final"
```

## 4. Event Type Naming

EasyChamp uses "scorer" internally, not "goal".

```json
// WRONG
"EventType": "goal"

// CORRECT
"EventType": "scorer"
```

## 5. Player ID Consistency

The same player must have the SAME ID everywhere they appear - events, squads, team rosters.

```json
// WRONG - different IDs for same player
Events: [{ Player: { Id: "abc123" } }]
HomeSquad: [{ Player: { Id: "xyz789" } }]  // MISMATCH

// CORRECT - same ID everywhere
Events: [{ Player: { Id: "abc123" } }]
HomeSquad: [{ Player: { Id: "abc123" } }]  // MATCH
```

## 6. Squad Population

Include ALL team members in squads, not just scorers. The import service only adds scorers from events to squads automatically, losing non-scoring players.

```json
// WRONG - only scorers
"HomeSquad": [{ "Player": { "FullName": "K. Moosa" } }]

// CORRECT - full roster
"HomeSquad": [
  { "Player": { "FullName": "K. Moosa" }, "IsPlayed": true },
  { "Player": { "FullName": "L. Peralta" }, "IsPlayed": true },
  { "Player": { "FullName": "J. Doe" }, "IsPlayed": true },
  { "Player": { "FullName": "M. Smith" }, "IsPlayed": false }
]
```

## 7. Duplicate Players Across Teams

Players on multiple teams need unique IDs per team to avoid cross-team linking.

```json
// WRONG - same ID for player on two teams
Team A: [{ Id: "abc123", Name: "F. Gutierrez" }]
Team B: [{ Id: "abc123", Name: "F. Gutierrez" }]

// CORRECT - unique ID per team
Team A: [{ Id: "abc123-teamA", Name: "F. Gutierrez" }]
Team B: [{ Id: "abc123-teamB", Name: "F. Gutierrez" }]
```

## 8. Scorer String Parsing

Handle multiple separator formats and multiplier patterns:

```python
# Separators: semicolons AND commas
"K. Moosa; L. Peralta"  # semicolons
"K. Moosa, L. Peralta"  # commas

# Multipliers
"5x K. Moosa"    # prefix multiplier = 5 goals
"K. Moosa x5"    # suffix multiplier = 5 goals

# Skip these entries
"walk over"      # Not a player
"forfeit"        # Not a player
""               # Empty
```

## 9. Walk Over / Forfeit Games

Don't create fake player entries for forfeits.

```json
// WRONG
"Events": [{ "Player": { "FullName": "Walk Over" } }]

// CORRECT
"Events": []  // Empty array, set scores to reflect result
```

## 10. Fixture Order Field via API

`PUT /fixture/{id}/score` silently ignores the `Order` field. It returns 200 but Order is not saved.

```bash
# WRONG - Order is NOT saved
curl -X PUT /fixture/{id}/score -d '{"Order": 4}'

# CORRECT - Update Order directly in MongoDB
db.fixtures.updateOne(
  { _id: "fixture-id-string" },
  { $set: { Order: 4 } }
)
```

Root cause: `UpdateFixtureScoreAsync` in `SharedFixtureService.cs` doesn't process the Order field. Only `UpdateOneAsync` in `FixtureService.cs` (line 853) handles it, but it has no direct API endpoint.

## 11. Champ.TeamRefs Logos

RabbitMQ `UpdateImage` consumer updates `groups.TeamRefs` and `fixtures.HomeTeam/AwayTeam` but does NOT update `champs.TeamRefs`. Must update directly in MongoDB.

```javascript
// Fix champ team logos
db.champs.updateOne(
  { _id: ObjectId("champId"), "TeamRefs.Id": "teamId" },
  { $set: { "TeamRefs.$.ImageUrl": "new-url" } }
)
```

## 12. PeriodScores Type Field

Must be lowercase "penalties" for penalty shootout display.

```json
// WRONG
"PeriodScores": [{ "Type": "Penalties" }]
"PeriodScores": [{ "Type": "penalty" }]

// CORRECT
"PeriodScores": [{ "Type": "penalties", "Home_score": "2", "Away_score": "3" }]
```

## 13. Player.OtherFullName Required

The API requires `OtherFullName` to be present. Can be empty string but must not be omitted.

```json
// WRONG - field omitted
{ "FullName": "K. Moosa", "SportKindName": "Soccer" }

// CORRECT - empty string is fine
{ "FullName": "K. Moosa", "OtherFullName": "", "SportKindName": "Soccer" }
```

## 14. MongoDB _id Types

Fixture `_id` is stored as string in MongoDB, not UUID/ObjectId. Use string queries.

```python
# WRONG
db.fixtures.find_one({"_id": UUID("75980061-...")})

# CORRECT
db.fixtures.find_one({"_id": "75980061-..."})
```

## 15. MongoDB Collection Names

Collection names are lowercase: `fixtures`, `champs`, `groups`, `stages`, `teams`.

```python
# WRONG
db.Fixture.find()  # 0 results

# CORRECT
db.fixtures.find()  # All fixtures
```

## 16. Events Not Imported (ChampTeamId Missing)

**Fixed 2026-02-12** in `ImportLeagueService.cs`.

The event import code computed `champTeamId` via `GetChampTeamIdFromFixtureByPlayerId()` but never assigned it to `eventDto.ChampTeamId`. Events were created with `ChampTeamId = Guid.Empty`, causing silent failure (events not visible on fixtures).

```csharp
// BEFORE (broken) - eventDto.ChampTeamId was never set
var champTeamId = GetChampTeamIdFromFixtureByPlayerId(player.Id, existingFixture);
var champTeamPlayer = await _champTeamPlayerService.GetChampTeamPlayer(champTeamId, player.Id);
eventDto.ChampTeamPlayerId = champTeamPlayer.Id;
eventDto.PlayerId = player.Id;
// ChampTeamId is Guid.Empty here!

// AFTER (fixed) - must explicitly set ChampTeamId
eventDto.ChampTeamId = champTeamId;  // THIS LINE WAS MISSING
```

## 17. PeriodScores AutoMapper Field Name Mismatch

**Fixed 2026-02-12** in `ApiCoreImportEntityProfile.cs`.

Import model uses PascalCase (`HomeScore`/`AwayScore`) but DTO uses snake_case (`Home_score`/`Away_score`). AutoMapper convention-based mapping doesn't match these, so PeriodScores were created with null values.

```csharp
// Must add explicit mapping in AutoMapper profile
CreateMap<PeriodScore, PeriodScoreDto>()
    .ForMember(dest => dest.Home_score, source => source.MapFrom(s => s.HomeScore))
    .ForMember(dest => dest.Away_score, source => source.MapFrom(s => s.AwayScore));
```

## 18. Team Logos Not Updated on Reimport

**Fixed 2026-02-12** in `ImportTeamsService.cs`.

The `ImportTeamsService` had a dead code bug where the team update branch was unreachable. The original code checked `if (existingTeam != null)` followed by `else if (existingTeam == null)`, covering all cases - the `else if (...)` update branch could never execute.

Fix: Restructure to `if (null) → create; else if (needs update) → update; else → skip`. Added `existingTeam.ImageUrl != team.ImageUrl` condition to trigger updates when logos change.

## 19. PeriodScores Required for Penalty Display

The frontend reads penalties ONLY from `fixture.periodScores.find(x => x.type === "penalties")` (in `ec-webcore-lib/src/utils/score.ts`). Setting `HomePenaltyScore`/`AwayPenaltyScore` string fields is NOT sufficient - `SharedFixtureService.cs` actually CLEARS those fields when `PeriodScores` list is empty.

```json
// WRONG - penalty fields set but PeriodScores missing
{
  "HomePenaltyScore": "2",
  "AwayPenaltyScore": "3"
}

// CORRECT - MUST include PeriodScores
{
  "HomePenaltyScore": "2",
  "AwayPenaltyScore": "3",
  "PeriodScores": [
    { "HomeScore": "4", "AwayScore": "4", "Type": "regular_period", "Number": 1 },
    { "HomeScore": "2", "AwayScore": "3", "Type": "penalties", "Number": 2 }
  ]
}
```

## 20. ExternalId Refresh Rules for Reimport

When reimporting (delete + recreate), only refresh structural IDs - NOT team/player IDs:

- **Refresh**: League, Champ, Stage, Group, Fixture, Event IDs (structural hierarchy)
- **Keep**: Team and Player ExternalIds (used for matching existing global entities)

If team/player ExternalIds are refreshed, new duplicates are created instead of reusing existing entities.

## 21. Import Idempotency (League Level)

`ImportLeagueService.cs` checks `if (existingChampLeague != null) return;` at lines 100-105. This means once a league ExternalId exists, the entire import is silently skipped - no updates.

To reimport: delete the league first (`DELETE /champ-leagues/{id}?forceDelete=true`), then import with fresh structural ExternalIds.

## 22. Duplicate League Creation (League.Id / ExternalId Mismatch)

**CRITICAL**: The `League.Id` field in the import JSON becomes the league's `ExternalId` in MongoDB. The import service uses this to find existing leagues.

For PS23 Soccer League, ALWAYS use:
```json
"League": {
  "Id": "PS23 Soccer League",
  "Name": "PS23 Soccer League"
}
```

**NEVER** use the league's MongoDB `_id` (e.g., `8f541539-...`) as the `League.Id`. This creates a new league with `ExternalId` = that UUID, instead of matching the existing one with `ExternalId` = `"PS23 Soccer League"`.

**What happened (2026-03-01)**: C108 import used a generated UUID as `League.Id`, creating a duplicate league. C108 ended up under the wrong league and 404'd on the original league's page. Fixed by manually updating `ChampLeagueRef` in MongoDB and deleting 4 duplicate league entries.

**Algorithm for finding existing league**:
1. Query `champLeagues.findOne({ExternalId: "PS23 Soccer League"})` 
2. If found → use its `_id` and full ref object as `ChampLeagueRef`
3. If not found → the import will create it (first time only)
4. **NEVER pass a league _id as ExternalId** — this chains duplicates

## 23. GHA Concurrency Cancellation

Pushing rapidly to the same branch may cancel in-progress GHA builds. The latest push's build includes all prior commits, so only the last build's Docker image matters. But be aware that cancelled builds mean intermediate commits are never independently deployed.
