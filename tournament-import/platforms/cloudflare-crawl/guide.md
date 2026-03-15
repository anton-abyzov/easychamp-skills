# Cloudflare /crawl - Universal Tournament Scraper

## Overview

Cloudflare's Browser Rendering `/crawl` endpoint enables scraping any tournament website with a single API call — no custom parsers, no browser automation, no Selenium/Playwright. Point it at a URL, describe the data you want, and get structured JSON back.

This is the **recommended approach for new platforms** where you don't have admin JSON exports. Instead of writing a per-platform parser, you define an AI extraction prompt that maps the site's data to EasyChamp's import schema.

## When to Use This vs. a Custom Parser

| Scenario | Approach |
|----------|----------|
| Platform has admin JSON export (like PS23) | Custom parser — structured data is already clean |
| New platform, no API access | **Cloudflare /crawl** — fastest path to structured data |
| JavaScript-heavy site (like FlashScore) | **Cloudflare /crawl with `render: true`** — handles JS rendering |
| Static HTML site | Cloudflare /crawl with `render: false` — free, fast |
| One-off import from an unfamiliar site | **Cloudflare /crawl** — no parser code to maintain |
| Ongoing imports from a well-known platform | Custom parser — more control, deterministic output |

## Prerequisites

1. **Cloudflare account** with Browser Rendering enabled
2. **API token** with "Browser Rendering - Edit" permission
3. **Account ID** (found in Cloudflare dashboard → Overview → right sidebar)

## API Reference

### Endpoint

```
POST https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/crawl
GET  https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/crawl/{job_id}
```

### Authentication

```
Authorization: Bearer {api_token}
Content-Type: application/json
```

### Start a Crawl Job

```json
{
  "url": "https://example-league.com/season-2025",
  "limit": 50,
  "depth": 3,
  "formats": ["json", "markdown"],
  "render": true,
  "jsonOptions": {
    "prompt": "Extract tournament fixture data...",
    "response_format": { "type": "json_object" }
  },
  "options": {
    "includePatterns": ["*/fixtures*", "*/standings*", "*/match/*"],
    "excludePatterns": ["*/login*", "*/admin*", "*/ads*"]
  },
  "rejectResourceTypes": ["image", "media", "font", "stylesheet"]
}
```

**Response:** `{ "success": true, "result": "job-id-uuid" }`

### Poll for Results

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/crawl/{job_id}" \
  -H "Authorization: Bearer {api_token}" | jq .
```

**Response structure:**
```json
{
  "success": true,
  "result": {
    "status": "completed",
    "total": 25,
    "finished": 25,
    "pages": [
      {
        "url": "https://example-league.com/match/123",
        "status": "completed",
        "json": {
          "home_team": "Team A",
          "away_team": "Team B",
          "score": "3-1",
          "scorers": [...]
        },
        "markdown": "# Match: Team A vs Team B\n...",
        "metadata": { "status": 200, "title": "Match Details" }
      }
    ],
    "cursor": "next-page-cursor"
  }
}
```

Use `cursor` parameter to paginate when results exceed 10 MB per response.

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `url` | required | Starting URL to crawl |
| `limit` | 10 | Max pages to crawl (free: 100, paid: 100,000) |
| `depth` | 100,000 | Max link depth from starting URL |
| `formats` | `["html"]` | Output formats: `html`, `markdown`, `json` |
| `render` | `true` | Use headless Chrome (`true`) or raw HTTP (`false`) |
| `jsonOptions.prompt` | — | AI extraction prompt (required for `json` format) |
| `options.includePatterns` | — | URL patterns to crawl (wildcard `*`, `**`) |
| `options.excludePatterns` | — | URL patterns to skip (takes priority over include) |
| `rejectResourceTypes` | — | Skip loading: `image`, `media`, `font`, `stylesheet` |
| `maxAge` | 86400 | Cache duration in seconds (max 604,800 = 7 days) |
| `modifiedSince` | — | Only crawl pages newer than this Unix timestamp |

### Pricing

| | Free Plan | Paid Plan |
|---|-----------|-----------|
| Browser time | 10 min/day | 10 hrs/month, then $0.09/hr |
| Concurrent browsers | 3 | 10 (avg), then $2/browser |
| Jobs/day | 5 | Unlimited |
| Pages/job | 100 | 100,000 |
| `render: false` | Free (beta) | Workers pricing post-beta |

## Workflow: Tournament Import via /crawl

### Step 1: Crawl the tournament site

Start a crawl job targeting fixture/match pages:

```bash
python platforms/cloudflare-crawl/crawl.py start \
  --url "https://league-site.com/season-2025" \
  --account-id "$CF_ACCOUNT_ID" \
  --api-token "$CF_API_TOKEN" \
  --limit 50 \
  --depth 3 \
  --render \
  --include "*/fixtures*" "*/match/*" "*/standings*" \
  --exclude "*/login*" "*/admin*"
