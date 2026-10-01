import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Menu, X } from 'lucide-react'

const navLinks = [
  { to: '/', label: '首页', end: true },
  { to: '/setup', label: '开始面试' },
  { to: '/history', label: '报告与历史' },
]

export default function SiteNav() {
  const [open, setOpen] = useState(false)

  return (
    <header className="site-nav">
      <div className="nav-inner">
        <Link className="brand" to="/" aria-label="NEWRAG 首页">
          <span className="brand-mark" aria-hidden="true" />
          <span>NEWRAG</span>
        </Link>

        <nav className="desktop-nav" aria-label="主导航">
          {navLinks.map((link) => (
            <NavLink
              key={link.to}
              className={({ isActive }) => `nav-link ${isActive ? 'is-active' : ''}`}
              end={link.end}
              to={link.to}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <button
          className="nav-menu-button"
          type="button"
          aria-label={open ? '关闭导航' : '打开导航'}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={20} strokeWidth={1.8} /> : <Menu size={20} strokeWidth={1.8} />}
        </button>
      </div>

      {open ? (
        <nav className="mobile-nav" aria-label="移动端导航">
          {navLinks.map((link) => (
            <NavLink
              key={link.to}
              className={({ isActive }) => `mobile-nav-link ${isActive ? 'is-active' : ''}`}
              end={link.end}
              onClick={() => setOpen(false)}
              to={link.to}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
    </header>
  )
}
