#!/usr/bin/env python3
"""knowledge-video: step-by-step video generation pipeline.

Subcommands (called independently by the agent at each workflow step):
  render       JSON → HTML slides → PNG screenshots
  tts          JSON → MP3 narration audio per slide
  assemble     PNGs + MP3s → video clips → final MP4
  list-voices  List available TTS voices
"""

import argparse
import asyncio
import html as html_mod
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ── Data ────────────────────────────────────────────────────────

@dataclass
class KeyPoint:
    text: str
    image: str = ""
    narration: str = ""


@dataclass
class SlideData:
    type: str = "content"
    title: str = ""
    key_points: List[KeyPoint] = field(default_factory=list)
    narration: str = ""
    subtitle: str = ""
    icon: str = ""
    image: str = ""


def load_json_slides(path: Path) -> List[SlideData]:
    data = json.loads(path.read_text("utf-8"))
    raw = data.get("slides", data if isinstance(data, list) else [])
    slides = []
    for s in raw:
        kps = []
        for kp in s.get("key_points", []):
            if isinstance(kp, str):
                kps.append(KeyPoint(text=kp))
            elif isinstance(kp, dict):
                kps.append(KeyPoint(
                    text=kp.get("text", ""),
                    image=kp.get("image", ""),
                    narration=kp.get("narration", ""),
                ))
        slides.append(SlideData(
            type=s.get("type", "content"),
            title=s.get("title", ""),
            key_points=kps,
            narration=s.get("narration", ""),
            subtitle=s.get("subtitle", ""),
            icon=s.get("icon", ""),
            image=s.get("image", ""),
        ))
    return slides


def _has_image_points(slide: SlideData) -> bool:
    return any(kp.image for kp in slide.key_points)


def _has_sub_narrations(slide: SlideData) -> bool:
    return any(kp.narration for kp in slide.key_points)


# ── Accent color palette (rotates per slide) ───────────────────

ACCENT_PALETTE = [
    {"main": "#3B82F6", "light": "#93C5FD", "glow": "rgba(59,130,246,0.30)",  "bg": "rgba(59,130,246,0.12)"},
    {"main": "#8B5CF6", "light": "#C4B5FD", "glow": "rgba(139,92,246,0.30)",  "bg": "rgba(139,92,246,0.12)"},
    {"main": "#EC4899", "light": "#F9A8D4", "glow": "rgba(236,72,153,0.30)",  "bg": "rgba(236,72,153,0.12)"},
    {"main": "#F59E0B", "light": "#FCD34D", "glow": "rgba(245,158,11,0.30)",  "bg": "rgba(245,158,11,0.12)"},
    {"main": "#10B981", "light": "#6EE7B7", "glow": "rgba(16,185,129,0.30)",  "bg": "rgba(16,185,129,0.12)"},
    {"main": "#06B6D4", "light": "#67E8F9", "glow": "rgba(6,182,212,0.30)",   "bg": "rgba(6,182,212,0.12)"},
]

_GRAD_TEXT = "-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent"


# ── HTML slide generation ───────────────────────────────────────

_E = html_mod.escape


def _render_text(text: str) -> str:
    """Escape HTML, converting ==text== to accent-highlighted spans."""
    parts = re.split(r'(==.+?==)', text)
    result = []
    for p in parts:
        if p.startswith('==') and p.endswith('=='):
            result.append(f'<span class="hl">{_E(p[2:-2])}</span>')
        else:
            result.append(_E(p))
    return ''.join(result)


_CSS_BASE = """\
*{box-sizing:border-box;margin:0;padding:0}
body{
  width:1920px;height:1080px;overflow:hidden;position:relative;
  background:radial-gradient(ellipse at 50% 25%,#111827,#0a0e1a 40%,#08080f 70%,#050508);
  font-family:'PingFang SC','Noto Sans SC','Microsoft YaHei','Hiragino Sans GB',system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;
}
.bg-orb{position:absolute;border-radius:50%;filter:blur(100px);pointer-events:none}
.page-num{
  position:absolute;bottom:44px;right:56px;
  font-size:22px;color:rgba(255,255,255,0.20);font-weight:500;
  font-variant-numeric:tabular-nums;letter-spacing:0.5px;
}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes fadeInUp{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeInDown{from{opacity:0;transform:translateY(-30px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeInLeft{from{opacity:0;transform:translateX(-40px)}to{opacity:1;transform:translateX(0)}}
@keyframes fadeInRight{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:translateX(0)}}
@keyframes growX{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes zoomIn{from{opacity:0;transform:scale(0.85)}to{opacity:1;transform:scale(1)}}"""


def _html_doc(css_extra: str, body: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
        f"<style>\n{_CSS_BASE}\n{css_extra}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>"
    )


# ── Original templates (no images) ──────────────────────────────

