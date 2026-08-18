import { useEffect, useRef, useState } from 'react'
import JobEditor from './JobEditor'
import LogViewer from './LogViewer'
import ServerPanel from './ServerPanel'
import MessagePanel from './MessagePanel'
import TokenPanel from './TokenPanel'
import LoginScreen from './LoginScreen'
import * as api from './api'

function fmtNextRun(ts, running) {
  if (!running || !ts) return '—'
  const diff = ts * 1000 - Date.now()
  if (diff <= 0) return 'now'
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

const THEME_ORDER = ['light', 'dark', 'system']
function resolveTheme(pref) {
  if (pref !== 'system') return pref
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const DEFAULT_DRAFT = { chanId: '', html: '', intv: '60', delay: '0', intvH: '0', intvM: '60', intvS: '0' }

function App() {
  const [state, setState] = useState({
    jobs: [],
    engine_running: false,
    humanizer_settings: null,
  })
  const [editor, setEditor] = useState(null)
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme') || 'system' } catch { return 'system' }
  })
  const [tokens, setTokens] = useState({})
  const [activeTab, setActiveTab] = useState('')
  const [focusRequest, setFocusRequest] = useState(0)
  const [newTabOpen, setNewTabOpen] = useState(false)
  const [tabState, setTabState] = useState({})
  const [authUser, setAuthUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const loadedFor = useRef(null)
  const customLoadedFor = useRef(null)
  const [customChannels, setCustomChannels] = useState([])

  // Per-tab state (channel, message, interval, delay) is saved per user so
  // refreshes and re-logins keep every tab's config.
  useEffect(() => {
    if (!authUser) {
      loadedFor.current = null
      customLoadedFor.current = null
      setCustomChannels([])
      return
    }
    try {
      const raw = localStorage.getItem(`tabState-${authUser}`)
      setTabState(raw ? JSON.parse(raw) : {})
    } catch {
      setTabState({})
    }
    loadedFor.current = authUser

    try {
      const raw = localStorage.getItem(`customChannels-${authUser}`)
      setCustomChannels(raw ? JSON.parse(raw) : [])
    } catch {
      setCustomChannels([])
    }
    customLoadedFor.current = authUser
  }, [authUser])

  useEffect(() => {
    if (!authUser || loadedFor.current !== authUser) return
    try { localStorage.setItem(`tabState-${authUser}`, JSON.stringify(tabState)) } catch {}
  }, [tabState, authUser])

  useEffect(() => {
    api
      .authMe()
      .then((r) => setAuthUser(r.user || null))
      .catch(() => setAuthUser(null))
      .finally(() => setAuthLoading(false))
  }, [])

  const afterAuth = (username) => {
    setAuthUser(username)
    refresh()
    loadTokens()
  }

  const onLogout = () => {
    if (!window.confirm(`Log out of '${authUser}'? Your jobs keep running in the background.`)) return
    api.logout().finally(() => {
      setAuthUser(null)
      setTokens({})
      setActiveTab('')
      setTabState({})
      setCustomChannels([])
      setNewTabOpen(false)
    })
  }

  useEffect(() => {
    if (!authUser || customLoadedFor.current !== authUser) return
    try { localStorage.setItem(`customChannels-${authUser}`, JSON.stringify(customChannels)) } catch {}
  }, [customChannels, authUser])

  const addCustomChannel = (url, name, h, m, s) => {
    const parsed = String(url || '').match(/channels\/(\d+)(?:\/(\d+))?/)
    if (!parsed) return 'Invalid request URL — paste a full channel URL like https://discord.com/api/v9/channels/123456789012345678/messages'
    const id = parsed[2] || parsed[1]
    if (customChannels.some((c) => c.id === id)) return 'Channel already added.'
    const intervalSec =
      (parseFloat(h) || 0) * 3600 + (parseFloat(m) || 0) * 60 + (parseFloat(s) || 0)
    setCustomChannels((cs) => [
      ...cs,
      { id, name: name.trim() || `custom-${id}`, intervalSec: intervalSec > 0 ? intervalSec : 3600 },
    ])
    return null
  }

  const removeCustomChannel = (id) => {
    setCustomChannels((cs) => cs.filter((c) => c.id !== id))
  }

  const refresh = () => api.getJobs().then(setState).catch(() => {})

  const loadTokens = () =>
    api
      .getManager()
      .then((m) => {
        const t = m.tokens || {}
        setTokens(t)
        const nicks = Object.keys(t)
        setActiveTab((cur) => (t[cur] ? cur : nicks[0] || ''))
      })
      .catch(() => {})

  useEffect(() => {
    refresh()
    loadTokens()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolveTheme(theme))
    try { localStorage.setItem('theme', theme) } catch {}
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => document.documentElement.setAttribute('data-theme', mq.matches ? 'dark' : 'light')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  const onToggleEngine = () => {
    (state.engine_running ? api.stopEngine() : api.startEngine()).then(refresh).catch(() => {})
  }

  const onSaveJob = (payload, isEdit) => {
    const p = isEdit ? api.updateJob(editor.job.id, payload) : api.createJob(payload)
    return p.then(() => { setEditor(null); refresh(); return true }).catch(() => false)
  }

  const onDelete = (job) => {
    if (window.confirm(`Remove task ${job.id}?`))
      api.deleteJob(job.id).then(refresh).catch(() => {})
  }

  const onSendNow = (job) => api.sendNow(job.id).then(refresh).catch(() => {})

  const onTabDelete = (n) => {
    api
      .deleteManagerEntry('tokens', n)
      .then(() => {
        setTabState((s) => {
          const next = { ...s }
          delete next[n]
          return next
        })
        loadTokens()
      })
      .catch(() => {})
  }

  const patchTab = (patch) => {
    setTabState((s) => ({ ...s, [activeTab]: { ...DEFAULT_DRAFT, ...(s[activeTab] || {}), ...patch } }))
  }

  const onTabAdd = () => {
    setNewTabOpen(true)
    setActiveTab('')
    setFocusRequest((x) => x + 1)
  }

  const onTabSaved = (n) => {
    setNewTabOpen(false)
    setActiveTab(n)
    loadTokens()
  }

  const nextRunTs = state.jobs.length
    ? Math.min(...state.jobs.map((j) => j.next_run || Infinity))
    : null
  const nextLabel = nextRunTs === Infinity ? null : nextRunTs

  const tabNicks = Object.keys(tokens)
  const visibleJobs = activeTab ? state.jobs.filter((j) => j.acc === activeTab) : state.jobs

  if (authLoading) return null
  if (!authUser) {
    return (
      <div className="app">
        <LoginScreen onAuthed={afterAuth} />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1 className="wordmark">ihelmo auto msg</h1>
          <span className="wordmark-sub">scheduler — control panel</span>
        </div>
        <div className="topbar-right">
          <span className="auth-chip" title="Logged in">
            <span className="auth-chip-name">{authUser}</span>
            <button className="auth-logout" onClick={onLogout}>
              <span className="auth-logout-icon">↪</span>
              log out
            </button>
          </span>
          <button className="theme-toggle" onClick={() => setTheme((t) => THEME_ORDER[(THEME_ORDER.indexOf(t) + 1) % THEME_ORDER.length])}>{theme}</button>
        </div>
      </header>

      <section className="engine-bar">
        <button className={`btn ${state.engine_running ? '' : 'primary'}`} onClick={onToggleEngine}>
          {state.engine_running ? 'stop engine' : 'start engine'}
        </button>
        <span className="engine-state">
          {state.engine_running
            ? `running — next in ${fmtNextRun(nextLabel, true)}`
            : `${state.jobs.length} task${state.jobs.length === 1 ? '' : 's'} queued — idle`}
        </span>

        <div className="tab-bar">
          {tabNicks.map((n) => (
            <span key={n} className={`tab ${n === activeTab ? 'active' : ''}`} onClick={() => setActiveTab(n)}>
              {n}
              <button className="tab-close" title={`Remove ${n}`} onClick={(e) => { e.stopPropagation(); onTabDelete(n) }}>✕</button>
            </span>
          ))}
          {newTabOpen && (
            <span className="tab active new-tab" title="New account — save a token below">
              new
              <button className="tab-close" title="Cancel" onClick={() => setNewTabOpen(false)}>✕</button>
            </span>
          )}
          <button className="tab-add" title="Add account token" onClick={onTabAdd}>+</button>
        </div>
      </section>

      <div className="layout-sidebar">
        <aside className="sidebar">
          <ServerPanel
            tokenNick={activeTab}
            customChannels={customChannels}
            onAddCustom={addCustomChannel}
            onRemoveCustom={removeCustomChannel}
            onSelectChannel={(ch) => patchTab({ chanId: String(ch.id) })}
          />
        </aside>
        <main className="main-col">
          <TokenPanel onTokensChange={loadTokens} onTokenSaved={onTabSaved} focusRequest={focusRequest} />

          <MessagePanel
            key={activeTab || 'new'}
            chanId={tabState[activeTab]?.chanId || ''}
            acc={activeTab}
            hasToken={tabNicks.length > 0}
            draft={tabState[activeTab] || DEFAULT_DRAFT}
            customChannels={customChannels}
            onDraftChange={patchTab}
            onAdded={refresh}
          />

          <section className="panel">
            <div className="panel-head">
              <div><h2 className="panel-title">Scheduler</h2></div>
              <span className="panel-hint">{activeTab ? `account: ${activeTab}` : 'no account selected'}</span>
            </div>
            <div className="table-wrap">
              <table className="jobs-table">
                <thead>
                  <tr><th>Channel</th><th>Int</th><th>Unit</th><th>Message</th><th>Next run</th><th>Actions</th></tr>
                </thead>
                <tbody>
                  {visibleJobs.length === 0 && (
                    <tr><td colSpan={6} className="empty">
                      {state.jobs.length > 0
                        ? `No tasks for '${activeTab}' yet.`
                        : 'No tasks — compose a message to add one.'}
                    </td></tr>
                  )}
                  {visibleJobs.map((j) => (
                    <tr key={j.id}>
                      <td>{j.chan}</td>
                      <td className="nums">{j.int}</td>
                      <td>{j.unit}</td>
                      <td className="msg-cell" title={j.msg}>{j.preview}</td>
                      <td className="nums">{fmtNextRun(j.next_run, state.engine_running)}</td>
                      <td className="row-actions">
                        <button onClick={() => setEditor({ job: j })}>edit</button>
                        <button className="send" onClick={() => onSendNow(j)}>send now</button>
                        <button className="danger" onClick={() => onDelete(j)}>remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head"><div><h2 className="panel-title">Live log</h2></div></div>
            <LogViewer />
          </section>
        </main>
      </div>

      {editor && (
        <JobEditor
          job={editor.job}
          channel={editor.channel}
          onSave={onSaveJob}
          onClose={() => setEditor(null)}
        />
      )}
    </div>
  )
}

export default App
