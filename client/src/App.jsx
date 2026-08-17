import { useEffect, useState } from 'react'
import JobEditor from './JobEditor'
import LogViewer from './LogViewer'
import ManagerPanel from './ManagerPanel'
import HumanizerPanel from './HumanizerPanel'
import ListenerPanel from './ListenerPanel'
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
    listening: false,
    next_runs: {},
    humanizer_settings: null,
    listener_settings: null,
  })
  const [manager, setManager] = useState({ tokens: {}, channels: {}, webhooks: {}, replacers: {} })
  const [editor, setEditor] = useState(null) // { job: null|job } when open
  const [jsonModal, setJsonModal] = useState(null) // { text, error } when open
  const [toast, setToast] = useState('')
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('theme') || 'system'
    } catch {
      return 'system'
    }
  })
  const [tab, setTab] = useState(() => {
    try {
      return localStorage.getItem('tab') || 'message'
    } catch {
      return 'message'
    }
  })

  const refresh = () => api.getJobs().then(setState).catch(() => {})
  const loadManager = () => api.getManager().then(setManager).catch(() => {})

  useEffect(() => {
    refresh()
    loadManager()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolveTheme(theme))
    try {
      localStorage.setItem('theme', theme)
    } catch {}
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () =>
      document.documentElement.setAttribute('data-theme', mq.matches ? 'dark' : 'light')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  const cycleTheme = () =>
    setTheme((t) => THEME_ORDER[(THEME_ORDER.indexOf(t) + 1) % THEME_ORDER.length])

  useEffect(() => {
    try {
      localStorage.setItem('tab', tab)
    } catch {}
  }, [tab])

  const flash = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(''), 5000)
  }

  const onToggleEngine = () => {
    const p = state.engine_running ? api.stopEngine() : api.startEngine()
    p.then(refresh).catch((e) => flash(e.message))
  }

  const onSaveJob = (payload, isEdit) => {
    const p = isEdit ? api.updateJob(editor.job.id, payload) : api.createJob(payload)
    return p
      .then((res) => {
        if (res.redacted) {
          flash('⚠️ Sensitive Discord authorization detected in message — replaced with a placeholder.')
        }
        setEditor(null)
        refresh()
        return true
      })
      .catch((e) => {
        flash(e.message)
        return false
      })
  }

  const onStoreReplacer = (findTxt, repTxt) => {
    return api
      .storeManagerEntry('replacers', findTxt, repTxt)
      .then(() => {
        loadManager()
        return true
      })
      .catch(() => false)
  }

  const onDelete = (job) => {
    if (window.confirm(`Remove task ${job.id} (${job.acc} -> ${job.chan})?`)) {
      api.deleteJob(job.id).then(refresh).catch((e) => flash(e.message))
    }
  }

  const onSendNow = (job) => {
    api.sendNow(job.id).then(refresh).catch((e) => flash(e.message))
  }

  const openJsonEdit = () => {
    api
      .getData()
      .then((data) => setJsonModal({ text: JSON.stringify(data, null, 2), error: '' }))
      .catch((e) => flash(e.message))
  }

  const saveJsonEdit = () => {
    let parsed
    try {
      parsed = JSON.parse(jsonModal.text)
    } catch (e) {
      setJsonModal((m) => ({ ...m, error: `Invalid JSON: ${e.message}` }))
      return
    }
    api
      .putData(parsed)
      .then(() => {
        setJsonModal(null)
        refresh()
        loadManager()
        flash('app_data.json updated — engine reloaded from new data.')
      })
      .catch((e) => setJsonModal((m) => ({ ...m, error: e.message })))
  }

  const nextRunTs = state.jobs.length
    ? Math.min(...state.jobs.map((j) => j.next_run || Infinity))
    : null
  const nextRunLabel = nextRunTs === Infinity ? null : nextRunTs

  const listenerTarget = (() => {
    const tid = state.listener_settings?.target_job_id
    if (!tid) return '—'
    const j = state.jobs.find((x) => x.id === tid)
    return j ? `${j.acc} → ${j.chan}` : tid
  })()

  return (
    <div className="app">
      <header className="topbar">
        <div className="fade-up">
          <h1 className="wordmark">discord auto msg</h1>
          <span className="wordmark-sub">scheduler — control panel</span>
        </div>
        <div className="topbar-right fade-up">
          <span className="micro-label">theme</span>
          <button className="theme-toggle" onClick={cycleTheme} title="Cycle theme">
            {theme}
          </button>
        </div>
      </header>

      <nav className="tabs fade-up" role="tablist" aria-label="Views">
        <button
          className={`tab ${tab === 'message' ? 'active' : ''}`}
          role="tab"
          aria-selected={tab === 'message'}
          onClick={() => setTab('message')}
        >
          auto message
        </button>
        <button
          className={`tab ${tab === 'grab' ? 'active' : ''}`}
          role="tab"
          aria-selected={tab === 'grab'}
          onClick={() => setTab('grab')}
        >
          auto-grab
        </button>
      </nav>

      {toast && <div className="toast">{toast}</div>}

      <div className="bento">
        {tab === 'message' ? (
          <>
            <section className="stats" aria-label="System status">
              <div className="stat">
                <span className="stat-label">Engine</span>
                <span className="stat-value nums">
                  <span className={`dot ${state.engine_running ? 'live' : ''}`} aria-hidden="true" />
                  {state.engine_running ? 'running' : 'stopped'}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Tasks</span>
                <span className="stat-value nums">{state.jobs.length} queued</span>
              </div>
              <div className="stat">
                <span className="stat-label">Listener</span>
                <span className="stat-value nums">
                  <span className={`dot ${state.listening ? 'live' : ''}`} aria-hidden="true" />
                  {state.listening ? 'active' : 'idle'}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Next run</span>
                <span className="stat-value nums">{fmtNextRun(nextRunLabel, state.engine_running)}</span>
              </div>
            </section>

            <section className="engine-bar">
              <button className={`btn ${state.engine_running ? '' : 'primary'}`} onClick={onToggleEngine}>
                {state.engine_running ? '■ stop engine' : '▶ start engine'}
              </button>
              <span className="engine-state">
                {state.engine_running ? '1–3h random gap active' : 'idle — nothing is being sent'}
              </span>
              <button className="btn primary" onClick={() => setEditor({ job: null })}>
                + add to queue
              </button>
              <button className="btn ghost" onClick={openJsonEdit}>
                manual edit (json)
              </button>
            </section>

            <div className="span-2">
              <ManagerPanel
                manager={manager}
                onChanged={loadManager}
                onEditJson={openJsonEdit}
                num="01"
              />
            </div>

            <div className="span-2">
              <HumanizerPanel settings={state.humanizer_settings} onSaved={refresh} num="02" />
            </div>

            <section className="panel span-4">
              <div className="panel-head">
                <div>
                  <div className="section-label">03 — scheduler</div>
                  <h2 className="panel-title">Message Scheduler</h2>
                </div>
                <span className="panel-hint">variants via '---'</span>
              </div>
              <div className="table-wrap">
                <table className="jobs-table">
                  <thead>
                    <tr>
                      <th>Acc</th>
                      <th>Chan</th>
                      <th>Int</th>
                      <th>Unit</th>
                      <th>Message</th>
                      <th>Webhook</th>
                      <th>Next run</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.jobs.length === 0 && (
                      <tr>
                        <td colSpan={8} className="empty">No tasks in queue — add one above.</td>
                      </tr>
                    )}
                    {state.jobs.map((j) => (
                      <tr key={j.id}>
                        <td>{j.acc}</td>
                        <td>{j.chan}</td>
                        <td className="nums">{j.int}</td>
                        <td>{j.unit}</td>
                        <td className="msg-cell" title={j.msg}>{j.preview}</td>
                        <td>{j.web}</td>
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

            <section className="panel span-4">
              <div className="panel-head">
                <div>
                  <div className="section-label">04 — live log</div>
                  <h2 className="panel-title">Live Log</h2>
                </div>
              </div>
              <LogViewer />
            </section>
          </>
        ) : (
          <>
            <section className="stats" aria-label="Auto-grab status">
              <div className="stat">
                <span className="stat-label">Listener</span>
                <span className="stat-value nums">
                  <span className={`dot ${state.listening ? 'live' : ''}`} aria-hidden="true" />
                  {state.listening ? 'active' : 'idle'}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Channel</span>
                <span className="stat-value nums">{state.listener_settings?.channel_id || '—'}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Target</span>
                <span className="stat-value nums">{listenerTarget}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Sorting</span>
                <span className="stat-value nums">{state.listener_settings?.slash_sorting || 'Interval'}</span>
              </div>
            </section>

            <div className="span-4">
              <ListenerPanel
                listening={state.listening}
                settings={state.listener_settings}
                tokens={Object.keys(manager.tokens)}
                jobs={state.jobs}
                onChanged={refresh}
              />
            </div>

            <section className="panel span-4">
              <div className="panel-head">
                <div>
                  <div className="section-label">02 — live log</div>
                  <h2 className="panel-title">Live Log</h2>
                </div>
              </div>
              <LogViewer />
            </section>
          </>
        )}
      </div>

      {editor && (
        <JobEditor
          job={editor.job}
          manager={manager}
          onSave={onSaveJob}
          onStoreReplacer={onStoreReplacer}
          onClose={() => setEditor(null)}
        />
      )}

      {jsonModal && (
        <div className="modal-backdrop" onClick={() => setJsonModal(null)}>
          <div className="modal json-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Manual Edit — app_data.json</h2>
            <p className="json-warning">
              Raw data, including stored tokens, is shown here. It is written to the same
              app_data.json the desktop app uses — do not run both apps at once.
            </p>
            <textarea
              className="json-editor"
              rows={18}
              spellCheck={false}
              value={jsonModal.text}
              onChange={(e) => setJsonModal((m) => ({ ...m, text: e.target.value }))}
            />
            {jsonModal.error && <div className="modal-error">{jsonModal.error}</div>}
            <div className="modal-actions">
              <button className="btn ghost" onClick={() => setJsonModal(null)}>cancel</button>
              <button className="btn primary" onClick={saveJsonEdit}>save json</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
