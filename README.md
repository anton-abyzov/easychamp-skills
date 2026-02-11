# EasyChamp Skills

Claude Code skills for importing tournament data into EasyChamp from external platforms.

## Architecture

```
Core (platform-agnostic)          Platform Plugins (source-specific)
========================          ==================================
EasyChamp API knowledge           PS23 Soccer parser
Data type rules & pitfalls        FlashScore parser (planned)
Validation scripts                {Your platform here}
Post-import fix scripts
Bracket structure reference
```

The **core** captures everything about importing INTO EasyChamp - API endpoints, data types, pitfalls, bracket structure. It works regardless of where the data comes from.

**Platform plugins** handle parsing FROM a specific source website. Each plugin has its own parser, knowledge docs, and skill file.

## Installation

### Core skill (always needed)
```bash
cp .claude/commands/tournament-import.md /path/to/project/.claude/commands/
```

### Platform skill (pick the ones you need)
```bash
cp .claude/commands/import-ps23.md /path/to/project/.claude/commands/
```

### Or clone and symlink
```bash
git clone https://github.com/anton-abyzov/easychamp-skills.git
ln -s $(pwd)/easychamp-skills/.claude/commands/tournament-import.md ~/.claude/commands/
ln -s $(pwd)/easychamp-skills/.claude/commands/import-ps23.md ~/.claude/commands/
```

## Available Platforms

| Platform | Skill | Parser | Status |
|----------|-------|--------|--------|
| PS23 Soccer | `import-ps23.md` | `platforms/ps23/scripts/parse.py` | Available |
| FlashScore | - | - | Planned |

## Repository Structure

```
easychamp-skills/
├── .claude/commands/
│   ├── tournament-import.md          # Core skill (platform-agnostic)
│   └── import-ps23.md               # PS23 platform skill
├── core/
│   ├── knowledge/
│   │   ├── api-reference.md          # EasyChamp API endpoints
│   │   ├── data-types.md             # MongoDB field types
│   │   ├── common-pitfalls.md        # 15 known pitfalls
│   │   └── knockout-bracket.md       # Binary tree bracket reference
│   ├── templates/
│   │   ├── fixture-import.json       # Minimal fixture template
│   │   ├── league-import.json        # Full league hierarchy template
│   │   └── playoff-bracket-mapping.json
│   └── scripts/
│       ├── validate_import.py        # Pre-import validation
│       └── fix_post_import.py        # Post-import MongoDB fixes
├── platforms/
│   └── ps23/
│       ├── README.md
│       ├── knowledge/
│       │   └── platform-guide.md     # PS23 data format & parsing rules
│       └── scripts/
│           └── parse.py              # PS23-specific parser
├── PLATFORM-TEMPLATE.md              # Guide for adding new platforms
└── README.md
```

## Workflow

```
Source website ──→ Platform parser ──→ import.json ──→ validate ──→ API import ──→ verify
                   (ps23/parse.py)     (EasyChamp      (validate     (POST          (fix_post
                                        format)        _import.py)   /import/       _import.py)
                                                                     league)
```

## Adding a New Platform

See [PLATFORM-TEMPLATE.md](PLATFORM-TEMPLATE.md) for step-by-step instructions.

Quick summary:
1. Create `platforms/{name}/knowledge/platform-guide.md`
2. Create `platforms/{name}/scripts/parse.py`
3. Create `.claude/commands/import-{name}.md`
4. Update this README

## Key Rules (from core)

- **Scores**: Always strings (`"5"` not `5`)
- **Event types**: `"scorer"` not `"goal"`
- **Playoff stages**: lowercase, no hyphens (`"quarterfinal"`)
- **Order field**: API silently ignores it - must update MongoDB directly
- **Team logos**: Must be updated in 3 separate collections
