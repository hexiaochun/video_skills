---
name: svg-video
description: 生成 Lottie 动画讲解短视频：输入主题 → 调研 → 短句文案+关键词 → 自动搜索 LottieFiles 动画 → 生成 HTML → TTS 配音 → Playwright 录屏 → FFmpeg 合成 1080p 视频。当用户想要制作讲解视频、科普动画、Lottie 动画视频、animated explainer video 时使用。
---

# Lottie 动画讲解短视频生成器

输入主题，生成 1920×1080 的 **Lottie 动画 + 口播配音** 快节奏讲解短视频。

每段只写一句话（10-20 字），配一个从 LottieFiles 自动搜索的动画，节奏紧凑，适合短视频平台。

你（Agent）是导演兼编剧，负责调研、撰稿、提供动画关键词；Python 脚本负责搜索动画、生成 HTML、配音、录屏、剪辑。

---

## 触发条件

用户要求生成：讲解视频、动画科普视频、Lottie 动画视频、animated explainer、SVG 动画视频，或提到 svg-video。

## 前置依赖（首次使用前确认）

```bash
pip install -r skills/svg-video/requirements.txt
playwright install chromium
```

还需要 `ffmpeg`（`brew install ffmpeg`）。

---

## 流程：7 个步骤，逐步执行

### Step 1 — 明确需求

从用户消息中提取以下信息。缺失的主动询问：

| 信息 | 默认值 |
|------|--------|
| 主题 | （必须有） |
| 受众 | 普通人 / 小白 |
| 时长 | 30s-1 分钟 |
| 风格 | 快节奏短视频 |
| 语言 | zh（中文） |
| 语音偏好 | 男声 / 女声（默认使用 xskill 海螺语音，效果更自然） |

确定工作目录名：`out/<主题简称>-lottie-video/`

### Step 2 — 调研素材

使用 **WebSearch** 搜索主题，收集 3-5 条有实质内容的资料。

搜索策略：
- 第一轮：`<主题> 是什么 最新进展`
- 第二轮：`<主题> 普通人 影响`（或针对受众的角度）
- 如果是英文主题，加一轮英文搜索

提取并整理：核心定义 / 关键数据 / 时间节点 / 最新进展 / 与受众的关系。

> 如果用户已提供完整文案或详细素材，可跳过此步。

### Step 3 — 撰写结构化脚本

根据调研结果，撰写视频脚本。**创建工作目录并写入 segments.json：**

```python
import json
from pathlib import Path

work_dir = Path("out/<项目名>-lottie-video")
work_dir.mkdir(parents=True, exist_ok=True)

segments_data = {
    "title": "视频总标题",
    "lang": "zh",
    "segments": [
        # ... 见下方格式 ...
    ]
}

(work_dir / "segments.json").write_text(
    json.dumps(segments_data, ensure_ascii=False, indent=2), encoding="utf-8"
)
```

#### JSON 格式

```json
{
  "title": "视频总标题",
  "lang": "zh",
  "segments": [
    {
      "type": "opening",
      "title": "",
      "narration": "你焦虑过吗？",
      "lottie_keywords": ["anxiety", "worried person"],
      "lottie_keywords_en": "anxiety worried"
    },
    {
      "type": "content",
      "title": "",
      "narration": "全球三亿人正在焦虑",
      "lottie_keywords": ["world", "global people"],
      "lottie_keywords_en": "world globe people"
    },
    {
      "type": "closing",
      "title": "",
      "narration": "两分钟，就是改变的开始",
      "lottie_keywords": ["success", "rocket launch star"],
      "lottie_keywords_en": "rocket launch success star"
    }
  ]
}
```

**字段说明：**

| 字段 | 用途 |
|------|------|
| `type` | `opening` 开场 / `content` 主体 / `closing` 总结 |
| `title` | 留空即可（短句模式下不需要单独标题） |
| `narration` | TTS 朗读文案，同时以大字居中显示在画面底部（**10-20 字**） |
| `lottie_keywords` | 英文关键词数组，用于逐个搜索 LottieFiles 动画（回退用） |
| `lottie_keywords_en` | 空格分隔的英文关键词字符串，优先用于组合搜索 |

**段数建议：** 30s → 10-12 段 ｜ 1 分钟 → 15-20 段 ｜ 2 分钟 → 30-40 段

#### 文案写作规范（严格遵守）

**核心原则：一段一句话，10-20 个字。**

**风格：**
- 极简短句，像弹幕一样一句一句蹦出来
- 口语化，有节奏感
- 用"你"称呼观众

**开场（opening）：**
- 用一个问句或惊人数据直接抓住注意力
- ✅ "你焦虑过吗？"
- ✅ "全球三亿人正在焦虑"
- ❌ "大家好，今天我们来聊聊焦虑这个话题"

**主体（content）：**
- 每段只讲一个点，一句话说完
- 数据、方法、结论拆成独立的句子
- ✅ "每周三次，每次三十分钟"
- ✅ "效果不输药物"
- ❌ "柳叶刀的一项大规模研究发现，每周三次每次三十分钟的有氧运动降低焦虑的效果不输药物"（太长，应拆成多段）

**总结（closing）：**
- 给一个今天就能做的具体行动
- ✅ "今晚，试一次呼吸法"
- ❌ "以上就是今天的五个方法"

**关键词写作规范：**
- `lottie_keywords_en`：2-3 个英文单词，空格分隔，描述该句话的视觉主题
- `lottie_keywords`：2-3 个备选英文关键词数组，从具体到抽象排列
- 关键词应偏向可视化的名词（如 breathing、running、moon），避免抽象形容词