def _title_slide(s: SlideData, a: dict, pg: str) -> str:
    badge = ""
    if s.icon:
        badge = (
            f'<div class="top-badge" style="animation:fadeInDown 0.5s ease 0s both">'
            f'<span class="top-dot" style="background:{a["main"]}"></span>'
            f'{_E(s.icon)}</div>'
        )
    sub = ""
    if s.subtitle:
        sub = f'<div class="sub" style="animation:fadeInUp 0.5s ease 0.7s both">{_render_text(s.subtitle)}</div>'
    tags_html = ""
    if s.key_points:
        tag_colors = ["#a78bfa", "#34d399", "#60a5fa", "#f472b6", "#fbbf24", "#fb923c"]
        items = []
        for i, kp in enumerate(s.key_points[:6]):
            tc = tag_colors[i % len(tag_colors)]
            items.append(
                f'<div class="kp-tag" style="animation:fadeInUp 0.4s ease {0.9 + i * 0.12:.2f}s both">'
                f'<span class="kp-dot" style="background:{tc}"></span>{_E(kp.text)}</div>'
            )
        tags_html = '<div class="kp-row">' + "\n".join(items) + '</div>'
    narr = ""
    if s.narration.strip():
        narr = f'<div class="narr" style="animation:fadeIn 0.8s ease 1.2s both">{_E(s.narration)}</div>'
    css = f"""\
.wrap{{position:relative;z-index:1;width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:60px 100px 100px}}
.top-badge{{display:inline-flex;align-items:center;gap:10px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:24px;padding:10px 24px;font-size:20px;color:rgba(240,240,245,0.50);font-weight:500;letter-spacing:0.3px;margin-bottom:44px}}
.top-dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0;box-shadow:0 0 10px {a["glow"]}}}
.title{{font-size:82px;font-weight:800;line-height:1.12;letter-spacing:-0.8px;max-width:1500px;background:linear-gradient(135deg,#ffffff 30%,{a["light"]} 100%);{_GRAD_TEXT}}}
.sub{{font-size:38px;color:rgba(240,240,245,0.55);font-weight:500;line-height:1.50;max-width:1300px;margin-top:20px}}
.sub .hl{{font-weight:700;background:linear-gradient(90deg,{a["main"]},{a["light"]});{_GRAD_TEXT}}}
.kp-row{{display:flex;align-items:center;gap:32px;margin-top:44px;flex-wrap:wrap;justify-content:center}}
.kp-tag{{display:flex;align-items:center;gap:10px;font-size:22px;color:rgba(240,240,245,0.55);font-weight:500;white-space:nowrap}}
.kp-dot{{width:11px;height:11px;border-radius:50%;flex-shrink:0}}
.narr{{position:absolute;bottom:60px;left:100px;right:160px;text-align:left;font-size:28px;font-weight:700;line-height:1.55;background:linear-gradient(90deg,{a["main"]},{a["light"]});{_GRAD_TEXT}}}"""
    body = f"""\
<div class="bg-orb" style="width:900px;height:900px;background:{a["bg"]};top:-300px;left:-200px;opacity:0.45"></div>
<div class="bg-orb" style="width:550px;height:550px;background:{a["bg"]};bottom:-200px;right:-120px;opacity:0.28"></div>
<div class="wrap">
  {badge}
  <div class="title" style="animation:fadeInUp 0.6s ease 0.3s both">{_E(s.title)}</div>
  {sub}{tags_html}
</div>
{narr}
<div class="page-num" style="animation:fadeIn 0.4s ease 1s both">{_E(pg)}</div>"""
    return _html_doc(css, body)


def _content_slide(s: SlideData, a: dict, pg: str) -> str:
    icon = f'<span style="font-size:32px;margin-right:8px">{_E(s.icon)}</span>' if s.icon else ""
    pts = "\n".join(
        f'<div class="pt" style="animation:fadeInUp 0.5s ease {0.45 + i * 0.18:.2f}s both">'
        f'<div class="num"><span>{i:02d}</span></div>'
        f'<div class="pt-body"><div class="txt">{_E(p.text)}</div></div></div>'
        for i, p in enumerate(s.key_points[:5], 1)
    )
    css = f"""\
.wrap{{position:relative;z-index:1;padding:68px 88px;height:100%;display:flex;flex-direction:column}}
.header{{margin-bottom:8px}}
.eyebrow{{display:inline-flex;align-items:center;gap:10px;font-size:17px;color:rgba(240,240,245,0.30);font-weight:500;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px}}
.eyebrow-line{{width:28px;height:2px;background:{a["main"]};border-radius:1px;opacity:0.7}}
.hd{{display:flex;align-items:center;justify-content:space-between}}
.title{{font-size:50px;font-weight:750;line-height:1.15;letter-spacing:-0.3px;background:linear-gradient(90deg,#f0f0f5 40%,{a["light"]});{_GRAD_TEXT}}}
.line{{height:2px;margin:24px 0 0;background:linear-gradient(90deg,{a["main"]}90,transparent 50%);transform-origin:left}}
.pts{{display:flex;flex-direction:column;gap:14px;flex:1;padding:28px 0;justify-content:center}}
.pt{{display:flex;align-items:center;gap:26px;background:rgba(255,255,255,0.022);border:1px solid rgba(255,255,255,0.04);border-radius:18px;padding:28px 36px;flex:1;min-height:0}}
.num{{min-width:52px;height:52px;display:flex;align-items:center;justify-content:center;background:{a["bg"]};border:2px solid {a["main"]}40;border-radius:14px;flex-shrink:0}}
.num span{{font-size:24px;font-weight:700;background:linear-gradient(180deg,{a["light"]},{a["main"]});{_GRAD_TEXT}}}
.pt-body{{flex:1;min-width:0}}
.txt{{font-size:33px;color:rgba(240,240,245,0.85);line-height:1.55;font-weight:420}}"""
    body = f"""\
<div class="bg-orb" style="width:600px;height:600px;background:{a["bg"]};top:-100px;right:-120px;opacity:0.45"></div>
<div class="bg-orb" style="width:400px;height:400px;background:{a["bg"]};bottom:-150px;left:-80px;opacity:0.25"></div>
<div class="wrap">
  <div class="header">
    <div class="eyebrow" style="animation:fadeIn 0.4s ease 0s both"><div class="eyebrow-line"></div>SECTION</div>
    <div class="hd">
      <div style="display:flex;align-items:center;animation:fadeIn 0.5s ease 0.1s both">{icon}<div class="title">{_E(s.title)}</div></div>
      <div class="page-num" style="position:static;animation:fadeIn 0.4s ease 1s both">{_E(pg)}</div>
    </div>
    <div class="line" style="animation:growX 0.5s ease 0.3s both"></div>
  </div>
  <div class="pts">{pts}</div>
</div>"""
    return _html_doc(css, body)


