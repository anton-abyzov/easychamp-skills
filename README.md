# EasyChamp Tournament Import Skill

A [Claude Code skill](https://docs.anthropic.com/en/docs/claude-code/skills) for importing tournament data into EasyChamp from external sports platforms.

## Installation

### Personal skill (all your projects)
```bash
git clone https://github.com/anton-abyzov/easychamp-skills.git
cp -r easychamp-skills/.claude/skills/tournament-import ~/.claude/skills/
```

### Project skill (single project)
```bash
git clone https://github.com/anton-abyzov/easychamp-skills.git
cp -r easychamp-skills/.claude/skills/tournament-import /path/to/project/.claude/skills/
```

### Or symlink for easy updates
```bash
git clone https://github.com/anton-abyzov/easychamp-skills.git
ln -s $(pwd)/easychamp-skills/.claude/skills/tournament-import ~/.claude/skills/tournament-import
```

## Usage

Invoke the skill in Claude Code:
```
/tournament-import parse ~/Downloads/C92_data.json
/tournament-import verify {champId}
/tournament-import fix-brackets {champId}
```

## Supported Platforms

| Platform | Status | Guide |
|----------|--------|-------|
| PS23 Soccer | Available | [guide.md](.claude/skills/tournament-import/platforms/ps23/guide.md) |
| FlashScore | Planned | - |

## Structure

```
.claude/skills/tournament-import/
├── SKILL.md                       # Main skill (entry point)
├── core/                          # EasyChamp import knowledge (platform-agnostic)
│   ├── api-reference.md           # API endpoints and payloads
│   ├── data-types.md              # MongoDB schemas and field types
│   ├── common-pitfalls.md         # 22 production pitfalls
│   └── knockout-bracket.md        # Binary tree bracket algorithm
├── platforms/                     # Site-specific parsers and knowledge
│   ├── ps23/
│   │   ├── guide.md               # PS23 data format and parsing rules
│   │   └── parse.py               # PS23 JSON parser
│   └── ADDING-PLATFORM.md         # Guide for adding new sites
├── scripts/                       # Shared utilities
│   ├── validate_import.py         # Pre-import JSON validation
│   └── fix_post_import.py         # Post-import MongoDB fixes
└── templates/                     # JSON import format templates
    ├── fixture-import.json
    ├── league-import.json
    └── playoff-bracket-mapping.json
```

**Core** contains everything about importing INTO EasyChamp - API endpoints, data types, pitfalls, bracket structure. Platform-agnostic.

**Platforms** handle parsing FROM a specific source website. Each platform has its own parser and knowledge doc.

## Workflow

```
Source website → Platform parser → import.json → validate → API import → verify & fix
                (ps23/parse.py)    (EasyChamp     (validate    (POST         (fix_post
                                    format)       _import.py)  /import/      _import.py)
                                                               league)
```

## Adding a New Platform

See [ADDING-PLATFORM.md](.claude/skills/tournament-import/platforms/ADDING-PLATFORM.md).

## Key Rules

- **Scores**: Always strings (`"5"` not `5`)
- **Event types**: `"scorer"` not `"goal"`
- **Playoff stages**: lowercase, no hyphens (`"quarterfinal"`)
- **Order field**: API silently ignores it on some endpoints
- **Team logos**: Must be hosted on MinIO, updated in 3 collections
