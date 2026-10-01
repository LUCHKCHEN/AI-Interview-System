import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileText,
  LoaderCircle,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-react'
import { ApiError, formatDate, formatDuration, getInterviewReport, getInterviewSession } from '../api/client'
import RadarChart from '../components/RadarChart'
import Reveal from '../components/Reveal'
import type { DimensionKey, DimensionScore, InterviewReport, InterviewSessionDetail, ReportResponse } from '../types'
import './ReportPage.css'

const dimensionMeta: Record<DimensionKey, string> = {
  technical_accuracy: '技术深度与准确性',
  logic_expression: '逻辑思维与表达条理',
  adaptability_learning: '应变与学习潜力',
  job_match: '岗位匹配度',
}

function reportDimensions(report: InterviewReport): DimensionScore[] {
  return (Object.keys(dimensionMeta) as DimensionKey[]).map((key) => ({
    key,
    label: dimensionMeta[key],
    score: report.dimensions[key]?.score ?? 0,
    weight: report.dimensions[key]?.weight ?? 0,
    comment: report.dimensions[key]?.reason ?? '暂无评分说明。',
  }))
}

export default function ReportPage() {
  const { sessionId = '' } = useParams()
  const [session, setSession] = useState<InterviewSessionDetail | null>(null)
  const [response, setResponse] = useState<ReportResponse | null>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    getInterviewSession(sessionId)
      .then((data) => {
        if (active) setSession(data)
      })
      .catch((error: unknown) => {
        if (active) setMessage(error instanceof ApiError ? error.message : '面试信息加载失败。')
      })
    return () => {
      active = false
    }
  }, [sessionId])

  useEffect(() => {
    let active = true
    let timer = 0
    const load = () => {
      getInterviewReport(sessionId)
        .then((data) => {
          if (!active) return
          setResponse(data)
          if (data.status === 'processing' || data.status === 'idle') {
            timer = window.setTimeout(load, 1500)
          }
          if (data.status === 'failed') {
            setMessage(data.message ?? '评分暂时不可用。')
          }
        })
        .catch((error: unknown) => {
          if (!active) return
          setMessage(error instanceof ApiError ? error.message : '报告加载失败。')
        })
    }
    load()
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [sessionId])

  const report = response?.report ?? null
  const dimensions = useMemo(() => report ? reportDimensions(report) : [], [report])

  if (!report) {
    return (
      <section className="missing-report">
        {response?.status === 'processing' || response?.status === 'idle' ? <LoaderCircle className="report-spinner" size={26} /> : null}
        <h1>{message || (response?.status === 'failed' ? '评分没有完成' : '正在生成四维评分报告')}</h1>
        <p>
          {response?.status === 'processing' || response?.status === 'idle'
            ? '系统正在对照题目骨架、岗位关键词和回答完整度评分。'
            : '可以返回准备页重新创建一轮面试。'}
        </p>
        {response?.status !== 'processing' && response?.status !== 'idle' ? (
          <Link className="pill-button pill-button-blue" to="/setup">去创建面试</Link>
        ) : null}
      </section>
    )
  }

  const topDimension = [...dimensions].sort((a, b) => b.score - a.score)[0]
  const lowDimension = [...dimensions].sort((a, b) => a.score - b.score)[0]
  const duration = session?.turns.reduce((sum, turn) => sum + turn.duration_ms, 0) ?? 0

  return (
    <div className="report-page">
      <section className="report-hero">
        <div className="report-hero-inner">
          <Reveal>
            <Link className="back-link back-link-light" to={`/interview/${sessionId}`}>
              <ArrowLeft size={16} strokeWidth={1.9} />
              返回面试
            </Link>
            <p className="page-eyebrow">面试评分报告</p>
            <h1>{session?.company || '目标公司'} · {session?.role || '目标岗位'}</h1>
            <p className="page-lead">
              {report.level}。报告基于回答转写、题目骨架、岗位关键词与结构完整度生成
              {report.estimated ? '，当前为本地降级估算。' : '。'}
            </p>
          </Reveal>

          <Reveal delay={120} className="score-hero-card">
            <div className="score-number">
              <strong>{report.total_score}</strong>
              <span>分</span>
            </div>
            <div className="score-notes">
              <span><CheckCircle2 size={16} strokeWidth={1.8} /> {report.qa.length} 题已归档</span>
              <span><Clock3 size={16} strokeWidth={1.8} /> 回答 {formatDuration(duration)}</span>
              <span><Sparkles size={16} strokeWidth={1.8} /> {topDimension?.label}表现最强</span>
            </div>
            <Link className="report-back-to-interview" to={`/interview/${sessionId}`}>
              重看本轮面试
              <ChevronRight size={16} strokeWidth={2} />
            </Link>
          </Reveal>
        </div>
      </section>

      <section className="report-content">
        <div className="report-overline">能力画像</div>
        <Reveal className="radar-section">
          <div className="radar-copy">
            <h2>四维得分</h2>
            <p>权重固定为技术 40%、表达 25%、应变 20%、匹配 15%，每条理由都对应回答证据。</p>
            <div className="dimension-summary">
              <span>最高：{topDimension?.label} {topDimension?.score}</span>
              <span>建议优先：{lowDimension?.label} {lowDimension?.score}</span>
            </div>
          </div>
          <RadarChart dimensions={dimensions} />
        </Reveal>

        <div className="dimension-list" aria-label="四维评分详情">
          {dimensions.map((item, index) => (
            <Reveal className="dimension-row" delay={index * 60} key={item.key}>
              <div className="dimension-label">
                <strong>{item.label} · {Math.round(item.weight * 100)}%</strong>
                <span>{item.comment}</span>
              </div>
              <div className="dimension-score"><strong>{item.score}</strong><span>/ 100</span></div>
            </Reveal>
          ))}
        </div>

        <div className="insight-grid">
          <Reveal className="insight-panel">
            <div className="insight-heading">
              <span className="insight-icon insight-positive"><TrendingUp size={18} strokeWidth={1.8} /></span>
              <h2>值得保持</h2>
            </div>
            <ul className="insight-list">
              {report.strengths.map((item) => (
                <li key={item}><BadgeCheck size={16} strokeWidth={1.8} />{item}</li>
              ))}
            </ul>
          </Reveal>
          <Reveal className="insight-panel" delay={80}>
            <div className="insight-heading">
              <span className="insight-icon insight-next"><Target size={18} strokeWidth={1.8} /></span>
              <h2>下一步练习</h2>
            </div>
            <ul className="insight-list suggestion-list">
              {report.suggestions.map((item) => <li key={item}>{item}</li>)}
            </ul>
            <Link className="text-link" to="/history">
              从历史弱项开始
              <ArrowRight size={16} strokeWidth={2} />
            </Link>
          </Reveal>
        </div>

        <section className="transcript-section">
          <Reveal>
            <div className="section-heading-row">
              <div>
                <p className="report-overline">回答证据</p>
                <h2>逐题转写</h2>
              </div>
              <span className="transcript-count">{report.qa.length} 道题</span>
            </div>
          </Reveal>
          <div className="transcript-list">
            {report.qa.map((item, index) => {
              const turn = session?.turns.find((entry) => entry.turn_no === index + 1)
              return (
                <Reveal className="transcript-item" delay={index * 60} key={item.question}>
                  <div className="transcript-item-head">
                    <span className="transcript-number">0{index + 1}</span>
                    <div>
                      <h3>{item.question}</h3>
                      <span><Clock3 size={14} strokeWidth={1.8} /> 回答 {formatDuration(turn?.duration_ms ?? 0)} · 转写完成</span>
                    </div>
                    <span className="transcript-score">{item.score}</span>
                  </div>
                  <p>{item.transcript || '本题没有形成有效转写。'}</p>
                </Reveal>
              )
            })}
          </div>
        </section>

        {report.weak_tags.length ? (
          <Reveal className="report-weak-tags">
            <div>
              <FileText size={20} strokeWidth={1.8} />
              <strong>已沉淀弱项标签</strong>
            </div>
            <div className="capability-list">
              {report.weak_tags.map((tag) => <span key={tag}>{tag}</span>)}
            </div>
          </Reveal>
        ) : null}

        <Reveal className="report-final-actions">
          <div>
            <FileText size={22} strokeWidth={1.8} />
            <h2>这份报告已经进入你的历史画像</h2>
            <p>弱项标签会作为下一轮出题和知识库补强的隐式权重。生成时间：{formatDate(report.created_at)}</p>
          </div>
          <Link className="pill-button pill-button-blue" to="/setup">
            生成补强面试
            <ArrowRight size={17} strokeWidth={2} />
          </Link>
        </Reveal>
      </section>
    </div>
  )
}