def _content_single_noimg_slide(s: SlideData, kp: KeyPoint, kp_idx: int, kp_total: int,
                                a: dict, pg: str) -> str:
    """Full-width layout for a single key_point without image."""
    icon = f'<span style="font-size:30px;margin-right:10px">{_E(s.icon)}</span>' if s.icon else ""
    counter = f"{kp_idx + 1} / {kp_total}" if kp_total > 1 else ""
    num_display = f"{kp_idx + 1:02d}"
    desc_html = ""
    if kp.narration.strip():
        desc_html = (
            f'<div class="desc-card" style="animation:fadeInUp 0.5s ease 0.8s both">'
            f'<div class="desc">{_E(kp.narration)}</div></div>'
        )
    css = f"""\
.wrap{{position:relative;z-index:1;padding:64px 88px;height:100%;display:flex;flex-direction:column}}
.header{{flex-shrink:0}}
.eyebrow{{display:inline-flex;align-items:center;gap:10px;font-size:17px;color:rgba(240,240,245,0.28);font-weight:500;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px}}
.eyebrow-line{{width:28px;height:2px;background:{a["main"]};border-radius:1px;opacity:0.7}}
.hd{{display:flex;align-items:center}}
.title{{font-size:32px;font-weight:600;color:rgba(240,240,245,0.35);line-height:1.3}}
.line{{height:2px;margin:18px 0 0;background:linear-gradient(90deg,{a["main"]}80,transparent 40%);transform-origin:left}}
.main{{flex:1;display:flex;flex-direction:column;justify-content:center;padding:20px 0}}
.big-num{{font-size:160px;font-weight:800;line-height:1;margin-bottom:-40px;letter-spacing:-6px;pointer-events:none;background:linear-gradient(180deg,{a["main"]}18,{a["main"]}03);{_GRAD_TEXT}}}
.point{{font-size:54px;font-weight:700;line-height:1.35;letter-spacing:-0.3px;max-width:1500px;background:linear-gradient(135deg,#ffffff 20%,{a["light"]});{_GRAD_TEXT}}}
.desc-card{{margin-top:32px;background:rgba(255,255,255,0.025);border:1px solid rgba(255,255,255,0.04);border-radius:16px;padding:28px 36px;max-width:1400px}}
.desc{{font-size:28px;color:rgba(240,240,245,0.50);line-height:1.7;font-weight:400}}
.footer{{flex-shrink:0;display:flex;justify-content:space-between;align-items:center;padding-top:12px}}
.counter{{font-size:19px;color:rgba(255,255,255,0.15);font-weight:500;letter-spacing:0.5px}}"""
    body = f"""\
<div class="bg-orb" style="width:750px;height:750px;background:{a["bg"]};top:-180px;right:-140px;opacity:0.5"></div>
<div class="bg-orb" style="width:500px;height:500px;background:{a["bg"]};bottom:-180px;left:-100px;opacity:0.3"></div>
<div class="wrap">
  <div class="header">
    <div class="eyebrow" style="animation:fadeIn 0.4s ease 0s both"><div class="eyebrow-line"></div>SECTION</div>
    <div class="hd" style="animation:fadeIn 0.5s ease 0.1s both">{icon}<div class="title">{_E(s.title)}</div></div>
    <div class="line" style="animation:growX 0.5s ease 0.3s both"></div>
  </div>
  <div class="main">
    <div class="big-num" style="animation:fadeIn 1s ease 0.2s both">{num_display}</div>
    <div class="point" style="animation:fadeInUp 0.6s ease 0.5s both">{_E(kp.text)}</div>
    {desc_html}
  </div>
  <div class="footer">
    <div class="counter" style="animation:fadeIn 0.4s ease 1.0s both">{_E(counter)}</div>
  </div>
</div>
<div class="page-num" style="animation:fadeIn 0.4s ease 1s both">{_E(pg)}</div>"""
    return _html_doc(css, body)


