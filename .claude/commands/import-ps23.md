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
  knowledge:
    - platforms/ps23/knowledge/platform-guide.md
  scripts:
    - platforms/ps23/scripts/parse.py
```

---

## PS23 IMPORT WORKFLOW

```
1. Get data: PS23 admin JSON export OR scrape from ps23soccer.com/competition/{id}
2. Parse:    python platforms/ps23/scripts/parse.py --input data.json --output import.json
3. Validate: python core/scripts/validate_import.py import.json --strict
4. Import:   curl -X POST https://api.easychamp.com/import/league -d @import.json
5. Fix:      python core/scripts/fix_post_import.py verify --champ-id {id}
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
https://ps23soccer.com/webfiles/ps23/escudos/{team_id}.png
```

Logo IDs must be looked up from the PS23 admin dashboard or website HTML.
There is NO programmatic API to get logo IDs.

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
5. **Stale logo URLs**: PS23 changes logo IDs when teams re-register. Always verify URLs return HTTP 200.
6. **Video/media links**: Games may have `video_url` and `media_album` fields. Not imported to EasyChamp but worth preserving.

## VALIDATION CHECKLIST (PS23-Specific)

After parsing, verify:
```
[ ] Team names match exactly between games, standings, and player stats
[ ] Total goals in standings (GF) matches sum of home/away scores
[ ] No duplicate fixtures (team pair + week)
[ ] All playoff fixtures have correct matchDayName (lowercase, no hyphens)
[ ] Logo URLs return HTTP 200
[ ] Player goal counts match between events and player stats
[ ] Dates are in chronological order
```

Then run core validation:
```
python core/scripts/validate_import.py import.json --strict
```
