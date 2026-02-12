# PS23 Soccer Import

Platform skill for importing tournament data from PS23 Soccer (ps23soccer.com) into EasyChamp.

## AGENT DEFINITION

```yaml
agent:
  name: PS23 Soccer Importer
  id: import-ps23
  title: PS23 Soccer Tournament Data Importer
  whenToUse: >
    Use when importing tournament data specifically from PS23 Soccer (ps23soccer.com).
    Handles PS23's JSON export format, scorer string parsing, logo URL mapping,
    and all PS23-specific data quirks. Outputs standard EasyChamp import JSON
    that can be validated and imported using the core tournament-import skill.

persona:
  role: PS23 Soccer Data Extraction Specialist
  style: Detail-oriented, validates every field mapping
  identity: Expert in PS23's data format and EasyChamp's import requirements
  focus: Accurate parsing, scorer multiplier handling, logo mapping, deduplication

commands:
  - help: Show PS23 import commands
  - parse {file}: Parse PS23 JSON export into EasyChamp import format
  - scrape {url}: Scrape tournament data from PS23 website URL (requires web access)

dependencies:
  core_skill: tournament-import.md
  scripts:
    - scripts/ps23_data_import.py
```

---

## PS23 IMPORT WORKFLOW

```bash
# 1. Single competition transform:
python scripts/ps23_data_import.py --input ~/Downloads/C92_ULTIMATE_COMPLETE.json

# 2. Multi-competition (shared teams):
python scripts/ps23_data_import.py --multi -c C86 C92

# 3. Full pipeline (transform + clean + migrate logos + import + verify):
python scripts/ps23_data_import.py --multi -c C86 C92 \
  --clean --migrate-logos --post-import --validate --validate-brackets

# 4. Import existing JSON:
python scripts/ps23_data_import.py --input /path/to/PS23_MULTI_IMPORT.json --post-import

# 5. Verify existing import:
python scripts/ps23_data_import.py --verify-only
```

## PS23 JSON EXPORT FORMAT

```json
{
  "competition": {
    "id": "C92",
    "name": "Superliga 8v8",
    "start_date": "2024-10-29",
    "end_date": "2025-01-28",
    "playoffs": {
      "quarterfinals": [
        { "home": "Team A", "away": "Team B", "score": "3-1", "date": "..." }
      ],
      "semifinals": [...],
      "final": { "home": "...", "away": "...", "score": "2-1" }
    }
  },
  "all_games": [
    {
      "home": "EasyChamp", "away": "Touch-Volley FC",
      "score": "5-3", "week": 1,
      "home_scorers": "K. Moosa; L. Peralta; J. Doe",
      "away_scorers": "M. Smith x2; R. Johnson",
      "date": "2024-10-29",
      "video_url": "https://youtube.com/...",
      "media_album": "https://..."
    }
  ],
  "standings": [
    { "team": "EasyChamp", "pos": 1, "played": 9, "wins": 8,
      "draws": 0, "losses": 1, "gf": 45, "ga": 12, "pts": 24 }
  ],
  "all_player_stats": [
    { "player": "K. Moosa", "team": "EasyChamp", "goals": 15, "assists": 3 }
  ]
}
```

## SCORER PARSING RULES

PS23 uses inconsistent scorer formats across competitions:

| Format | Example | Result |
|--------|---------|--------|
| Semicolon separated | "K. Moosa; L. Peralta" | 2 scorers, 1 goal each |
| Comma separated | "K. Moosa, L. Peralta" | 2 scorers, 1 goal each |
| Prefix multiplier | "5x K. Moosa" | 1 scorer, 5 goals |
| Suffix multiplier | "K. Moosa x5" | 1 scorer, 5 goals |
| Walk over | "walk over" | Skip (no events) |
| Forfeit | "forfeit" | Skip (no events) |
| Empty | "" | Skip (no events) |

## LOGO URL PATTERN

```
Source: https://ps23soccer.com/webfiles/ps23/escudos/{team_id}.png
```

Logo IDs must be looked up from the PS23 admin dashboard or website HTML.
There is NO programmatic API to get logo IDs.

**IMPORTANT**: All logos MUST be hosted on MinIO, not external URLs. Use `--migrate-logos`
flag to auto-download from PS23 and re-upload to MinIO (`minio.easychamp.com/sportchamp-prod`).

## EXTERNAL ID GENERATION

Deterministic IDs for deduplication:
```
Team:    "ps23:team:{md5_12(team_name)}"
Player:  "ps23:player:{md5_12(player_name)}"
Fixture: "ps23:fixture:{home_slug}-vs-{away_slug}-{week}"
Comp:    "ps23:comp:{comp_name_slug}"
```

## PS23-SPECIFIC GOTCHAS