def _summary_slide(s: SlideData, a: dict, pg: str) -> str:
    icon = f'<div style="font-size:36px">{_E(s.icon)}</div>' if s.icon else ""
    chk = '<svg viewBox="0 0 20 20" fill="white" style="width:18px;height:18px"><path d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"/></svg>'
    pts = "\n".join(
        f'<div class="pt" style="animation:fadeInUp 0.5s ease {0.5 + i * 0.22:.2f}s both"><div class="ck">{chk}</div><div class="txt">{_E(p.text)}</div></div>'
        for i, p in enumerate(s.key_points[:5])
    )
    narr = ""
    if s.narration.strip():
        narr = f'\n    <div class="narr" style="animation:fadeIn 0.6s ease 1.5s both">{_E(s.narration)}</div>'
    css = f"""\
.wrap{{position:relative;z-index:1;padding:68px 88px;height:100%;display:flex;flex-direction:column}}
.header{{flex-shrink:0}}
.eyebrow{{display:inline-flex;align-items:center;gap:10px;font-size:17px;color:rgba(240,240,245,0.28);font-weight:500;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px}}
.eyebrow-line{{width:28px;height:2px;background:{a["main"]};border-radius:1px;opacity:0.7}}
.hd{{display:flex;align-items:center;gap:16px}}
.title{{font-size:52px;font-weight:750;letter-spacing:-0.3px;background:linear-gradient(90deg,#f0f0f5 40%,{a["light"]});{_GRAD_TEXT}}}
.bar{{width:100px;height:3px;background:linear-gradient(90deg,{a["main"]},{a["light"]});border-radius:2px;margin:24px 0 0;box-shadow:0 0 18px {a["glow"]};transform-origin:left}}
.main{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:24px;padding:20px 0}}
.pts{{display:flex;flex-direction:column;gap:22px}}
.pt{{display:flex;align-items:center;gap:22px;padding:10px 0}}
.ck{{width:42px;height:42px;background:linear-gradient(135deg,{a["main"]},{a["light"]});border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 4px 18px {a["glow"]}}}
.txt{{font-size:35px;color:rgba(240,240,245,0.85);line-height:1.52;font-weight:420}}
.narr{{font-size:28px;font-weight:600;line-height:1.65;padding-top:12px;background:linear-gradient(90deg,{a["main"]},{a["light"]});{_GRAD_TEXT}}}"""
    body = f"""\
<div class="bg-orb" style="width:700px;height:700px;background:{a["bg"]};bottom:-220px;left:-120px;opacity:0.45"></div>
<div class="bg-orb" style="width:400px;height:400px;background:{a["bg"]};top:-140px;right:-80px;opacity:0.25"></div>
<div class="wrap">
  <div class="header">
    <div class="eyebrow" style="animation:fadeIn 0.4s ease 0s both"><div class="eyebrow-line"></div>SUMMARY</div>
    <div class="hd" style="animation:fadeIn 0.5s ease 0.1s both">{icon}<div class="title">{_E(s.title)}</div></div>
    <div class="bar" style="animation:growX 0.5s ease 0.3s both"></div>
  </div>
  <div class="main">
    <div class="pts">{pts}</div>{narr}
  </div>
</div>
<div class="page-num" style="animation:fadeIn 0.4s ease 1s both">{_E(pg)}</div>"""
    return _html_doc(css, body)


# ── New templates (with images) ──────────────────────────────────

def _image_slide(image_uri: str, a: dict, pg: str) -> str:
    """Standalone centered image on dark background."""
    css = f"""\
.wrap{{position:relative;z-index:1;width:100%;height:100%;display:flex;align-items:center;justify-content:center}}
.img-box{{border-radius:24px;overflow:hidden;box-shadow:0 20px 80px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.06)}}
.img-box img{{display:block;max-width:1600px;max-height:920px;object-fit:contain}}"""
    body = f"""\
<div class="bg-orb" style="width:600px;height:600px;background:{a["bg"]};top:-120px;left:50%;transform:translateX(-50%);opacity:0.4"></div>
<div class="wrap">
  <div class="img-box" style="animation:zoomIn 0.7s ease 0.2s both"><img src="{_E(image_uri)}"></div>
</div>
<div class="page-num" style="animation:fadeIn 0.4s ease 1s both">{_E(pg)}</div>"""
    return _html_doc(css, body)


