# Football Highlights Generation Workflow

## Overview
Automated pipeline for extracting goal highlights from full match videos recorded by VO3 camera at PS23 Soccer tournaments.

## Method: Audio Peak Detection + Visual Verification

### Why Audio?
- VO3 camera auto-pans and often misses the exact goal moment visually
- **Audio volume spikes reliably mark goal celebrations** — crowd cheering, players shouting
- Audio peaks are detected via RMS level analysis, then cross-verified with visual frame inspection

### Step 1: Download Match Video
```bash
yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" \
  -o "match-%(id)s.mp4" "YOUTUBE_URL"
```

### Step 2: Extract Audio RMS Levels
```bash
ffmpeg -i match.mp4 -vn \
  -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=audio_levels.txt" \
  -f null - 2>/dev/null
```

This produces a file with two-line entries:
```
frame:NNN    pts:NNN    pts_time:SSS.SSS
lavfi.astats.Overall.RMS_level=-XX.XXXXXX
```

### Step 3: Find Volume Peaks (Goal Celebrations)
Parse the audio levels file and find the loudest moments:

```python
import re
from collections import defaultdict

levels = []
current_time = None
with open("audio_levels.txt") as f:
    for line in f:
        line = line.strip()
        m_time = re.search(r'pts_time:([\d.]+)', line)
        if m_time:
            current_time = float(m_time.group(1))
            continue
        m_level = re.search(r'RMS_level=(-?[\d.]+)', line)
        if m_level and current_time is not None:
            lev = float(m_level.group(1))
            levels.append((current_time, lev))
            current_time = None

# Group by 1-second windows, take max level per second
sec_max = defaultdict(lambda: -200)
for t, lev in levels:
    sec = int(t)
    if lev > sec_max[sec]:
        sec_max[sec] = lev

# Sort by loudness (higher = louder, values are negative dB)
sorted_secs = sorted(sec_max.items(), key=lambda x: x[1], reverse=True)

# Cluster nearby peaks (25s gap) into distinct events
peaks_sorted = sorted(sorted_secs[:100], key=lambda x: x[0])
events = []
used = set()
for sec, lev in peaks_sorted:
    if sec in used:
        continue
    cluster = [(sec, lev)]
    for s2, l2 in peaks_sorted:
        if s2 != sec and abs(s2 - sec) <= 25 and s2 not in used:
            cluster.append((s2, l2))
            used.add(s2)
    used.add(sec)
    best = max(cluster, key=lambda x: x[1])
    events.append(best)
```

### Step 4: Filter Out Non-Goal Events
Remove these from the detected peaks:
- **Game start** (~0-30s) — opening whistle/cheer
- **Halftime** (~midpoint of video, ±60s) — loudest peak is often halftime chatter
- **Second half kickoff** (~halftime + 60s) — restart, not a goal

### Step 5: Visual Verification (Optional but Recommended)
For each audio peak timestamp T, extract frames at T and T+5:
```bash
ffmpeg -ss T -i match.mp4 -frames:v 1 -q:v 2 peak_T.jpg
ffmpeg -ss $((T+5)) -i match.mp4 -frames:v 1 -q:v 2 peak_T_plus5.jpg
```
Look for: ball in net, players celebrating (arms up, hugging), goalkeeper beaten, restart positioning.

### Step 6: Cut Goal Clips

**Clip timing formula:**
- **First half clips:** Start at `T - 25`, End at `T + 8`
- **Second half clips:** Start at `T - 27`, End at `T + 8`
  - 2nd half clips start 2s earlier because the camera may be slower to track

```bash
# First half
ffmpeg -y -ss $((T - 25)) -to $((T + 8)) -i match.mp4 \
  -c:v libx264 -crf 20 -preset fast -r 30 \
  -c:a aac -ar 48000 -b:a 192k goal_N.mp4

# Second half
ffmpeg -y -ss $((T - 27)) -to $((T + 8)) -i match.mp4 \
  -c:v libx264 -crf 20 -preset fast -r 30 \
  -c:a aac -ar 48000 -b:a 192k goal_N.mp4
```

### Step 7: Add Transitions (Fade In/Out)
```bash
dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 goal_N.mp4)
fade_out=$(echo "$dur - 0.5" | bc)

ffmpeg -y -i goal_N.mp4 \
  -vf "fade=t=in:st=0:d=0.5,fade=t=out:st=${fade_out}:d=0.5" \
  -af "afade=t=in:st=0:d=0.3,afade=t=out:st=${fade_out}:d=0.5" \
  -c:v libx264 -crf 20 -preset fast -r 30 -pix_fmt yuv420p \
  -c:a aac -ar 48000 -b:a 192k faded_N.mp4
```

### Step 8: Create Intro & Outro Slides
```bash
# Intro (4s) - dark background with match info
ffmpeg -y -f lavfi -i "color=c=0x0a0a2e:s=1920x1080:d=4,format=yuv420p" \
  -f lavfi -i "anullsrc=r=48000:cl=stereo" \
  -vf "drawtext=text='Home Team  SCORE  Away Team':fontsize=64:fontcolor=white:x=(w-text_w)/2:y=h/2-80:fontfile=/System/Library/Fonts/Helvetica.ttc,\
drawtext=text='Week N · Tournament · HIGHLIGHTS':fontsize=32:fontcolor=0xaaaaaa:x=(w-text_w)/2:y=h/2+20:fontfile=/System/Library/Fonts/Helvetica.ttc" \
  -c:v libx264 -crf 18 -preset fast -r 30 -pix_fmt yuv420p \
  -c:a aac -ar 48000 -b:a 192k -shortest intro.mp4

# Outro (5s) - scorers, lineup, EasyChamp branding (similar drawtext pattern)
```

### Step 9: Assemble Final Video
```bash
echo "file 'faded_intro.mp4'" > concat.txt
for i in $(seq 1 N); do echo "file 'faded_$(printf '%02d' $i).mp4'" >> concat.txt; done
echo "file 'faded_outro.mp4'" >> concat.txt

ffmpeg -y -f concat -safe 0 -i concat.txt -c copy -movflags +faststart highlights.mp4
```

### Step 10: Instagram Re-encode (if posting as Reel)
Instagram silently rejects videos at 29.97fps. Always re-encode:
```bash
ffmpeg -i highlights.mp4 -c:v libx264 -profile:v high -level:v 4.0 -pix_fmt yuv420p \
  -r 30 -g 60 -crf 20 -preset medium \
  -c:a aac -ar 48000 -b:a 192k -ac 2 \
  -movflags +faststart -f mp4 highlights_ig.mp4
```

## Duration Target
- **Under 10 minutes** total
- If over 10 min, reduce candidate clips (keep highest-confidence audio peaks)
- For a match with N goals, expect N + 2-5 extra candidate clips (over-sample)

## Key Learnings
1. **Audio > Visual** for goal detection with VO3 auto-tracking cameras
2. **Volume peaks** at -3 to -7 dB (relative to max) are almost always goals
3. **Halftime** is often the loudest single peak — always exclude it
4. **Second half clips need 2s earlier start** — camera tracking lags more
5. **Over-sample** rather than miss goals — include borderline audio peaks
6. **Clip timing:** 25-27s before peak captures build-up, 8s after captures celebration
7. **Fade transitions** between clips for professional look
8. **Always include intro (match info) and outro (scorers/lineup/branding)**
