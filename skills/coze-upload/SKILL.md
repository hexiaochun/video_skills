---
name: coze-upload
description: 上传本地文件到云端并返回可访问 URL。支持图片（png/jpg/webp/gif）和视频（mp4/webm/mov）。当用户需要上传图片、上传视频、将本地文件转为 URL、获取图片链接、获取视频链接、图片转链接、本地图片转 URL、附带了本地图片/视频路径需要转成链接、或提到 coze upload 时使用此 skill。
---

# Coze Upload — 本地文件转临时媒体链接

将本地图片或视频上传到 Coze，返回可访问的临时 URL。

## 流程

```
本地文件 → ① 获取 Token → ② 上传到 Coze → ③ Workflow 转链接 → 媒体 URL
```

1. GET `https://api.xskill.ai/api/fal/tasks/coze_token`（无需认证）→ `upload_key` + `data`
2. POST `https://api.coze.cn/v1/files/upload`（Bearer = upload_key）→ `file_id`
3. POST `https://api.coze.cn/v1/workflow/run`（Bearer = data, workflow_id = `7527555709244801087`）→ 媒体 URL

## 脚本使用

脚本路径：`.cursor/skills/coze-upload/scripts/coze_upload.py`

无外部依赖，仅用 Python 标准库。

```bash
# 单个文件
python .cursor/skills/coze-upload/scripts/coze_upload.py /path/to/image.png

# 批量上传
python .cursor/skills/coze-upload/scripts/coze_upload.py a.png b.mp4 c.jpg
```

进度信息输出到 stderr，最终 URL 输出到 stdout，支持管道：

```bash
URL=$(python .cursor/skills/coze-upload/scripts/coze_upload.py /tmp/photo.jpg)
echo "媒体链接: $URL"
```

## Python 调用

```python
import subprocess, sys

def coze_upload(filepath: str) -> str:
    """上传本地文件，返回临时媒体链接。"""
    script = ".cursor/skills/coze-upload/scripts/coze_upload.py"
    result = subprocess.run([sys.executable, script, filepath], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"上传失败: {result.stderr}")
    return result.stdout.strip()
```

也可直接 import：

```python
from scripts.coze_upload import upload

url = upload("/tmp/photo.jpg")
```

## 自动触发条件

当以下情况发生时，应自动使用此 skill：

- AI 模型需要文件 URL，但用户提供了本地路径
- 用户要求上传文件获取链接
- 其他 skill 流程中需要将本地产物转为可访问 URL

## 注意事项

- 返回的是**临时链接**，有时效性
- 支持图片和视频文件
- 无需 API Key 或任何认证配置