def _content_single_slide(s: SlideData, kp: KeyPoint, kp_idx: int, kp_total: int,
                          image_uri: str, a: dict, pg: str) -> str:
    """Split layout: left text (55%) + right image (45%)."""
    icon = f'<span style="font-size:28px;margin-right:10px">{_E(s.icon)}</span>' if s.icon else ""
    counter = f"{kp_idx + 1} / {kp_total}" if kp_total > 1 else ""
    num_display = f"{kp_idx + 1:02d}"
    desc_html = ""
    if kp.narration.strip():
        desc_html = (
            f'<div class="desc-card" style="animation:fadeInUp 0.5s ease 0.8s both">'
            f'<div class="desc">{_E(kp.narration)}</div></div>'
        )
    css = f"""\
.wrap{{position:relative;z-index:1;padding:64px 72px;height:100%;display:flex;align-items:stretch;gap:48px}}
.left{{flex:0 0 52%;display:flex;flex-direction:column}}
.l-header{{flex-shrink:0}}
.eyebrow{{display:inline-flex;align-items:center;gap:10px;font-size:17px;color:rgba(240,240,245,0.28);font-weight:500;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}}
.eyebrow-line{{width:28px;height:2px;background:{a["main"]};border-radius:1px;opacity:0.7}}
.hd{{display:flex;align-items:center}}
.title{{font-size:30px;font-weight:600;color:rgba(240,240,245,0.35);line-height:1.3}}
.line{{height:2px;margin:14px 0 0;background:linear-gradient(90deg,{a["main"]}80,transparent 45%);transform-origin:left}}
.l-main{{flex:1;display:flex;flex-direction:column;justify-content:center;padding:12px 0}}
.big-num{{font-size:120px;font-weight:800;line-height:1;margin-bottom:-28px;letter-spacing:-5px;pointer-events:none;background:linear-gradient(180deg,{a["main"]}18,{a["main"]}03);{_GRAD_TEXT}}}
.point{{font-size:40px;font-weight:700;line-height:1.4;letter-spacing:-0.3px;background:linear-gradient(135deg,#ffffff 20%,{a["light"]});{_GRAD_TEXT}}}
.desc-card{{margin-top:24px;background:rgba(255,255,255,0.025);border:1px solid rgba(255,255,255,0.04);border-radius:14px;padding:22px 28px}}
.desc{{font-size:25px;color:rgba(240,240,245,0.48);line-height:1.65;font-weight:400}}
.l-footer{{flex-shrink:0;padding-top:10px}}
.counter{{font-size:19px;color:rgba(255,255,255,0.15);font-weight:500;letter-spacing:0.5px}}
.right{{flex:1;display:flex;align-items:center;justify-content:center}}
.img-box{{border-radius:20px;overflow:hidden;box-shadow:0 16px 60px rgba(0,0,0,0.45),0 0 0 1px rgba(255,255,255,0.05)}}
.img-box img{{display:block;max-width:100%;max-height:900px;object-fit:contain}}"""
    body = f"""\
<div class="bg-orb" style="width:550px;height:550px;background:{a["bg"]};top:-100px;right:-80px;opacity:0.4"></div>
<div class="wrap">
  <div class="left">
    <div class="l-header">
      <div class="eyebrow" style="animation:fadeIn 0.4s ease 0s both"><div class="eyebrow-line"></div>SECTION</div>
      <div class="hd" style="animation:fadeIn 0.5s ease 0.1s both">{icon}<div class="title">{_E(s.title)}</div></div>
      <div class="line" style="animation:growX 0.5s ease 0.3s both"></div>
    </div>
    <div class="l-main">
      <div class="big-num" style="animation:fadeIn 1s ease 0.2s both">{num_display}</div>
      <div class="point" style="animation:fadeInUp 0.6s ease 0.5s both">{_E(kp.text)}</div>
      {desc_html}
    </div>
    <div class="l-footer">
      <div class="counter" style="animation:fadeIn 0.4s ease 1.0s both">{_E(counter)}</div>
    </div>
  </div>
  <div class="right">
    <div class="img-box" style="animation:zoomIn 0.6s ease 0.7s both"><img src="{_E(image_uri)}"></div>
  </div>
</div>
<div class="page-num" style="animation:fadeIn 0.4s ease 1s both">{_E(pg)}</div>"""
    return _html_doc(css, body)


def _summary_split_slide(s: SlideData, image_uri: str, a: dict, pg: str) -> str:
    """Summary with checkmarks on left + image on right."""
    icon = f'<div style="font-size:36px">{_E(s.icon)}</div>' if s.icon else ""
    chk = '<svg viewBox="0 0 20 20" fill="white" style="width:18px;height:18px"><path d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"/></svg>'
    pts = "\n".join(
        f'<div class="pt" style="animation:fadeInUp 0.5s ease {0.5 + i * 0.22:.2f}s both"><div class="ck">{chk}</div><div class="txt">{_E(p.text)}</div></div>'
        for i, p in enumerate(s.key_points[:5])
    )
    css = f"""\
.wrap{{position:relative;z-index:1;padding:72px 80px;height:100%;display:flex;align-items:stretch;gap:52px}}
.left{{flex:0 0 50%;display:flex;flex-direction:column;justify-content:center}}
.eyebrow{{display:inline-flex;align-items:center;gap:10px;font-size:17px;color:rgba(240,240,245,0.28);font-weight:500;letter-spacing:1px;text-transform:uppercase;margin-bottom:14px}}
.eyebrow-line{{width:28px;height:2px;background:{a["main"]};border-radius:1px;opacity:0.7}}
.hd{{display:flex;align-items:center;gap:16px}}
.title{{font-size:50px;font-weight:750;letter-spacing:-0.3px;background:linear-gradient(90deg,#f0f0f5 40%,{a["light"]});{_GRAD_TEXT}}}
.bar{{width:100px;height:3px;background:linear-gradient(90deg,{a["main"]},{a["light"]});border-radius:2px;margin:26px 0 34px;box-shadow:0 0 18px {a["glow"]};transform-origin:left}}
.pts{{display:flex;flex-direction:column;gap:18px}}
.pt{{display:flex;align-items:center;gap:18px;padding:6px 0}}
.ck{{width:36px;height:36px;background:linear-gradient(135deg,{a["main"]},{a["light"]});border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 4px 18px {a["glow"]}}}
.txt{{font-size:31px;color:rgba(240,240,245,0.85);line-height:1.48;font-weight:420}}
.right{{flex:1;display:flex;align-items:center;justify-content:center}}
.img-box{{border-radius:20px;overflow:hidden;box-shadow:0 16px 60px rgba(0,0,0,0.45),0 0 0 1px rgba(255,255,255,0.05)}}
.img-box img{{display:block;max-width:100%;max-height:880px;object-fit:contain}}"""
    body = f"""\
<div class="bg-orb" style="width:550px;height:550px;background:{a["bg"]};bottom:-140px;left:-80px;opacity:0.4"></div>
<div class="wrap">
  <div class="left">
    <div class="eyebrow" style="animation:fadeIn 0.4s ease 0s both"><div class="eyebrow-line"></div>SUMMARY</div>
    <div class="hd" style="animation:fadeIn 0.5s ease 0.1s both">{icon}<div class="title">{_E(s.title)}</div></div>
    <div class="bar" style="animation:growX 0.5s ease 0.3s both"></div>
    <div class="pts">{pts}</div>
  </div>
  <div class="right">
    <div class="img-box" style="animation:zoomIn 0.6s ease 0.8s both"><img src="{_E(image_uri)}"></div>
  </div>
</div>
<div class="page-num" style="animation:fadeIn 0.4s ease 1s both">{_E(pg)}</div>"""
    return _html_doc(css, body)


