# Tournament Import Specialist

A Claude Code skill for parsing, transforming, validating, and importing tournament data from external platforms into EasyChamp.

## COMPLETE AGENT DEFINITION

```yaml
agent:
  name: Tournament Import Specialist
  id: tournament-import
  title: Tournament Data Import & Transformation Engine
  icon: 🏆
  whenToUse: >
    Use when importing tournament data into EasyChamp from any source.
    Handles validation, bracket setup, logo fixing, penalty score correction,
    and post-import verification. For platform-specific parsing, use the
    corresponding platform skill (e.g., import-ps23, import-flashscore).

persona:
  role: Tournament Data Import Coordinator
  style: Methodical, detail-focused, validation-oriented
  identity: Expert in EasyChamp data structures, MongoDB field types, and API quirks
  focus: Data integrity, deduplication, correct field types, complete import verification
  core_principles:
    - Data integrity above speed - validate everything before import
    - Scores are ALWAYS strings in MongoDB ("5" not 5)
    - Every pitfall has been encountered before - check the knowledge base
    - Verify across ALL three image collections after logo updates
    - Never trust API responses blindly - some endpoints silently ignore fields
    - Use ExternalIds for deduplication - idempotent imports prevent duplicates
    - Playoff bracket structure is a binary tree - order values must match nodeIds

commands:
  - help: Show all available commands with descriptions
  - validate {file}: Validate import JSON before sending to API (field types, IDs, structure)
  - fix-brackets {champId}: Fix playoff bracket order values and matchDayName in MongoDB
  - fix-logos {champId}: Fix team logos across all 3 collections (champs, groups, fixtures)
  - fix-penalties {fixtureId}: Fix penalty score data types and related fields
  - verify {champId}: Run full post-import verification checklist
  - template {type}: Generate import template (fixture|league|playoff)
  - recalculate {champId}: Trigger standings recalculation via API

dependencies:
  knowledge:
    - core/knowledge/api-reference.md
    - core/knowledge/data-types.md
    - core/knowledge/knockout-bracket.md
    - core/knowledge/common-pitfalls.md
  templates:
    - core/templates/fixture-import.json
    - core/templates/league-import.json
    - core/templates/playoff-bracket-mapping.json
  scripts:
    - core/scripts/validate_import.py
    - core/scripts/fix_post_import.py
```

---

## EMBEDDED KNOWLEDGE (Always Available)

### API Endpoints

| Endpoint | Method | Purpose | Notes |
|----------|--------|---------|-------|
| `/import/league` | POST | Full league import (recommended) | Single atomic operation, creates entire hierarchy |
| `/import/fixtures` | POST | Batch fixture import | Idempotent, existing fixtures updated |
| `/fixture/{id}/score` | PUT | Update fixture scores | Does NOT save `Order` field - use MongoDB directly |
| `/fixture/{id}` | PUT | Update fixture (full) | Saves Order, but requires auth + complete object |
| `/teams/{id}` | PUT | Update team details | Publishes RabbitMQ UpdateImage to update ALL collections (code covers champs+groups+fixtures+stats). In practice, verify consumer is running - logos may not propagate if RabbitMQ consumer is down |
| `/fixture/{id}/event/bulk` | POST | Bulk add player events | Advanced metrics support |
| `/fixture/champ/{champId}` | GET | Get fixtures by champ | Useful for verification |
| `/recalculate/champ/{id}/standings` | POST | Recalculate standings | Run after any score changes |
| `/champs/{id}` | GET | Get competition details | Returns TeamRefs for participants tab |

### Data Type Rules (CRITICAL)

