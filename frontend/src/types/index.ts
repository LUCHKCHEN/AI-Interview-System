export type InterviewMode = 'precise' | 'broad'

export type SessionStatus =
  | 'ready'
  | 'interviewing'
  | 'scoring'
  | 'ready_report'
  | 'failed'

export type DimensionKey =
  | 'technical_accuracy'
  | 'logic_expression'
  | 'adaptability_learning'
  | 'job_match'

export interface InterviewQuestion {
  id: string
  number: number
  title: string
  intent: string
  hint: string
  dimension: string
}

export interface InterviewTurn {
  turn_no: number
  question: string
  transcript: string
  char_count: number
  duration_ms: number
  matched_keyword: string
}

export interface ResumeSummary {
  skills: string[]
  projects: string[]
  education: string
}

export interface InterviewSessionDetail {
  session_id: string
  created_at: string
  status: SessionStatus
  mode: InterviewMode
  company: string
  role: string
  company_style: string
  resume_name: string
  resume_summary: ResumeSummary
  jd_keywords: string[]
  weak_tags: string[]
  questions: InterviewQuestion[]
  turns: InterviewTurn[]
  current_turn_no: number
  error_code: string
  message: string
}

export interface DimensionScore {
  key: DimensionKey
  label: string
  score: number
  weight: number
  comment: string
}

export interface ReportQA {
  question: string
  transcript: string
  audio_url: string
  score: number
}

export interface InterviewReport {
  session_id: string
  created_at: string
  total_score: number
  level: string
  estimated: boolean
  dimensions: Record<DimensionKey, {
    score: number
    weight: number
    reason: string
  }>
  strengths: string[]
  weaknesses: string[]
  weak_tags: string[]
  suggestions: string[]
  short_answer_penalty: boolean
  qa: ReportQA[]
}

export interface ReportResponse {
  status: 'idle' | 'processing' | 'ready' | 'failed'
  report: InterviewReport | null
  error_code?: string
  message?: string
}

export interface HistoryEntry {
  session_id: string
  created_at: string
  company: string
  role: string
  mode: InterviewMode
  status: SessionStatus
  score: number | null
  level: string
  weak_tags: string[]
  questions: number
}

export interface WeakTag {
  tag: string
  count: number
  last_seen_at?: string
}

export interface HistoryResponse {
  items: HistoryEntry[]
  weak_tags: WeakTag[]
}

export interface KnowledgeStatus {
  status: 'idle' | 'rebuilding' | 'ready'
  message: string
  updated_at: string
}

export interface KnowledgeCatalogItem {
  name: string
  files: number
  size: number
}