# ── Render plan: expand slides into sub-pages ───────────────────

@dataclass
class RenderPage:
    """One HTML page to render."""
    slide_num: int          # 1-based slide number (for grouping with audio)
    sub: str                # suffix: "" for single, "a"/"b"/"c" for multi
    html: str               # full HTML string
    work_dir: Path = field(default_factory=Path)

    @property
    def stem(self) -> str:
        return f"slide-{self.slide_num:02d}{self.sub}"


def _resolve_image(image_rel: str, work_dir: Path) -> str:
    """Turn a work-dir-relative image path into a file:// URI."""
    p = (work_dir / image_rel).resolve()
    return p.as_uri() if p.exists() else ""


def expand_slides(slides: List[SlideData], work_dir: Path) -> List[RenderPage]:
    """Expand each slide into one or more RenderPages."""
    total = len(slides)
    pages: List[RenderPage] = []

    for idx, s in enumerate(slides):
        accent = ACCENT_PALETTE[idx % len(ACCENT_PALETTE)]
        pg = f"{idx + 1:02d} / {total:02d}"
        num = idx + 1

        if s.type == "title":
            pages.append(RenderPage(num, "", _title_slide(s, accent, pg), work_dir))

        elif s.type == "summary":
            if s.image:
                uri = _resolve_image(s.image, work_dir)
                if uri:
                    pages.append(RenderPage(num, "", _summary_split_slide(s, uri, accent, pg), work_dir))
                else:
                    pages.append(RenderPage(num, "", _summary_slide(s, accent, pg), work_dir))
            else:
                pages.append(RenderPage(num, "", _summary_slide(s, accent, pg), work_dir))

        elif _has_image_points(s) or _has_sub_narrations(s):
            kp_total = len(s.key_points)
            for ki, kp in enumerate(s.key_points):
                sub = chr(97 + ki)  # a, b, c, ...
                uri = _resolve_image(kp.image, work_dir) if kp.image else ""
                if uri:
                    html = _content_single_slide(s, kp, ki, kp_total, uri, accent, pg)
                else:
                    html = _content_single_noimg_slide(s, kp, ki, kp_total, accent, pg)
                pages.append(RenderPage(num, sub, html, work_dir))

        else:
            pages.append(RenderPage(num, "", _content_slide(s, accent, pg), work_dir))

    return pages


# ── Subcommand: render ──────────────────────────────────────────

def _find_audio_for_stem(audio_dir: Path, stem: str) -> Optional[Path]:
    """Find the matching MP3 for a render page stem, with fallback."""
    mp3 = audio_dir / f"{stem}.mp3"
    if mp3.exists():
        return mp3
    num_match = re.match(r"slide-(\d+)", stem)
    if num_match:
        fallback = audio_dir / f"slide-{num_match.group(1)}.mp3"
        if fallback.exists():
            return fallback
    return None


async def _do_render(pages: List[RenderPage], html_dir: Path, slides_dir: Path):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        for rp in pages:
            html_path = html_dir / f"{rp.stem}.html"
            png_path = slides_dir / f"{rp.stem}.png"
            html_path.write_text(rp.html, encoding="utf-8")
            await page.goto(html_path.resolve().as_uri())
            await page.wait_for_timeout(2500)
            await page.screenshot(path=str(png_path), full_page=False, type="png")
            print(f"  [render] {png_path.name}")
        await browser.close()


async def _do_render_video(pages: List[RenderPage], html_dir: Path,
                           video_dir: Path, audio_dir: Path):
    """Record each HTML page as a WebM video using Playwright screen recording."""
    from playwright.async_api import async_playwright
    import tempfile
    async with async_playwright() as pw:
        for rp in pages:
            html_path = html_dir / f"{rp.stem}.html"
            html_path.write_text(rp.html, encoding="utf-8")

            mp3 = _find_audio_for_stem(audio_dir, rp.stem)
            hold_ms = int(_get_audio_duration(mp3) * 1000) + 800 if mp3 else 5000

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

            target = video_dir / f"{rp.stem}.webm"
            await ctx.close()
            await page.video.save_as(str(target))
            await browser.close()
            for f in tmp_dir.iterdir():
                f.unlink()
            tmp_dir.rmdir()
            print(f"  [record] {target.name} ({hold_ms}ms)")


def cmd_render(args):
    slides = load_json_slides(Path(args.json))
    work = Path(args.work_dir)
    html_dir = work / "html"
    pages = expand_slides(slides, work)

    mode = getattr(args, "mode", "screenshot")
    if mode == "video":
        video_dir = work / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        html_dir.mkdir(parents=True, exist_ok=True)
        audio_dir = Path(args.audio_dir) if args.audio_dir else work / "audio"
        asyncio.run(_do_render_video(pages, html_dir, video_dir, audio_dir))
        print(f"\n  {len(pages)} 页录屏 → {video_dir}")
    else:
        slides_dir = work / "slides"
        for d in (html_dir, slides_dir):
            d.mkdir(parents=True, exist_ok=True)
        asyncio.run(_do_render(pages, html_dir, slides_dir))
        print(f"\n  {len(pages)} 页幻灯片 → {slides_dir}")


