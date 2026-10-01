import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  CircleHelp,
  Database,
  FileText,
  LoaderCircle,
  Upload,
} from 'lucide-react'
import { ApiError, createInterviewSession, getKnowledgeCatalog, getKnowledgeStatus } from '../api/client'
import Reveal from '../components/Reveal'
import type { KnowledgeCatalogItem, KnowledgeStatus } from '../types'
import './SetupPage.css'

export default function SetupPage() {
  const navigate = useNavigate()
  const [jdText, setJdText] = useState('')
  const [company, setCompany] = useState('')
  const [role, setRole] = useState('')
  const [fileName, setFileName] = useState('')
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [resumeText, setResumeText] = useState('')
  const [showResumeText, setShowResumeText] = useState(false)
  const [knowledge, setKnowledge] = useState<KnowledgeStatus | null>(null)
  const [catalog, setCatalog] = useState<KnowledgeCatalogItem[]>([])
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    Promise.all([getKnowledgeStatus(), getKnowledgeCatalog()])
      .then(([status, items]) => {
        setKnowledge(status)
        setCatalog(items.items)
      })
      .catch((error: unknown) => {
        setMessage(error instanceof ApiError ? error.message : '知识库状态暂时不可用。')
      })
  }, [])

  const handleFile = (file: File | null) => {
    setResumeFile(file)
    setFileName(file?.name ?? '')
    setMessage('')
    setShowResumeText(false)
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!jdText.trim()) {
      setMessage('请先填写岗位描述或 JD。')
      return
    }
    if (!resumeFile && !resumeText.trim()) {
      setShowResumeText(true)
      setMessage('请上传简历 PDF，或直接粘贴简历文本。')
      return
    }

    const form = new FormData()
    if (resumeFile) form.append('resume_pdf', resumeFile)
    if (resumeText.trim()) form.append('resume_text', resumeText.trim())
    form.append('jd', jdText.trim())
    form.append('company', company.trim())
    form.append('role', role.trim())

    setSubmitting(true)
    setMessage('')
    try {
      const session = await createInterviewSession(form)
      navigate(`/interview/${session.session_id}`)
    } catch (error) {
      const apiError = error instanceof ApiError ? error : null
      if (apiError?.code === 'SCANNED_PDF') {
        setShowResumeText(true)
      }
      setMessage(apiError?.message ?? '创建面试没有完成，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  const libraryStatus = [
    {
      label: '本地知识库',
      value: knowledge?.status === 'ready' ? '索引已就绪' : knowledge?.message || '首次提问时自动构建',
      ready: knowledge?.status === 'ready',
    },
    {
      label: '知识库模块',
      value: catalog.length ? `${catalog.length} 个模块 · ${catalog.reduce((sum, item) => sum + item.files, 0)} 份资料` : '等待索引扫描',
      ready: catalog.some((item) => item.files > 0),
    },
    {
      label: '岗位 JD 能力点',
      value: jdText.trim() ? '将在创建时提取' : '等待填写 JD',
      ready: Boolean(jdText.trim()),
    },
    {
      label: '候选人简历',
      value: resumeFile?.name || (resumeText.trim() ? '已使用粘贴文本' : '等待上传或粘贴'),
      ready: Boolean(resumeFile || resumeText.trim()),
    },
  ]

  return (
    <div className="setup-page">
      <section className="page-hero setup-hero">
        <Reveal>
          <p className="page-eyebrow">准备一次模拟面试</p>
          <h1>先定义问题，再开始对话。</h1>
          <p className="page-lead">
            输入简历、目标岗位和公司，NEWRAG 会提取能力差集并生成三题连续面试。
          </p>
        </Reveal>
      </section>

      <section className="setup-workspace">
        <Reveal className="setup-form-column">
          <form className="setup-form" onSubmit={handleSubmit}>
            <div className="form-section-heading">
              <span className="form-step">01</span>
              <div>
                <h2>上传简历</h2>
                <p>优先解析文字型 PDF；扫描件可切换到文本通道。</p>
              </div>
            </div>

            <label className="upload-zone">
              <input
                type="file"
                accept=".pdf"
                onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
              />
              <span className="upload-icon"><Upload size={22} strokeWidth={1.8} /></span>
              <span className="upload-title">{fileName || '选择文字型 PDF 简历'}</span>
              <span className="upload-note">文件只在本机解析</span>
            </label>

            <div className="selected-file">
              <FileText size={17} strokeWidth={1.8} />
              <span>{fileName || '尚未选择文件，可在下方粘贴简历文本'}</span>
              <CheckCircle2 size={17} strokeWidth={1.8} />
            </div>

            <label className="field-label resume-text-field">
              <span>简历文本备用通道</span>
              <textarea
                value={resumeText}
                onChange={(event) => {
                  setResumeText(event.target.value)
                  setMessage('')
                }}
                rows={showResumeText ? 7 : 3}
                placeholder="扫描 PDF 无法提取文字时，在这里粘贴简历内容。"
              />
            </label>

            <div className="form-section-heading form-section-spacer">
              <span className="form-step">02</span>
              <div>
                <h2>补充岗位信息</h2>
                <p>JD 中的技术关键词决定精准模式或广度模式。</p>
              </div>
            </div>

            <div className="field-row two-field-row">
              <label className="field-label">
                <span>目标公司</span>
                <span className="field-with-icon">
                  <Building2 size={17} strokeWidth={1.8} />
                  <input
                    value={company}
                    onChange={(event) => setCompany(event.target.value)}
                    placeholder="选填"
                  />
                </span>
              </label>
              <label className="field-label">
                <span>目标岗位</span>
                <span className="field-with-icon">
                  <BriefcaseBusiness size={17} strokeWidth={1.8} />
                  <input
                    value={role}
                    onChange={(event) => setRole(event.target.value)}
                    placeholder="例如 Java 后端工程师"
                  />
                </span>
              </label>
            </div>

            <label className="field-label">
              <span>岗位描述或 JD</span>
              <textarea
                value={jdText}
                onChange={(event) => setJdText(event.target.value)}
                rows={7}
                placeholder="粘贴完整 JD，或写下你希望系统重点追问的技术方向。"
              />
            </label>

            <div className="form-hint-row">
              <CircleHelp size={16} strokeWidth={1.8} />
              <span>系统只做能力差集与追问生成，不会修改原始简历或 JD。</span>
            </div>

            {message ? <div className="form-message" role="status">{message}</div> : null}

            <button
              className="pill-button pill-button-blue setup-start-button"
              type="submit"
              disabled={submitting}
            >
              {submitting ? <LoaderCircle className="spin-icon" size={17} /> : null}
              {submitting ? '正在生成三题面试' : '创建三题面试'}
              {!submitting ? <ArrowRight size={17} strokeWidth={2} /> : null}
            </button>
          </form>
        </Reveal>

        <Reveal className="setup-context-column" delay={120}>
          <div className="context-heading">
            <div className="context-mark"><Database size={20} strokeWidth={1.8} /></div>
            <div>
              <h2>知识库状态</h2>
              <p>最近一次更新的本地资料会参与检索。</p>
            </div>
          </div>

          <div className="context-list">
            {libraryStatus.map((item) => (
              <div className={`context-row ${item.ready ? 'is-ready' : ''}`} key={item.label}>
                <span className="context-state-icon">
                  {item.ready ? <CheckCircle2 size={17} strokeWidth={1.8} /> : <CircleHelp size={17} strokeWidth={1.8} />}
                </span>
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.value}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="context-preview">
            <div className="preview-label">当前流程</div>
            <div className="capability-list">
              <span>文字型 PDF 解析</span>
              <span>JD 技术关键词提取</span>
              <span>三题分层递进</span>
              <span>实时关键词切题</span>
            </div>
          </div>

          <div className="context-note">
            <span>本地优先</span>
            语音只朗读题目，考察理由保留在屏幕；录音和会话记录不会上传到第三方存储。
          </div>
        </Reveal>
      </section>
    </div>
  )
}
