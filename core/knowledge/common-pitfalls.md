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
