#!/usr/bin/env python3
"""
Tumblr Post Video Generator

Converts text content into a Tumblr-style post video with TTS narration.
Each line of text is revealed progressively in sync with the audio.
Default background: Minecraft parkour gameplay video.

Features:
  - Zero API keys required (uses free edge-tts)
  - Word-level timestamp alignment
  - Automatic line detection and frame capture
  - Minecraft background by default (--green-screen for no background)

Usage:
    python tumblr_video.py "Your text content here"
    python tumblr_video.py -i text.txt -o my-video.mp4
    python tumblr_video.py -i text.txt --voice en-US-AriaNeural
    python tumblr_video.py -i text.txt --green-screen
    python tumblr_video.py --list-voices
"""

import asyncio
import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("Error: playwright not installed. Run: pip install playwright && playwright install chromium")

try:
    import edge_tts
except ImportError:
    sys.exit("Error: edge-tts not installed. Run: pip install edge-tts")

try:
    from PIL import Image
except ImportError:
    sys.exit("Error: Pillow not installed. Run: pip install Pillow")

# ── Video layout ─────────────────────────────────────────────
VIDEO_W, VIDEO_H = 1440, 2560
CARD_W = 1296          # 90 % of VIDEO_W
PAD_X = (VIDEO_W - CARD_W) // 2   # 72
PAD_Y = 256            # top offset 10 %
BG_COLOR = (0, 255, 0) # green-screen
FPS = 30
HEADER_DUR = 0.5       # seconds for header-only frame
TAIL_DUR = 2.0         # seconds to hold full frame after audio ends
DEVICE_SCALE = 3       # Playwright device scale for retina screenshots
VIEWPORT_W = 580       # browser viewport width

# ── Tumblr metadata pools ────────────────────────────────────
_ADJ = ["sleepy", "cosmic", "quiet", "midnight", "gentle", "feral",
        "overthinking", "chaotic", "dreamy", "wandering", "celestial",
        "cryptic", "cozy", "caffeinated", "nostalgic", "softcore"]
_NOUN = ["owl", "dust", "storms", "coffee", "letters", "cranes",
         "foxes", "tea", "rain", "moth", "stars", "books", "soup",
         "cats", "void", "bread"]
_BADGE = {
    "turbo":    '<span class="badge turbo" title="Turbo"><svg viewBox="0 0 16 16"><path d="M8 1l2 5h5l-4 3.5 1.5 5L8 11.5 3.5 14.5 5 9.5 1 6h5z"/></svg></span>',
    "plus":     '<span class="badge plus" title="Plus"><svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="5"/></svg></span>',
    "ad-free":  '<span class="badge ad-free" title="Ad-Free"><svg viewBox="0 0 16 16"><path d="M4 8l3 3 5-6"/></svg></span>',
    "verified": '<span class="badge verified" title="Verified"><svg viewBox="0 0 16 16"><path d="M4 8l3 3 5-6"/></svg></span>',
}
_AV_COLORS = ["#FF6B6B","#4ECDC4","#45B7D1","#96CEB4","#FFEAA7",
              "#DDA0DD","#98D8C8","#F7DC6F","#BB8FCE","#85C1E9"]
_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
           "Jul","Aug","Sep","Oct","Nov","Dec"]
_STOP = {"that","this","with","from","they","have","been","were",
         "will","about","would","could","their","there","because",
         "after","before","like","just","into","your","what","when",
         "some","them","than","more","very","also","much","does"}