**禁止清单：**
- ❌ 单段超过 20 字
- ❌ "让我们来看看..." / "关于 XXX..."
- ❌ "首先...其次...最后..."
- ❌ 一段里塞两个以上信息点

#### 检查点

将脚本展示给用户，简要说明结构。用户确认后继续。

### Step 4 — 搜索 Lottie 动画 & 生成 HTML

运行自动化脚本，根据关键词从 LottieFiles 搜索动画并生成 HTML 页面：

```bash
python3 skills/svg-video/scripts/lottie_html_gen.py \
  <work-dir>/segments.json \
  <work-dir>/html
```

脚本工作原理：
1. 读取 segments.json 中每个段落的关键词
2. 通过 LottieFiles GraphQL API（`https://graphql.lottiefiles.com/2022-08`）搜索动画
3. 优先使用 `lottie_keywords_en` 组合搜索，未命中则逐个尝试 `lottie_keywords`
4. 按下载量 + 点赞数排序，选择最佳匹配
5. 生成 1920×1080 的 HTML 页面（Lottie 动画居中 + 底部大字文案），自动轮换 6 种配色主题

**输出：**
- `<work-dir>/html/segment-01.html`、`segment-02.html` ...
- `<work-dir>/lottie_search_log.json`（搜索匹配日志）

> 如果某段动画不满意，可手动修改对应 HTML 中的 `<dotlottie-player src="...">` URL。

### Step 5 — TTS 配音

**重要：** 优先使用 xskill 海螺语音（Minimax TTS），效果更自然真实。

#### 5a — 选择配音角色

先查看可用音色：

```bash
python3 skills/svg-video/scripts/svg_video.py xskill-voices --tag 男
python3 skills/svg-video/scripts/svg_video.py xskill-voices --tag 女
```

根据视频风格选择音色：

| 场景 | 推荐音色 ID | 名称 |
|------|------------|------|
| 科普解说（男声） | `male-qn-qingse` | 青涩青年 |
| 专业权威（男声） | `male-qn-jingying` | 精英青年 |
| 知性讲解（女声） | `female-chengshu` | 成熟女性 |
| 活泼风格（女声） | `female-shaonv` | 少女 |
| 甜美旁白（女声） | `female-tianmei` | 甜美女性 |
| 御姐解说（女声） | `female-yujie` | 御姐 |

#### 5b — 执行语音合成

**方式一：xskill 海螺语音（推荐，效果更好）**

需要 `XSKILL_API_KEY` 环境变量（获取方式见 xskill-api skill）。

```bash
python3 skills/svg-video/scripts/svg_video.py tts \
  --json <work-dir>/segments.json \
  --work-dir <work-dir> \
  --engine xskill \
  --voice-id male-qn-qingse
```

可选参数：
- `--tts-model speech-2.8-hd` — 模型版本（默认，效果最好）
- `--tts-model speech-2.8-turbo` — 速度更快，略降质量

脚本会批量提交所有语音任务并行合成，自动轮询下载。

**方式二：Edge TTS（免费备选，无需 API Key）**

```bash
python3 skills/svg-video/scripts/svg_video.py tts \
  --json <work-dir>/segments.json \
  --work-dir <work-dir> \
  --engine edge \
  --voice zh-CN-YunxiNeural
```

Edge TTS 可用中文语音：`zh-CN-YunxiNeural`（男）、`zh-CN-XiaoxiaoNeural`（女）、`zh-CN-YunjianNeural`（沉稳男）、`zh-CN-XiaoyiNeural`（活泼女）。

Edge TTS 可用英文语音：`en-US-AndrewNeural`（男）、`en-US-AriaNeural`（女）、`en-GB-SoniaNeural`（英式女）。

完整列表：`python3 skills/svg-video/scripts/svg_video.py list-voices`

**输出：** `<work-dir>/audio/segment-01.mp3`、`segment-02.mp3` ...

### Step 6 — Playwright 录屏

```bash
python3 skills/svg-video/scripts/svg_video.py render \
  --work-dir <work-dir> \
  --min-hold-ms 4000
```

`--min-hold-ms 4000` 确保每段至少录制 4 秒，给 Lottie 动画从 CDN 加载留出足够时间（短句模式下音频可能只有 2-3 秒）。

脚本自动扫描 `html/segment-*.html`，查找对应音频获取时长，用 Playwright 录屏。

**输出：** `<work-dir>/video/segment-01.webm`、`segment-02.webm` ...

### Step 7 — FFmpeg 合成

```bash
python3 skills/svg-video/scripts/svg_video.py assemble \
  --work-dir <work-dir> \
  --output <work-dir>/output.mp4
```

可选参数：
- `--bg-music <path>` — 添加背景音乐（15% 音量混入）

**输出：** `<work-dir>/output.mp4`

### 交付

告知用户：
1. 最终视频路径
2. 工作目录位置
3. 如需调整某段，可修改 segments.json 关键词后从 Step 4 重新执行

---

## 产物目录结构

```
<work-dir>/
├── segments.json               # 结构化脚本（含关键词）
├── lottie_search_log.json      # Lottie 搜索匹配日志
├── html/segment-*.html         # Lottie 动画 HTML 页面
├── audio/segment-*.mp3         # 分段配音
├── video/segment-*.webm        # Playwright 录屏
├── clips/clip-*.mp4            # 单段合成片段
├── concat.txt                  # FFmpeg 拼接清单
└── output.mp4                  # 最终视频
```
