import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from './api'
import { HARDCODED_CHANNELS } from './channels'
import { INTERVAL_OPTIONS, fmtIntervalMin } from './intervals'

function variantCount(msg) {
  const parts = msg
    .split(/\n?\s*(?:---|===)\s*\n?/)
    .map((p) => p.trim())
    .filter(Boolean)
  return Math.max(1, parts.length)
}

function fmtSec(sec) {
  sec = Math.round(sec)
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h ${Math.round((sec % 3600) / 60)}m`
  if (sec >= 60) return `${Math.round(sec / 60)}m`
  return `${sec}s`
}

function MessagePanel({ chanId, onAdded }) {
  const [server, setServer] = useState(null)
  const [manager, setManager] = useState(null)
  const [msg, setMsg] = useState('')
  const [intv, setIntv] = useState('60')
  const [delay, setDelay] = useState('0')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const taRef = useRef(null)

  useEffect(() => {
    let alive = true
    setError('')
    api
      .getServer()
      .then((d) => {
        if (alive) setServer(d)
      })
      .catch((e) => {
        if (alive && e.message !== 'No account token saved yet.') setError(e.message)
      })
    api
      .getManager()
      .then((m) => {
        if (alive) setManager(m)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  const channels = useMemo(() => {
    const live = new Map()
    for (const c of server?.channels ?? []) {
      if (c && c.id) live.set(String(c.id), c)
    }
    return HARDCODED_CHANNELS.map((hc) => {
      const lv = live.get(hc.id)
      if (!lv) return hc
      const rest = { ...lv }
      delete rest.name
      return { ...hc, ...rest }
    })
  }, [server])

  const current = channels.find((c) => String(c.id) === chanId) || null
  const tokenNicks = Object.keys(manager?.tokens ?? {})

  const slowSec = current?.rate_limit_per_user || 0
  const delaySec = (parseFloat(delay) || 0) * 60
  const minSec = Math.max(3600, slowSec + delaySec)
  const baseSec = (parseFloat(intv) || 60) * 60

  const insert = (text) => {
    setMsg((m) => m + text)
    const ta = taRef.current
    if (ta) {
      const pos = ta.value.length + text.length
      requestAnimationFrame(() => {
        ta.focus()
        ta.setSelectionRange(pos, pos)
      })
    }
  }

  const wrap = (before, after) => {
    const ta = taRef.current
    if (!ta) return
    const start = ta.selectionStart ?? ta.value.length
    const end = ta.selectionEnd ?? ta.value.length
    const selected = ta.value.slice(start, end)
    const next = ta.value.slice(0, start) + before + selected + after + ta.value.slice(end)
    setMsg(next)
    requestAnimationFrame(() => {
      ta.focus()
      const selStart = start + before.length
      ta.setSelectionRange(selStart, selStart + selected.length)
    })
  }

  const toggleHeading = (marker) => {
    const ta = taRef.current
    if (!ta) return
    const pos = ta.selectionStart ?? ta.value.length
    const lineStart = ta.value.lastIndexOf('\n', pos - 1) + 1
    const line = ta.value.slice(lineStart)
    const has = line.startsWith(marker)
    const stripped = line.replace(/^#{1,3}\s/, '')
    const next = has
      ? ta.value.slice(0, lineStart) + line.slice(marker.length) + ta.value.slice(lineStart + line.length)
      : ta.value.slice(0, lineStart) + marker + stripped
    setMsg(next)
    requestAnimationFrame(() => {
      ta.focus()
      const caret = lineStart + (has ? 0 : marker.length)
      ta.setSelectionRange(caret, caret)
    })
  }

  const stripHeading = () => {
    const ta = taRef.current
    if (!ta) return
    const pos = ta.selectionStart ?? ta.value.length
    const lineStart = ta.value.lastIndexOf('\n', pos - 1) + 1
    const line = ta.value.slice(lineStart)
    const m = line.match(/^#{1,3}\s/)
    if (!m) return
    setMsg(
      ta.value.slice(0, lineStart) + line.slice(m[0].length) + ta.value.slice(lineStart + line.length),
    )
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(lineStart, lineStart)
    })
  }

  const setSize = (size) => {
    if (size === 'normal') stripHeading()
    else if (size === 'h1') toggleHeading('# ')
    else if (size === 'h2') toggleHeading('## ')
    else if (size === 'h3') toggleHeading('### ')
  }

  const add = () => {
    if (!msg.trim()) {
      setError('Message is required.')
      return
    }
    if (!current) {
      setError('Click a channel on the left panel first.')
      return
    }
    if (tokenNicks.length === 0) {
      setError("Save an account token in the sidebar — it's the posting account.")
      return
    }
    const effSec = Math.ceil(Math.max(baseSec, minSec) / 60) * 60
    setBusy(true)
    setError('')
    setNote('')
    api
      .createJob({
        acc: tokenNicks[0],
        chan: current.name,
        web: 'None',
        channel_id: String(current.id),
        msg: msg.trim(),
        int: `${effSec / 60}`,
        unit: 'Min',
      })
      .then((res) => {
        setMsg('')
        setNote(
          res.redacted
            ? `Task queued for #${current.name} (via token '${tokenNicks[0]}') — sensitive auth content was redacted.`
            : effSec > baseSec
              ? `Task queued for #${current.name} (via token '${tokenNicks[0]}') — interval raised to ${fmtSec(effSec)} (channel minimum ${fmtSec(minSec)}).`
              : `Task queued for #${current.name} (via token '${tokenNicks[0]}').`,
        )
        onAdded()
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const variants = variantCount(msg)

  return (
    <section className="panel composer-panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Compose message</h2>
        </div>
        <span className="panel-hint">adds a new task to the scheduler</span>
      </div>

      <div className="form-row">
        <label>
          Channel
          <span className="composer-channel">
            {current ? (
              <span className="composer-channel-name">#{current.name}</span>
            ) : (
              <span className="unit-hint">click a channel on the left panel</span>
            )}
          </span>
        </label>
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
        <label>
          Delay Buffer (min)
          <span className="int-input">
            <input value={delay} onChange={(e) => setDelay(e.target.value)} />
            <span className="unit-hint">min</span>
          </span>
        </label>
      </div>

      {current && tokenNicks.length === 0 && (
        <p className="panel-note">
          #<b>{current.name}</b> can't post yet — save an <b>account token</b> in the sidebar first.
        </p>
      )}

      {current && minSec > 0 && (
        <p className="panel-note">
          Minimum interval for #<b>{current.name}</b>: {fmtSec(minSec)}
          {slowSec > 0
            ? ` (slowmode ${fmtSec(slowSec)}${parseFloat(delay) > 0 ? ` + ${delay}m delay` : ''})`
            : parseFloat(delay) > 0
              ? ` (60m minimum + ${delay}m delay)`
              : ' (60m minimum)'} —
          the queued interval is never set below this
        </p>
      )}

      <label className="composer-msg-label">
        Message <span className="unit-hint">(separate pools with ---)</span>
        <textarea
          ref={taRef}
          className="composer-textarea"
          rows={6}
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Message text…"
        />
      </label>

      <div className="format-bar">
        <button type="button" className="fmt fmt-bold" title="Bold" onClick={() => wrap('**', '**')}>B</button>
        <button type="button" className="fmt fmt-italic" title="Italic" onClick={() => wrap('*', '*')}>I</button>
        <button type="button" className="fmt fmt-underline" title="Underline" onClick={() => wrap('__', '__')}>U</button>
        <button type="button" className="fmt" title="Strikethrough" onClick={() => wrap('~~', '~~')}>S</button>
        <select className="fmt-size" value="" onChange={(e) => setSize(e.target.value)}>
          <option value="" disabled>Size</option>
          <option value="normal">Normal</option>
          <option value="h1">H1 — large</option>
          <option value="h2">H2 — medium</option>
          <option value="h3">H3 — small</option>
        </select>
        <span className="format-sep" />
        <button type="button" className="fmt" onClick={() => insert('{time}')}>{'{time}'}</button>
        <button type="button" className="fmt" onClick={() => insert('{min}')}>{'{min}'}</button>
        <button type="button" className="fmt" onClick={() => insert('{date}')}>{'{date}'}</button>
        <button type="button" className="fmt" onClick={() => insert('\n---\n')}>+ '---' (Separator)</button>
        {variants > 1 && (
          <span className="unit-hint">[{variants} Variants] — one picked per send</span>
        )}
      </div>

      {note && <p className="panel-note ok">{note}</p>}
      {error && <div className="panel-error">{error}</div>}

      <div className="composer-foot">
        <button className="btn primary" onClick={add} disabled={busy || tokenNicks.length === 0}>
          {busy ? 'Queuing…' : 'Add to Queue'}
        </button>
      </div>
    </section>
  )
}

export default MessagePanel
