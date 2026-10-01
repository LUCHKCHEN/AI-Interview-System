import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleHelp,
  FileAudio,
  Headphones,
  ListChecks,
  LoaderCircle,
  Mic,
  MicOff,
  Play,
  RotateCcw,
  Square,
  Volume2,
  VolumeX,
} from 'lucide-react'
import {
  ApiError,
  finishInterview,
  formatDuration,
  getAnswerWebSocketUrl,
  getCompletionAudioUrl,
  getInterviewSession,
  getQuestionAudioUrl,
} from '../api/client'
import { usePcmRecorder } from '../hooks/usePcmRecorder'
import type { InterviewSessionDetail } from '../types'
import './InterviewPage.css'

type InterviewPhase =
  | 'loading'
  | 'ready'
  | 'playing'
  | 'countdown'
  | 'starting'
  | 'recording'
  | 'finalizing'
  | 'review'
  | 'text'
  | 'done'

interface SocketEvent {
  type: string
  message?: string
  interim_text?: string
  chars?: number
  elapsed_ms?: number
  transcript?: string
  next_turn_no?: number
}

export default function InterviewPage() {
  const { sessionId = '' } = useParams()
  const [session, setSession] = useState<InterviewSessionDetail | null>(null)
  const [turnNo, setTurnNo] = useState(1)
  const [phase, setPhase] = useState<InterviewPhase>('loading')
  const [elapsedMs, setElapsedMs] = useState(0)
  const [chars, setChars] = useState(0)
  const [interim, setInterim] = useState('')
  const [fallbackText, setFallbackText] = useState('')
  const [notice, setNotice] = useState('')
  const [audioPlaying, setAudioPlaying] = useState(false)
  const [audioMuted, setAudioMuted] = useState(false)
  const [countdown, setCountdown] = useState(3)
  const socketRef = useRef<WebSocket | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const turnRef = useRef(1)
  const startFlowRef = useRef(0)
  const questionCountRef = useRef(3)

  const sendChunk = useCallback((chunk: ArrayBuffer) => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) socket.send(chunk)
  }, [])
  const { start: startRecorder, stop: stopRecorder } = usePcmRecorder(sendChunk)

  useEffect(() => {
    let active = true
    getInterviewSession(sessionId)
      .then((data) => {
        if (!active) return
        setSession(data)
        questionCountRef.current = data.questions.length
        const current = Math.min(
          Math.max(data.current_turn_no, 1),
          questionCountRef.current,
        )
        setTurnNo(current)
        turnRef.current = current
        setChars(0)
        setPhase('ready')
      })
      .catch((error: unknown) => {
        if (!active) return
        setNotice(error instanceof ApiError ? error.message : '面试会话加载失败。')
        setPhase('done')
      })
    return () => {
      active = false
      startFlowRef.current += 1
      socketRef.current?.close()
      stopRecorder()
      audioRef.current?.pause()
    }
  }, [sessionId, stopRecorder])

  useEffect(() => {
    if (phase !== 'recording') return undefined
    const timer = window.setInterval(() => setElapsedMs((value) => value + 1000), 1000)
    return () => window.clearInterval(timer)
  }, [phase])

  useEffect(() => {
    turnRef.current = turnNo
  }, [turnNo])

  const playQuestion = useCallback(async (targetTurn = turnNo) => {
    if (!session) return false
    audioRef.current?.pause()
    const audio = new Audio(getQuestionAudioUrl(session.session_id, targetTurn))
    audioRef.current = audio
    audio.muted = audioMuted
    setAudioPlaying(true)
    return await new Promise<boolean>((resolve) => {
      let settled = false
      const finish = (played: boolean) => {
        if (settled) return
        settled = true
        setAudioPlaying(false)
        resolve(played)
      }
      audio.onended = () => finish(true)
      audio.onerror = () => {
        setNotice('题目语音加载失败，请检查后端语音服务。')
        finish(false)
      }
      audio.play().catch(() => {
        setNotice('浏览器没有自动播放题音，请点击“重听题目”后重试。')
        finish(false)
      })
    })
  }, [audioMuted, session, turnNo])

  const toggleAudioMute = () => {
    setAudioMuted((muted) => {
      const next = !muted
      if (audioRef.current) audioRef.current.muted = next
      return next
    })
  }

  const playCompletion = useCallback(async () => {
    audioRef.current?.pause()
    const audio = new Audio(getCompletionAudioUrl(sessionId))
    audioRef.current = audio
    setAudioPlaying(true)
    audio.onended = () => setAudioPlaying(false)
    audio.onerror = () => setAudioPlaying(false)
    try {
      await audio.play()
    } catch {
      setAudioPlaying(false)
      setNotice('结束语语音未能自动播放，评分流程仍会继续。')
    }
  }, [sessionId])

  const handleSocketEvent = useCallback(async (event: SocketEvent) => {
    if (event.type === 'status') {
      if (typeof event.interim_text === 'string') setInterim(event.interim_text)
      if (typeof event.chars === 'number') setChars(event.chars)
      if (typeof event.elapsed_ms === 'number') setElapsedMs(event.elapsed_ms)
      if (event.message === '技术面试结束，接下来进入评分环节。') {
        setNotice(event.message)
      }
      return
    }
    if (event.type === 'warning' || event.type === 'transition') {
      setNotice(event.message ?? '系统正在等待下一步。')
      return
    }
    if (event.type === 'error') {
      stopRecorder()
      setNotice(event.message ?? '录音链路暂时不可用，可改用文本补充。')
      setPhase('text')
      return
    }
    if (event.type === 'finalized') {
      stopRecorder()
      const finalText = event.transcript ?? ''
      setInterim(finalText)
      setChars(finalText.match(/[\u4e00-\u9fff]/g)?.length ?? 0)
      setPhase('review')
      setNotice(event.next_turn_no === turnRef.current ? '本题已保存。' : '好的，了解了')
      if (turnRef.current >= questionCountRef.current) {
        setNotice('技术面试结束，接下来进入评分环节。')
        setPhase('done')
        void playCompletion()
        try {
          await finishInterview(sessionId)
        } catch (error) {
          setNotice(error instanceof ApiError ? error.message : '评分任务暂未启动，请稍后重试。')
        }
      }
    }
  }, [playCompletion, sessionId, stopRecorder])

  const openSocket = useCallback(async (targetTurn: number) => {
    const socket = new WebSocket(getAnswerWebSocketUrl(sessionId, targetTurn))
    socketRef.current = socket
    socket.onmessage = (event) => {
      try {
        void handleSocketEvent(JSON.parse(event.data as string) as SocketEvent)
      } catch {
        setNotice('收到无法识别的录音状态。')
      }
    }
    socket.onerror = () => {
      setNotice('录音连接暂时中断，可改用文本补充。')
    }
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => {
        socket.send(JSON.stringify({ type: 'start', turn_no: targetTurn }))
        resolve()
      }
      socket.onclose = () => reject(new Error('socket-closed'))
    })
    return socket
  }, [handleSocketEvent, sessionId])

  const startRecording = async () => {
    const flowId = ++startFlowRef.current
    setNotice('')
    setElapsedMs(0)
    setChars(0)
    setInterim('')
    setPhase('playing')
    const played = await playQuestion()
    if (flowId !== startFlowRef.current) return
    if (!played) {
      setPhase('ready')
      return
    }

    setPhase('countdown')
    for (let value = 3; value > 0; value -= 1) {
      setCountdown(value)
      await new Promise<void>((resolve) => window.setTimeout(resolve, 1000))
      if (flowId !== startFlowRef.current) return
    }

    try {
      setPhase('starting')
      await openSocket(turnNo)
      await startRecorder()
      setPhase('recording')
    } catch {
      socketRef.current?.close()
      stopRecorder()
      setNotice('无法使用麦克风，请检查浏览器权限或改用文本补充。')
      setPhase('text')
    }
  }

  const stopRecording = () => {
    const socket = socketRef.current
    stopRecorder()
    setPhase('finalizing')
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'finish', reason: 'manual' }))
    } else {
      setNotice('录音连接已断开，请改用文本补充。')
      setPhase('text')
    }
  }

  const submitTextAnswer = async () => {
    if (fallbackText.trim().length < 2) {
      setNotice('请先写下本题回答，再提交。')
      return
    }
    setNotice('')
    setPhase('finalizing')
    try {
      const socket = await openSocket(turnNo)
      socket.send(JSON.stringify({ type: 'text_answer', transcript: fallbackText.trim() }))
    } catch {
      setNotice('文本提交没有完成，请稍后重试。')
      setPhase('text')
    }
  }

  const goNext = () => {
    if (!session || turnNo >= session.questions.length) return
    startFlowRef.current += 1
    const next = turnNo + 1
    setTurnNo(next)
    turnRef.current = next
    setElapsedMs(0)
    setChars(0)
    setInterim('')
    setFallbackText('')
    setNotice('')
    setPhase('ready')
    void playQuestion(next)
  }

  if (!session) {
    return (
      <div className="interview-page interview-loading">
        <LoaderCircle className="spin-icon" size={26} />
        <p>{notice || '正在加载面试会话…'}</p>
        <Link className="pill-button pill-button-light" to="/setup">返回准备</Link>
      </div>
    )
  }

  const question = session.questions[turnNo - 1]
  const isDone = phase === 'review' || phase === 'done'
  const questionControlsLocked =
    phase === 'playing' || phase === 'countdown' || phase === 'starting' || phase === 'recording' || phase === 'finalizing'

  return (
    <div className="interview-page">
      <section className="interview-header">
        <div className="interview-header-inner">
          <div className="interview-title-row">
            <div>
              <Link className="back-link" to="/setup">
                <ArrowLeft size={16} strokeWidth={1.9} />
                返回准备
              </Link>
              <p className="page-eyebrow">动态模拟面试 · {session.mode === 'precise' ? '精准模式' : '广度模式'}</p>
              <h1>{session.company || '目标公司'} · {session.role}</h1>
            </div>
            <Link className="pill-button pill-button-blue" to={`/report/${session.session_id}`}>
              {phase === 'done' ? '查看评分结果' : '查看报告'}
              <ArrowRight size={17} strokeWidth={2} />
            </Link>
          </div>
          <div className="interview-meta-row">
            <span><FileAudio size={16} strokeWidth={1.8} /> {session.resume_name}</span>
            <span><Headphones size={16} strokeWidth={1.8} /> 三题连续作答</span>
            <span><ListChecks size={16} strokeWidth={1.8} /> 回答后说“回答完毕”自动切题</span>
          </div>
        </div>
      </section>

      <section className="interview-console" aria-label="面试驾驶舱">
        <div className="question-progress" aria-label="题目进度">
          {session.questions.map((item) => {
            const current = item.number === turnNo
            const completed = item.number < turnNo || (current && isDone)
            return (
              <div className={`progress-step ${current ? 'is-current' : ''} ${completed ? 'is-done' : ''}`} key={item.id}>
                <span className="progress-index">{completed && !current ? <Check size={14} strokeWidth={2.2} /> : `0${item.number}`}</span>
                <div className="progress-copy">
                  <strong>{completed && !current ? '已完成' : current ? '当前题目' : '待开始'}</strong>
                  <span>{item.dimension}</span>
                </div>
              </div>
            )
          })}
        </div>

        <div className="console-grid">
          <div className="interview-question-panel">
            <div className="question-panel-top">
              <span className="micro-label">题目 {String(question.number).padStart(2, '0')}</span>
              <span className="dimension-pill">{question.dimension}</span>
            </div>
            <h2>{question.title}</h2>
            <div className="intent-note">
              <CircleHelp size={18} strokeWidth={1.8} />
              <p><strong>考察意图</strong>{question.intent}</p>
            </div>
            <div className="structure-note">
              <p className="micro-label">建议回答结构</p>
              <p>{question.hint}</p>
            </div>

            <div className="question-controls">
              <button className="icon-control" type="button" onClick={() => void playQuestion()} aria-label="重听题目" disabled={questionControlsLocked}>
                <RotateCcw size={18} strokeWidth={1.8} />
                <span>{audioPlaying ? '正在播放' : '重听题目'}</span>
              </button>
              <button className="icon-control" type="button" onClick={() => void playQuestion()} aria-label="播放题声音频" disabled={questionControlsLocked}>
                <Play size={17} strokeWidth={1.8} fill="currentColor" />
                <span>仅朗读题目</span>
              </button>
              <button
                className={`volume-control ${audioMuted ? 'is-muted' : ''}`}
                type="button"
                onClick={toggleAudioMute}
                aria-label={audioMuted ? '取消静音题目语音' : '静音题目语音'}
                aria-pressed={audioMuted}
                title={audioMuted ? '取消静音' : '静音题目语音'}
              >
                {audioMuted ? <VolumeX size={18} strokeWidth={1.8} /> : <Volume2 size={18} strokeWidth={1.8} />}
              </button>
            </div>
          </div>

          <div className="recording-console-panel">
            <div className={`recorder-state ${phase}`}>
              <div className={`recorder-icon ${phase === 'recording' ? 'is-pulsing' : ''}`}>
                {phase === 'recording' ? <Mic size={28} strokeWidth={1.7} /> : <MicOff size={28} strokeWidth={1.7} />}
              </div>
              <p className="recorder-title">
                {phase === 'ready' ? '准备开始本题'
                  : phase === 'playing' ? '正在播放题目'
                    : phase === 'countdown' ? `${countdown} 秒后开始录音`
                      : phase === 'starting' ? '正在启动录音'
                  : phase === 'recording' ? '正在录音'
                    : phase === 'finalizing' ? '正在整理回答'
                      : phase === 'text' ? '改用文本补充'
                        : phase === 'done' ? '本轮面试已完成'
                          : '已保存本题回答'}
              </p>
              <p className={`recorder-time ${phase === 'countdown' ? 'is-countdown' : ''}`} aria-live="polite">
                {phase === 'countdown' ? countdown : formatDuration(elapsedMs)}
              </p>
              <div className={`live-wave ${phase === 'recording' ? 'is-live' : ''}`} aria-hidden="true">
                {Array.from({ length: 34 }, (_, index) => (
                  <span key={index} className={`wave-item wave-${(index % 7) + 1}`} />
                ))}
              </div>
              <div className="recorder-meta">
                <span>
                  {phase === 'playing' ? '正在朗读题目'
                    : phase === 'countdown' ? '请准备回答'
                      : phase === 'starting' ? '正在连接麦克风' : `有效汉字约 ${chars}`}
                </span>
                <span>
                  {phase === 'playing' ? '播放结束后进入倒计时'
                    : phase === 'countdown' ? '倒计时结束后自动录音'
                      : phase === 'starting' ? '请允许浏览器使用麦克风'
                        : chars < 50 && phase !== 'ready' ? '建议回答不少于 50 字' : '实时转写中'}
                </span>
              </div>
            </div>

            {phase === 'text' ? (
              <div className="text-answer-panel">
                <textarea
                  value={fallbackText}
                  onChange={(event) => setFallbackText(event.target.value)}
                  rows={6}
                  placeholder="语音不可用时，在这里输入本题回答。"
                />
                <button className="pill-button pill-button-blue" type="button" onClick={() => void submitTextAnswer()}>
                  提交文本回答
                  <ArrowRight size={16} strokeWidth={2} />
                </button>
              </div>
            ) : null}

            {interim && (phase === 'recording' || phase === 'finalizing' || phase === 'review') ? (
              <p className="interim-copy">{interim}</p>
            ) : null}

            <div className="recorder-actions">
              {phase === 'playing' ? <span className="recorder-status"><Volume2 size={16} />正在播放题目，请先听题</span> : null}
              {phase === 'countdown' ? <span className="recorder-status"><Mic size={16} />准备回答，倒计时结束后自动录音</span> : null}
              {phase === 'starting' ? <span className="recorder-status"><LoaderCircle className="spin-icon" size={16} />正在连接麦克风</span> : null}
              {phase === 'ready' ? (
                <button className="pill-button pill-button-blue" type="button" onClick={() => void startRecording()}>
                  <Mic size={16} strokeWidth={2} />
                  播放题目并开始录音
                </button>
              ) : null}
              {phase === 'ready' ? (
                <button className="icon-control" type="button" onClick={() => void playQuestion()}>
                  <Play size={16} strokeWidth={2} />
                  只播放题目
                </button>
              ) : null}
              {phase === 'recording' ? (
                <button className="pill-button pill-button-stop" type="button" onClick={stopRecording}>
                  <Square size={14} strokeWidth={2.2} fill="currentColor" />
                  停止并提交
                </button>
              ) : null}
              {phase === 'finalizing' ? <span className="recorder-status"><LoaderCircle className="spin-icon" size={16} />正在转写和保存</span> : null}
              {phase === 'review' && turnNo < 3 ? (
                <button className="pill-button pill-button-blue" type="button" onClick={goNext}>
                  进入下一题
                  <ArrowRight size={17} strokeWidth={2} />
                </button>
              ) : null}
              {phase === 'text' ? (
                <button className="icon-control" type="button" onClick={() => setPhase('ready')}>
                  <Mic size={16} strokeWidth={2} />
                  返回语音作答
                </button>
              ) : null}
            </div>
          </div>
        </div>

        {notice ? <div className="interview-notice" role="status">{notice}</div> : null}

        {phase === 'done' ? (
          <div className="interview-done">
            <CheckCircle2 size={22} strokeWidth={1.8} />
            <div>
              <strong>技术面试结束，接下来进入评分环节。</strong>
              <span>回答和题目上下文已经保存，报告将在评分完成后自动展示。</span>
            </div>
            <Link className="pill-button pill-button-light" to={`/report/${session.session_id}`}>
              查看完整报告
              <ArrowRight size={17} strokeWidth={2} />
            </Link>
          </div>
        ) : null}

        <div className="console-bottom-note">
          <span className="live-dot" />
          16kHz 单声道 PCM · 关键词切题 · 超长静默自动兜底
        </div>
      </section>
    </div>
  )
}
