# Adding a New Platform to EasyChamp Skills

This guide walks through creating a new platform plugin for importing tournament
data from a new source website into EasyChamp.

## Step 1: Create the directory structure

```bash
mkdir -p platforms/{platform-name}/knowledge
mkdir -p platforms/{platform-name}/scripts
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

## Step 3: Create the platform knowledge doc

Create `platforms/{platform-name}/knowledge/platform-guide.md`:

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
| ... | ... | |

## Logo URL Pattern
{How to construct logo URLs from team data}

## Known Gotchas
{Platform-specific issues you discovered}

## Validation Checklist
{What to verify after parsing, specific to this platform}
```

## Step 4: Create the parser script

Create `platforms/{platform-name}/scripts/parse.py`:

```python
#!/usr/bin/env python3
"""
{Platform Name} tournament parser for EasyChamp imports.

Usage:
    python parse.py --input data.json --output import.json
"""

import json
import sys
import argparse
from pathlib import Path

PREFIX = "{platform-name}"  # Used in ExternalId generation


def parse(data, sport="Soccer"):
    """Parse {platform} data into EasyChamp import format."""
    # TODO: Implement parsing logic
    #
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
    # CRITICAL RULES (see core/knowledge/common-pitfalls.md):
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
    print(f"Next: python ../../core/scripts/validate_import.py {args.output}")


if __name__ == "__main__":
    main()
```

## Step 5: Create the skill file

Create `.claude/commands/import-{platform-name}.md`:

```markdown
# {Platform Name} Import

Platform skill for importing tournament data from {Platform Name} into EasyChamp.

## AGENT DEFINITION

\```yaml
agent:
  name: {Platform Name} Importer
  id: import-{platform-name}
  title: {Platform Name} Tournament Data Importer
  whenToUse: >
    Use when importing tournament data from {Platform Name}.
    Outputs standard EasyChamp import JSON.

commands:
  - help: Show commands
  - parse {file}: Parse {platform} data into EasyChamp import format
  - scrape {url}: Scrape tournament data from {platform} URL

dependencies:
  core_skill: tournament-import.md
  knowledge:
    - platforms/{platform-name}/knowledge/platform-guide.md
  scripts:
    - platforms/{platform-name}/scripts/parse.py
\```

---

## WORKFLOW

\```
1. Get data: {describe how to get data}
2. Parse:    python platforms/{platform-name}/scripts/parse.py --input data.json --output import.json
3. Validate: python core/scripts/validate_import.py import.json --strict
4. Import:   curl -X POST https://api.easychamp.com/import/league -d @import.json
5. Verify:   python core/scripts/fix_post_import.py verify --champ-id {id}
\```

## DATA FORMAT
{Document the source data format}

## FIELD MAPPING
{Document how source fields map to EasyChamp fields}

## PLATFORM-SPECIFIC GOTCHAS
{Document quirks discovered during implementation}
```

## Step 6: Test

```bash
# Parse source data
python platforms/{platform-name}/scripts/parse.py --input sample.json --output import.json

# Validate output
python core/scripts/validate_import.py import.json --strict

# If validation passes, import
curl -X POST https://api.easychamp.com/import/league \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d @import.json
```

## Checklist

- [ ] `platforms/{name}/knowledge/platform-guide.md` documents data format
- [ ] `platforms/{name}/scripts/parse.py` outputs valid EasyChamp import JSON
- [ ] `.claude/commands/import-{name}.md` skill file created
- [ ] `core/scripts/validate_import.py import.json --strict` passes with 0 errors
- [ ] README.md updated with new platform in the table