1. **Abbreviated player names**: "K. Moosa" style. Same player may appear as "Kobi Moosa" elsewhere. Use fuzzy matching if cross-referencing.
2. **Duplicate players across teams**: Same player on multiple teams (e.g., F. Gutierrez in C92). Parser generates unique IDs per team automatically.
3. **Playoff fixtures in group stage**: Some exports include playoff games in `all_games` AND `playoffs`. Deduplicate by team pair + score.
4. **Missing dates**: Playoff fixtures may have null dates. Calculate from week number or use end_date.
5. **Stale logo URLs**: PS23 changes logo IDs when teams re-register. Always verify against ps23soccer.com/tables-{comp_id} HTML source.
6. **Video/media links**: Games may have `video_url` and `media_album` fields. Not imported to EasyChamp but worth preserving.
7. **Penalty shootouts need PeriodScores**: Setting `HomePenaltyScore`/`AwayPenaltyScore` is NOT enough. Must also include `PeriodScores` with `regular_period` (full-time score) and `penalties` entries. Frontend reads exclusively from PeriodScores.
8. **Logo ID mismatches**: Teams may share similar names across competitions but have different escudo IDs. Always verify by inspecting the PS23 competition page HTML. Known corrections from C86/C92: FE.FC=329, FC Noise=325, Nacional=326, Miramar CF=316.
9. **Event players MUST be in champ-level Teams**: The import creates ChampTeamPlayers from `Champs[].Teams[].TeamMembers` (NOT from fixture-level TeamMembers). If a player scores but is missing from the champ-level team roster, the import crashes with NullReferenceException at `ImportLeagueService.cs:313`. Always ensure ALL event players appear in BOTH champ-level AND fixture-level TeamMembers.
10. **PS23 Week numbering quirk**: PS23 website sometimes labels two different weeks as "Week 2" (skipping "Week 3"). The import script should use sequential week numbering regardless of PS23 labels.
11. **Incomplete scorer data**: PS23 may list fewer scorers than the actual score (e.g., 3 scorers for 7 goals). The import correctly sets the score but events will be incomplete. This is a data quality limitation of PS23 exports.

## LOGO VERIFICATION

Logo IDs change between PS23 competition registrations. To verify:

```bash
# Fetch PS23 competition page and extract logo URLs from HTML
curl -s 'https://ps23soccer.com/tables-92' | grep -oP 'escudos/\d+\.png' | sort -u

# Cross-reference with _TEAM_LOGOS_RAW dictionary in ps23_data_import.py
# Each team's logo ID must match what's rendered on the PS23 website
```

Known correct logo IDs (as of Feb 2026):
| Team | Logo ID | Notes |
|------|---------|-------|
| Atenas Pocito | 328 | |
| EasyChamp | 319 | |
| FE.FC | 329 | Was incorrectly 317 |
| FC Noise | 325 | Was incorrectly 320 |
| Nacional | 326 | Was incorrectly 316 |
| Miramar CF | 316 | Was incorrectly 326 (swapped with Nacional) |

## REIMPORT STRATEGY

### Quick reimport (update teams/logos only):
Reimport is idempotent - no deletion needed:
1. **Transform**: `python scripts/ps23_data_import.py --multi -c C86 C92`
2. **Import**: `python scripts/ps23_data_import.py --input PS23_MULTI_IMPORT.json --post-import`
   - Existing league/champ: reused, teams & players updated (logos, names)
   - New league/champ: full structure created
3. **Verify**: Check events, penalties, logos, standings, brackets

### Full reimport (recreate everything):
Use the **hard delete** API endpoint for cascading deletion, then reimport:
1. **Delete**: `DELETE /champs/{champId}?forceDelete=true` (cascades stages, groups, fixtures, events, stats, ratings)
2. **Change Champ.Id**: Generate a new UUID for `Champ.Id` in the JSON to avoid ExternalId lookup match
3. **Import**: Re-run the import pipeline

### Two-phase import (workaround for NullRef bug):
If import fails with NullReferenceException on events:
1. **Phase 1**: Import JSON with ALL events removed (`Events: []` on every fixture) → creates all fixtures
2. **Phase 2**: Add missing ChampTeamPlayers directly to MongoDB if needed
3. **Phase 3**: Add events via `POST /fixture/{id}/event/bulk` API endpoint

**Note**: Structural data (stages, groups, fixtures, events) is only created on first import.
`ImportLeagueService.cs:140` uses `Champ.Id` (NOT `Champ.ExternalId`) for the existing champ lookup.

## VALIDATION CHECKLIST (PS23-Specific)

After parsing, verify:
```
[ ] Team names match exactly between games, standings, and player stats
[ ] Total goals in standings (GF) matches sum of home/away scores
[ ] No duplicate fixtures (team pair + week)
[ ] All playoff fixtures have correct matchDayName (lowercase, no hyphens)
[ ] Logo URLs return HTTP 200 (verify against PS23 website HTML)
[ ] Player goal counts match between events and player stats
[ ] Dates are in chronological order
[ ] PeriodScores included for all penalty fixtures (regular_period + penalties)
[ ] Bracket Order values follow binary tree pattern (see tournament-import.md)
```

Then run the built-in validation:
```bash
python scripts/ps23_data_import.py --input import.json --validate --validate-brackets
```
