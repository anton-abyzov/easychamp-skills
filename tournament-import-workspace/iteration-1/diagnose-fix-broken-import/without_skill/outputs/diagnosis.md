# Diagnosis of broken-import.json

## Issues Found and Fixed

### 1. Stage Type uses string values instead of numeric enums
- **Location**: `Stages[0].Type` and `Stages[1].Type`
- **Broken**: `"Type": "League"` and `"Type": "Playoff"`
- **Fixed**: `"Type": 0` (League/Group stage) and `"Type": 1` (Playoff/Knockout stage)
- **Impact**: The system cannot determine stage rendering mode. League stages render as tables; Playoff stages render as brackets. String values are not recognized, so neither mode works correctly. This directly causes the broken bracket visualization.

### 2. EventType uses string values instead of numeric enums
- **Location**: `Events[].EventType` in fixture-1
- **Broken**: `"EventType": "goal"`
- **Fixed**: `"EventType": 0` (Goal = 0 in the event type enum)
- **Impact**: Goal events are not recognized by the system because it expects numeric enum values. This is why goal events are not showing up in the match details.

### 3. Minute field is a string instead of an integer
- **Location**: `Events[].Minute` in fixture-1
- **Broken**: `"Minute": "15"` and `"Minute": "67"`
- **Fixed**: `"Minute": 15` and `"Minute": 67`
- **Impact**: Event timeline rendering may fail or sort incorrectly when the minute value is a string instead of a number. This contributes to goal events not displaying properly.

### 4. Playoff fixtures have duplicate MatchDay values (broken bracket)
- **Location**: `Stages[1].Groups[0].Fixtures` (the Playoff stage)
- **Broken**: Both Quarter-Final (`fixture-qf1`) and Semi-Final (`fixture-sf1`) have `"MatchDay": 1`
- **Fixed**: Quarter-Final keeps `"MatchDay": 1`, Semi-Final changed to `"MatchDay": 2`
- **Impact**: Bracket visualization relies on MatchDay to determine which round a fixture belongs to. When both rounds share the same MatchDay, the bracket renderer cannot distinguish rounds, causing all matches to collapse into a single column. This is a primary cause of the broken bracket.

### 5. PeriodScores Type uses string instead of numeric enum
- **Location**: `PeriodScores[0].Type` in fixture-qf1
- **Broken**: `"Type": "Penalties"`
- **Fixed**: `"Type": 4` (Penalties period type enum)
- **Impact**: The system cannot identify the period type, so penalty shootout scores may not render correctly. This contributes to scores not displaying properly for matches that went to penalties.

### 6. Semi-Final teams missing required fields (SportKindName, ImageUrl)
- **Location**: `Stages[1].Groups[0].Fixtures[1]` (fixture-sf1) HomeTeam and AwayTeam
- **Broken**: HomeTeam and AwayTeam objects only contain `Id` and `Name`
- **Fixed**: Added `"ImageUrl": null` and `"SportKindName": "Soccer"` to both teams
- **Impact**: Missing required team fields can cause rendering errors or data validation failures when the system tries to display team information in the bracket or match details.

## Summary

The root causes map to the three reported symptoms:

| Symptom | Root Causes |
|---|---|
| Scores not displaying properly | PeriodScores Type as string (#5) |
| Bracket visualization broken | Stage Type as string (#1), duplicate MatchDay in playoff rounds (#4) |
| Goal events not showing up | EventType as string (#2), Minute as string (#3) |