# ── Subcommand: tts ─────────────────────────────────────────────

async def _do_tts(slides: List[SlideData], audio_dir: Path, voice: str):
    import edge_tts
    count = 0
    for idx, s in enumerate(slides):
        num = idx + 1
        has_sub = any(kp.narration for kp in s.key_points)

        if has_sub:
            for ki, kp in enumerate(s.key_points):
                if not kp.narration.strip():
                    continue
                sub = chr(97 + ki)
                out = audio_dir / f"slide-{num:02d}{sub}.mp3"
                await edge_tts.Communicate(kp.narration, voice).save(str(out))
                print(f"  [tts] {out.name}")
                count += 1
        elif s.narration.strip():
            out = audio_dir / f"slide-{num:02d}.mp3"
            await edge_tts.Communicate(s.narration, voice).save(str(out))
            print(f"  [tts] {out.name}")
            count += 1

            if s.image and not has_sub:
                sub_pages = _count_sub_pages(s)
                if sub_pages > 1:
                    for si in range(sub_pages):
                        sub = chr(97 + si)
                        dst = audio_dir / f"slide-{num:02d}{sub}.mp3"
                        if not dst.exists():
                            import shutil
                            shutil.copy2(str(out), str(dst))
    return count


def _count_sub_pages(s: SlideData) -> int:
    """Count how many sub-pages a slide will produce."""
    if s.type == "title" and s.image:
        return 2
    if _has_image_points(s) or _has_sub_narrations(s):
        return len(s.key_points)
    return 1


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
    """Recursively search for an audio URL in xskill task result."""
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


def _do_tts_xskill(slides: List[SlideData], audio_dir: Path, voice_id: str,
                    api_key: str, tts_model: str = "speech-2.8-hd") -> int:
    """Batch TTS via xskill minimax/t2a: submit all → poll all → download."""
    segments: list[tuple[str, Path]] = []
    for idx, s in enumerate(slides):
        num = idx + 1
        has_sub = any(kp.narration for kp in s.key_points)
        if has_sub:
            for ki, kp in enumerate(s.key_points):
                if not kp.narration.strip():
                    continue
                sub = chr(97 + ki)
                segments.append((kp.narration, audio_dir / f"slide-{num:02d}{sub}.mp3"))
        elif s.narration.strip():
            segments.append((s.narration, audio_dir / f"slide-{num:02d}.mp3"))

    if not segments:
        return 0

    tasks: list[tuple[str, Path]] = []
    for text, out_path in segments:
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

    for idx, s in enumerate(slides):
        num = idx + 1
        has_sub = any(kp.narration for kp in s.key_points)
        if s.narration.strip() and s.image and not has_sub:
            main_mp3 = audio_dir / f"slide-{num:02d}.mp3"
            if main_mp3.exists():
                sub_pages = _count_sub_pages(s)
                if sub_pages > 1:
                    import shutil
                    for si in range(sub_pages):
                        sub = chr(97 + si)
                        dst = audio_dir / f"slide-{num:02d}{sub}.mp3"
                        if not dst.exists():
                            shutil.copy2(str(main_mp3), str(dst))

    return completed


def cmd_tts(args):
    slides = load_json_slides(Path(args.json))
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
        count = _do_tts_xskill(slides, audio_dir, voice_id, api_key, tts_model)
    else:
        count = asyncio.run(_do_tts(slides, audio_dir, args.voice))

    print(f"\n  {count} 条配音 → {audio_dir}")


# ── Subcommand: list-voices / xskill-voices ─────────────────────

def cmd_list_voices(_args):
    import edge_tts
    voices = asyncio.run(edge_tts.list_voices())
    for v in voices:
        print(f"  {v.get('ShortName',''):30s} {v.get('Locale',''):10s} {v.get('Gender','')}")


def cmd_xskill_voices(args):
    resp = _xskill_req("POST", "/api/v2/minimax/voices?status=active", body={})
    voices = resp.get("data", {}).get("public_voices", [])
    tag = getattr(args, "tag", None)
    if tag:
        voices = [v for v in voices if tag in (v.get("tags") or [])]
    for v in voices:
        tags = ",".join(v.get("tags") or [])
        audio = v.get("audio_url", "")
        print(f"  {v['voice_id']:<45} {v['voice_name']:<20} [{tags}]")
        if audio:
            print(f"    试听: {audio}")
    print(f"\n共 {len(voices)} 个公共音色")


# ── Subcommand: assemble ───────────────────────────────────────

