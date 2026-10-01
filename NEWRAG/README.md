# NEWRAG 后端

NEWRAG 当前包含两套 FastAPI 服务：

- 动态模拟面试服务：`interview_api.py`，默认端口 `8002`。
- 原语音资料问答服务：`voice_api.py`，默认端口 `8001`。

面试服务读取上一级 `data/` 知识库，使用 DeepSeek 生成题目和评分，复用 FunASR 与 sherpa-onnx 完成语音转写和题目/结束语朗读。所有面试记录保存在上一级 `interview_records/`。

## 新增文件

```
interview_api.py       面试 HTTP/WebSocket 服务
interview_service.py   简历解析、出题、切题和评分逻辑
interview_store.py     会话、录音路径和弱项标签的本地持久化
speech_service.py      面试接口复用的 ASR/TTS 适配层
test_interview_service.py
test_interview_api.py
```

保留的原有模块：

```
rag_engine.py          LangChain + FAISS + DeepSeek 文本 RAG
voice_api.py           语音问答、音频上传下载与本地 TTS
test_newrag.py
test_voice_api.py
```

## 环境准备

推荐使用 Python 3.10+。

```powershell
pip install -r requirements.txt
```

在上一级 `.env` 中配置：

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_CHAT_MODEL=deepseek-v4-flash
```

DeepSeek 不可用时，题目生成和评分自动使用本地规则，评分报告会标记 `estimated: true`。

## 启动面试服务

```powershell
cd NEWRAG
python interview_api.py
```

默认监听 `http://127.0.0.1:8002`，健康检查为 `GET /health`。

可选环境变量：

```dotenv
INTERVIEW_API_HOST=127.0.0.1
INTERVIEW_API_PORT=8002
INTERVIEW_RECORDS_DIR=..\interview_records
INTERVIEW_AUTO_REBUILD=1
```

`INTERVIEW_AUTO_REBUILD=0` 可关闭评分后的 FAISS 索引自动重建。

## 面试流程

1. `POST /api/interview/sessions` 接收文字型 PDF 或粘贴简历、JD、公司和岗位。
2. 服务提取 JD 关键词并与简历技能比对，生成“精准模式”或“广度模式”下的三道递进题。
3. 前端通过 WebSocket 发送 16kHz、16-bit、单声道 PCM 音频。
4. 服务转写音频，检测“回答完毕”“以上就是我的回答”等切题关键词，并保存本题回答。
5. 第 3 题完成后调用评分接口；前端同时显示并播放“技术面试结束，接下来进入评分环节。”
6. 报告写入会话目录，弱项标签写入 `weak_tags.json`，并可在 `data/05_自动补强/` 生成复习文档。

扫描型 PDF 无法提取文字时返回 `SCANNED_PDF`，前端可切换到粘贴文本通道。

## HTTP 与 WebSocket 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/interview/sessions` | 创建面试 |
| `GET` | `/api/interview/sessions/{id}` | 获取会话 |
| `GET` | `/api/interview/sessions/{id}/turns/{turn}/question-audio` | 获取题目 WAV，首次访问时生成并缓存 |
| `GET` | `/api/interview/sessions/{id}/turns/{turn}/answer-audio` | 获取本题回答 WAV |
| `GET` | `/api/interview/sessions/{id}/completion-audio` | 获取结束语 WAV，首次访问时生成并缓存 |
| `POST` | `/api/interview/sessions/{id}/finish` | 开始后台评分 |
| `GET` | `/api/interview/sessions/{id}/report` | 查询评分状态和报告 |
| `GET` | `/api/history` | 分页获取历史记录和弱项标签 |
| `GET` | `/api/history/{id}` | 获取单条历史详情 |
| `DELETE` | `/api/history/{id}` | 删除单条历史 |
| `GET` | `/api/history/{id}/export` | 导出会话 JSON |
| `GET` | `/api/knowledge/status` | 查询知识库索引状态 |
| `GET` | `/api/knowledge/catalog` | 查询知识库目录统计 |
| `WS` | `/api/interview/sessions/{id}/turns/{turn}/answers` | 录音、实时转写、切题和文本降级提交 |

WebSocket 客户端事件：

- 二进制帧：PCM 音频。
- `{"type":"start"}`：开始本题。
- `{"type":"finish"}`：手动结束并提交。
- `{"type":"text_answer","transcript":"..."}`：文本降级提交。

服务端事件包含 `status`、`warning`、`transition`、`finalized`、`error`。

## 评分与数据

评分维度：

- 技术深度与准确性：40%
- 逻辑思维与表达条理：25%
- 应变与学习潜力：20%
- 岗位匹配度：15%

回答有效汉字少于 50 字会被提示并影响评分；单题少于 20 字时，总分上限为 60。

本地数据：

```text
interview_records/
  {session_id}/
    session.json
    turn-{n}.json
    turn-{n}.wav
    question-{n}.wav
    completion.wav
  weak_tags.json
```

题目、用户回答和报告默认保存在本机，不会上传到第三方，但使用 DeepSeek 评分时会将作答文本发送给所配置的模型接口。

## 设计边界与已知限制

- 面试录音、转写和会话记录默认只保存在本机；使用 DeepSeek 时，简历摘要、岗位信息和回答文本会发送到配置的模型接口。
- TTS 需要先把 `vits-melo-tts-zh_en` 放到 `models/`；向量模型和 FunASR 模型可能在首次运行时下载。
- FAISS 索引使用全量重建，资料较多时会增加等待时间；评分后默认异步重建，可通过 `INTERVIEW_AUTO_REBUILD=0` 关闭。
- 知识库目前只读取 Markdown 和 txt，不支持 Word、网页或扫描件 OCR。
- 检索数量固定，暂未加入相关性阈值和重排序，复杂语义查询可能召回一般相关片段。
- 面试题和评分依赖 DeepSeek 时存在网络、限流、成本和内容稳定性风险；不可用时自动降级为本地规则评分。
- 浏览器实时转写按已缓冲 PCM 分段调用 ASR，不是独立的逐词流式识别；麦克风仅能在 localhost 或 HTTPS 下使用。
- 自动化测试覆盖接口、会话状态和降级路径，不覆盖真实模型下载、真实 DeepSeek 调用和长时间录音。

前端不应直接依赖 `rag_engine.py` 内部结构，应通过 FastAPI 接口交互。面试记录目前使用本地 JSON/WAV 存储；引入数据库或云同步前，需要先明确隐私、迁移和删除策略。

## 启动原语音问答服务

```powershell
cd NEWRAG
python voice_api.py
```

默认监听 `http://127.0.0.1:8001`。接口说明见本文的 HTTP 与 WebSocket 接口章节，模型目录与运行限制见“设计边界与已知限制”。

## 测试

```powershell
cd NEWRAG
python -m unittest test_newrag.py test_voice_api.py test_interview_service.py test_interview_api.py -v
```

测试默认不调用真实 ASR、TTS 或 DeepSeek 网络接口。
