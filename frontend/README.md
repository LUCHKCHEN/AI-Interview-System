# NEWRAG 前端

React + TypeScript + Vite 单页应用，已接入 `NEWRAG/interview_api.py` 的真实 HTTP 和 WebSocket 接口。

## 开发启动

先启动后端：

```powershell
cd NEWRAG
python interview_api.py
```

再启动前端：

```powershell
cd frontend
npm install
npm run dev
```

访问 [http://127.0.0.1:5173/setup](http://127.0.0.1:5173/setup)。

默认情况下，[vite.config.ts](vite.config.ts) 会把 `/api` 的 HTTP 和 WebSocket 请求代理到 `http://127.0.0.1:8002`，因此本地开发不需要额外环境变量。

## 环境变量

需要前后端分离部署时，可在构建前设置：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8002
VITE_WS_BASE_URL=ws://127.0.0.1:8002
```

- `VITE_API_BASE_URL`：HTTP API 根地址。
- `VITE_WS_BASE_URL`：WebSocket 根地址；不设置时使用当前页面的 host。

使用 Vite 代理时保留两者为空即可。

## 路由

| 路由 | 页面 |
| --- | --- |
| `/` | 首页与流程入口 |
| `/setup` | 简历、JD、公司和岗位表单 |
| `/interview/:sessionId` | 三题面试驾驶舱 |
| `/report/:sessionId` | 四维评分报告 |
| `/history` | 历史记录、分数趋势和弱项标签 |

## 接口接入

`src/api/client.ts` 封装了会话创建、会话详情、报告轮询、历史查询、删除、导出和音频 URL。

录音流程：

- `src/hooks/usePcmRecorder.ts` 使用 `getUserMedia` 和 Web Audio API。
- 浏览器音频转为 16kHz、16-bit、单声道 PCM。
- PCM 帧通过 `/api/interview/sessions/{id}/turns/{turn}/answers` 的 WebSocket 发送。
- 语音不可用时，页面提供文本回答通道，仍走同一套会话状态。

## 构建与检查

```powershell
npm run build
npm run lint
```

生产构建输出到 `dist/`。当前构建仅有 Vite 的单包体积提示，不影响运行。
