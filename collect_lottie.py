import json
import re
import sys
import urllib.request
import urllib.error
import ssl
import time

ssl._create_default_https_context = ssl._create_unverified_context

CATEGORIES = {
    "medical": [
        "medical", "healthcare", "doctor", "hospital", "health"
    ],
    "people": [
        "teamwork", "collaboration", "communication", "social-media", "people-working"
    ],
    "success": [
        "rocket-launch", "success", "trophy", "celebration", "achievement", "target"
    ],
    "general": [
        "loading", "transition", "intro", "abstract-animation", "geometric"
    ],
}

def fetch_url(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "text/html,application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None

def get_animation_slugs(search_term):
    url = f"https://lottiefiles.com/free-animations/{search_term}"
    html = fetch_url(url)
    if not html:
        return []
    pattern = r'href="[^"]*?/free-animation/([^"]+)"'
    slugs = re.findall(pattern, html)
    return list(dict.fromkeys(slugs))[:8]

def get_animation_data(slug):
    url = f"https://lottiefiles.com/api/v1/animation/{slug}"
    raw = fetch_url(url)
    if not raw:
        return None
    try:
        resp = json.loads(raw)
        data = resp.get("data", {})
        if not data:
            return None
        
        lottie_path = data.get("lottiePath", "")
        json_path = ""
        for v in data.get("variants", []):
            if v.get("type") == "json" and not v.get("isOptimized"):
                json_path = f"https://assets-v2.lottiefiles.com/{v['path']}"
                break
        
        if not json_path:
            for v in data.get("variants", []):
                if v.get("type") == "json":
                    json_path = f"https://assets-v2.lottiefiles.com/{v['path']}"
                    break
        
        return {
            "name": data.get("name", ""),
            "description": data.get("description", "")[:200],
            "lottie_url": lottie_path,
            "json_url": json_path,
            "slug": slug,
            "downloads": data.get("downloadCount", "0"),
        }
    except Exception as e:
        print(f"  Error parsing {slug}: {e}", file=sys.stderr)
        return None

def main():
    all_results = {}
    
    for category, terms in CATEGORIES.items():
        print(f"\n=== Category: {category} ===", file=sys.stderr)
        seen_slugs = set()
        category_anims = []
        
        for term in terms:
            if len(category_anims) >= 5:
                break
            print(f"  Searching: {term}...", file=sys.stderr)
            slugs = get_animation_slugs(term)
            print(f"    Found {len(slugs)} slugs", file=sys.stderr)
            
            for slug in slugs:
                if len(category_anims) >= 5:
                    break
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                
                data = get_animation_data(slug)
                if data and (data["lottie_url"] or data["json_url"]):
                    category_anims.append(data)
                    print(f"    + {data['name']}", file=sys.stderr)
                    print(f"      URL: {data['lottie_url'] or data['json_url']}", file=sys.stderr)
                time.sleep(0.3)
        
        all_results[category] = category_anims
    
    json.dump(all_results, sys.stdout, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
