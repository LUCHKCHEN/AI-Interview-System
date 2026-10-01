import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BadgeCheck,
  BarChart3,
  CircleHelp,
  FileUp,
  Headphones,
  History,
  Mic,
  Play,
  ScanSearch,
} from 'lucide-react'
import Reveal from '../components/Reveal'
import './HomePage.css'

const productEntries = [
  {
    title: '按 JD 出题',
    description: '从目标岗位描述中提取能力点，生成场景化追问，而不是重复背诵问题。',
    icon: ScanSearch,
    to: '/setup',
    label: '准备面试',
  },
  {
    title: '语音作答',
    description: '以贴近真实面试的节奏播放题目、录音并记录停顿，界面只保留需要的信息。',
    icon: Mic,
    to: '/setup',
    label: '进入面试',
  },
  {
    title: '四维评分',
    description: '技术深度、逻辑表达、应变潜力和岗位匹配度，用统一权重解释每次提升。',
    icon: BarChart3,
    to: '/history',
    label: '查看报告',
  },
  {
    title: '历史进化',
    description: '积累弱项和复盘证据，把反复出现的回答问题转成下一次面试的准备方向。',
    icon: History,
    to: '/history',
    label: '查看历史',
  },
]

export default function HomePage() {
  return (
    <div className="home-page">
      <section className="home-hero">
        <div className="home-hero-grid" />
        <div className="home-hero-content">
          <Reveal>
            <p className="hero-eyebrow">
              <span className="hero-dot" />
              NEWRAG 动态模拟面试
            </p>
          </Reveal>
          <Reveal delay={80}>
            <h1 className="hero-title">把下一次面试，<br />练成一场可复盘的对话。</h1>
          </Reveal>
          <Reveal delay={160}>
            <p className="hero-subtitle">
              结合你的简历、目标岗位与本地知识库，连续生成三道追问，并围绕回答证据给出可行动的报告。
            </p>
          </Reveal>
          <Reveal delay={240}>
            <div className="hero-actions">
              <Link className="pill-button pill-button-light" to="/setup">
                开始准备面试
                <ArrowRight size={17} strokeWidth={2} />
              </Link>
              <Link className="pill-button pill-button-dark" to="/setup">
                <Play size={15} strokeWidth={2} fill="currentColor" />
                创建一场面试
              </Link>
            </div>
          </Reveal>
        </div>

        <Reveal className="hero-product-frame" delay={320}>
          <div className="mock-console">
            <div className="console-topbar">
              <span className="console-brand">
                <span className="console-logo" />
                NEWRAG Interview
              </span>
              <span className="console-session">智境科技 · RAG 应用工程师</span>
              <span className="console-live"><span /> 第 2 题</span>
            </div>
            <div className="console-body">
              <div className="question-column">
                <p className="micro-label">正在播放题目</p>
                <div className="console-question">
                  <span className="question-index">02</span>
                  <h2>如果线上向量检索耗时突然上升一倍，你会先看哪些环节？</h2>
                </div>
                <div className="hint-line">
                  <CircleHelp size={16} strokeWidth={1.8} />
                  考察指标意识、二分定位与生产沟通
                </div>
              </div>
              <div className="recording-panel">
                <div className="recording-ring is-recording">
                  <Mic size={26} strokeWidth={1.8} />
                  <span />
                </div>
                <p className="recording-state">正在录音</p>
                <div className="waveform" aria-hidden="true">
                  {Array.from({ length: 22 }, (_, index) => (
                    <span key={index} className={`wave-bar wave-${(index % 6) + 1}`} />
                  ))}
                </div>
                <div className="recording-meta">
                  <span>01:42</span>
                  <span>约 186 字</span>
                </div>
              </div>
            </div>
            <div className="console-footer">
              <div className="flow-dots" aria-label="三题进度">
                <span className="flow-dot is-done" />
                <span className="flow-dot is-active" />
                <span className="flow-dot" />
              </div>
              <span>回答结束后将自动生成切题与完整度标记</span>
              <span className="live-tag"><span /> LIVE</span>
            </div>
          </div>
        </Reveal>
      </section>

      <section className="home-section home-section-dark">
        <div className="section-copy-narrow">
          <Reveal>
            <p className="section-eyebrow">一整套面试证据链</p>
            <h2 className="section-title">从录音到报告，每一步都在为下一次练习服务。</h2>
            <p className="section-lead">
              NEWRAG 把面试过程拆成三个可见阶段：先按岗位准备，再通过语音连续作答，最后查看带证据引用的评分报告。
            </p>
          </Reveal>
          <Reveal delay={140}>
            <Link className="text-link" to="/history">
              查看评分报告
              <ArrowRight size={17} strokeWidth={2} />
            </Link>
          </Reveal>
        </div>

        <Reveal className="report-visual" delay={220}>
          <div className="report-card-preview" aria-label="NEWRAG 报告界面预览">
            <div className="report-preview-header">
              <div>
                <span className="micro-label">面试报告</span>
                <h3>智境科技 · RAG 应用工程师</h3>
              </div>
              <div className="score-preview">
                <strong>88</strong>
                <span>/ 100</span>
              </div>
            </div>
            <div className="report-preview-grid">
              <div className="radar-mini">
                <div className="radar-mini-copy">
                  {['岗位匹配', '表达清晰', '知识深度', '临场稳定'].map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
                <div className="radar-mini-shape" aria-hidden="true">
                  <svg viewBox="0 0 240 240" role="presentation">
                    <polygon points="120,28 190,86 160,198 80,198 50,86" fill="none" stroke="rgba(52,120,246,0.24)" strokeWidth="2" />
                    <polygon points="120,55 170,98 146,176 94,176 70,98" fill="#3478f6" fillOpacity="0.22" stroke="#3478f6" strokeWidth="2" />
                    <polyline points="120,55 152,101 135,168 98,160 79,105" fill="none" stroke="#f5a524" strokeWidth="2" />
                  </svg>
                </div>
              </div>
              <div className="report-preview-detail">
                <div className="suggestion-row">
                  <BadgeCheck size={18} strokeWidth={1.8} />
                  <span>量化结果清楚，追问后能补充关键细节</span>
                </div>
                <div className="suggestion-row">
                  <BarChart3 size={18} strokeWidth={1.8} />
                  <span>边界条件说明偏少，建议增加 5 道定制追问</span>
                </div>
                <div className="suggestion-row">
                  <Headphones size={18} strokeWidth={1.8} />
                  <span>三题录音证据已归档到历史记录</span>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      <section className="home-section home-section-light">
        <div className="section-grid-heading">
          <Reveal>
            <div>
              <p className="section-eyebrow">产品流程</p>
              <h2 className="section-title">四个入口，串起完整的面试准备闭环。</h2>
            </div>
          </Reveal>
          <Reveal delay={120}>
            <p className="section-aside">不把页面做成信息堆叠，而是让每个动作在对话链路上自然发生。</p>
          </Reveal>
        </div>

        <div className="product-entry-grid">
          {productEntries.map((entry, index) => {
            const Icon = entry.icon
            return (
              <Reveal key={entry.title} delay={index * 80}>
                <Link className="product-entry" to={entry.to}>
                  <span className="product-entry-icon"><Icon size={22} strokeWidth={1.8} /></span>
                  <h3>{entry.title}</h3>
                  <p>{entry.description}</p>
                  <span className="product-entry-action">
                    {entry.label}
                    <ArrowRight size={15} strokeWidth={2} />
                  </span>
                </Link>
              </Reveal>
            )
          })}
        </div>
      </section>

      <section className="home-section home-section-soft">
        <div className="closing-band">
          <Reveal>
            <p className="section-eyebrow">完整面试闭环</p>
            <h2 className="section-title">真实简历、真实录音，直接形成可复盘报告。</h2>
            <p className="section-lead">
              PDF 与 JD 解析、三题动态生成、关键词切题、四维评分和历史弱项沉淀已经接入本地后端。
            </p>
            <div className="closing-actions">
              <Link className="pill-button pill-button-blue" to="/setup">
                准备你的第一场面试
                <ArrowRight size={17} strokeWidth={2} />
              </Link>
              <Link className="text-link text-link-on-light" to="/history">
                查看历史记录
                <History size={16} strokeWidth={2} />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="home-tools-strip" aria-label="前端能力">
        <Reveal>
          <div className="tools-strip-inner">
            <span><FileUp size={17} strokeWidth={1.8} /> React + TypeScript + Vite</span>
            <span><BarChart3 size={17} strokeWidth={1.8} /> Recharts 雷达图</span>
            <span><Headphones size={17} strokeWidth={1.8} /> 16kHz WebSocket 录音</span>
            <span><ScanSearch size={17} strokeWidth={1.8} /> 会话与弱项持久化</span>
          </div>
        </Reveal>
      </section>
    </div>
  )
}
