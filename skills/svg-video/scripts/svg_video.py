#!/usr/bin/env python3
"""svg-video: SVG animation explainer video pipeline.

Subcommands (called independently by the agent at each workflow step):
  tts          segments.json → MP3 narration audio per segment
  render       HTML files → WebM screen recordings via Playwright
  assemble     WebMs + MP3s → video clips → final MP4
  list-voices  List available TTS voices
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import List, Optional


# ── Data ────────────────────────────────────────────────────────

def load_segments(path: Path) -> List[dict]:
    data = json.loads(path.read_text("utf-8"))
    return data.get("segments", [])


# ── Audio helpers ───────────────────────────────────────────────

def _get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _find_audio(audio_dir: Path, stem: str) -> Optional[Path]:
    mp3 = audio_dir / f"{stem}.mp3"
    return mp3 if mp3.exists() else None


# ── Subcommand: tts ─────────────────────────────────────────────

async def _do_tts(segments: List[dict], audio_dir: Path, voice: str):
    import edge_tts
    count = 0
    for idx, seg in enumerate(segments):
        narration = seg.get("narration", "").strip()
        if not narration:
            continue
        num = idx + 1
        out = audio_dir / f"segment-{num:02d}.mp3"
        await edge_tts.Communicate(narration, voice).save(str(out))
        print(f"  [tts] {out.name}")
        count += 1
    return count


def cmd_tts(args):
    segments = load_segments(Path(args.json))
    audio_dir = Path(args.work_dir) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    engine = getattr(args, "engine", "xskill")

    if engine == "xskill":
        api_key = os.environ.get("XSKILL_API_KEY")
        if not api_key:
            print("错误: 未设置 XSKILL_API_KEY 环境变量", file=sys.stderr)
            print("请执行: export XSKILL_API_KEY='sk-xxx'", file=sys.stderr)
            sys.exit(1)
        voice_id = getattr(args, "voice_id", None) or "male-qn-qingse"
        tts_model = getattr(args, "tts_model", None) or "speech-2.8-hd"
        count = _do_tts_xskill(segments, audio_dir, voice_id, api_key, tts_model)
    else:
        count = asyncio.run(_do_tts(segments, audio_dir, args.voice))

    print(f"\n  {count} 条配音 → {audio_dir}")


# ── xskill TTS (Minimax) ──────────────────────────────────────────

XSKILL_BASE = "https://api.xskill.ai"


def _xskill_req(method: str, path: str, body: dict | None = None,
                token: str | None = None) -> dict:
    url = f"{XSKILL_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.xskill.ai",
        "Referer": "https://www.xskill.ai/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _extract_audio_url(result) -> str | None:
    if isinstance(result, str) and result.startswith("http"):
        return result
    if isinstance(result, dict):
        for key in ("audio_url", "audio_file", "url", "output_url", "file_url"):
            v = result.get(key)
            if v and isinstance(v, str) and v.startswith("http"):
                return v
        for v in result.values():
            found = _extract_audio_url(v)
            if found:
                return found
    if isinstance(result, list):
        for item in result:
            found = _extract_audio_url(item)
            if found:
                return found
    return None


def _download_file(url: str, path: Path):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        path.write_bytes(resp.read())


def _do_tts_xskill(segments: List[dict], audio_dir: Path, voice_id: str,
                    api_key: str, tts_model: str = "speech-2.8-hd") -> int:
    """Batch TTS via xskill minimax/t2a: submit all → poll all → download."""
    items: list[tuple[str, Path]] = []
    for idx, seg in enumerate(segments):
        narration = seg.get("narration", "").strip()
        if not narration:
            continue
        num = idx + 1
        items.append((narration, audio_dir / f"segment-{num:02d}.mp3"))

    if not items:
        return 0

    tasks: list[tuple[str, Path]] = []
    for text, out_path in items:
        params = {"text": text, "voice_id": voice_id, "model": tts_model,
                  "output_format": "url"}
        try:
            resp = _xskill_req("POST", "/api/v3/tasks/create",
                               body={"model": "minimax/t2a", "params": params},
                               token=api_key)
            task_id = resp.get("data", {}).get("task_id")
            if task_id:
                tasks.append((task_id, out_path))
                print(f"  [submit] {out_path.name} → {task_id[:8]}...")
            else:
                print(f"  [error] submit failed {out_path.name}", file=sys.stderr)
        except Exception as e:
            print(f"  [error] {out_path.name}: {e}", file=sys.stderr)
        time.sleep(0.2)

    if not tasks:
        return 0

    print(f"\n  已提交 {len(tasks)} 个语音任务，等待合成...")

    pending = dict(tasks)
    completed = 0
    elapsed = 0
    timeout = 300

    while pending and elapsed < timeout:
        time.sleep(3)
        elapsed += 3
        done = []
        for task_id, out_path in list(pending.items()):
            try:
                resp = _xskill_req("POST", "/api/v3/tasks/query",
                                   body={"task_id": task_id}, token=api_key)
                status = resp.get("data", {}).get("status", "unknown")
                if status == "completed":
                    result = resp.get("data", {}).get("result", {})
                    audio_url = _extract_audio_url(result)
                    if audio_url:
                        _download_file(audio_url, out_path)
                        print(f"  [tts] {out_path.name}")
                        completed += 1
                    else:
                        print(f"  [error] no audio URL: {out_path.name}", file=sys.stderr)
                    done.append(task_id)
                elif status == "failed":
                    err = resp.get("data", {}).get("error", "unknown")
                    print(f"  [error] {out_path.name}: {err}", file=sys.stderr)
                    done.append(task_id)
            except Exception as e:
                print(f"  [warn] poll {out_path.name}: {e}", file=sys.stderr)
        for tid in done:
            pending.pop(tid, None)

    if pending:
        print(f"  [warn] {len(pending)} tasks timed out", file=sys.stderr)

    return completed


# ── Subcommand: list-voices / xskill-voices ─────────────────────


def cmd_xskill_voices(args):
    api_key = os.environ.get("XSKILL_API_KEY")
    if not api_key:
        print("错误: 未设置 XSKILL_API_KEY 环境变量", file=sys.stderr)
        sys.exit(1)
    resp = _xskill_req("POST", "/api/v2/minimax/voices?status=active",
                       body={}, token=api_key)
    voices = resp.get("data", {}).get("public_voices", [])
    tag = getattr(args, "tag", None)
    if tag:
        voices = [v for v in voices if tag in ",".join(v.get("tags") or [])]
    for v in voices:
        tags = ",".join(v.get("tags") or [])
        audio = v.get("audio_url", "")
        print(f"  {v['voice_id']:<45} {v['voice_name']:<20} [{tags}]")
        if audio:
            print(f"    试听: {audio}")
    print(f"\n共 {len(voices)} 个公共音色")


# ── Subcommand: render ──────────────────────────────────────────

async def _do_render(html_dir: Path, video_dir: Path, audio_dir: Path,
                     preload_ms: int = 0, min_hold_ms: int = 0):
    from playwright.async_api import async_playwright
    import tempfile

    html_files = sorted(html_dir.glob("segment-*.html"))
    if not html_files:
        sys.exit(f"未找到 HTML 文件: {html_dir}")

    async with async_playwright() as pw:
        for html_path in html_files:
            stem = html_path.stem
            mp3 = _find_audio(audio_dir, stem)
            audio_ms = int(_get_audio_duration(mp3) * 1000) if mp3 else 4000
            hold_ms = max(audio_ms + 800, min_hold_ms) if min_hold_ms else audio_ms + 800

            if preload_ms > 0:
                browser = await pw.chromium.launch()
                pre_ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                )
                pre_page = await pre_ctx.new_page()
                await pre_page.goto(html_path.resolve().as_uri())
                await pre_page.wait_for_timeout(preload_ms)
                await pre_ctx.close()
                await browser.close()

            tmp_dir = Path(tempfile.mkdtemp(dir=video_dir))
            browser = await pw.chromium.launch()
            ctx = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(tmp_dir),
                record_video_size={"width": 1920, "height": 1080},
            )
            page = await ctx.new_page()
            await page.goto(html_path.resolve().as_uri())
            await page.wait_for_timeout(hold_ms)

            target = video_dir / f"{stem}.webm"
            await ctx.close()
            await page.video.save_as(str(target))
            await browser.close()
            for f in tmp_dir.iterdir():
                f.unlink()
            tmp_dir.rmdir()
            print(f"  [record] {target.name} ({hold_ms}ms)")


def cmd_render(args):
    work = Path(args.work_dir)
    html_dir = work / "html"
    video_dir = work / "video"
    audio_dir = Path(args.audio_dir) if args.audio_dir else work / "audio"
    video_dir.mkdir(parents=True, exist_ok=True)
    preload_ms = int(args.preload_ms) if args.preload_ms else 0
    min_hold_ms = int(args.min_hold_ms) if args.min_hold_ms else 0
    asyncio.run(_do_render(html_dir, video_dir, audio_dir, preload_ms, min_hold_ms))
    count = len(list(video_dir.glob("segment-*.webm")))
    print(f"\n  {count} 段录屏 → {video_dir}")


# ── Subcommand: assemble ───────────────────────────────────────

def _mux_clip(video: Path, audio: Path, out: Path):
    cmd = [
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _concat_clips(clips: List[Path], bg_music: Optional[Path], output: Path):
    lst = output.parent / "concat.txt"
    lst.write_text(
        "\n".join(f"file 'clips/{c.name}'" for c in clips), encoding="utf-8"
    )
    if bg_music:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-i", str(bg_music),
            "-filter_complex",
            "[1:a]volume=0.15[bm];[0:a][bm]amix=inputs=2:duration=first[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
            "-shortest", str(output),
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c", "copy", str(output),
        ]
    subprocess.run(cmd, check=True)


def cmd_assemble(args):
    work = Path(args.work_dir)
    audio_dir = work / "audio"
    video_dir = work / "video"
    clips_dir = work / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    webms = sorted(video_dir.glob("segment-*.webm"))
    if not webms:
        sys.exit(f"未找到录屏文件: {video_dir}")

    print(f"  [mode] 视频录屏模式 ({len(webms)} WebM)")

    clips: list[Path] = []
    for src in webms:
        stem = src.stem
        mp3 = _find_audio(audio_dir, stem)
        if not mp3:
            print(f"  [skip] {src.name} (无音频)")
            continue
        clip = clips_dir / f"clip-{stem.replace('segment-', '')}.mp4"
        _mux_clip(src, mp3, clip)
        clips.append(clip)
        print(f"  [clip] {clip.name}  ← {src.name} + {mp3.name}")

    if not clips:
        sys.exit("没有可拼接的片段")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    bg_music = Path(args.bg_music) if args.bg_music else None
    _concat_clips(clips, bg_music, output)

    duration = _get_audio_duration(output)
    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"\n  视频 → {output}")
    print(f"  时长: {duration:.1f}s | 大小: {size_mb:.1f}MB")


# ── Subcommand: list-voices ────────────────────────────────────

def cmd_list_voices(_args):
    import edge_tts
    voices = asyncio.run(edge_tts.list_voices())
    for v in voices:
        print(f"  {v.get('ShortName',''):30s} {v.get('Locale',''):10s} {v.get('Gender','')}")


# ── CLI entry ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="svg_video",
        description="SVG 动画讲解视频管线（由 Agent 逐步调用）",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("tts", help="segments.json → MP3 配音")
    p.add_argument("--json", required=True, help="segments.json 路径")
    p.add_argument("--work-dir", required=True, help="工作目录")
    p.add_argument("--engine", choices=["xskill", "edge"], default="xskill",
                   help="TTS 引擎：xskill（海螺，默认）/ edge（Edge TTS 免费备选）")
    p.add_argument("--voice-id", default=None,
                   help="xskill 音色 ID（如 male-qn-qingse）")
    p.add_argument("--tts-model", default="speech-2.8-hd",
                   help="xskill TTS 模型（默认 speech-2.8-hd）")
    p.add_argument("--voice", default="zh-CN-YunxiNeural",
                   help="Edge TTS 语音（仅 --engine edge 时使用）")

    p = sub.add_parser("render", help="HTML → Playwright 录屏 WebM")
    p.add_argument("--work-dir", required=True, help="工作目录（含 html/ audio/ 子目录）")
    p.add_argument("--audio-dir", default=None, help="音频目录（默认 <work-dir>/audio）")
    p.add_argument("--preload-ms", default=None, help="预加载等待时间（ms），用于 CDN 资源预热")
    p.add_argument("--min-hold-ms", default=None, help="最小录屏时长（ms），确保动画加载完成")

    sub.add_parser("list-voices", help="列出 Edge TTS 语音")

    p = sub.add_parser("xskill-voices", help="列出 xskill 可用音色（海螺 Minimax）")
    p.add_argument("--tag", help="按标签筛选（如 男/女/中文/英文/儿童）")

    p = sub.add_parser("assemble", help="WebM + MP3 → 最终 MP4")
    p.add_argument("--work-dir", required=True, help="工作目录")
    p.add_argument("--output", required=True, help="输出 mp4 路径")
    p.add_argument("--bg-music", default=None, help="背景乐（可选）")

    args = parser.parse_args()
    dispatch = {
        "tts": cmd_tts,
        "render": cmd_render,
        "list-voices": cmd_list_voices,
        "xskill-voices": cmd_xskill_voices,
        "assemble": cmd_assemble,
    }
    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
