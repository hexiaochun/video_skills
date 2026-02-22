---
name: xskill-api
description: 通过 xskill.ai API 查看可用 AI 模型列表、获取模型参数详情、提交生成任务、查询任务结果。支持图片生成、视频生成、语音合成、视频/图片理解、视频平台无水印视频下载等能力。当用户需要调用大模型 API、提交 AI 生成任务、画图、生成视频、语音合成、下载视频、查看模型列表、查询任务状态，或提到 xskill、NEX AI 时使用此 skill。
---

# xskill API 调用指南

通过 4 个核心接口完成：浏览模型 → 了解参数 → 提交任务 → 获取结果。

## 前置：API Key

提交任务和查询任务需要 API Key（`sk-` 开头）。

**获取方式**：若用户未提供 API Key，引导用户前往 https://www.xskill.ai/#/v2/api-keys 获取。

**持久化**：用户提供 API Key 后，执行以下命令写入环境变量，后续自动读取：

```bash
echo 'export XSKILL_API_KEY="sk-xxx"' >> ~/.zshrc && source ~/.zshrc
```

**检测优先级**：环境变量 `XSKILL_API_KEY` > 命令行参数 `--api-key`

## API 概览

Base URL: `https://api.xskill.ai`

| 接口 | 方法 | 路径 | 认证 |
|------|------|------|------|
| 模型列表 | GET | `/api/v3/mcp/models` | 无 |
| 模型详情 | GET | `/api/v3/models/{model_id}/docs` | 无 |
| 提交任务 | POST | `/api/v3/tasks/create` | Bearer Token |
| 查询任务 | POST | `/api/v3/tasks/query` | Bearer Token |
| 公共音色列表 | POST | `/api/v2/minimax/voices?status=active` | 无 |

## 接口 1：模型列表

```bash
curl -s 'https://api.xskill.ai/api/v3/mcp/models' \
  -H 'content-type: application/json'
```

**响应结构**：

```json
{
  "code": 200,
  "data": {
    "models": [
      {
        "id": "st-ai/super-seed2",
        "name": "Seedance 2.0 全能模型",
        "category": "video",
        "task_type": "i2v",
        "description": "...",
        "isHot": true,
        "stats": {
          "success_rate": 0.49,
          "total_tasks": 17661
        }
      }
    ]
  }
}
```

**关键字段**：`id`（提交任务用）、`category`（image/video/audio）、`task_type`（t2i/i2v/t2v 等）

## 接口 2：模型详情

`model_id` 中的 `/` 需 URL 编码为 `%2F`。

```bash
curl -s 'https://api.xskill.ai/api/v3/models/st-ai%2Fsuper-seed2/docs' \
  -H 'content-type: application/json'
```

可加 `?lang=en` 获取英文文档。

**响应结构**：

```json
{
  "code": 200,
  "data": {
    "id": "st-ai/super-seed2",
    "name": "Seedance 2.0 All-in-One",
    "params_schema": {
      "type": "object",
      "properties": {
        "prompt": {"type": "string", "description": "提示词"},
        "duration": {"type": "integer", "minimum": 4, "maximum": 15}
      },
      "required": ["prompt"]
    },
    "pricing": {
      "base_price": 40,
      "price_type": "dynamic_per_second",
      "price_description": "按秒计费..."
    }
  }
}
```

**关键字段**：`params_schema`（提交任务的参数定义）、`pricing`（价格信息）

## 接口 3：提交任务

```bash
curl -X POST 'https://api.xskill.ai/api/v3/tasks/create' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer sk-YOUR_API_KEY' \
  -d '{
    "model": "st-ai/super-seed2",
    "params": {
      "prompt": "一位穿着红色裙子的女孩在花田中旋转跳舞",
      "duration": 5,
      "ratio": "16:9"
    }
  }'
```

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | string | 是 | 模型 ID（从模型列表获取） |
| params | object | 是 | 模型参数（从模型详情的 params_schema 获取） |
| channel | string | 否 | 渠道标识，一般传 null |

**响应**：返回 `task_id` 和扣费信息。

## 接口 4：查询任务

```bash
curl -X POST 'https://api.xskill.ai/api/v3/tasks/query' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer sk-YOUR_API_KEY' \
  -d '{"task_id": "your-task-id"}'
```

**任务状态**：

| 状态 | 说明 |
|------|------|
| pending | 排队中 |
| processing | 处理中 |
| completed | 完成，结果在 result 字段 |
| failed | 失败，原因在 error 字段 |

## 接口 5：公共音色列表

获取 Minimax TTS 公共音色，无需认证。

```bash
curl -X POST 'https://api.xskill.ai/api/v2/minimax/voices?status=active' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

**响应结构**：

```json
{
  "code": 200,
  "data": {
    "public_voices": [
      {
        "voice_id": "male-qn-qingse",
        "voice_name": "青涩青年音色",
        "voice_type": "system",
        "voice_type_display": "系统音色",
        "tags": ["青年", "中文", "男"],
        "audio_url": "https://st-video.cc/minimax_voices/..."
      }
    ]
  }
}
```

**关键字段**：`voice_id`（TTS 调用时传入）、`tags`（可按 男/女/中文/英文/儿童 等筛选）、`audio_url`（试听音频）

## 标准工作流

```
1. list_models     → 选择模型 ID
2. get_model_info  → 了解参数 schema 和价格
3. submit_task     → 提交任务，获取 task_id
4. get_task        → 轮询状态直到 completed/failed
```

## MCP 工具调用

在 Cursor 中可直接通过 MCP 服务 `user-xskill-ai` 调用，无需手动构造 HTTP 请求：

**list_models** -- 获取模型列表：

```json
{"category": "all"}
```

category 可选：`image` / `video` / `audio` / `all`

**get_model_info** -- 获取模型详情：

```json
{"model_id": "st-ai/super-seed2"}
```

**submit_task** -- 提交任务：

```json
{
  "model_id": "st-ai/super-seed2",
  "parameters": {
    "prompt": "一位穿着红色裙子的女孩在花田中旋转跳舞",
    "duration": 5,
    "ratio": "16:9"
  }
}
```

**get_task** -- 查询任务：

```json
{"task_id": "your-task-id"}
```

## 脚本工具

提供 `skills/xskill-api/scripts/xskill_api.py` 封装了全部 4 个接口，支持命令行直接调用：

```bash
python skills/xskill-api/scripts/xskill_api.py list                          # 查看所有模型
python skills/xskill-api/scripts/xskill_api.py list --category video         # 筛选视频模型
python skills/xskill-api/scripts/xskill_api.py info st-ai/super-seed2        # 查看模型详情
python skills/xskill-api/scripts/xskill_api.py submit st-ai/super-seed2 \    # 提交任务
  --params '{"prompt":"测试","duration":5}'
python skills/xskill-api/scripts/xskill_api.py query <task_id>               # 查询任务
python skills/xskill-api/scripts/xskill_api.py run st-ai/super-seed2 \       # 提交并轮询到完成
  --params '{"prompt":"测试","duration":5}'
python skills/xskill-api/scripts/xskill_api.py voices                       # 查看所有公共音色
python skills/xskill-api/scripts/xskill_api.py voices --tag 女              # 筛选女声音色
python skills/xskill-api/scripts/xskill_api.py voices --tag 英文            # 筛选英文音色
python skills/xskill-api/scripts/xskill_api.py voices --json                # 输出完整 JSON
```

首次使用时脚本会提示输入 API Key 并自动保存到 `~/.zshrc`。
