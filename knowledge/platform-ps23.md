# PS23 Soccer Platform - Import Guide

## Overview

PS23 Soccer (ps23soccer.com) is a league management platform used in Miami, USA.
Tournament data is available through their admin dashboard as JSON exports and through their public website for scraping.

## Data Sources

### 1. Admin JSON Export (Recommended)
Direct JSON export from PS23 admin dashboard.

**Structure:**
```json
{
  "competition": {
    "id": "C92",
    "name": "Superliga 8v8",
    "start_date": "2024-10-29",
    "end_date": "2025-01-28",
    "format": "8v8",
    "playoffs": {
      "quarterfinals": [
        { "home": "Team A", "away": "Team B", "score": "3-1", "date": "..." }
      ],
      "semifinals": [...],
      "final": { "home": "Team X", "away": "Team Y", "score": "2-1" }
    }
  },
  "all_games": [
    {
      "home": "EasyChamp",
      "away": "Touch-Volley FC",
      "score": "5-3",
      "week": 1,
      "home_scorers": "K. Moosa; L. Peralta; J. Doe",
      "away_scorers": "M. Smith x2; R. Johnson",
      "date": "2024-10-29",
      "video_url": "https://youtube.com/...",
      "media_album": "https://..."
    }
  ],
  "standings": [
    { "team": "EasyChamp", "pos": 1, "played": 9, "wins": 8, "draws": 0, "losses": 1, "gf": 45, "ga": 12, "pts": 24 }
  ],
  "all_player_stats": [
    { "player": "K. Moosa", "team": "EasyChamp", "goals": 15, "assists": 3 }
  ]
}
```

### 2. Web Scraping
The PS23 Soccer website has public pages for completed competitions.

**URL Patterns:**
- Competition page: `https://ps23soccer.com/competition/{id}`
- Standings: embedded in competition page
- Fixtures: embedded in competition page
- Player stats: embedded in competition page
- Team logos: `https://ps23soccer.com/webfiles/ps23/escudos/{team_id}.png`

## Scorer String Parsing

PS23 uses inconsistent scorer formats across competitions:

```
Format 1: Semicolon separated
"K. Moosa; L. Peralta; J. Doe"

Format 2: Comma separated
"K. Moosa, L. Peralta, J. Doe"

Format 3: With multipliers
"5x K. Moosa"     → 5 goals by K. Moosa
"K. Moosa x5"     → 5 goals by K. Moosa
"K. Moosa (5)"    → 5 goals by K. Moosa

Format 4: With minute info (rare)
"K. Moosa (5', 23', 45')"

Skip these entries:
"walk over"
"forfeit"
"w/o"
""  (empty)
```

### Parsing Algorithm

```python
import re

def parse_scorers(scorers_str, team_name):
    if not scorers_str or scorers_str.strip().lower() in ['walk over', 'forfeit', 'w/o']:
        return []

    # Split by semicolons first, then commas
    raw_scorers = re.split(r'[;,]', scorers_str)

    events = []
    for raw in raw_scorers:
        raw = raw.strip()
        if not raw:
            continue

        # Check for multiplier prefix: "5x Name"
        prefix_match = re.match(r'^(\d+)x\s+(.+)$', raw, re.IGNORECASE)
        # Check for multiplier suffix: "Name x5"
        suffix_match = re.match(r'^(.+?)\s*x(\d+)$', raw, re.IGNORECASE)

        if prefix_match:
            count = int(prefix_match.group(1))
            name = prefix_match.group(2).strip()
        elif suffix_match:
            name = suffix_match.group(1).strip()
            count = int(suffix_match.group(2))
        else:
            name = raw
            count = 1

        for i in range(count):
            events.append({
                "player_name": name,
                "team": team_name,
                "minute": str(5 + (len(events) + i) * 5)  # Spread goals across match
            })

    return events
```

## Logo URL Mapping

PS23 team logos are at: `https://ps23soccer.com/webfiles/ps23/escudos/{id}.png`

The ID must be looked up manually from the PS23 admin dashboard or website.
There is NO programmatic API to get logo IDs.

### Known Team Logo IDs (C92 Superliga 8v8)

| Team | Logo ID | URL |
|------|---------|-----|
| Atenas Pocito | 328 | .../escudos/328.png |
| Azzurri FC | 348 | .../escudos/348.png |
| EasyChamp | 319 | .../escudos/319.png |
| HD FC Miami | 327 | .../escudos/327.png |
| Hebraica | 146 | .../escudos/146.png |
| Miami All Stars | 165 | .../escudos/165.png |
| Super Campeones | 303 | .../escudos/303.png |
| Tigres FC | 288 | .../escudos/288.png |
| Touch-Volley FC | 349 | .../escudos/349.png |
| US1 FC | 350 | .../escudos/350.png |

## ExternalId Generation

Use consistent, deterministic IDs for deduplication:

```python
import hashlib

def make_id(prefix, *parts):
    slug = '-'.join(p.lower().replace(' ', '-') for p in parts)
    return f"{prefix}:{slug}"

def make_team_id(team_name):
    h = hashlib.md5(team_name.encode()).hexdigest()[:12]
    return f"ps23:team:{h}"

def make_player_id(player_name):
    h = hashlib.md5(player_name.encode()).hexdigest()[:12]
    return f"ps23:player:{h}"

def make_fixture_id(comp_id, home, away, week):
    home_slug = home.lower().replace(' ', '-')
    away_slug = away.lower().replace(' ', '-')
    return f"{comp_id}:fixture:{home_slug}-vs-{away_slug}-{week}"
```

## Known Gotchas

1. **Abbreviated player names**: PS23 uses "K. Moosa" style. The same player may appear as "Kobi Moosa" in a different section. Use fuzzy matching.
2. **Duplicate players across teams**: F. Gutierrez played for both Touch-Volley FC and Super Campeones in C92. Give unique IDs per team.
3. **Group stage copies of playoff fixtures**: Some PS23 exports include playoff fixtures in the group stage section AND the playoffs section. Deduplicate by team pair + score.
4. **Missing dates**: Some exports have null dates for playoff fixtures. Calculate from week number.
5. **Stale logo URLs**: PS23 occasionally changes logo IDs when teams re-register. Always verify URLs are accessible.
6. **Video/media links**: Games may have YouTube video URLs and photo album links attached. Preserve these in the import for future use.

## Validation Checklist (PS23-Specific)

```
[ ] All team names match exactly between games, standings, and player stats
[ ] Total goals in standings (GF) matches sum of home/away scores
[ ] No duplicate fixtures (check team pair + week)
[ ] All playoff fixtures have correct matchDayName format
[ ] Logo URLs are accessible (HTTP 200)
[ ] Player goal counts match between events and player stats
[ ] Dates are in correct order (week 1 before week 2, etc.)
```
