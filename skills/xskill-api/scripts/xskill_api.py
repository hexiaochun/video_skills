#!/usr/bin/env python3
"""xskill.ai API 命令行工具 — 模型浏览、任务提交与查询"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.xskill.ai"
ENV_KEY = "XSKILL_API_KEY"
SHELL_RC = os.path.expanduser("~/.zshrc")


# ── helpers ──────────────────────────────────────────────────────────


def _request(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.xskill.ai",
        "Referer": "https://www.xskill.ai/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        sys.exit(1)


def _ensure_api_key(args) -> str:
    key = getattr(args, "api_key", None) or os.environ.get(ENV_KEY)
    if key:
        return key

    print("=" * 60)
    print("未检测到 API Key。")
    print(f"请前往 https://www.xskill.ai/#/v2/api-keys 获取。")
    print("=" * 60)
    key = input("请输入 API Key (sk-xxx): ").strip()
    if not key:
        print("未输入 API Key，退出。", file=sys.stderr)
        sys.exit(1)

    _save_api_key(key)
    return key


def _save_api_key(key: str):
    """将 API Key 写入 ~/.zshrc 并设置当前进程环境变量。"""
    os.environ[ENV_KEY] = key
    export_line = f'export {ENV_KEY}="{key}"'

    existing = ""
    if os.path.exists(SHELL_RC):
        with open(SHELL_RC) as f:
            existing = f.read()

    if ENV_KEY in existing:
        lines = existing.splitlines()
        with open(SHELL_RC, "w") as f:
            for line in lines:
                if line.strip().startswith(f"export {ENV_KEY}="):
                    f.write(export_line + "\n")
                else:
                    f.write(line + "\n")
        print(f"已更新 {SHELL_RC} 中的 {ENV_KEY}")
    else:
        with open(SHELL_RC, "a") as f:
            f.write(f"\n{export_line}\n")
        print(f"已写入 {SHELL_RC}，重开终端或执行 source ~/.zshrc 生效")


def _print_json(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ── API functions ────────────────────────────────────────────────────


def list_models(category: str = "all") -> dict:
    resp = _request("GET", "/api/v3/mcp/models")
    models = resp.get("data", {}).get("models", [])
    if category and category != "all":
        models = [m for m in models if m.get("category") == category]
    return models


def get_model_info(model_id: str, lang: str = "en") -> dict:
    encoded = urllib.parse.quote(model_id, safe="")
    resp = _request("GET", f"/api/v3/models/{encoded}/docs?lang={lang}")
    return resp.get("data", {})


def submit_task(model_id: str, params: dict, token: str) -> dict:
    body = {"model": model_id, "params": params, "channel": None}
    resp = _request("POST", "/api/v3/tasks/create", body=body, token=token)
    return resp.get("data", resp)


def get_task(task_id: str, token: str) -> dict:
    resp = _request("POST", "/api/v3/tasks/query", body={"task_id": task_id}, token=token)
    return resp.get("data", resp)


def list_voices(tag: str | None = None) -> list:
    """获取 Minimax 公共音色列表。"""
    resp = _request("POST", "/api/v2/minimax/voices?status=active", body={})
    voices = resp.get("data", {}).get("public_voices", [])
    if tag:
        voices = [v for v in voices if tag in (v.get("tags") or [])]
    return voices


def run_task(model_id: str, params: dict, token: str, poll_interval: int = 5, timeout: int = 600) -> dict:
    """提交任务并轮询至完成。"""
    result = submit_task(model_id, params, token)
    task_id = result.get("task_id")
    if not task_id:
        print("提交失败，未返回 task_id", file=sys.stderr)
        _print_json(result)
        sys.exit(1)

    print(f"任务已提交: {task_id}")
    if "price" in result:
        print(f"扣费: {result['price']} 积分")

    elapsed = 0
    while elapsed < timeout:
        time.sleep(poll_interval)
        elapsed += poll_interval
        status_data = get_task(task_id, token)
        status = status_data.get("status", "unknown")
        print(f"  [{elapsed}s] 状态: {status}")

        if status == "completed":
            print("任务完成!")
            return status_data
        elif status == "failed":
            print("任务失败!", file=sys.stderr)
            _print_json(status_data)
            sys.exit(1)

    print(f"超时 ({timeout}s)，任务仍在进行中", file=sys.stderr)
    sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="xskill.ai API CLI")
    parser.add_argument("--api-key", help="API Key (或设置 XSKILL_API_KEY 环境变量)")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="查看模型列表")
    p_list.add_argument("--category", default="all", choices=["image", "video", "audio", "all"])

    p_info = sub.add_parser("info", help="查看模型详情")
    p_info.add_argument("model_id", help="模型 ID，如 st-ai/super-seed2")
    p_info.add_argument("--lang", default="en", choices=["en", "zh"])

    p_submit = sub.add_parser("submit", help="提交任务")
    p_submit.add_argument("model_id", help="模型 ID")
    p_submit.add_argument("--params", required=True, help="JSON 格式参数")

    p_query = sub.add_parser("query", help="查询任务")
    p_query.add_argument("task_id", help="任务 ID")

    p_run = sub.add_parser("run", help="提交并等待完成")
    p_run.add_argument("model_id", help="模型 ID")
    p_run.add_argument("--params", required=True, help="JSON 格式参数")
    p_run.add_argument("--interval", type=int, default=5, help="轮询间隔（秒）")
    p_run.add_argument("--timeout", type=int, default=600, help="超时时间（秒）")

    p_voices = sub.add_parser("voices", help="查看 Minimax 公共音色列表")
    p_voices.add_argument("--tag", help="按标签筛选，如 男/女/中文/英文/儿童")
    p_voices.add_argument("--json", action="store_true", dest="as_json", help="输出完整 JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "list":
        models = list_models(args.category)
        for m in models:
            hot = " [HOT]" if m.get("isHot") else ""
            rate = (m.get("stats") or {}).get("success_rate", 0)
            print(f"  {m['id']:<55} {m['name']:<30} {m['category']:<8} 成功率:{rate:.0%}{hot}")
        print(f"\n共 {len(models)} 个模型")

    elif args.command == "info":
        info = get_model_info(args.model_id, args.lang)
        _print_json(info)

    elif args.command == "submit":
        token = _ensure_api_key(args)
        params = json.loads(args.params)
        result = submit_task(args.model_id, params, token)
        _print_json(result)

    elif args.command == "query":
        token = _ensure_api_key(args)
        result = get_task(args.task_id, token)
        _print_json(result)

    elif args.command == "run":
        token = _ensure_api_key(args)
        params = json.loads(args.params)
        result = run_task(args.model_id, params, token, args.interval, args.timeout)
        _print_json(result)

    elif args.command == "voices":
        voices = list_voices(tag=args.tag)
        if args.as_json:
            _print_json(voices)
        else:
            for v in voices:
                tags = ",".join(v.get("tags") or [])
                print(f"  {v['voice_id']:<45} {v['voice_name']:<20} [{tags}]")
            print(f"\n共 {len(voices)} 个公共音色")


if __name__ == "__main__":
    main()
