# PS23 Soccer Platform

Import plugin for [PS23 Soccer](https://ps23soccer.com) league management platform (Miami, USA).

## Usage

```bash
# Parse PS23 JSON export
python platforms/ps23/scripts/parse.py --input data.json --output import.json

# Validate before import
python core/scripts/validate_import.py import.json --strict

# Import to EasyChamp
curl -X POST https://api.easychamp.com/import/league \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @import.json
```

## Data Sources

1. **Admin JSON export** (recommended) - Download from PS23 admin dashboard
2. **Web scraping** - Public pages at `ps23soccer.com/competition/{id}`

## Key Details

- **Scorer format**: Semicolons or commas, with optional multipliers (`5x Name` or `Name x5`)
- **Logo URLs**: `https://ps23soccer.com/webfiles/ps23/escudos/{team_id}.png`
- **ExternalIds**: `ps23:team:{md5}`, `ps23:player:{md5}`, `ps23:fixture:{slug}`

See [platform-guide.md](knowledge/platform-guide.md) for full documentation.
