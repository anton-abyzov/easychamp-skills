# Diagnosis: broken-import.json

## Issues Found: 11

### Issue 1: Champs array at root level instead of inside League (CRITICAL - silent failure)

**Location**: Root-level `Champs` array
**Problem**: The `Champs` array is placed at the JSON root alongside `League`, but the API deserializer expects `Champs` nested inside the `League` object. This causes the API to return 200 OK but import 0 champs (silent failure).
**Reference**: Common Pitfall #23
**Fix**: Moved `Champs` array inside the `League` object.

### Issue 2: Score fields are integers instead of strings (CRITICAL - causes HTTP 500)

**Location**: All fixtures - `HomeTeamScore`, `AwayTeamScore`
**Problem**: Scores are integers (e.g., `2`, `1`, `3`) but MongoDB requires strings. Integer scores cause serialization errors and HTTP 500 responses.
**Reference**: Common Pitfall #1, Data Types table
**Fix**: Changed all score values to strings: `"2"`, `"1"`, `"3"`, `"0"`.

### Issue 3: EventType is "goal" instead of "scorer" (events won't display)

**Location**: `fixture-1` Events array, both events
**Problem**: `"EventType": "goal"` is not recognized by EasyChamp. The system uses `"scorer"` internally.
**Reference**: Common Pitfall #4
**Fix**: Changed `"goal"` to `"scorer"` on both events.

### Issue 4: MatchDayName format wrong for playoff fixtures (bracket won't render)

**Location**: `fixture-qf1` has `"Quarter-Final"`, `fixture-sf1` has `"Semi-Final"`
**Problem**: Playoff MatchDayName values must be lowercase with no hyphens, matching the PlayoffStage enum exactly. Invalid values cause fixtures to be skipped during bracket tree generation.
**Reference**: Common Pitfall #3, Knockout Bracket `PLAYOFF_STAGES_ORDER` mapping
**Fix**: Changed to `"quarterfinal"` and `"semifinal"`.

### Issue 5: Missing Order field on playoff fixtures (bracket won't render)

**Location**: Both playoff fixtures (`fixture-qf1`, `fixture-sf1`)
**Problem**: The `fillTree` algorithm's first pass matches `fixture.order == node.nodeId`. Without Order values, fixtures fall through to sequential fill which produces incorrect placement or empty brackets.
**Reference**: Knockout Bracket documentation, binary tree node mapping
**Fix**: Added `"Order": 4` to QF fixture (quarterfinal node 4) and `"Order": 2` to SF fixture (semifinal node 2).

### Issue 6: Penalty scores are integers instead of strings (causes HTTP 500)

**Location**: `fixture-qf1` - `HomePenaltyScore: 5`, `AwayPenaltyScore: 4`
**Problem**: Same as regular scores - penalty scores must be strings in MongoDB.
**Reference**: Common Pitfall #2
**Fix**: Changed to `"5"` and `"4"`.

### Issue 7: PeriodScores Type is "Penalties" (capital P) instead of "penalties"

**Location**: `fixture-qf1` PeriodScores array
**Problem**: The frontend reads penalties from `periodScores.find(x => x.type === "penalties")`. Capital "Penalties" won't match.
**Reference**: Common Pitfall #12
**Fix**: Changed `"Type": "Penalties"` to `"Type": "penalties"`.

### Issue 8: PeriodScores missing regular_period entry and scores are integers

**Location**: `fixture-qf1` PeriodScores array
**Problem**: Two sub-issues: (a) Only has a penalties entry, missing the `regular_period` entry showing the regulation-time score. (b) `HomeScore`/`AwayScore` values are integers (`5`, `4`) instead of strings. The regular_period entry is needed for proper penalty display formatting ("X-X (pen Y-Z)").
**Reference**: Common Pitfall #19, Data Types table
**Fix**: Added `regular_period` entry with `"HomeScore": "2", "AwayScore": "2"` (the regulation-time score). Changed penalties entry scores to strings. Added `Number` fields (1 for regular_period, 2 for penalties).

### Issue 9: Missing OtherFullName on all Player objects

**Location**: Every Player object throughout the file
**Problem**: The API requires `OtherFullName` to be present on Player objects. It can be an empty string but must not be omitted. Missing field causes import errors.
**Reference**: Common Pitfall #13
**Fix**: Added `"OtherFullName": ""` to all Player objects.

### Issue 10: Missing WinnerTeamId on penalty shootout fixture

**Location**: `fixture-qf1`
**Problem**: Penalty fixtures require `WinnerTeamId` to identify the shootout winner. Without it, the winner highlight won't display correctly.
**Reference**: Common Pitfall #2
**Fix**: Added `"WinnerTeamId": "team-atlas"` (home team won 5-4 on penalties).

### Issue 11: Missing SportKindName on semifinal team objects

**Location**: `fixture-sf1` HomeTeam and AwayTeam
**Problem**: The HomeTeam and AwayTeam objects in the semifinal fixture are missing `SportKindName`. All team references should include this field for proper entity matching.
**Reference**: League import template, Common Pitfall #23
**Fix**: Added `"SportKindName": "Soccer"` to both team objects. Also added `ImageUrl: null` for consistency.

---

## Summary of Changes

| Category | Issues | Impact |
|----------|--------|--------|
| JSON structure | Champs placement (#1) | 0 champs imported (silent failure) |
| Data types | Scores as integers (#2, #6, #8) | HTTP 500 errors |
| Event naming | EventType "goal" (#3) | Events invisible |
| Bracket rendering | MatchDayName format (#4), missing Order (#5) | Broken bracket visualization |
| Penalty display | PeriodScores Type case (#7), missing regular_period (#8) | Penalty scores not displayed |
| Player data | Missing OtherFullName (#9) | Import errors |
| Penalty metadata | Missing WinnerTeamId (#10) | No winner highlight |
| Team completeness | Missing SportKindName (#11) | Team matching issues |