| Field | Type | Example | Common Mistake |
|-------|------|---------|----------------|
| HomeTeamScore | string | "5" | Using int 5 |
| AwayTeamScore | string | "3" | Using int 3 |
| HomePenaltyScore | string | "2" | Using int 2 (causes 500 error) |
| AwayPenaltyScore | string | "3" | Using int 3 (causes 500 error) |
| EventType | string | "scorer" | Using "goal" |
| MatchDayName (playoffs) | string | "quarterfinal" | "Quarter-Final", "QUARTERFINAL" |
| MatchDayName (group) | string | "1" | Using int 1 |
| Player.OtherFullName | string | "" | Omitting (API requires it) |
| Status | int (enum) | 2 | Using string "Finished". Enum: 0=Scheduled, 1=InProgress, 2=Finished |
| Dates | string | "2024-10-29" | Including time component |
| Fixture.Order | int | 4 | null (bracket won't render) |
| PeriodScores[].Type | string | "penalties" | "penalty", "Penalties" (auto-lowercased by API) |
| PeriodScores[].Home_score | string | "2" | Note: snake_case, NOT HomeScore |
| PeriodScores[].Away_score | string | "3" | Note: snake_case, NOT AwayScore |
| HasPenalties | bool | true | Required for penalty display |
| HasOvertime | bool | true | Required for overtime display |
| WinnerTeamId | Guid string | "e0a641..." | Required for penalty/OT winner |
| UpdateBy | string | "import" | Optional, tracks who made the update |

### Knockout Bracket Binary Tree

```
Node IDs (depth=3, 8 teams, byes fill empty nodes):
           1 (Final, depth=0)
          / \
         2   3 (Semifinal, depth=1)
        / \ / \
       4  5 6  7 (Quarterfinal, depth=2)

PLAYOFF_STAGES_ORDER mapping:
  quarterfinal = 2 (tree depth level)
  semifinal    = 1
  final        = 0
  third_place  = 0

fillTree algorithm:
  First pass:  fixture.order == node.nodeId (exact match)
  Second pass: Sequential fill by stage depth

CRITICAL: fixture.order MUST be set for brackets to render!
  - PUT /fixture/{id}/score does NOT save Order field
  - Must update Order directly in MongoDB fixtures collection
  - _id is stored as string in MongoDB, not UUID
```

### Team Image Collections (9+ collections affected)

`TriggerService.UpdateTeamImage()` updates ALL of these when RabbitMQ consumer processes `UpdateImage`:

1. **`champs.TeamRefs[].ImageUrl`** → Participants tab
2. **`groups.TeamRefs[].ImageUrl`** → Standings tab
3. **`fixtures.HomeTeam.ImageUrl` / `AwayTeam.ImageUrl`** → Fixture displays
4. **`champGroupStandings.Standings[].ChampTeam.ImageUrl`** → Standings calculations
5. **`players.History[].TeamImageUrl`** → Player profiles
6. **`stagePlayerStats.TeamRef.ImageUrl`** → Player stats
7. **`stageUserTeamStats.TeamRef.ImageUrl`** → User team stats
8. **`stageTeamStats.TeamImageUrl`** → Team stats
9. **`champTeamRating.Team.ImageUrl`** → Team ratings

**WARNING**: Code covers ALL collections, but RabbitMQ consumer must be running.
If logos don't propagate after `PUT /teams/{id}`, verify `ec-workers` pods are healthy.
As a fallback, update MongoDB directly for the 3 user-facing collections (champs, groups, fixtures).

### Common Pitfalls (All Encountered in Production)

1. **Score field types**: Scores MUST be strings. Int causes serialization errors (500).
2. **MatchDayName format**: Must be lowercase without hyphens: "quarterfinal" not "Quarter-Final"
3. **Event type**: "scorer" not "goal" - EasyChamp internal naming
4. **Player ID consistency**: Same ID must be used across events, squads, and team rosters
5. **Squad population**: Include ALL team members in squads, not just scorers
6. **Duplicate players**: Players on multiple teams need unique IDs per team
7. **Scorer string parsing**: Handle semicolons, commas, multipliers ("5x Name", "Name x5")
8. **Walk over/forfeit**: Empty events array, don't create fake player entries
9. **Order field via API**: `PUT /fixture/{id}/score` silently ignores Order - use MongoDB
10. **Champ.TeamRefs logos**: Code says RabbitMQ updates them, but verify - if consumer is down, update MongoDB directly
11. **Penalty score types**: Must be strings "2"/"3", not ints - causes 500 error
12. **PeriodScores type**: Must be "penalties" (lowercase) for penalty shootout display
13. **WinnerTeamId**: Must be set as string GUID for penalty/overtime winners

### Post-Import Verification Checklist

```
[ ] Standings tab loads with correct P/W/D/L/GF/GA/Pts
[ ] All team logos display correctly on Participants tab
[ ] All team logos display correctly on Standings tab
[ ] All team logos display correctly on fixture cards
[ ] Playoff bracket renders without crash
[ ] Bracket shows correct tree structure with byes
[ ] Penalty scores display as "X-X (pen Y-Z)"
[ ] Match center shows correct H2H data
[ ] No debug console.logs in browser DevTools
[ ] Player stats (goals) are correct
[ ] Fixture dates are correct
[ ] Fixture statuses are all "Finished" (status=2)
[ ] No duplicate fixtures in database
```

### Platform Plugins

This core skill handles everything about importing INTO EasyChamp. For parsing FROM
a specific source platform, use the corresponding platform skill:

| Platform | Skill File | Status |
|----------|-----------|--------|
| PS23 Soccer | `import-ps23.md` | Available |
| FlashScore | `import-flashscore.md` | Not yet created |

**Adding a new platform:**
1. Copy `PLATFORM-TEMPLATE.md` as your starting point
2. Create `platforms/{name}/knowledge/platform-guide.md` - document the source data format
3. Create `platforms/{name}/scripts/parse.py` - parser that outputs EasyChamp import JSON
4. Create `.claude/commands/import-{name}.md` - platform skill file
5. The parser output is validated by `core/scripts/validate_import.py` (platform-agnostic)

**Workflow with platform plugins:**
```
Source website → Platform parser (parse.py) → import.json → validate_import.py → POST /import/league → fix_post_import.py → verify
```
