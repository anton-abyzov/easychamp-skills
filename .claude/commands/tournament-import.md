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
    - All images (logos, photos) MUST be hosted on MinIO, not external URLs

commands:
  - help: Show all available commands with descriptions
  - validate {file}: Validate import JSON before sending to API (field types, IDs, structure)
  - fix-brackets {champId}: Fix playoff bracket order values and matchDayName in MongoDB
  - fix-logos {champId}: Fix team logos across all 3 collections (champs, groups, fixtures)
  - fix-penalties {fixtureId}: Fix penalty score data types and related fields
  - verify {champId}: Run full post-import verification checklist
  - template {type}: Generate import template (fixture|league|playoff)
  - recalculate {champId}: Trigger standings recalculation via API

scripts:
  - scripts/ps23_data_import.py  # Consolidated import pipeline
```

---

## EMBEDDED KNOWLEDGE (Always Available)

### Consolidated Import Pipeline

The main import tool is `scripts/ps23_data_import.py`. It handles the full pipeline:

```bash
# Transform only (write JSON):
python scripts/ps23_data_import.py --input /path/to/data.json

# Multi-competition transform with shared teams:
python scripts/ps23_data_import.py --multi -c C86 C92

# Full pipeline: transform + clean + migrate logos + import + verify:
python scripts/ps23_data_import.py --multi -c C86 C92 \
  --clean --migrate-logos --post-import --validate --validate-brackets

# Verify existing import only:
python scripts/ps23_data_import.py --verify-only

# Dry run (show plan without executing):
python scripts/ps23_data_import.py --multi -c C86 C92 --clean --post-import --dry-run
```

**Flags:**
| Flag | Purpose |
|------|---------|
| `--input / -i` | Input JSON file(s) |
| `--output / -o` | Output JSON file |
| `--competition / -c` | Competition ID(s) - auto-finds in Downloads |
| `--multi` | Combine multiple JSONs into one league import |
| `--validate / -v` | Validate output JSON structure |
| `--validate-brackets` | Print bracket tree and verify team progression |
| `--post-import` | Import to production via Keycloak + API |
| `--clean` | Delete existing league/competitions first |
| `--migrate-logos` | Download external logos → upload to MinIO |
| `--dry-run` | Show what would happen without executing |
| `--verify-only` | Only verify existing import |
| `--kc-user` | Keycloak admin username (default: admin) |
| `--kc-password` | Keycloak password (or KC_ADMIN_PASSWORD env var) |

### API Endpoints

| Endpoint | Method | Purpose | Notes |
|----------|--------|---------|-------|
| `/import/league` | POST | Full league import (recommended) | Single atomic operation, creates entire hierarchy |
| `/import/fixtures` | POST | Batch fixture import | Idempotent, existing fixtures updated |
| `/image` | POST | Upload image to MinIO | Params: entity=Teams, sportKind=Soccer |
| `/fixture/{id}/score` | PUT | Update fixture scores | Does NOT save `Order` field - use MongoDB directly |
| `/fixture/{id}` | PUT | Update fixture (full) | Saves Order, but requires auth + complete object |
| `/fixture/{id}/event/bulk` | POST | Bulk add events to fixture | Use for adding events after structural import |
| `/champs/{id}?forceDelete=true` | DELETE | Hard delete champ + all deps | Cascades: stages, groups, fixtures, events, stats |
| `/teams/{id}` | PUT | Update team details | Publishes RabbitMQ UpdateImage |
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

### Knockout Bracket Binary Tree

```
Node IDs (depth=3, 8 teams, byes fill empty nodes):
           1 (Final, depth=0)
          / \
         2   3 (Semifinal, depth=1)
        / \ / \
       4  5 6  7 (Quarterfinal, depth=2)

Bracket order assignment algorithm:
  1. Final gets Order=1
  2. SF whose winner = Final.HomeTeam → Order=2
  3. SF whose winner = Final.AwayTeam → Order=3
  4. QF whose winner appears in SF(Order=2) → Order=4 or 5
  5. QF whose winner appears in SF(Order=3) → Order=6 or 7

CRITICAL: Fixture.Order property added to ec-apicore-lib v3.0.18
  - AutoMapper now maps Order from import JSON → SaveFixtureDto → MongoDB
  - ec-standings-api must reference apicore-lib >= 3.0.18
```

### Image Hosting (MinIO)

All images MUST be hosted on MinIO (`minio.easychamp.com/sportchamp-prod`):
- Upload via `POST /image?entity=Teams&sportKind=Soccer`
- Returns relative path like `Teams/Soccer/logo_guid.png`
- Full URL: `https://minio.easychamp.com/sportchamp-prod/Teams/Soccer/logo_guid.png`
- Use `--migrate-logos` flag to auto-download external logos and re-upload to MinIO

