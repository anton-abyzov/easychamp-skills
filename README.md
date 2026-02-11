# EasyChamp Skills

Claude Code skills for EasyChamp tournament import and management.

## Installation

### Option 1: Copy skill file directly
```bash
cp .claude/commands/tournament-import.md /path/to/your/project/.claude/commands/
```

### Option 2: Clone and symlink
```bash
git clone https://github.com/anton-abyzov/easychamp-skills.git
ln -s /path/to/easychamp-skills/.claude/commands/tournament-import.md \
      /path/to/your/project/.claude/commands/tournament-import.md
```

## Available Skills

### Tournament Import (`tournament-import`)

A comprehensive skill for parsing, transforming, validating, and importing tournament data from external platforms into EasyChamp.

**Commands:**
| Command | Description |
|---------|-------------|
| `*help` | Show all available commands |
| `*import {platform} {file}` | Parse and transform tournament data |
| `*validate {file}` | Validate import JSON before API call |
| `*fix-brackets {champId}` | Fix playoff bracket structure |
| `*fix-logos {champId}` | Fix team logos across all collections |
| `*fix-penalties {fixtureId}` | Fix penalty score data |
| `*verify {champId}` | Run post-import verification |
| `*template {type}` | Generate import template |
| `*recalculate {champId}` | Trigger standings recalculation |

**Supported Platforms:**
- PS23 Soccer (JSON export)
- Generic CSV/JSON (via templates)

## Repository Structure

```
easychamp-skills/
├── .claude/commands/
│   └── tournament-import.md      # Main skill file (self-contained)
├── templates/
│   ├── fixture-import.json       # Minimal fixture template
│   ├── league-import.json        # Full league hierarchy template
│   └── playoff-bracket-mapping.json  # Binary tree node reference
├── knowledge/
│   ├── common-pitfalls.md        # 15 known pitfalls with solutions
│   ├── knockout-bracket.md       # Binary tree algorithm reference
│   ├── platform-ps23.md          # PS23-specific parsing guide
│   ├── api-reference.md          # All import-related endpoints
│   └── data-types.md             # MongoDB field types
└── scripts/
    ├── parse_tournament.py       # Generic tournament parser
    ├── validate_import.py        # Pre-import validation
    └── fix_post_import.py        # Common post-import fixes
```

## Key Concepts

### Data Type Rules
- **Scores**: Always strings (`"5"` not `5`)
- **Penalty scores**: Always strings (`"2"` not `2`)
- **Event types**: `"scorer"` not `"goal"`
- **Playoff stages**: lowercase, no hyphens (`"quarterfinal"`)
- **Dates**: Date-only strings (`"2024-10-29"`)

### Three Image Collections
Team logos must be updated in THREE separate MongoDB collections:
1. `champs.TeamRefs` - Participants tab
2. `groups.TeamRefs` - Standings tab
3. `fixtures.HomeTeam/AwayTeam` - Fixture displays

### Knockout Bracket
Binary tree with node IDs: root=1, left=2, right=3, etc.
`fixture.order` must match `node.nodeId` for correct placement.

## Contributing

Add new platform parsers by creating a `knowledge/platform-{name}.md` file documenting:
- Source data format (JSON/CSV structure)
- Field mapping to EasyChamp format
- Logo URL patterns
- Known quirks and workarounds
