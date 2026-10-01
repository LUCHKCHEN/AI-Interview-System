import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  ChevronRight,
  Download,
  History,
  LoaderCircle,
  PlayCircle,
  RotateCcw,
  Target,
  Trash2,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ApiError, deleteHistory, formatDate, getHistory, getHistoryExportUrl } from '../api/client'
import Reveal from '../components/Reveal'
import type { HistoryResponse } from '../types'
import './HistoryPage.css'

export default function HistoryPage() {
  const [data, setData] = useState<HistoryResponse>({ items: [], weak_tags: [] })
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [deleting, setDeleting] = useState('')

  useEffect(() => {
    let active = true
    getHistory()
      .then((response) => {
        if (!active) return
        setData(response)
        setMessage('')
      })
      .catch((error: unknown) => {
        if (!active) return
        setMessage(error instanceof ApiError ? error.message : '历史记录加载失败。')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const scored = data.items.filter((entry) => entry.score !== null)
  const average = scored.length
    ? Math.round(scored.reduce((sum, entry) => sum + (entry.score ?? 0), 0) / scored.length)
    : 0
  const recent = data.items[0]
  const weakest = data.weak_tags[0]
  const trendData = useMemo(
    () => [...scored].reverse().map((entry) => ({
      name: formatDate(entry.created_at).slice(5, 10),
      score: entry.score ?? 0,
      role: entry.role,
    })),
    [scored],
  )

  const removeEntry = async (sessionId: string) => {
    setDeleting(sessionId)
    try {
      await deleteHistory(sessionId)
      setData((current) => ({
        ...current,
        items: current.items.filter((item) => item.session_id !== sessionId),
      }))
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : '删除没有完成。')
    } finally {
      setDeleting('')
    }
  }

  return (
    <div className="history-page">
      <section className="history-hero">
        <Reveal>
          <p className="page-eyebrow">历史与进化</p>
          <h1>让每一次面试，都成为下一条能力曲线。</h1>
          <p className="page-lead">
            这里保留岗位、分数、弱项和报告入口。高频短板会进入下一轮出题与知识库补强。
          </p>
          <Link className="pill-button pill-button-blue history-primary-action" to="/setup">
            开始新一轮
            <ArrowRight size={17} strokeWidth={2} />
          </Link>
        </Reveal>
      </section>

      <section className="history-overview">
        <Reveal className="history-summary">
          <div>
            <span className="summary-label">累计平均分</span>
            <strong>{average}</strong>
            <p>{scored.length ? `基于 ${scored.length} 份已完成报告` : '等待第一份报告'}</p>
          </div>
          <div>
            <span className="summary-label">历史场次</span>
            <strong>{data.items.length}</strong>
            <p>覆盖 {new Set(data.items.map((item) => item.role)).size} 个目标岗位</p>
          </div>
          <div>
            <span className="summary-label">当前最弱标签</span>
            <strong>{weakest?.tag ?? '暂无'}</strong>
            <p>{weakest ? `累计出现 ${weakest.count} 次` : '完成评分后自动沉淀'}</p>
          </div>
          <div className="summary-action">
            <Target size={20} strokeWidth={1.8} />
            <p>{weakest ? '下一轮会提高相关追问的出现权重' : '完成一轮后形成个人弱项地图'}</p>
          </div>
        </Reveal>
      </section>

      <section className="history-main">
        <Reveal className="trend-card">
          <div className="section-heading-row">
            <div>
              <p className="report-overline">能力曲线</p>
              <h2>总分变化</h2>
            </div>
            {trendData.length > 1 ? (
              <span className="trend-status">
                <BarChart3 size={16} strokeWidth={1.8} />
                最近变化 {trendData.at(-1)!.score - trendData.at(-2)!.score} 分
              </span>
            ) : null}
          </div>
          <div className="trend-chart">
            {trendData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData} margin={{ top: 12, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="historyScore" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="#3478f6" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="#3478f6" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(29, 29, 31, 0.08)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: '#6e6e73', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: '#6e6e73', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ border: '1px solid rgba(29, 29, 31, 0.1)', borderRadius: 8, boxShadow: '0 12px 40px rgba(0,0,0,0.08)' }}
                    formatter={(value) => [`${value} 分`, '总分']}
                  />
                  <Area type="monotone" dataKey="score" stroke="#3478f6" strokeWidth={2.5} fill="url(#historyScore)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <div className="history-empty-chart">完成一次评分后显示能力曲线</div>}
          </div>
        </Reveal>

        <div className="history-list-column">
          <div className="section-heading-row history-list-heading">
            <div>
              <p className="report-overline">历史记录</p>
              <h2>最近的面试</h2>
            </div>
            <span className="history-count">{data.items.length} 条</span>
          </div>

          {message ? <div className="history-message" role="status">{message}</div> : null}

          <div className="history-list">
            {loading ? (
              <div className="history-loading"><LoaderCircle className="spin-icon" size={20} />正在加载历史记录</div>
            ) : null}
            {!loading && !data.items.length ? (
              <div className="history-loading">还没有面试记录，先创建第一轮模拟面试。</div>
            ) : null}
            {data.items.map((entry, index) => (
              <Reveal delay={index * 50} key={entry.session_id}>
                <div className="history-row">
                  <div className="history-row-score">
                    <strong>{entry.score ?? '—'}</strong>
                    <span>{entry.score === null ? '未评分' : '分'}</span>
                  </div>
                  <div className="history-row-main">
                    <div className="history-title-line">
                      <h3>{entry.company || '未填写公司'}</h3>
                      <span>{entry.role || '目标岗位'} · {entry.mode === 'precise' ? '精准模式' : '广度模式'}</span>
                    </div>
                    <div className="history-meta">
                      <span><CalendarDays size={14} strokeWidth={1.8} /> {formatDate(entry.created_at)}</span>
                      <span><PlayCircle size={14} strokeWidth={1.8} /> {entry.questions} 题</span>
                      <span><RotateCcw size={14} strokeWidth={1.8} /> {entry.weak_tags.slice(0, 2).join('、') || entry.level}</span>
                    </div>
                  </div>
                  <div className="history-row-actions">
                    <Link className="history-open" to={`/report/${entry.session_id}`} aria-label={`查看 ${entry.company} 报告`}>
                      <ArrowUpRight size={18} strokeWidth={1.8} />
                    </Link>
                    <a href={getHistoryExportUrl(entry.session_id)} download aria-label="下载历史报告">
                      <Download size={17} strokeWidth={1.8} />
                    </a>
                    <button
                      type="button"
                      aria-label="删除历史记录"
                      disabled={deleting === entry.session_id}
                      onClick={() => void removeEntry(entry.session_id)}
                    >
                      {deleting === entry.session_id ? <LoaderCircle className="spin-icon" size={16} /> : <Trash2 size={17} strokeWidth={1.8} />}
                    </button>
                  </div>
                  <Link className="history-row-chevron" to={`/report/${entry.session_id}`} aria-label={`打开 ${entry.company}`}>
                    <ChevronRight size={20} strokeWidth={1.8} />
                  </Link>
                </div>
              </Reveal>
            ))}
          </div>

          {recent ? (
            <Reveal className="history-cta">
              <History size={22} strokeWidth={1.8} />
              <div>
                <h3>打开最近一次报告</h3>
                <p>{recent.company || '未填写公司'} · {recent.role} · {recent.score ?? '未评分'}{recent.score === null ? '' : ' 分'}</p>
              </div>
              <Link className="pill-button pill-button-blue" to={`/report/${recent.session_id}`}>
                查看报告
                <ArrowRight size={16} strokeWidth={2} />
              </Link>
            </Reveal>
          ) : null}
        </div>
      </section>
    </div>
  )
}
