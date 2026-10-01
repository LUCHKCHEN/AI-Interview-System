import type {
  HistoryResponse,
  InterviewSessionDetail,
  KnowledgeCatalogItem,
  KnowledgeStatus,
  ReportResponse,
} from '../types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  code: string
  status: number

  constructor(message: string, code = 'REQUEST_FAILED', status = 0) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, options)
  } catch {
    throw new ApiError('无法连接本地面试服务，请确认 8002 端口已启动。', 'NETWORK_ERROR')
  }
  const contentType = response.headers.get('content-type') ?? ''
  const data = contentType.includes('application/json')
    ? await response.json() as Record<string, unknown>
    : null
  if (!response.ok) {
    throw new ApiError(
      String(data?.message ?? data?.detail ?? '请求没有完成，请稍后重试。'),
      String(data?.error_code ?? 'REQUEST_FAILED'),
      response.status,
    )
  }
  return data as T
}

export function getKnowledgeStatus() {
  return request<KnowledgeStatus>('/api/knowledge/status')
}

export function getKnowledgeCatalog() {
  return request<{ items: KnowledgeCatalogItem[] }>('/api/knowledge/catalog')
}

export function createInterviewSession(form: FormData) {
  return request<InterviewSessionDetail>('/api/interview/sessions', {
    method: 'POST',
    body: form,
  })
}

export function getInterviewSession(sessionId: string) {
  return request<InterviewSessionDetail>(`/api/interview/sessions/${sessionId}`)
}

export function getInterviewReport(sessionId: string) {
  return request<ReportResponse>(`/api/interview/sessions/${sessionId}/report`)
}

export function finishInterview(sessionId: string) {
  return request<{ session_id: string; status: string; message: string }>(
    `/api/interview/sessions/${sessionId}/finish`,
    { method: 'POST' },
  )
}

export function getHistory() {
  return request<HistoryResponse>('/api/history?limit=50&offset=0')
}

export function deleteHistory(sessionId: string) {
  return request<{ message: string }>(`/api/history/${sessionId}`, {
    method: 'DELETE',
  })
}

export function getQuestionAudioUrl(sessionId: string, turnNo: number) {
  return `${API_BASE}/api/interview/sessions/${sessionId}/turns/${turnNo}/question-audio`
}

export function getCompletionAudioUrl(sessionId: string) {
  return `${API_BASE}/api/interview/sessions/${sessionId}/completion-audio`
}

export function getAnswerAudioUrl(audioUrl: string) {
  return `${API_BASE}${audioUrl}`
}

export function getHistoryExportUrl(sessionId: string) {
  return `${API_BASE}/api/history/${sessionId}/export`
}

export function getAnswerWebSocketUrl(sessionId: string, turnNo: number) {
  const explicit = import.meta.env.VITE_WS_BASE_URL as string | undefined
  const base = explicit?.replace(/\/$/, '') ?? (
    `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  )
  return `${base}/api/interview/sessions/${sessionId}/turns/${turnNo}/answers`
}

export function formatDuration(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

export function formatDate(value: string) {
  if (!value) return '刚刚'
  return value.replace('T', ' ').slice(0, 16)
}
