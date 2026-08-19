import { useEffect, useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { UserButton } from '@clerk/clerk-react'
import { LayoutDashboard, MessageSquare, Menu, X, Sun, Moon, Building2, BrainCircuit, FileText, Settings, CheckSquare } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'
import { useApi } from '../api/client'

const navItems = [
  { to: '/dashboard',  icon: LayoutDashboard, label: 'Dashboard'  },
  { to: '/office',     icon: Building2,       label: 'Office'     },
  { to: '/chat',       icon: MessageSquare,   label: 'Chat'       },
  { to: '/approvals',  icon: CheckSquare,     label: 'Approvals'  },
  { to: '/agents',     icon: BrainCircuit,    label: 'Agents'     },
  { to: '/docs',       icon: FileText,        label: 'Documents'  },
  { to: '/setup',      icon: Settings,        label: 'Setup'      },
]

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [pending, setPending] = useState(0)
  const { theme, toggleTheme } = useTheme()
  const api = useApi()

  useEffect(() => {
    let cancelled = false
    const poll = () =>
      api.get('/api/v1/approvals/counts')
        .then(d => { if (!cancelled) setPending(d.total_pending || 0) })
        .catch(() => {})
    poll()
    const t = setInterval(poll, 30000)
    return () => { cancelled = true; clearInterval(t) }
  }, [api])

  return (
    <div className="flex flex-col md:flex-row h-screen w-screen overflow-hidden" style={{ background: 'var(--bg)' }}>

      {/* Mobile Top Bar */}
      <header className="flex md:hidden items-center justify-between px-4 py-3"
        style={{
          background: 'var(--card-bg)',
          borderBottom: '1px solid var(--card-border)',
          zIndex: 30,
        }}>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMobileOpen(true)}
            style={{ color: 'var(--text-secondary)', background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}
          >
            <Menu size={20} />
          </button>
          <span style={{
            fontFamily: "'Kola-Regular', serif",
            fontSize: '1.15rem', fontWeight: 600,
            letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-primary)',
          }}>
            Fashion<span style={{ color: 'var(--gold)', fontWeight: 700 }}>OS</span>
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 30, height: 30, borderRadius: 8, flexShrink: 0,
              background: 'var(--hover-bg)', border: '1px solid var(--card-border)',
              color: 'var(--gold)', cursor: 'pointer',
            }}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/70 z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 md:static flex flex-col w-56 h-full transition-transform duration-300 ease-in-out md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        style={{
          background: 'var(--sidebar-gradient)',
          borderRight: '1px solid var(--sidebar-border)',
        }}
      >
        {/* Brand */}
        <div className="p-5 flex items-center justify-between" style={{ borderBottom: '1px solid var(--card-border)' }}>
          <span style={{
            fontFamily: "'Kola-Regular', serif",
            fontSize: '1.25rem', fontWeight: 600,
            letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-primary)',
          }}>
            Fashion<span style={{ color: 'var(--gold)', fontWeight: 700 }}>OS</span>
          </span>
          <button onClick={() => setMobileOpen(false)} className="md:hidden"
            style={{ color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={16} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} className="block" onClick={() => setMobileOpen(false)}>
              {({ isActive }) => (
                <div
                  style={isActive ? {
                    background: 'var(--active-nav)',
                    borderLeft: `2px solid var(--gold)`,
                    paddingLeft: 10,
                    color: 'var(--gold)',
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px 8px 10px',
                    borderRadius: '0 8px 8px 0',
                    transition: 'all 0.15s',
                    cursor: 'pointer',
                  } : {
                    color: 'var(--text-muted)',
                    borderLeft: '2px solid transparent',
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px',
                    borderRadius: '0 8px 8px 0',
                    transition: 'all 0.15s',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={e => { if (!isActive) { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.background = 'var(--hover-bg)' } }}
                  onMouseLeave={e => { if (!isActive) { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = '' } }}
                >
                  <Icon size={15} style={{ color: isActive ? 'var(--gold)' : 'inherit', flexShrink: 0 }} />
                  <span style={{ fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", fontSize: '0.78rem', letterSpacing: '0.02em', flex: 1 }}>
                    {label}
                  </span>
                  {to === '/approvals' && pending > 0 && (
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      minWidth: 18, height: 18, padding: '0 5px', borderRadius: 999,
                      background: pending > 0 ? 'rgba(250,204,21,0.15)' : 'transparent',
                      border: `1px solid ${pending > 0 ? 'rgba(250,204,21,0.45)' : 'transparent'}`,
                      color: '#facc15', fontSize: '0.55rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                      flexShrink: 0,
                    }}>
                      {pending}
                    </span>
                  )}
                </div>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Bottom */}
        <div className="p-4 flex items-center justify-between gap-2.5" style={{ borderTop: '1px solid var(--card-border)' }}>
          <div className="flex items-center gap-2.5">
            <UserButton afterSignOutUrl="/" />
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontFamily: "'Panchang-Variable', 'Panchang-Regular', sans-serif", textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              Account
            </span>
          </div>
          <button
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 28, height: 28, borderRadius: 8, flexShrink: 0,
              background: 'var(--hover-bg)', border: '1px solid var(--card-border)',
              color: 'var(--gold)', cursor: 'pointer',
            }}
          >
            {theme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto h-full w-full" style={{ position: 'relative' }}>
        <Outlet />
      </main>
    </div>
  )
}