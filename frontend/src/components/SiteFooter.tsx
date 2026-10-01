import { Link } from 'react-router-dom'
import { BookOpen, Database, Headphones } from 'lucide-react'

const footerLinks = [
  { label: '准备面试', to: '/setup' },
  { label: '历史记录', to: '/history' },
]

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-column footer-brand">
          <Link className="brand brand-footer" to="/">
            <span className="brand-mark" aria-hidden="true" />
            NEWRAG
          </Link>
          <p className="footer-description">AI 动态模拟面试系统。简历、岗位与本地知识库驱动的三题语音面试。</p>
          <div className="footer-tech">
            <span><BookOpen size={15} strokeWidth={1.8} /> PDF 与 JD 解析</span>
            <span><Headphones size={15} strokeWidth={1.8} /> WebSocket 录音</span>
            <span><Database size={15} strokeWidth={1.8} /> 本地会话与报告</span>
          </div>
        </div>
        <div className="footer-column footer-link-group">
          <h3 className="footer-heading">产品流程</h3>
          {footerLinks.map((link) => (
            <Link key={link.label} className="footer-link" to={link.to}>
              {link.label}
            </Link>
          ))}
        </div>
        <div className="footer-column">
          <h3 className="footer-heading">设计边界</h3>
          <p className="footer-note">本地音频、会话和报告默认只保存在设备中。</p>
          <p className="footer-note">界面素材与图标均使用项目自有资源及开源图标库。</p>
        </div>
      </div>
      <div className="footer-bottom">
        <span>© 2026 NEWRAG</span>
        <span>React · FastAPI · WebSocket</span>
      </div>
    </footer>
  )
}