# ── HTML template (clean card, no control panel) ─────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--blue:#00b8ff;--bg:#fff;--r:6px;--c:#000;--g:#8c8c8c;--red:#ff4930;--grn:#00cf35}
html{font-size:16px;-webkit-font-smoothing:antialiased}
body{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:transparent;margin:0;padding:20px}
.post{background:var(--bg);border-radius:var(--r);overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.12);max-width:540px}
.post-header{display:flex;align-items:center;padding:16px 16px 0;gap:10px}
.avatar{width:40px;height:40px;border-radius:6px;overflow:hidden;flex-shrink:0;display:flex;align-items:center;justify-content:center;background:%%AVCOL%%}
.avatar-letter{color:#fff;font-size:18px;font-weight:700;text-transform:uppercase}
.post-meta{flex:1;min-width:0}
.username-row{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.username{font-weight:700;font-size:15px;color:var(--c);text-decoration:none;letter-spacing:-.01em;line-height:1.2}
.badges{display:flex;align-items:center;gap:2px;margin-left:2px}
.badge{width:14px;height:14px;border-radius:3px;display:inline-flex;align-items:center;justify-content:center;color:#fff;flex-shrink:0}
.badge.turbo{background:#9b59b6}.badge.plus{background:#ff4930}.badge.ad-free{background:#00cf35}.badge.verified{background:var(--blue)}
.badge svg{width:10px;height:10px;fill:#fff}
.post-date{font-size:13px;color:var(--g);line-height:1.3}
.header-actions{display:flex;align-items:center;gap:8px;flex-shrink:0}
.follow-btn{background:none;border:none;color:var(--blue);font-size:15px;font-weight:600;cursor:pointer;padding:4px 0;font-family:inherit}
.more-btn{background:none;border:none;color:var(--g);cursor:pointer;padding:4px;border-radius:50%;display:flex;align-items:center;justify-content:center}
.more-btn svg{width:20px;height:20px}
.post-body{padding:12px 16px 16px}
.post-text{font-size:15px;line-height:1.55;color:var(--c);word-wrap:break-word;overflow-wrap:break-word}
.post-text p{margin-bottom:.8em}
.post-text p:last-child{margin-bottom:0}
.post-tags{padding:0 16px 12px;display:flex;flex-wrap:wrap;gap:4px}
.tag{font-size:13px;color:var(--g);text-decoration:none}
.post-footer{border-top:1px solid #f0f0f0;padding:0 8px;display:flex;align-items:center;height:46px}
.notes-count{font-size:13px;color:var(--g);padding:0 8px;flex:1;font-weight:500}
.post-actions{display:flex;align-items:center}
.action-btn{background:none;border:none;padding:8px 10px;display:flex;align-items:center;justify-content:center;border-radius:4px}
.action-btn svg{width:20px;height:20px;fill:none;stroke:#8c8c8c;stroke-width:1.8}
</style></head><body>
<article class="post" id="post-card">
  <div class="post-header">
    <div class="avatar"><span class="avatar-letter">%%AVLET%%</span></div>
    <div class="post-meta">
      <div class="username-row">
        <a href="#" class="username">%%USER%%</a>
        <span class="badges">%%BADGES%%</span>
      </div>
      <div class="post-date">%%DATE%%</div>
    </div>
    <div class="header-actions">
      <button class="follow-btn">Follow</button>
      <button class="more-btn" aria-label="More"><svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg></button>
    </div>
  </div>
  <div class="post-body">
    <div class="post-text" id="post-text">%%CONTENT%%</div>
  </div>
  <div class="post-tags" id="post-tags">%%TAGS%%</div>
  <div class="post-footer" id="post-footer">
    <span class="notes-count">%%NOTES%% notes</span>
    <div class="post-actions">
      <button class="action-btn"><svg viewBox="0 0 24 24"><path d="M4 12v7a2 2 0 002 2h12a2 2 0 002-2v-7M16 6l-4-4-4 4M12 2v13"/></svg></button>
      <button class="action-btn"><svg viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg></button>
      <button class="action-btn"><svg viewBox="0 0 24 24"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg></button>
      <button class="action-btn"><svg viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg></button>
    </div>
  </div>
</article>
</body></html>"""


# ═══════════════════════════════════════════════════════════════
#  Step 1 — Generate Tumblr HTML from text
# ═══════════════════════════════════════════════════════════════

def _rand_username():
    return random.choice(_ADJ) + random.choice(_NOUN)

def _rand_date():
    d = datetime.now() - timedelta(days=random.randint(1, 730))
    return f"{_MONTHS[d.month-1]} {d.day}, {d.year}"

def _rand_notes():
    return f"{random.randint(1000, 500000):,}"

def _rand_badges():
    keys = random.sample(list(_BADGE), k=random.randint(0, 3))
    return "".join(_BADGE[k] for k in keys)

def _auto_tags(text):
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    freq = {}
    for w in words:
        if w not in _STOP:
            freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda k: -freq[k])[:5]
    return top or ["thoughts", "life"]


def generate_html(text: str, out: Path) -> Path:
    """Render text into a Tumblr-style HTML card."""
    paras = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    if len(paras) <= 1:
        paras = [p.strip() for p in text.strip().split("\n") if p.strip()]
    content = "\n".join(f"<p>{p}</p>" for p in paras)

    user = _rand_username()
    tags = " ".join(f'<a href="#" class="tag">#{t}</a>' for t in _auto_tags(text))

    html = (HTML_TEMPLATE
            .replace("%%AVCOL%%", random.choice(_AV_COLORS))
            .replace("%%AVLET%%", user[0].upper())
            .replace("%%USER%%",  user)
            .replace("%%BADGES%%", _rand_badges())
            .replace("%%DATE%%",  _rand_date())
            .replace("%%CONTENT%%", content)
            .replace("%%TAGS%%", tags)
            .replace("%%NOTES%%", _rand_notes()))
    out.write_text(html, encoding="utf-8")
    print(f"  [ok] HTML -> {out}")
    return out


# ═══════════════════════════════════════════════════════════════
#  Step 2 — Capture frames + extract line texts  (Playwright)
# ═══════════════════════════════════════════════════════════════

# JS: detect visual lines via Range per-word measurement (non-destructive)
_JS_DETECT = """() => {
  const pt = document.getElementById('post-text');
  const base = pt.getBoundingClientRect();
  const lines = [];
  let lastTop = -Infinity;
  pt.querySelectorAll('p').forEach(p => {
    const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    let nd;
    while (nd = w.nextNode()) {
      const txt = nd.textContent;
      let pos = 0;
      for (const part of txt.split(/(\\s+)/)) {
        if (!part.trim()) { pos += part.length; continue; }
        const r = document.createRange();
        r.setStart(nd, pos);
        r.setEnd(nd, Math.min(pos + part.length, txt.length));
        const rc = r.getClientRects();
        if (rc.length > 0) {
          const top = Math.round(rc[0].top - base.top);
          const bot = Math.round(rc[0].bottom - base.top);
          if (top > lastTop + 2) {
            lastTop = top;
            lines.push({bottom: bot, text: part});
          } else if (lines.length) {
            lines[lines.length-1].text += ' ' + part;
            lines[lines.length-1].bottom = Math.max(lines[lines.length-1].bottom, bot);
          }
        }
        pos += part.length;
      }
    }
  });
  return {
    lineBottoms: lines.map(l => l.bottom),
    lineTexts:   lines.map(l => l.text)
  };
}"""

_JS_APPLY = """({fi, lb}) => {
  const pt = document.getElementById('post-text');
  const tg = document.getElementById('post-tags');
  const ft = document.getElementById('post-footer');
  if (fi < 0) {
    pt.style.overflow='hidden'; pt.style.maxHeight='0px';
    tg.style.display='none'; ft.style.display='none';
  } else if (fi >= lb.length) {
    pt.style.overflow=''; pt.style.maxHeight='';
    tg.style.display=''; ft.style.display='';
  } else {
    tg.style.display='none'; ft.style.display='none';
    pt.style.overflow='hidden'; pt.style.maxHeight=(lb[fi]+2)+'px';
  }
}"""


async def capture_frames(html_path: Path, frames_dir: Path):
    """Return (frame_files: list[Path], line_texts: list[str])."""
    frames_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(
            viewport={"width": VIEWPORT_W, "height": 3000},
            device_scale_factor=DEVICE_SCALE,
        )
        await page.goto(f"file://{html_path.resolve()}")
        await page.wait_for_timeout(600)

        data = await page.evaluate(_JS_DETECT)
        lb = data["lineBottoms"]
        lt = data["lineTexts"]
        print(f"  [ok] {len(lb)} visual lines detected")
        for i, t in enumerate(lt):
            print(f"       L{i+1}: {t[:70]}{'...' if len(t)>70 else ''}")

        card = page.locator("#post-card")
        files = []

        # frame-00  header only
        await page.evaluate(_JS_APPLY, {"fi": -1, "lb": lb})
        await page.wait_for_timeout(80)
        p = frames_dir / "frame-00.png"
        await card.screenshot(path=p)
        files.append(p)

        # frame-01 … frame-NN  progressive reveal
        for i in range(len(lb)):
            await page.evaluate(_JS_APPLY, {"fi": i, "lb": lb})
            await page.wait_for_timeout(80)
            p = frames_dir / f"frame-{i+1:02d}.png"
            await card.screenshot(path=p)
            files.append(p)

        # frame-full  complete post
        await page.evaluate(_JS_APPLY, {"fi": len(lb), "lb": lb})
        await page.wait_for_timeout(80)
        p = frames_dir / "frame-full.png"
        await card.screenshot(path=p)
        files.append(p)

        print(f"  [ok] {len(files)} frames captured")
        await browser.close()
    return files, lt


# ═══════════════════════════════════════════════════════════════
#  Step 3 — TTS audio generation  (edge-tts)
# ═══════════════════════════════════════════════════════════════

def _get_audio_duration(path: Path) -> float:
    """Get audio duration in seconds via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries",
         "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    return float(r.stdout.strip())


async def generate_audio(text: str, voice: str, out: Path) -> Path:
    """Generate TTS audio. Returns audio_path."""
    comm = edge_tts.Communicate(text, voice)
    chunks = []

    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])

    with open(out, "wb") as f:
        for c in chunks:
            f.write(c)

    dur = _get_audio_duration(out)
    print(f"  [ok] Audio -> {out}  ({dur:.2f}s)")
    return out


# ═══════════════════════════════════════════════════════════════
#  Step 4 — Build timeline  (proportional char-count allocation)
# ═══════════════════════════════════════════════════════════════

def build_timeline(line_texts, frame_files, audio_path: Path):
    """Distribute audio duration across lines proportionally by character count.

    Returns list of {frame_file, start, end, duration, text}.
    """
    audio_dur = _get_audio_duration(audio_path)

    total_chars = sum(len(t) for t in line_texts) or 1
    speech_dur = audio_dur   # total time for line-reveal portion

    tl = []

    # ── header frame (brief pause before speech) ─────────────
    tl.append(dict(frame_file=str(frame_files[0]),
                   start=0.0, end=HEADER_DUR,
                   duration=HEADER_DUR, text="(header)"))

    # ── per-line frames (proportional allocation) ────────────
    cursor = HEADER_DUR
    for li, lt in enumerate(line_texts):
        char_ratio = len(lt) / total_chars
        dur = round(speech_dur * char_ratio, 3)
        dur = max(dur, 0.15)  # minimum 150ms per line

        fidx = li + 1   # frame_files[0] = header
        if fidx < len(frame_files) - 1:   # last = frame-full
            tl.append(dict(frame_file=str(frame_files[fidx]),
                           start=round(cursor, 3),
                           end=round(cursor + dur, 3),
                           duration=dur, text=lt))
            cursor += dur

    # ── full-post tail ───────────────────────────────────────
    tl.append(dict(frame_file=str(frame_files[-1]),
                   start=round(cursor, 3),
                   end=round(cursor + TAIL_DUR, 3),
                   duration=TAIL_DUR, text="(full post)"))

    return tl


# ═══════════════════════════════════════════════════════════════
#  Step 5 — Prepare frames  (scale + pad to uniform canvas)
# ═══════════════════════════════════════════════════════════════

def prepare_frames(timeline, prep_dir: Path):
    """Resize each frame onto a VIDEO_W x VIDEO_H green canvas. Returns updated timeline."""
    prep_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, e in enumerate(timeline):
        img = Image.open(e["frame_file"])
        scale = CARD_W / img.width
        h = int(img.height * scale)
        img = img.resize((CARD_W, h), Image.LANCZOS)
        canvas = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
        canvas.paste(img, (PAD_X, PAD_Y))
        p = prep_dir / f"p-{i:03d}.png"
        canvas.save(p)
        out.append({**e, "prepared": str(p)})
    print(f"  [ok] {len(out)} frames prepared ({VIDEO_W}x{VIDEO_H})")
    return out


# ═══════════════════════════════════════════════════════════════
#  Step 6 — Assemble video  (FFmpeg)
# ═══════════════════════════════════════════════════════════════

def _build_greenscreen(timeline, audio: Path, out: Path):
    """Concat frames + audio → green-screen MP4."""
    concat = out.parent / "frames.txt"
    with open(concat, "w") as f:
        for e in timeline:
            f.write(f"file '{Path(e['prepared']).resolve()}'\n")
            f.write(f"duration {e['duration']:.3f}\n")
        f.write(f"file '{Path(timeline[-1]['prepared']).resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [FAIL] FFmpeg stderr:\n{r.stderr[-800:]}")
        raise RuntimeError("FFmpeg failed")
    return out


def _composite_on_bg(greenscreen: Path, bg_video: Path, audio: Path,
                     out: Path):
    """Replace green-screen with background video via chromakey overlay."""
    gs_dur = _get_audio_duration(greenscreen)

    # Step A: prepare background — trim, scale, crop to match canvas
    bg_prep = greenscreen.parent / "bg-prep.mp4"
    cmd_bg = [
        "ffmpeg", "-y", "-i", str(bg_video),
        "-t", str(gs_dur + 2),
        "-vf", f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
               f"crop={VIDEO_W}:{VIDEO_H}",
        "-r", str(FPS), "-an",
        "-c:v", "libx264", "-preset", "fast",
        str(bg_prep),
    ]
    r = subprocess.run(cmd_bg, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"BG prep failed:\n{r.stderr[-500:]}")
    print(f"  [ok] Background prepared -> {bg_prep}")

    # Step B: chromakey overlay  green → transparent → composite
    cmd_ck = [
        "ffmpeg", "-y",
        "-i", str(bg_prep),
        "-i", str(greenscreen),
        "-filter_complex",
        "[1:v]chromakey=0x00FF00:0.25:0.05[fg];"
        "[0:v][fg]overlay=0:0[v]",
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    r = subprocess.run(cmd_ck, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [FAIL] Chromakey stderr:\n{r.stderr[-800:]}")
        raise RuntimeError("Chromakey composite failed")
    print(f"  [ok] Composited -> {out}")
    return out


def assemble_video(timeline, audio: Path, out: Path,
                   bg_video: Path | None = None,
                   work_dir: Path | None = None):
    """Build final video.  If bg_video is given, composite on it;
    otherwise output the green-screen version."""
    tmp = work_dir or out.parent
    gs_path = tmp / "greenscreen.mp4" if bg_video else out
    print(f"  [..] FFmpeg encoding green-screen...")
    _build_greenscreen(timeline, audio, gs_path)
    print(f"  [ok] Green-screen -> {gs_path}")

    if bg_video:
        print(f"  [..] Compositing on background video...")
        _composite_on_bg(gs_path, bg_video, audio, out)
    else:
        print(f"  [ok] Video -> {out}")
    return out


# ═══════════════════════════════════════════════════════════════
#  Pipeline
# ═══════════════════════════════════════════════════════════════

async def run(text: str, output: str, voice: str,
              work_dir: str | None = None, bg_video: str | None = None):
    base = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="tumblr-vid-"))
    base.mkdir(parents=True, exist_ok=True)
    out_path = Path(output).resolve()
    bg_path = Path(bg_video).resolve() if bg_video else None

    bar = "=" * 56
    print(f"\n{bar}")
    print(f"  Tumblr Post Video Generator")
    print(f"{bar}")
    print(f"  Text:   {text[:80]}{'...' if len(text)>80 else ''}")
    print(f"  Voice:  {voice}")
    if bg_path:
        print(f"  BG:     {bg_path}")
    print(f"  Output: {out_path}")
    print(f"  Work:   {base}")
    print(f"{bar}\n")

    # 1 ── HTML
    print("[1/6] Generating HTML...")
    html = generate_html(text, base / "post.html")

    # 2 ── Frames
    print("\n[2/6] Capturing frames...")
    frame_files, line_texts = await capture_frames(html, base / "frames")

    # 3 ── TTS
    print("\n[3/6] Generating TTS audio...")
    audio_path = await generate_audio(text, voice, base / "audio.mp3")

    # 4 ── Timeline
    print("\n[4/6] Building timeline...")
    timeline = build_timeline(line_texts, frame_files, audio_path)
    tl_path = base / "timeline.json"
    tl_path.write_text(json.dumps(timeline, indent=2, ensure_ascii=False))
    print(f"  [ok] Timeline -> {tl_path}")
    for e in timeline:
        print(f"       [{e['start']:6.2f}s – {e['end']:6.2f}s]"
              f"  {e['duration']:5.2f}s  {e['text'][:50]}")

    # 5 ── Prepare
    print("\n[5/6] Preparing frames...")
    timeline = prepare_frames(timeline, base / "prepared")

    # 6 ── FFmpeg
    print("\n[6/6] Assembling video...")
    assemble_video(timeline, audio_path, out_path,
                   bg_video=bg_path, work_dir=base)

    print(f"\n{bar}")
    print(f"  Done!  {out_path}")
    print(f"  Size:  {out_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"{bar}\n")
    return out_path


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

async def _list_voices():
    voices = await edge_tts.list_voices()
    en = [v for v in voices if v["Locale"].startswith("en-")]
    print(f"\nAvailable English voices ({len(en)}):\n")
    for v in sorted(en, key=lambda x: x["ShortName"]):
        print(f"  {v['ShortName']:40s}  {v.get('Gender','')}")
    print()


def main():
    ap = argparse.ArgumentParser(
        description="Generate Tumblr-style post video with TTS narration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python tumblr_video.py "I like talking to small children..."
  python tumblr_video.py -i story.txt -o output.mp4
  python tumblr_video.py -i story.txt --voice en-US-AriaNeural
  python tumblr_video.py -i story.txt --green-screen
  python tumblr_video.py -i story.txt --bg-video custom.mp4
  python tumblr_video.py --list-voices""")

    ap.add_argument("text", nargs="?", help="Text content (or use -i)")
    ap.add_argument("-i", "--input", help="Input text file")
    ap.add_argument("-o", "--output", default="tumblr-video.mp4",
                    help="Output video path  (default: tumblr-video.mp4)")
    ap.add_argument("--voice", default="en-US-AndrewNeural",
                    help="edge-tts voice  (default: en-US-AndrewNeural)")
    ap.add_argument("--bg-video",
                    help="Background video path (default: Minecraft parkour)")
    ap.add_argument("--green-screen", action="store_true",
                    help="Output green-screen video instead of Minecraft background")
    ap.add_argument("--work-dir",
                    help="Working directory for intermediate files")
    ap.add_argument("--list-voices", action="store_true",
                    help="List available English voices and exit")

    args = ap.parse_args()

    if args.list_voices:
        asyncio.run(_list_voices())
        return

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8").strip()
    elif args.text:
        text = args.text
    else:
        ap.print_help()
        sys.exit(1)

    bg = None if args.green_screen else args.bg_video

    asyncio.run(run(text, args.output, args.voice, args.work_dir, bg))


if __name__ == "__main__":
    main()
