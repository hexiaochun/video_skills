# 从视频链接用语音识别提取文案

使用 **parse_video**（解析链接）+ **xskill-ai 的 Scribe V2**（语音转文字）从分享链接提取视频口播文案。

## 调用流程

### 1. 解析视频链接（parse_video）

通过 MCP 工具 `user-xskill-ai` → `parse_video`：

```json
{
  "url": "https://v.douyin.com/xxxxx/"
}
```

返回中取 **音频 URL**：
- `audio_url`：首选音频地址（部分平台为人声+BGM 混合，抖音可能仅为 BGM）
- `video_url` / `video_urls`：视频地址；若需**人声**而平台只给 BGM，需下载视频后用 ffmpeg 提取音轨再转写

### 2. 提交语音转写任务（submit_task）

通过 MCP 工具 `user-xskill-ai` → `submit_task`：

```json
{
  "model_id": "fal-ai/elevenlabs/speech-to-text/scribe-v2",
  "parameters": {
    "audio_url": "<上一步的 audio_url 或可公网访问的音频 URL>",
    "language_code": "cmn",
    "diarize": false,
    "tag_audio_events": false
  }
}
```

| 参数 | 必填 | 说明 |
|------|------|------|
| audio_url | 是 | 音频文件 URL，支持 mp3/ogg/wav/m4a/aac |
| language_code | 否 | 如 `cmn`（中文）、`eng`（英文），不填则自动检测 |
| diarize | 否 | 是否说话人分离，默认 true |
| tag_audio_events | 否 | 是否标笑声/掌声等，默认 true |
| keyterms | 否 | 关键词列表，提高专有词识别（会加价约 30%） |

返回示例：`task_id: "2ff1f1b4-ce23-4637-bb5c-5472cc502a4a"`

### 3. 轮询任务结果（get_task）

通过 MCP 工具 `user-xskill-ai` → `get_task`：

```json
{
  "task_id": "<上一步返回的 task_id>"
}
```

- `status === "success"`：`output` 内为转写结果（含分段、时间戳等）
- `status === "failed"`：转写失败，需检查 `audio_url` 是否可被 fal 服务访问、是否为有效人声音频

## 注意事项

1. **音频 URL 必须公网可访问**：fal 会拉取该 URL，抖音等 CDN 可能防盗链导致失败，此时需：
   - 先下载视频/音频到本地；
   - 用 ffmpeg 从视频提取人声轨：`ffmpeg -i video.mp4 -vn -acodec copy audio.m4a`；
   - 将 `audio.m4a` 上传到可公网访问的存储（如对象存储、图床等），得到 URL 再作为 `audio_url` 提交。
2. **抖音**：parse_video 返回的 `audio_url` 常为 BGM，人声在视频音轨中，若转写结果为空或不对，请用上面「下载视频 → 提取音轨 → 上传」再转写。
3. **费用**：Scribe V2 按输入音频时长计费（约 $0.008/分钟），使用 keyterms 会加价约 30%。

## 模型信息查询

提交前可查看模型参数要求：

- MCP 工具：`user-xskill-ai` → `get_model_info`
- 参数：`{ "model_id": "fal-ai/elevenlabs/speech-to-text/scribe-v2" }`
