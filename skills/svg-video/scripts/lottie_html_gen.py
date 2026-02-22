#!/usr/bin/env python3
"""Search LottieFiles for animations and generate HTML pages for each segment."""

import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

GRAPHQL_URL = "https://graphql.lottiefiles.com/2022-08"

SEARCH_QUERY = """
query Search($query: String!, $first: Int) {
  searchPublicAnimations(query: $query, first: $first) {
    totalCount
    edges {
      node {
        id name lottieUrl jsonUrl imageUrl downloads likesCount
      }
    }
  }
}
"""

COLOR_THEMES = [
    {"accent": "#3B82F6", "light": "#93C5FD", "glow": "rgba(59,130,246,0.15)",  "bg_l": "#111827", "bg_d": "#08080f"},
    {"accent": "#8B5CF6", "light": "#C4B5FD", "glow": "rgba(139,92,246,0.15)", "bg_l": "#130f1f", "bg_d": "#08080f"},
    {"accent": "#EC4899", "light": "#F9A8D4", "glow": "rgba(236,72,153,0.15)", "bg_l": "#1a0f15", "bg_d": "#08080f"},
    {"accent": "#F59E0B", "light": "#FCD34D", "glow": "rgba(245,158,11,0.15)", "bg_l": "#1a1508", "bg_d": "#08080f"},
    {"accent": "#10B981", "light": "#6EE7B7", "glow": "rgba(16,185,129,0.15)", "bg_l": "#0f1a16", "bg_d": "#08080f"},
    {"accent": "#06B6D4", "light": "#67E8F9", "glow": "rgba(6,182,212,0.15)",  "bg_l": "#0f171a", "bg_d": "#08080f"},
]


