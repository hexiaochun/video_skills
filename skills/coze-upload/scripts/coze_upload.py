#!/usr/bin/env python3
"""本地文件上传到 Coze，获取可访问的临时媒体链接（图片/视频）。"""

import json
import mimetypes
import os
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request

XSKILL_BASE = "https://api.xskill.ai"
COZE_BASE = "https://api.coze.cn"
WORKFLOW_ID = "7527555709244801087"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"


def _get(url: str, headers: dict | None = None) -> dict:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _post_json(url: str, body: dict, token: str) -> dict:
    data = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _post_multipart(url: str, filepath: str, token: str) -> dict:
    boundary = uuid.uuid4().hex
    filename = os.path.basename(filepath)
    content_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"

    with open(filepath, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def get_tokens() -> tuple[str, str]:
    """Step 1: 从 xskill 获取 upload_key 和 workflow access token。"""
    resp = _get(f"{XSKILL_BASE}/api/fal/tasks/coze_token")
    upload_key = resp.get("upload_key")
    access_token = resp.get("data")
    if not upload_key or not access_token:
        print(f"获取 token 失败: {json.dumps(resp, ensure_ascii=False)}", file=sys.stderr)
        sys.exit(1)
    return upload_key, access_token


def upload_file(filepath: str, upload_key: str) -> str:
    """Step 2: 上传文件到 Coze，返回 file_id。"""
    resp = _post_multipart(f"{COZE_BASE}/v1/files/upload", filepath, upload_key)
    file_id = (resp.get("data") or {}).get("id")
    if not file_id:
        print(f"上传失败: {json.dumps(resp, ensure_ascii=False)}", file=sys.stderr)
        sys.exit(1)
    return file_id


def get_media_url(file_id: str, access_token: str) -> str:
    """Step 3: 通过 Coze Workflow 将 file_id 转为可访问的媒体链接。"""
    body = {
        "parameters": {"input": json.dumps({"file_id": file_id})},
        "workflow_id": WORKFLOW_ID,
    }
    resp = _post_json(f"{COZE_BASE}/v1/workflow/run", body, access_token)

    raw_data = resp.get("data")
    if not raw_data:
        print(f"Workflow 调用失败: {json.dumps(resp, ensure_ascii=False)}", file=sys.stderr)
        sys.exit(1)

    if isinstance(raw_data, str):
        try:
            parsed = json.loads(raw_data)
            return parsed.get("output", raw_data)
        except json.JSONDecodeError:
            return raw_data

    return raw_data.get("output", json.dumps(raw_data))


def upload(filepath: str) -> str:
    """完整流程：本地文件 → 临时媒体链接。"""
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        print(f"文件不存在: {filepath}", file=sys.stderr)
        sys.exit(1)

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"[1/3] 获取 Token ...", file=sys.stderr)
    upload_key, access_token = get_tokens()

    print(f"[2/3] 上传文件 ({size_mb:.1f} MB) ...", file=sys.stderr)
    file_id = upload_file(filepath, upload_key)
    print(f"      file_id: {file_id}", file=sys.stderr)

    print(f"[3/3] 获取媒体链接 ...", file=sys.stderr)
    url = get_media_url(file_id, access_token)
    print(f"      完成!", file=sys.stderr)

    return url


def main():
    if len(sys.argv) < 2:
        print("用法: python coze_upload.py <文件路径> [文件路径2 ...]", file=sys.stderr)
        print("示例: python coze_upload.py /tmp/image.png", file=sys.stderr)
        print("      python coze_upload.py a.png b.mp4  # 批量上传", file=sys.stderr)
        sys.exit(1)

    for filepath in sys.argv[1:]:
        try:
            url = upload(filepath)
            print(url)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            print(f"HTTP {e.code} - {filepath}: {err_body}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
