import { useEffect, useRef, useState } from 'react'
import * as api from './api'

function ListenerPanel({ listening, settings, tokens, jobs, onChanged, num = '01' }) {
  const [token, setToken] = useState('')
  const [chanId, setChanId] = useState('')
  const [teacherId, setTeacherId] = useState('')
  const [targetJobId, setTargetJobId] = useState('')
  const [slashInput, setSlashInput] = useState('')
  const [slashChan, setSlashChan] = useState('')
  const [sorting, setSorting] = useState('Interval')
  const [error, setError] = useState('')
  const synced = useRef(false)

  useEffect(() => {
    if (synced.current || !settings) return
    synced.current = true
    setToken(settings.token ?? '')
    setChanId(settings.channel_id ?? '')
    setTeacherId(settings.teacher_id ?? '')
    setTargetJobId(settings.target_job_id ?? '')
    setSlashInput(settings.slash_input ?? '')
    setSlashChan(settings.slash_channel ?? '')
    setSorting(settings.slash_sorting ?? 'Interval')
  }, [settings])

  const toggle = () => {
    setError('')
    if (listening) {
      api.listenerStop().then(onChanged).catch((e) => setError(e.message))
      return
    }
    api
      .listenerStart({
        token,
        channel_id: chanId,
        teacher_id: teacherId,
        target_job_id: targetJobId,
        slash_input: slashInput,
        slash_channel: slashChan,
        slash_sorting: sorting,
      })
      .then(onChanged)
      .catch((e) => setError(e.message))
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="section-label">{num} — auto-grab</div>
          <h2 className="panel-title">Auto-Grab Listener</h2>
        </div>
        <span className="panel-hint">players / multiple accounts</span>
      </div>

      <div className="form-row">
        <label>
          Listener's Token
          <select value={token} onChange={(e) => setToken(e.target.value)}>
            <option value="">— select —</option>
            {tokens.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <label>
          Channel/DM ID
          <input value={chanId} onChange={(e) => setChanId(e.target.value)} />
        </label>
        <label>
          Sender Whitelist (Optional)
          <input value={teacherId} onChange={(e) => setTeacherId(e.target.value)} placeholder="comma-separated IDs" />
        </label>
        <label>
          Default Target Task
          <select value={targetJobId} onChange={(e) => setTargetJobId(e.target.value)}>
            <option value="">— select —</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>{j.acc} -&gt; {j.chan} ({j.id})</option>
            ))}
          </select>
        </label>
      </div>

      <div className="form-row slash-row">
        <span className="slash-tag">/search</span>
        <input value={slashInput} onChange={(e) => setSlashInput(e.target.value)} placeholder="input" />
        <span className="slash-tag slash-tag--red">accessible</span>
        <input value={slashChan} onChange={(e) => setSlashChan(e.target.value)} placeholder="channel" />
        <span className="slash-tag slash-tag--amber">sorting</span>
        <select value={sorting} onChange={(e) => setSorting(e.target.value)}>
          <option value="Interval">Interval</option>
          <option value="Message">Message</option>
        </select>
        <button className={`btn ${listening ? '' : 'primary'}`} onClick={toggle}>
          {listening ? '■ deactivate listener' : '▶ activate listener'}
        </button>
      </div>

      {error && <div className="panel-error">{error}</div>}
    </section>
  )
}

export default ListenerPanel