```

Output: job ID for polling.

### Step 2: Poll and download results

```bash
python platforms/cloudflare-crawl/crawl.py poll \
  --job-id "abc-123" \
  --account-id "$CF_ACCOUNT_ID" \
  --api-token "$CF_API_TOKEN" \
  --output raw_crawl.json
```

### Step 3: Transform to EasyChamp format

```bash
python platforms/cloudflare-crawl/crawl.py transform \
  --input raw_crawl.json \
  --output import.json \
  --league-name "Example League" \
  --country "USA" \
  --sport "Soccer"
```

### Step 4: Validate and import (standard pipeline)

```bash
python scripts/validate_import.py import.json --strict
curl -X POST https://api.easychamp.com/import/league \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d @import.json
```

## AI Extraction Prompt

The key to good results is the `jsonOptions.prompt`. This tells Cloudflare's AI what to extract from each page.

### Recommended prompt for tournament sites:

```
Extract tournament fixture/match data from this page. For each match found, return:
- home_team: home team name (string)
- away_team: away team name (string)
- home_score: home team score (integer or null if not played)
- away_score: away team score (integer or null if not played)
- date: match date in YYYY-MM-DD format (string or null)
- round: round/matchday number or name (string)
- stage: "group" or "playoff" (string)
- playoff_round: if playoff, one of: "round_of_16", "quarterfinal", "semifinal", "final", "3rd_place_playoff" (string or null)
- home_scorers: list of scorer names for home team (array of strings)
- away_scorers: list of scorer names for away team (array of strings)
- home_penalty_score: penalty shootout score for home team (integer or null)
- away_penalty_score: penalty shootout score for away team (integer or null)
- competition_name: name of the competition/tournament (string)

Return as JSON: { "matches": [...], "teams": [...], "standings": [...] }

For teams, return: { "name": string, "logo_url": string or null }

For standings (if visible), return: { "team": string, "played": int, "wins": int, "draws": int, "losses": int, "goals_for": int, "goals_against": int, "points": int, "position": int }

If the page has no match data, return { "matches": [], "teams": [], "standings": [] }.
```

### Tips for prompt tuning

1. **Be specific about date formats** — sites vary wildly (MM/DD, DD/MM, "Jan 5", etc.)
2. **Mention scorer format** — some sites list scorers with minute marks, some don't
3. **Handle pagination** — increase `limit` and `depth` if matches span multiple pages
4. **Use `markdown` format as fallback** — if AI extraction misses data, the markdown output is clean and Claude can parse it in a second pass

## Two-Pass Strategy

For complex sites where single-pass AI extraction isn't reliable:

**Pass 1: Crawl with markdown format (cheap, reliable)**
```json
{
  "url": "https://league-site.com",
  "formats": ["markdown"],
  "render": true,
  "limit": 50
}
```

**Pass 2: Feed markdown to Claude for structured extraction**
Let Claude parse the markdown pages using the full EasyChamp schema context. This gives you:
- Better accuracy (Claude knows the exact target schema)
- Ability to cross-reference across pages (standings vs fixtures)
- Deduplication and data cleaning built in

This is often more reliable than the built-in JSON extraction because Claude has full context of the EasyChamp import rules.

## Environment Variables

```bash
export CF_ACCOUNT_ID="your-cloudflare-account-id"
export CF_API_TOKEN="your-cloudflare-api-token"
```

## Known Limitations

1. **robots.txt respected** — some sites block crawlers. Use `render: false` for lighter footprint
2. **Fixed User-Agent** — `CloudflareBrowserRenderingCrawler/1.0`, cannot be customized
3. **AI extraction quality varies** — complex table layouts or SPAs may need the two-pass strategy
4. **Rate limits** — free plan: 5 jobs/day, 10 min browser time/day
5. **No auth bypass** — cannot handle login-protected pages (use `authenticate` for basic auth only)
6. **Response size** — 10 MB per GET request; use cursor pagination for large crawls
