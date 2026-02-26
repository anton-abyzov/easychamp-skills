# News Article HTML Guidelines

## Overview
News articles on EasyChamp are stored in the `Description` field of the `news` MongoDB collection. The HTML must render correctly on **both light and dark themes** since:
- **Subdomain sites** (e.g., `ps23soccer.at.easychamp.com`) use a dark theme
- **Main app** (`easychamp.com/news/...`) uses a light theme

## Critical Rules

### 1. Never use `color:inherit; opacity:0.85` on body text
This causes washed-out text on light backgrounds and inconsistent rendering across themes.
**Bad:** `<p style="color:inherit;opacity:0.85">Text</p>`
**Good:** `<p style="font-size:15px;line-height:1.7;margin:0 0 16px 0">Text</p>`

Let the parent site's theme handle text color. Don't override it.

### 2. No blank lines between HTML elements
Extra whitespace in the `Description` field creates visible spacing gaps in the rendered output. Keep all HTML elements tightly packed — no empty lines between tags.

### 3. Use explicit margins, not inherited spacing
**Bad:** `margin-bottom:24px` (may compound with theme margins)
**Good:** `margin:0 0 24px 0` (explicit four-value shorthand, resets top margin)

### 4. Dark gradient header card is safe everywhere
The score card header with `background:linear-gradient(135deg,#0a0a2e ...)` works on both dark and light backgrounds because it's self-contained with white text on dark background.

### 5. Use `rgba()` backgrounds for section cards
Scorer boxes, lineup chips, and result cards should use semi-transparent backgrounds:
- Blue team: `background:rgba(49,95,211,0.12)` 
- Red/opponent: `background:rgba(211,47,47,0.12)`
- Neutral: `background:rgba(128,128,128,0.1)`

These adapt to both dark and light themes.

### 6. Accent links: use a mid-blue that works on both backgrounds
**Good:** `color:#4a7cf7` — visible on both white and dark backgrounds
**Avoid:** `color:#5b8af5` — can be too light on white backgrounds

### 7. YouTube embeds: use responsive iframe pattern
```html
<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:12px;margin:0 0 24px 0">
<iframe src="https://www.youtube.com/embed/VIDEO_ID" style="position:absolute;top:0;left:0;width:100%;height:100%;border:0" allowfullscreen></iframe>
</div>
```

### 8. New player highlight chips
Use a slightly bold blue that reads on both backgrounds:
```html
<span style="background:rgba(49,95,211,0.15);border:1px solid rgba(49,95,211,0.3);padding:6px 14px;border-radius:8px;font-size:13px;color:#4a7cf7">Player ✨</span>
```

## Template Structure
A match day news article should include these sections in order:
1. **Score card header** — dark gradient with team logos, score, date
2. **Narrative recap** — 2-3 paragraphs describing the match
3. **🎬 Full Game** — embedded YouTube full match (the highlights are already rendered by the site from `VideoUrl`, so do NOT embed them again in Description)
5. **⚽ Goal Scorers** — two-column flex layout with team colors
6. **📋 Team Lineup** — chip-style player names with new player indicators
7. **📊 Other Results** — compact score line for other fixtures
8. **Footer** — "Stats powered by EasyChamp" link

## MongoDB Fields
- `Description` — the full HTML content (NOT `Content` — that field doesn't exist)
- `VideoUrl` — the main highlight video URL. The site auto-renders this as a YouTube embed at the top of the article. Do NOT duplicate this embed in Description HTML.
- `ImageUrl` — Leave as `null` when `VideoUrl` is set. The Web Engine (subdomain site like `ps23soccer.at.easychamp.com`) uses `VideoUrl` directly and makes it clickable. The main EasyChamp site (`easychamp.com`) news list may show a default icon when `ImageUrl` is null, but setting `ImageUrl` causes a blank hero gap on the detail page — so keep it null. Setting it to a YouTube thumbnail causes rendering issues on the detail page.
- `Title` — article headline
- `ExternalId` — unique identifier for dedup (e.g., `c108-matchday1-recap`)
- `IsPublished` — must be `true` to appear publicly
- `IsPublic` — must be `true`
