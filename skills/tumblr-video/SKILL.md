---
name: tumblr-video
description: Generate Tumblr-style line-by-line reveal videos with TTS narration and Minecraft parkour background. Use when the user wants to create Tumblr post videos, social media short videos, narrated line-by-line animations, brainrot videos, or mentions tumblr video.
---

# Tumblr Post Video Generator

Text → Tumblr-style "line-by-line reveal + TTS narration" vertical short video.

## Description

Generates 1440×2560 vertical video (9:16) where text appears line by line in a Tumblr post card style, synced with TTS audio. Minecraft parkour gameplay is composited as background by default. Ideal for TikTok / Reels / Shorts.

## Instructions

Run the entry script — one command handles the entire pipeline (HTML render → screenshot → TTS → composite → auto-preview):

```bash
bash scripts/generate.sh "Your text content here"
```

> The path above is relative to this skill's directory. Resolve the full path from `SKILL.md` location before running.

### Setup (first time only)

```bash
pip install -r requirements.txt
playwright install chromium
```

### Parameter Reference

| Intent | Extra args |
|--------|-----------|
| Default (Minecraft background) | none |
| Female voice | `--voice en-US-AriaNeural` |
| British accent | `--voice en-GB-SoniaNeural` |
| Green screen output | `--green-screen` |
| Custom background video | `--bg-video /path/to/bg.mp4` |
| Read text from file | `-i story.txt` |
| Specify output path | `-o /path/output.mp4` |

### Available Voices

- `en-US-AndrewNeural` — Male (default)
- `en-US-AriaNeural` — Female
- `en-US-GuyNeural` — Male
- `en-US-JennyNeural` — Female
- `en-GB-SoniaNeural` — Female, British

## Validation

On success the script prints a summary (path, duration, file size) and opens the video on macOS. If it fails, check:

- FFmpeg installed: `ffmpeg -version`
- Python deps: `pip install -r requirements.txt`
- Playwright browser: `playwright install chromium`

## Notes

- Long text (>200 chars or multiline) is automatically saved to a temp file
- Default output path: `/tmp/tumblr-{timestamp}.mp4`
- Speed: ~5s (green screen), ~15s (with background compositing)