def search_lottie(keyword: str, limit: int = 8) -> list[dict]:
    payload = json.dumps({
        "query": SEARCH_QUERY,
        "variables": {"query": keyword, "first": limit},
    }).encode()
    req = Request(GRAPHQL_URL, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Origin": "https://lottiefiles.com",
        "Referer": "https://lottiefiles.com/",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        edges = data.get("data", {}).get("searchPublicAnimations", {}).get("edges", [])
        return [e["node"] for e in edges]
    except (URLError, KeyError, json.JSONDecodeError) as exc:
        print(f"  [warn] search '{keyword}' failed: {exc}", file=sys.stderr)
        return []


def pick_best(results: list[dict]) -> dict | None:
    if not results:
        return None
    scored = sorted(results, key=lambda r: (r.get("downloads", 0) or 0) + (r.get("likesCount", 0) or 0) * 2, reverse=True)
    for r in scored:
        if r.get("lottieUrl") or r.get("jsonUrl"):
            return r
    return scored[0] if scored else None


def generate_html(seg: dict, idx: int, total: int, lottie_url: str, lottie_name: str) -> str:
    theme = COLOR_THEMES[idx % len(COLOR_THEMES)]
    num_str = f"{idx+1:02d} / {total:02d}"
    narration = seg["narration"]
    src_url = lottie_url

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<script src="https://unpkg.com/@dotlottie/player-component@2.7.12/dist/dotlottie-player.mjs" type="module"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1920px; height: 1080px; overflow: hidden;
    background: radial-gradient(ellipse at 50% 30%, {theme["bg_l"]}, {theme["bg_d"]} 60%, #050508);
    font-family: 'PingFang SC','Noto Sans SC','Microsoft YaHei',system-ui,sans-serif;
    -webkit-font-smoothing: antialiased;
    position: relative;
  }}

  .bg-orb {{
    position: absolute; border-radius: 50%;
    filter: blur(120px); pointer-events: none;
  }}

  .lottie-stage {{
    position: absolute; top: 40px; left: 0;
    width: 1920px; height: 700px;
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
    animation: scaleIn 0.5s ease both;
  }}

  dotlottie-player {{
    width: 560px; height: 560px;
    filter: drop-shadow(0 0 80px {theme["glow"]});
  }}

  .text-bar {{
    position: absolute; bottom: 0; left: 0; right: 0;
    height: 340px;
    background: linear-gradient(to bottom, transparent 0%, rgba(5,5,8,0.7) 25%, rgba(5,5,8,0.95) 50%);
    display: flex; align-items: center; justify-content: center;
    padding: 0 120px;
  }}
  .text-content {{
    font-size: 64px; font-weight: 800; line-height: 1.4;
    text-align: center; letter-spacing: 4px;
    background: linear-gradient(135deg, #ffffff 0%, {theme["light"]} 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: fadeInUp 0.4s ease 0.2s both;
    text-shadow: 0 0 80px {theme["glow"]};
  }}

  .seg-num {{
    position: absolute; top: 20px; right: 40px;
    font-size: 18px; color: rgba(255,255,255,0.12); font-weight: 500;
  }}

  .accent-dot {{
    position: absolute; bottom: 60px; left: 50%;
    transform: translateX(-50%);
    width: 6px; height: 6px; border-radius: 50%;
    background: {theme["accent"]};
    opacity: 0.5;
    animation: pulse 1.5s ease infinite;
  }}

  @keyframes scaleIn {{ from {{ opacity: 0; transform: scale(0.85); }} to {{ opacity: 1; transform: scale(1); }} }}
  @keyframes fadeInUp {{ from {{ opacity: 0; transform: translateY(20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
  @keyframes pulse {{ 0%,100% {{ opacity: 0.3; }} 50% {{ opacity: 0.8; }} }}
</style>
</head>
<body>
  <div class="bg-orb" style="width:900px;height:900px;background:{theme["glow"]};top:-300px;left:-200px;opacity:0.4"></div>
  <div class="bg-orb" style="width:600px;height:600px;background:{theme["glow"]};bottom:50px;right:-150px;opacity:0.25"></div>

  <div class="lottie-stage">
    <dotlottie-player
      src="{src_url}"
      autoplay loop mode="normal">
    </dotlottie-player>
  </div>

  <div class="text-bar">
    <div class="text-content">{narration}</div>
  </div>

  <div class="accent-dot"></div>
  <div class="seg-num">{num_str}</div>
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python lottie_html_gen.py <segments.json> [output_dir]")
        sys.exit(1)

    seg_path = Path(sys.argv[1])
    data = json.loads(seg_path.read_text("utf-8"))
    segments = data.get("segments", [])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else seg_path.parent / "html"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(segments)
    results_log = []

    for idx, seg in enumerate(segments):
        keywords_en = seg.get("lottie_keywords_en", "")
        keywords_list = seg.get("lottie_keywords", [])

        print(f"\n[{idx+1}/{total}] {seg['title']}")
        print(f"  keywords: {keywords_en} | {keywords_list}")

        best = None
        # try the combined english keywords first
        if keywords_en:
            results = search_lottie(keywords_en, limit=8)
            best = pick_best(results)
            if best:
                print(f"  found (en): {best['name']} (downloads={best.get('downloads',0)})")

        # fallback: try individual keywords
        if not best:
            for kw in keywords_list:
                results = search_lottie(kw, limit=8)
                best = pick_best(results)
                if best:
                    print(f"  found (kw={kw}): {best['name']} (downloads={best.get('downloads',0)})")
                    break
                time.sleep(0.3)

        if not best:
            print(f"  [warn] no animation found, using fallback")
            best = {"name": "fallback", "lottieUrl": "https://assets-v2.lottiefiles.com/a/0e5f9e62-1153-11ee-8c46-4f56030c6b3d/QUKZrZTXlp.lottie", "jsonUrl": ""}

        lottie_url = best.get("lottieUrl") or best.get("jsonUrl") or ""
        html = generate_html(seg, idx, total, lottie_url, best.get("name", ""))

        html_path = out_dir / f"segment-{idx+1:02d}.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"  → {html_path.name}")

        results_log.append({
            "segment": idx + 1,
            "title": seg["title"],
            "keyword_used": keywords_en or (keywords_list[0] if keywords_list else ""),
            "lottie_name": best.get("name", ""),
            "lottie_url": lottie_url,
        })

        time.sleep(0.5)

    log_path = out_dir.parent / "lottie_search_log.json"
    log_path.write_text(json.dumps(results_log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  {total} 个 HTML 已生成 → {out_dir}")
    print(f"  搜索日志 → {log_path}")


if __name__ == "__main__":
    main()
