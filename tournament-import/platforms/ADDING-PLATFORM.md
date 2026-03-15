# Adding a New Platform

Guide for adding support for a new sports website to the tournament-import skill.

## Choose Your Approach

Before building a custom parser, consider whether the **Cloudflare /crawl** approach would be faster:

| Scenario | Recommended Approach |
|----------|---------------------|
| Platform has admin JSON export | Custom parser (this guide) |
| No API, scraping a website | [Cloudflare /crawl](cloudflare-crawl/guide.md) — no parser code needed |
| JavaScript-heavy SPA (e.g., FlashScore) | [Cloudflare /crawl](cloudflare-crawl/guide.md) with `render: true` |
| One-off import from an unfamiliar site | [Cloudflare /crawl](cloudflare-crawl/guide.md) — zero maintenance |
| Ongoing imports, need full control | Custom parser (this guide) |

The Cloudflare approach uses AI extraction to map any site's data to EasyChamp format with a single API call — no custom code required. See [cloudflare-crawl/guide.md](cloudflare-crawl/guide.md) for the full workflow.

---

## Custom Parser Approach

## Step 1: Create the directory structure

```bash
# From the skill root (.claude/skills/tournament-import/)
mkdir -p platforms/{platform-name}
```

## Step 2: Analyze the source website

Before writing any code, document:

1. **Where is the data?** (JSON API, HTML tables, CSV export, admin dashboard)
2. **What fields are available?** (team names, scores, dates, scorers, logos)
3. **What format are scores in?** (e.g., "5-3", separate fields, nested objects)
4. **How are scorers listed?** (comma-separated, semicolons, nested arrays)
5. **Where are team logos?** (URL pattern, embedded in page, separate API)
6. **Are there playoffs/brackets?** (how are knockout stages identified?)
7. **Any quirks?** (duplicate data, missing fields, inconsistent naming)

## Step 3: Create the platform guide

Create `platforms/{platform-name}/guide.md`:

```markdown
# {Platform Name} - Import Guide

## Overview
{Brief description of the platform and where data comes from}

## Data Source
{How to get the data - API endpoint, scraping target, export feature}

## Data Format
{JSON/HTML/CSV structure with examples}

## Field Mapping to EasyChamp

| Source Field | EasyChamp Field | Notes |
|-------------|-----------------|-------|
| team_name | HomeTeam.Name / AwayTeam.Name | |
| score | HomeTeamScore / AwayTeamScore | Must be strings |
| round | MatchDay / MatchDayName | |

## Logo URL Pattern
{How to construct logo URLs from team data}

## Known Gotchas
{Platform-specific issues you discovered}

## Validation Checklist
{What to verify after parsing, specific to this platform}
```

## Step 4: Create the parser script

Create `platforms/{platform-name}/parse.py`:

```python
#!/usr/bin/env python3
"""
{Platform Name} tournament parser for EasyChamp imports.

Usage:
    python parse.py --input data.json --output import.json
"""

import json
import argparse

PREFIX = "{platform-name}"  # Used in ExternalId generation


def parse(data, sport="Soccer"):
    """Parse {platform} data into EasyChamp import format."""
    # Output MUST match this structure:
    # {
    #   "ImportSource": 99,
    #   "ImportMode": 0,
    #   "League": {
    #     "Name": "...",
    #     "Country": "...",
    #     "SportKindName": "Soccer",
    #     "Champs": [{
    #       "Name": "...",
    #       "ExternalId": "{prefix}:comp:...",
    #       "StartDate": "YYYY-MM-DD",
    #       "EndDate": "YYYY-MM-DD",
    #       "Stages": [{
    #         "Name": "Group Stage",
    #         "Type": "League",   # or "Playoff"
    #         "Groups": [{
    #           "Name": "Group A",
    #           "Fixtures": [...]
    #         }]
    #       }]
    #     }]
    #   }
    # }
    #
    # CRITICAL RULES (see core/common-pitfalls.md):
    # - Scores MUST be strings: "5" not 5
    # - EventType MUST be "scorer" not "goal"
    # - MatchDayName for playoffs MUST be lowercase: "quarterfinal"
    # - Player.OtherFullName MUST be present (can be "")
    # - Playoff fixtures MUST have Order field (int)
    # - PeriodScores use Home_score/Away_score (snake_case)
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sport", default="Soccer")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    result = parse(data, sport=args.sport)

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Output: {args.output}")
    print(f"Next: python scripts/validate_import.py {args.output}")


if __name__ == "__main__":
    main()
```

## Step 5: Update the SKILL.md

Add a new "PLATFORM: {Name}" section to the main `SKILL.md` with:
- Platform-specific workflow commands
- Scorer/data parsing rules
- Logo URL patterns
- ExternalId generation scheme
- Platform-specific gotchas
- Reimport strategy

Use the existing PS23 Soccer section as a template.

## Step 6: Test

```bash
# Parse source data
python platforms/{platform-name}/parse.py --input sample.json --output import.json

# Validate output
python scripts/validate_import.py import.json --strict

# If validation passes, import
curl -X POST https://api.easychamp.com/import/league \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d @import.json
```

## Checklist

- [ ] `platforms/{name}/guide.md` documents data format and field mapping
- [ ] `platforms/{name}/parse.py` outputs valid EasyChamp import JSON
- [ ] SKILL.md updated with platform-specific section
- [ ] `scripts/validate_import.py import.json --strict` passes with 0 errors
- [ ] README.md updated with new platform in the table
