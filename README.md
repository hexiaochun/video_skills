# Tumblr Video Generator

**Cursor Plugin** — Generate Tumblr-style line-by-line reveal videos with TTS narration.

https://github.com/user-attachments/assets/placeholder

## What it does

Turn any text into a vertical short video (1440×2560, 9:16) where lines appear one by one in a Tumblr post card style, synced with AI-generated speech. Minecraft parkour gameplay plays in the background by default.

Perfect for TikTok, Instagram Reels, YouTube Shorts, and other short-form platforms.

## Installation

### From Cursor Marketplace

1. Open Cursor Settings → Marketplace
2. Search for **Tumblr Video Generator**
3. Click Install

### Manual

Clone this repo into your project's `.cursor/skills/` directory:

```bash
git clone https://github.com/user/tumblr-video .cursor/skills/tumblr-video
```

### Prerequisites

- **Python 3.10+**
- **FFmpeg** — `brew install ffmpeg`
- Python dependencies:

```bash
pip install playwright edge-tts Pillow
playwright install chromium
```

## Usage

In Cursor Agent chat, type `/tumblr-video` or just ask:

> "Make a tumblr video about why programmers hate daylight saving time"

The agent will run the pipeline automatically and open the result.

### Direct CLI usage

```bash
bash skills/tumblr-video/scripts/generate.sh "Your text here"
```

### Options

| Flag | Description |
|------|-------------|
| `--voice NAME` | TTS voice (default: `en-US-AndrewNeural`) |
| `--green-screen` | Output with green background (no Minecraft) |
| `--bg-video PATH` | Custom background video |
| `-i FILE` | Read text from file |
| `-o PATH` | Output file path |

### Available voices

| Voice | Gender | Accent |
|-------|--------|--------|
| `en-US-AndrewNeural` | Male | American (default) |
| `en-US-GuyNeural` | Male | American |
| `en-US-AriaNeural` | Female | American |
| `en-US-JennyNeural` | Female | American |
| `en-GB-SoniaNeural` | Female | British |

## Pipeline

1. **HTML Render** — Generates a Tumblr-styled HTML card with progressive line reveals
2. **Screenshot** — Captures each reveal state as a frame using Playwright
3. **TTS** — Synthesizes speech with Edge TTS, gets per-word timestamps
4. **Timeline** — Aligns frame transitions to speech timing
5. **Composite** — Assembles frames + audio + background with FFmpeg

## License

MIT
