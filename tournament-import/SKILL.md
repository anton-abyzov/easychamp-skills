---
name: tournament-import
description: "Import tournament data into EasyChamp from external sports platforms (PS23 Soccer). Handles parsing, validation, bracket setup, logo migration, penalties, and post-import verification."
disable-model-invocation: true
argument-hint: "<command> <args>"
---

# Tournament Import Specialist

You are an EasyChamp tournament data import specialist. Parse, transform, validate, and import
tournament data from external sports platforms into EasyChamp with absolute data integrity.

This skill is organized as:
- **Core** (`core/`) - EasyChamp import rules, API reference, data types, pitfalls (platform-agnostic)
- **Platforms** (`platforms/`) - Site-specific parsers and knowledge (currently PS23 Soccer)
- **Scripts** (`scripts/`) - Validation and post-import fix utilities
- **Templates** (`templates/`) - JSON import format templates

## Core Principles

- Data integrity above speed - validate everything before import
- Scores are ALWAYS strings in MongoDB ("5" not 5)
- Every pitfall has been encountered before - check the knowledge base
- Verify across ALL three image collections after logo updates
- Never trust API responses blindly - some endpoints silently ignore fields
- Playoff bracket structure is a binary tree - order values must match nodeIds
- All images MUST be hosted on MinIO, not external URLs

---

## CORE: EasyChamp Import Rules

### Import Pipeline

```
Source data --> Platform parser --> import.json --> validate --> API import --> verify & fix
```

### Full pipeline (PS23 example):
```bash
python scripts/ps23_data_import.py --multi -c C86 C92 \
  --clean --migrate-logos --post-import --validate --validate-brackets
```

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
| `--migrate-logos` | Download external logos and upload to MinIO |
| `--dry-run` | Show what would happen without executing |
| `--verify-only` | Only verify existing import |

### API Quick Reference

| Endpoint | Method | Purpose | Notes |
|----------|--------|---------|-------|
| `/import/league` | POST | Full league import (recommended) | Single atomic operation |
| `/import/fixtures` | POST | Batch fixture import | Idempotent |
| `/image` | POST | Upload image to MinIO | Params: entity=Teams, sportKind=Soccer |
| `/fixture/{id}/score` | PUT | Update scores | Does NOT save Order field |
| `/fixture/{id}` | PUT | Update fixture (full) | Saves Order |
| `/fixture/{id}/event/bulk` | POST | Bulk add events | Use after structural import |
| `/champs/{id}?forceDelete=true` | DELETE | Hard delete champ + deps | Cascades everything |
| `/teams/{id}` | PUT | Update team details | Publishes RabbitMQ UpdateImage |
| `/recalculate/champ/{id}/standings` | POST | Recalculate standings | Run after score changes |

### Data Type Rules (CRITICAL)