def _get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _make_clip(image: Path, audio: Path, out: Path,
               bg_video: Optional[Path], bg_color: str):
    """Single image + audio → video clip."""
    pad_ms = 300
    if bg_video:
        inputs = ["-i", str(bg_video), "-loop", "1", "-i", str(image), "-i", str(audio)]
        fc = (
            "[0:v]scale=1920:1080,setsar=1:1,boxblur=20:1[b];"
            "[1:v]scale=1920:1080[fg];"
            "[b][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[v]"
        )
    else:
        inputs = [
            "-f", "lavfi", "-i", f"color=c={bg_color}:s=1920x1080:d=120",
            "-loop", "1", "-i", str(image),
            "-i", str(audio),
        ]
        fc = (
            "[0:v]scale=1920:1080,setsar=1:1[vbg];"
            "[1:v]scale=1920:1080[fg];"
            "[vbg][fg]overlay=0:0:shortest=1[v]"
        )
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", fc,
        "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-af", f"adelay={pad_ms}|{pad_ms},apad=pad_dur=0.3",
        "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _make_slideshow_clip(images: List[Path], audio: Path, out: Path, bg_color: str):
    """Multiple images + one audio → video clip (images auto-rotate)."""
    pad_ms = 300
    duration = _get_audio_duration(audio)
    total_visual = duration + pad_ms / 1000.0 + 0.3
    per_image = total_visual / len(images)

    inputs = []
    for img in images:
        inputs.extend(["-loop", "1", "-t", f"{per_image:.3f}", "-i", str(img)])
    inputs.extend(["-i", str(audio)])

    n = len(images)
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]scale=1920:1080,setsar=1:1[v{i}]")
    concat_in = "".join(f"[v{i}]" for i in range(n))
    parts.append(f"{concat_in}concat=n={n}:v=1:a=0[v]")
    fc = ";".join(parts)

    audio_idx = n
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", fc,
        "-map", "[v]", "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-af", f"adelay={pad_ms}|{pad_ms},apad=pad_dur=0.3",
        "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _mux_clip(video: Path, audio: Path, out: Path):
    """Mux recorded WebM video + MP3 audio → MP4 clip."""
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
            "-filter_complex", "[1:a]volume=0.15[bm];[0:a][bm]amix=inputs=2:duration=first[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(output),
        ]
    else:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(output)]
    subprocess.run(cmd, check=True)


def cmd_assemble(args):
    work = Path(args.work_dir)
    audio_dir = work / "audio"
    clips_dir = work / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    video_dir = work / "video"
    slides_dir = work / "slides"
    webms = sorted(video_dir.glob("slide-*.webm")) if video_dir.exists() else []
    use_video = len(webms) > 0

    if use_video:
        sources = webms
        print(f"  [mode] 视频录屏模式 ({len(webms)} WebM)")
    else:
        sources = sorted(slides_dir.glob("slide-*.png"))
        print(f"  [mode] 静态截图模式 ({len(sources)} PNG)")

    if not sources:
        sys.exit(f"未找到幻灯片: {video_dir if use_video else slides_dir}")

    bg_video = Path(args.bg_video) if args.bg_video else None
    bg_music = Path(args.bg_music) if args.bg_music else None

    clips: list[Path] = []
    for src in sources:
        stem = src.stem
        mp3 = _find_audio_for_stem(audio_dir, stem)
        if not mp3:
            print(f"  [skip] {src.name} (无音频)")
            continue
        clip = clips_dir / f"clip-{stem.replace('slide-', '')}.mp4"
        if use_video:
            _mux_clip(src, mp3, clip)
        else:
            _make_clip(src, mp3, clip, bg_video, args.bg_color)
        clips.append(clip)
        print(f"  [clip] {clip.name}  ← {src.name} + {mp3.name}")

    if not clips:
        sys.exit("没有可拼接的片段")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _concat_clips(clips, bg_music, output)
    print(f"\n  视频 → {output}")


# ── CLI entry ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="knowledge_video",
        description="分步视频生成管线（由 Agent 逐步调用）",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("render", help="JSON → HTML → PNG/WebM")
    p.add_argument("--json", required=True, help="slides.json 路径")
    p.add_argument("--work-dir", required=True, help="工作目录")
    p.add_argument("--mode", choices=["screenshot", "video"], default="screenshot",
                   help="screenshot=截图PNG, video=Playwright录屏WebM")
    p.add_argument("--audio-dir", default=None,
                   help="音频目录（video 模式需要，用于确定录制时长）")

    p = sub.add_parser("tts", help="JSON → MP3 口播配音")
    p.add_argument("--json", required=True, help="slides.json 路径")
    p.add_argument("--work-dir", required=True, help="工作目录")
    p.add_argument("--engine", choices=["xskill", "edge"], default="xskill",
                   help="TTS 引擎：xskill（海螺，默认）/ edge（Edge TTS 免费备选）")
    p.add_argument("--voice-id", default=None,
                   help="xskill 音色 ID（如 male-qn-qingse）")
    p.add_argument("--tts-model", default="speech-2.8-hd",
                   help="xskill TTS 模型（默认 speech-2.8-hd）")
    p.add_argument("--voice", default="zh-CN-YunxiNeural",
                   help="Edge TTS 语音（仅 --engine edge 时使用）")

    sub.add_parser("list-voices", help="列出 Edge TTS 语音")

    p = sub.add_parser("xskill-voices", help="列出 xskill 可用音色（海螺 Minimax）")
    p.add_argument("--tag", help="按标签筛选（如 男/女/中文/英文/儿童）")

    p = sub.add_parser("assemble", help="PNG + MP3 → 视频片段 → 最终 MP4")
    p.add_argument("--work-dir", required=True, help="工作目录（含 slides/ audio/ 子目录）")
    p.add_argument("--output", required=True, help="输出 mp4 路径")
    p.add_argument("--bg-video", default=None, help="背景视频（可选）")
    p.add_argument("--bg-music", default=None, help="背景乐（可选）")
    p.add_argument("--bg-color", default="#08080f", help="底色（默认 #08080f）")

    args = parser.parse_args()
    dispatch = {
        "render": cmd_render,
        "tts": cmd_tts,
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
