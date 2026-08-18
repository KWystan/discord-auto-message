import { useEffect, useState } from 'react'
import JobEditor from './JobEditor'
import LogViewer from './LogViewer'
import ServerPanel from './ServerPanel'
import MessagePanel from './MessagePanel'
import TokenPanel from './TokenPanel'
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

function App() {
  const [state, setState] = useState({
    jobs: [],
    engine_running: false,
    humanizer_settings: null,
  })
  const [editor, setEditor] = useState(null)
  const [selectedChanId, setSelectedChanId] = useState('')
  const [toast, setToast] = useState('')
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme') || 'system' } catch { return 'system' }
  })

  const refresh = () => api.getJobs().then(setState).catch(() => {})

  useEffect(() => {
    refresh()
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

  const flash = (msg) => { setToast(msg); setTimeout(() => setToast(''), 5000) }

  const onToggleEngine = () => {
    (state.engine_running ? api.stopEngine() : api.startEngine()).then(refresh).catch((e) => flash(e.message))
  }

  const onSaveJob = (payload, isEdit) => {
    const p = isEdit ? api.updateJob(editor.job.id, payload) : api.createJob(payload)
    return p.then(() => { setEditor(null); refresh(); return true }).catch((e) => { flash(e.message); return false })
  }

  const onDelete = (job) => {
    if (window.confirm(`Remove task ${job.id}?`))
      api.deleteJob(job.id).then(refresh).catch((e) => flash(e.message))
  }

  const onSendNow = (job) => api.sendNow(job.id).then(refresh).catch((e) => flash(e.message))

  const nextRunTs = state.jobs.length
    ? Math.min(...state.jobs.map((j) => j.next_run || Infinity))
    : null
  const nextLabel = nextRunTs === Infinity ? null : nextRunTs

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1 className="wordmark">ihelmo auto msg</h1>
          <span className="wordmark-sub">scheduler — control panel</span>
        </div>
        <div className="topbar-right">
          <button className="theme-toggle" onClick={() => setTheme((t) => THEME_ORDER[(THEME_ORDER.indexOf(t) + 1) % THEME_ORDER.length])}>{theme}</button>
        </div>
      </header>

      {toast && <div className="toast">{toast}</div>}

      <section className="engine-bar">
        <button className={`btn ${state.engine_running ? '' : 'primary'}`} onClick={onToggleEngine}>
          {state.engine_running ? 'stop engine' : 'start engine'}
        </button>
        <span className="engine-state">
          {state.engine_running
            ? `running — next in ${fmtNextRun(nextLabel, true)}`
            : `${state.jobs.length} task${state.jobs.length === 1 ? '' : 's'} queued — idle`}
        </span>
      </section>

      <div className="layout-sidebar">
        <aside className="sidebar">
          <ServerPanel onSelectChannel={(ch) => setSelectedChanId(String(ch.id))} />
          <TokenPanel />
        </aside>
        <main className="main-col">
          <MessagePanel chanId={selectedChanId} onAdded={refresh} />

          <section className="panel">
            <div className="panel-head">
              <div><h2 className="panel-title">Scheduler</h2></div>
              <span className="panel-hint">variants via '---'</span>
            </div>
            <div className="table-wrap">
              <table className="jobs-table">
                <thead>
                  <tr><th>Channel</th><th>Int</th><th>Unit</th><th>Message</th><th>Next run</th><th>Actions</th></tr>
                </thead>
                <tbody>
                  {state.jobs.length === 0 && (
                    <tr><td colSpan={6} className="empty">No tasks — click a channel to add one.</td></tr>
                  )}
                  {state.jobs.map((j) => (
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