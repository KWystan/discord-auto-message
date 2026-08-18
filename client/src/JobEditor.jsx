import { useState } from 'react'
import { fmtSlow } from './api'
import { INTERVAL_OPTIONS, fmtIntervalMin } from './intervals'

function JobEditor({ job, channel, onSave, onClose }) {
  const isEdit = Boolean(job)
  const chanName = job?.chan ?? channel?.name ?? ''
  const slow = channel?.rate_limit_per_user
  const [msg, setMsg] = useState(job?.msg ?? '')
  const [intv, setIntv] = useState(job?.int ?? '60')
  const [mode, setMode] = useState('wait')
  const [error, setError] = useState('')

  const insert = (text) => setMsg((m) => m + text)

  const submit = () => {
    if (!msg.trim()) {
      setError('Message is required.')
      return
    }
    const baseSec = (parseFloat(intv) || 60) * 60
    const effSec = Math.ceil(Math.max(baseSec, 3600) / 60) * 60
    if (effSec > baseSec) setError(`Interval raised to ${effSec / 60} min (60m minimum).`)
    onSave(
      {
        acc: job?.acc ?? 'webhook',
        chan: chanName,
        web: job?.web ?? 'None',
        msg,
        int: `${effSec / 60}`,
        unit: 'Min',
        mode,
      },
      isEdit,
      channel,
    ).then((ok) => {
      if (!ok) setError('Save failed — see message above.')
    })
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{isEdit ? `edit task ${job.id}` : `auto message → #${chanName}`}</h2>

        <div className="editor-context">
          <span className="editor-context-label">Channel</span>
          <span className="editor-context-value">#{chanName}</span>
          {slow != null && slow > 0 && (
            <span className="editor-context-slow">
              channel slowmode: {fmtSlow(slow)} — sends are spaced to respect it
            </span>
          )}
        </div>

        <label>
          Message <span className="hint">(separate pools with ---)</span>
          <textarea
            rows={7}
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            placeholder="Message text…"
          />
        </label>

        <div className="quick-tools">
          Quick tools:
          <button type="button" onClick={() => insert('{time}')}>{'{time}'}</button>
          <button type="button" onClick={() => insert('{min}')}>{'{min}'}</button>
          <button type="button" onClick={() => insert('\n---\n')}>+ '---' (Separator)</button>
        </div>

        <div className="interval-row">
          <label>
            Base Interval
            <span className="int-input">
              <select value={intv} onChange={(e) => setIntv(e.target.value)}>
                {INTERVAL_OPTIONS.map((m) => (
                  <option key={m} value={String(m)}>
                    {fmtIntervalMin(m)}
                  </option>
                ))}
              </select>
            </span>
          </label>

          {isEdit && (
            <label>
              On Update
              <span className="radio-row">
                <label><input type="radio" checked={mode === 'now'} onChange={() => setMode('now')} /> Send Now</label>
                <label><input type="radio" checked={mode === 'wait'} onChange={() => setMode('wait')} /> Continue Count</label>
              </span>
            </label>
          )}
        </div>

        {error && <div className="modal-error">{error}</div>}

        <div className="modal-actions">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={submit}>
            {isEdit ? 'Update Task' : 'Add to Queue'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default JobEditor