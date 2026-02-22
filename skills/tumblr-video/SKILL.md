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
| 海螺语音（推荐，更自然） | `--engine xskill --voice-id male-qn-qingse` |
| 海螺女声 | `--engine xskill --voice-id female-chengshu` |
| Female voice (Edge TTS) | `--voice en-US-AriaNeural` |
| British accent (Edge TTS) | `--voice en-GB-SoniaNeural` |
| Green screen output | `--green-screen` |
| Custom background video | `--bg-video /path/to/bg.mp4` |
| Read text from file | `-i story.txt` |
| Specify output path | `-o /path/output.mp4` |

### Voice Selection

#### xskill 海螺语音（推荐，效果更自然）

需要 `XSKILL_API_KEY` 环境变量。查看可用音色：

```bash
python tumblr_video.py --xskill-voices --tag 男
python tumblr_video.py --xskill-voices --tag 女
```

推荐音色：

| 场景 | 音色 ID | 名称 |
|------|---------|------|
| 科普解说（男声） | `male-qn-qingse` | 青涩青年 |
| 专业权威（男声） | `male-qn-jingying` | 精英青年 |
| 知性讲解（女声） | `female-chengshu` | 成熟女性 |
| 活泼风格（女声） | `female-shaonv` | 少女 |
| 甜美旁白（女声） | `female-tianmei` | 甜美女性 |
| 御姐解说（女声） | `female-yujie` | 御姐 |

#### Edge TTS（免费备选，默认）

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