### Common Pitfalls (All Encountered in Production)

1. **Score field types**: Scores MUST be strings. Int causes serialization errors (500).
2. **MatchDayName format**: Must be lowercase without hyphens: "quarterfinal" not "Quarter-Final"
3. **Event type**: "scorer" not "goal" - EasyChamp internal naming
4. **Player ID consistency**: Same ID must be used across events, squads, and team rosters
5. **Squad population**: Include ALL team members in squads, not just scorers
6. **Duplicate players**: Players on multiple teams need unique IDs per team
7. **Walk over/forfeit**: Empty events array, don't create fake player entries
8. **Order field via API**: Requires ec-apicore-lib >= 3.0.18 (Order property added 2026-02-11)
9. **Penalty score types**: Must be strings "2"/"3", not ints - causes 500 error
10. **External logos**: Never reference external URLs - upload to MinIO first
11. **League ExternalId**: Must be consistent across imports for team reuse
12. **PeriodScores required for penalties**: Frontend reads from `periodScores.find(x => x.type === "penalties")` - NOT from HomePenaltyScore/AwayPenaltyScore fields. Must include PeriodScores with `regular_period` and `penalties` entries
13. **ExternalId refresh on reimport**: Only refresh structural IDs (league/champ/stage/group/fixture/event). Keep team/player IDs to reuse existing global entities
14. **Import is idempotent for teams**: Re-importing updates team logos and player data without needing to delete existing leagues/competitions
15. **Team ImageUrl change detection**: ImportTeamsService only updates when ImageUrl differs from existing value (fixed 2026-02-12)
16. **Champ.Id vs Champ.ExternalId**: `ImportLeagueService.cs:140` uses `Champ.Id` (NOT `Champ.ExternalId`) as the ExternalId filter for existing champ lookup. If an existing champ matches, import skips fixture creation and calls `ImportMissingStages` instead. To reimport fresh: delete first, then use a new `Champ.Id` UUID in JSON
17. **Champ-level vs fixture-level TeamMembers**: ChampTeamPlayers are created from `Champs[].Teams[].TeamMembers` (lines 162-190), NOT from fixture-level TeamMembers. ALL event players MUST appear in the champ-level team roster, otherwise NullReferenceException at line 313
18. **forceDelete endpoint**: `DELETE /champs/{id}?forceDelete=true` cascades ALL dependencies (stages, groups, fixtures, events, stats, ratings, news, favorites, permissions). Use this instead of manual MongoDB deletion. Also: `DELETE /aioptimize/champs/{name}?forceDelete=true`
19. **MongoDB collection names are camelCase**: `champs`, `fixtures`, `events`, `champTeamPlayers`, `champLeagues`, `champGroupStandings` (NOT PascalCase)
20. **Two-phase import workaround**: If events cause NullRef, import WITHOUT events first (all fixtures get created), add missing CTPs to MongoDB, then add events via `POST /fixture/{id}/event/bulk`

### Import Idempotency

The `/import/league` endpoint supports **idempotent re-imports**:
- If `League.ExternalId` exists, reuses existing league and continues processing champs
- If `Champ.ExternalId` exists, still runs team/player imports (updates logos, player data), then skips structural recreation (stages, groups, fixtures)
- If `Champ.ExternalId` is new, creates full structure as normal

**Re-import behavior** (no deletion needed):
- Team logos: Updated when ImageUrl differs from existing
- Player data: Updated on every import
- Structural data (stages, groups, fixtures, events): Only created on first import
- No duplicate fixtures or events on re-import

**Team-level idempotency** works correctly:
- Teams are matched by ExternalId first, then by (name + sportKind + country + ownerId)
- Teams update when: import not completed, not updated in 24h, or ImageUrl changed

### Post-Import Verification Checklist

```
[ ] Standings tab loads with correct P/W/D/L/GF/GA/Pts
[ ] All team logos display correctly (hosted on MinIO)
[ ] Playoff bracket renders with correct connections
[ ] QF winners flow to correct SF parent nodes
[ ] Penalty scores display as "X-X (pen Y-Z)" with winner highlighted
[ ] Player stats (goals) are correct - top scorers list complete
[ ] Events visible on fixture detail pages (goals, cards)
[ ] Fixture dates are correct
[ ] No duplicate fixtures in database
[ ] Teams shared across competitions in same league
[ ] PeriodScores have non-null Home_score/Away_score values
```

### Platform Plugins

| Platform | Skill File | Status |
|----------|-----------|--------|
| PS23 Soccer | `import-ps23.md` | Available |
| FlashScore | `import-flashscore.md` | Not yet created |