| Field | Type | Example | Common Mistake |
|-------|------|---------|----------------|
| HomeTeamScore | string | "5" | Using int 5 (causes 500) |
| AwayTeamScore | string | "3" | Using int 3 (causes 500) |
| HomePenaltyScore | string | "2" | Using int 2 (causes 500) |
| AwayPenaltyScore | string | "3" | Using int 3 (causes 500) |
| EventType | string | "scorer" | Using "goal" |
| MatchDayName (playoffs) | string | "quarterfinal" | "Quarter-Final", "QUARTERFINAL" |
| MatchDayName (group) | string | "1" | Using int 1 |
| Player.OtherFullName | string | "" | Omitting (API requires it) |
| Status | int enum | 2 | 0=Scheduled, 1=InProgress, 2=Finished |
| Dates | string | "2024-10-29" | Including time component |
| Fixture.Order | int | 4 | null (bracket won't render) |

### Knockout Bracket Binary Tree

```
Node IDs (depth=3, 8 teams):
         1 (Final)
        / \
       2   3 (Semifinal)
      / \ / \
     4  5 6  7 (Quarterfinal)
```

Bracket order: Final=1, SFs=2-3, QFs=4-7. `Fixture.Order` must match nodeId.
Depth = `Math.ceil(Math.log2(teamsCount))`.

Valid matchDayName values: `quarterfinal`, `semifinal`, `final`, `3rd_place_playoff`,
`round_of_16`, `round_of_32`, `round_of_64`, `round_of_128`.

### Image Hosting (MinIO)

All images MUST be hosted on MinIO (`minio.easychamp.com/sportchamp-prod`):
- Upload via `POST /image?entity=Teams&sportKind=Soccer`
- Returns relative path: `Teams/Soccer/logo_guid.png`
- Full URL: `https://minio.easychamp.com/sportchamp-prod/Teams/Soccer/logo_guid.png`
- Use `--migrate-logos` flag for automatic external-to-MinIO migration

### Top Pitfalls (All Encountered in Production)

1. **Score field types**: Scores MUST be strings. Int causes 500.
2. **MatchDayName format**: Lowercase without hyphens: "quarterfinal" not "Quarter-Final"
3. **Event type**: "scorer" not "goal"
4. **Player ID consistency**: Same ID across events, squads, and team rosters
5. **Squad population**: Include ALL team members, not just scorers
6. **Duplicate players**: Unique IDs per team for players on multiple teams
7. **Walk over/forfeit**: Empty events array, don't create fake players
8. **Order field via API**: Requires ec-apicore-lib >= 3.0.18
9. **Penalty scores**: Must be strings AND include PeriodScores array
10. **External logos**: Upload to MinIO first, never reference external URLs
11. **PeriodScores required**: Frontend reads from `periodScores.find(x => x.type === "penalties")` only
12. **ExternalId on reimport**: Only refresh structural IDs, keep team/player IDs
13. **Import idempotency**: Teams/players update, structural data only on first import
14. **Champ.Id vs ExternalId**: `ImportLeagueService.cs:140` uses `Champ.Id` for lookup
15. **Champ-level TeamMembers**: ALL event players MUST be in `Champs[].Teams[].TeamMembers`
16. **forceDelete**: `DELETE /champs/{id}?forceDelete=true` cascades all dependencies
17. **MongoDB collections**: camelCase names (`champs`, `fixtures`, `champTeamPlayers`)
18. **Two-phase import**: If events cause NullRef, import without events first, then bulk API

### Import Idempotency

`/import/league` supports idempotent re-imports:
- Existing `League.ExternalId`: reuses league, continues processing champs
- Existing `Champ.ExternalId`: runs team/player imports, skips structural recreation
- New `Champ.ExternalId`: creates full structure
- Team matching: ExternalId first, then (name + sportKind + country + ownerId)

### Post-Import Verification

```
[ ] Standings tab loads with correct P/W/D/L/GF/GA/Pts
[ ] All team logos display correctly (hosted on MinIO)
[ ] Playoff bracket renders with correct connections
[ ] QF winners flow to correct SF parent nodes
[ ] Penalty scores display as "X-X (pen Y-Z)" with winner highlighted
[ ] Player stats (goals) correct - top scorers list complete
[ ] Events visible on fixture detail pages
[ ] No duplicate fixtures in database
[ ] Teams shared across competitions in same league
[ ] PeriodScores have non-null Home_score/Away_score values
```

---

## PLATFORM: PS23 Soccer

PS23 Soccer (ps23soccer.com) is a league management platform in Miami, USA.

### PS23 Workflow

```bash
# Single competition:
python scripts/ps23_data_import.py --input ~/Downloads/C92_ULTIMATE_COMPLETE.json

# Multi-competition (shared teams):
python scripts/ps23_data_import.py --multi -c C86 C92

# Full pipeline:
python scripts/ps23_data_import.py --multi -c C86 C92 \
  --clean --migrate-logos --post-import --validate --validate-brackets
```

### Scorer Parsing Rules

| Format | Example | Result |
|--------|---------|--------|
| Semicolon separated | "K. Moosa; L. Peralta" | 2 scorers, 1 goal each |
| Comma separated | "K. Moosa, L. Peralta" | 2 scorers, 1 goal each |
| Prefix multiplier | "5x K. Moosa" | 1 scorer, 5 goals |
| Suffix multiplier | "K. Moosa x5" | 1 scorer, 5 goals |
| Walk over / forfeit | "walk over" | Skip (no events) |

### Logo URLs

Source: `https://ps23soccer.com/webfiles/ps23/escudos/{team_id}.png`
Logo IDs must be looked up from PS23 website HTML. No programmatic API.
All logos MUST be migrated to MinIO via `--migrate-logos`.

```bash
# Verify logo IDs against HTML source:
curl -s 'https://ps23soccer.com/tables-92' | grep -oP 'escudos/\d+\.png' | sort -u
```

### ExternalId Generation

```
Team:    "ps23:team:{md5_12(team_name)}"
Player:  "ps23:player:{md5_12(player_name)}"
Fixture: "ps23:fixture:{home_slug}-vs-{away_slug}-{week}"
```

### PS23-Specific Gotchas

1. **Abbreviated player names**: "K. Moosa" style - same player may appear as "Kobi Moosa"
2. **Duplicate players across teams**: Generate unique IDs per team automatically
3. **Playoff fixtures in group stage**: Deduplicate by team pair + score
4. **Missing playoff dates**: Calculate from week number or use end_date
5. **Stale logo URLs**: PS23 changes IDs on re-registration - always verify HTML source
6. **Penalty shootouts**: Must include PeriodScores with `regular_period` and `penalties`
7. **Event players in champ-level Teams**: Missing players cause NullReferenceException
8. **Week numbering quirks**: Use sequential numbering regardless of PS23 labels

### Reimport Strategy

**Quick reimport** (idempotent, no deletion):
1. Transform + Import - teams/logos updated, structural data reused
2. Verify events, penalties, logos, standings, brackets

**Full reimport** (recreate everything):
1. `DELETE /champs/{champId}?forceDelete=true`
2. Generate new `Champ.Id` UUID in JSON
3. Re-run import pipeline

---

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/validate_import.py` | Pre-import JSON validation | `python scripts/validate_import.py import.json --strict` |
| `scripts/fix_post_import.py` | Post-import MongoDB fixes | `python scripts/fix_post_import.py verify --champ-id {id}` |

### fix_post_import.py commands:
- `fix-brackets {champId}` - Fix playoff Order and MatchDayName in MongoDB
- `fix-logos {champId}` - Fix team logos across 3 collections
- `fix-penalties {fixtureId}` - Fix penalty data types
- `recalculate {champId}` - Trigger standings recalculation
- `verify {champId}` - Run full post-import verification

---

## Detailed Reference

- [API Reference](core/api-reference.md) - Complete endpoint documentation with payloads
- [Data Types](core/data-types.md) - MongoDB schemas and field type mapping
- [Common Pitfalls](core/common-pitfalls.md) - All 22 production pitfalls with code examples
- [Knockout Bracket](core/knockout-bracket.md) - Binary tree algorithm and React components
- [Direct MongoDB Import](core/direct-mongodb-import.md) - Complete import JSON template and manual fixes
- [News HTML Guidelines](core/news-html-guidelines.md) - HTML formatting for news articles
- [PS23 Platform Guide](platforms/ps23/guide.md) - Full PS23 data format and parsing algorithm
- [Import Templates](templates/) - JSON templates for fixture, league, and playoff imports
- [Adding a New Platform](platforms/ADDING-PLATFORM.md) - Step-by-step guide for new sites

## PLATFORM: Cloudflare /crawl (Universal Scraper)

For any tournament website where you don't have admin JSON exports, use Cloudflare's Browser Rendering
`/crawl` endpoint to scrape and extract structured data with zero custom parser code.

### When to Use

- New platform with no API access — point at the URL, get structured data back
- JavaScript-heavy sites (FlashScore, etc.) — `render: true` runs headless Chrome
- One-off imports from unfamiliar sites — no parser to maintain
- As a fallback for PS23 public pages when admin exports aren't available

### Quick Start

```bash
# 1. Start crawl job
python platforms/cloudflare-crawl/crawl.py start \
  --url "https://league-site.com/season-2025" \
  --account-id "$CF_ACCOUNT_ID" --api-token "$CF_API_TOKEN" \
  --limit 50 --depth 3 --render

# 2. Poll until complete
python platforms/cloudflare-crawl/crawl.py poll \
  --job-id "JOB_ID" --output raw_crawl.json

# 3. Transform to EasyChamp format
python platforms/cloudflare-crawl/crawl.py transform \
  --input raw_crawl.json --output import.json \
  --league-name "My League" --country "USA"

# 4. Standard pipeline
python scripts/validate_import.py import.json --strict
```

### Two-Pass Strategy (Recommended for Complex Sites)

For best results, crawl with `markdown` format first, then let Claude parse the pages
using full EasyChamp schema context. This gives better accuracy than single-pass AI extraction
because Claude can cross-reference across pages and apply all import rules.

### Full Reference

See [Cloudflare /crawl Guide](platforms/cloudflare-crawl/guide.md) for:
- API reference and parameters
- AI extraction prompt tuning
- Pricing and limits
- Two-pass strategy details
- Environment variables setup

---

## Extending to Other Platforms

To add support for a new sports website (e.g., FlashScore):

**Option A: Cloudflare /crawl (recommended for scraping)**
1. Use the universal scraper — see [Cloudflare /crawl Guide](platforms/cloudflare-crawl/guide.md)
2. No custom parser needed. Tune the AI extraction prompt if needed.

**Option B: Custom parser (recommended for structured APIs/exports)**
1. Create `platforms/{name}/guide.md` documenting the data format
2. Create `platforms/{name}/parse.py` to transform data into EasyChamp format
3. Update this SKILL.md with platform-specific workflow and gotchas
4. See [Adding a New Platform](platforms/ADDING-PLATFORM.md) for the full guide
