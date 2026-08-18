import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from './api'
import { HARDCODED_CHANNELS } from './channels'
import { fmtIntervalMin } from './intervals'

function fmtSec(sec) {
  sec = Math.round(sec)
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h ${Math.round((sec % 3600) / 60)}m`
  if (sec >= 60) return `${Math.round(sec / 60)}m`
  return `${sec}s`
}

function htmlToMd(html) {
  if (!html || html === '<br>' || html === '<div><br></div>') return ''
  let md = html
  md = md.replace(/<div[^>]*>/gi, '\n')
  md = md.replace(/<\/div>/gi, '')
  md = md.replace(/<p[^>]*>/gi, '\n')
  md = md.replace(/<\/p>/gi, '')
  md = md.replace(/<br\s*\/?>/gi, '\n')
  md = md.replace(/<ul[^>]*>/gi, '\n')
  md = md.replace(/<\/ul>/gi, '\n')
  md = md.replace(/<ol[^>]*>/gi, '\n')
  md = md.replace(/<\/ol>/gi, '\n')
  md = md.replace(/<li[^>]*>(.*?)<\/li>/gi, (_, c) => `- ${c}\n`)
  md = md.replace(/<(b|strong)[^>]*>(.*?)<\/\1>/gi, '**$2**')
  md = md.replace(/<(i|em)[^>]*>(.*?)<\/\1>/gi, '*$2*')
  md = md.replace(/<u[^>]*>(.*?)<\/u>/gi, '__$1__')
  md = md.replace(/<(s|del|strike)[^>]*>(.*?)<\/\1>/gi, '~~$2~~')
  md = md.replace(/<[^>]+>/g, '')
  md = md.replace(/&nbsp;/g, ' ')
  md = md.replace(/&amp;/g, '&')
  md = md.replace(/&lt;/g, '<')
  md = md.replace(/&gt;/g, '>')
  md = md.replace(/&quot;/g, '"')
  md = md.replace(/\n{3,}/g, '\n\n')
  return md.trim()
}

function MessagePanel({ chanId, acc, hasToken, draft, customChannels, onDraftChange, onAdded }) {
  const [server, setServer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const editorRef = useRef(null)
  const mounted = useRef(false)

  useEffect(() => {
    if (!mounted.current && editorRef.current) {
      editorRef.current.innerHTML = draft.html
      mounted.current = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    let alive = true
    setError('')
    if (!acc) return () => { alive = false }
    api
      .getServer(acc)
      .then((d) => {
        if (alive) setServer(d)
      })
      .catch((e) => {
        if (alive && e.message !== 'No account token saved yet.') setError(e.message)
      })
    return () => {
      alive = false
    }
  }, [acc])

  const channels = useMemo(() => {
    const live = new Map()
    for (const c of server?.channels ?? []) {
      if (c && c.id) live.set(String(c.id), c)
    }
    const hardcoded = HARDCODED_CHANNELS.map((hc) => {
      const lv = live.get(hc.id)
      if (!lv) return hc
      const rest = { ...lv }
      delete rest.name
      return { ...hc, ...rest }
    })
    return [...customChannels, ...hardcoded]
  }, [server, customChannels])

  const current = channels.find((c) => String(c.id) === chanId) || null
  const isCustom = Boolean(current && customChannels.some((c) => c.id === String(current.id)))

  useEffect(() => {
    const ch = customChannels.find((c) => c.id === String(current?.id))
    if (ch && ch.intervalSec) {
      const h = Math.floor(ch.intervalSec / 3600)
      const m = Math.floor((ch.intervalSec % 3600) / 60)
      const s = ch.intervalSec % 60
      onDraftChange({ intvH: String(h), intvM: String(m), intvS: String(s) })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id])

  const slowSec = current?.rate_limit_per_user || current?.limit || 0
  const delaySec = (parseFloat(draft.delay) || 0) * 60
  // Custom channels use their exact configured interval (no 60m floor);
  // preset channels keep the 60m minimum.
  const minSec = isCustom
    ? slowSec + delaySec
    : Math.max(3600, slowSec + delaySec)
  const baseSec = isCustom
    ? (parseFloat(draft.intvH) || 0) * 3600 + (parseFloat(draft.intvM) || 0) * 60 + (parseFloat(draft.intvS) || 0)
    : (parseFloat(draft.intv) || 60) * 60

  // Preset options adapt to the channel's limit: start at the slowmode cap
  // (rounded to whole minutes), then 30-min steps up to 6h; a cap above 6h
  // is offered on its own.
  const intervalOptions = useMemo(() => {
    const limitMin = Math.max(60, Math.ceil(slowSec / 60))
    const opts = []
    for (let m = limitMin; m <= 360; m += 30) opts.push(m)
    if (limitMin > 360) opts.push(limitMin)
    return opts.length ? opts : [60]
  }, [slowSec])

  useEffect(() => {
    if (!isCustom && intervalOptions.length && !intervalOptions.includes(parseFloat(draft.intv))) {
      onDraftChange({ intv: String(intervalOptions[0]) })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalOptions.join(',')])

  const exec = (cmd, val) => {
    document.execCommand(cmd, false, val)
    editorRef.current?.focus()
  }

  const add = () => {
    const html = editorRef.current?.innerHTML || ''
    const md = htmlToMd(html)
    if (!md.trim()) {
      setError('Message is required.')
      return
    }
    if (!current) {
      setError('Click a channel on the left panel first.')
      return
    }
    if (!hasToken || !acc) {
      setError("Save an account token above — it's the posting account.")
      return
    }
    const effSec = isCustom
      ? Math.max(baseSec, minSec)
      : Math.ceil(Math.max(baseSec, minSec) / 60) * 60
    setBusy(true)
    setError('')
    setNote('')
    api
      .createJob({
        acc,
        chan: current.name,
        web: 'None',
        channel_id: String(current.id),
        msg: md,
        int: isCustom ? `${Math.round(effSec)}` : `${effSec / 60}`,
        unit: isCustom ? 'Sec' : 'Min',
      })
      .then((res) => {
        if (editorRef.current) editorRef.current.innerHTML = ''
        onDraftChange({ html: '', intv: '60', delay: '0', intvH: '0', intvM: '60', intvS: '0' })
        setNote(
          res.redacted
            ? `Task queued for #${current.name} (via token '${acc}') — sensitive auth content was redacted.`
            : effSec > baseSec
              ? `Task queued for #${current.name} (via token '${acc}') — interval raised to ${fmtSec(effSec)} (channel minimum ${fmtSec(minSec)}).`
              : `Task queued for #${current.name} (via token '${acc}').`,
        )
        onAdded()
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

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
          {isCustom ? (
            <span className="int-input">
              <input className="int-num" value={draft.intvH} onChange={(e) => onDraftChange({ intvH: e.target.value })} />
              <span className="unit-hint">h</span>
              <input className="int-num" value={draft.intvM} onChange={(e) => onDraftChange({ intvM: e.target.value })} />
              <span className="unit-hint">m</span>
              <input className="int-num" value={draft.intvS} onChange={(e) => onDraftChange({ intvS: e.target.value })} />
              <span className="unit-hint">s</span>
            </span>
          ) : (
            <span className="int-input">
              <select value={draft.intv} onChange={(e) => onDraftChange({ intv: e.target.value })}>
                {intervalOptions.map((m) => (
                  <option key={m} value={String(m)}>
                    {fmtIntervalMin(m)}
                  </option>
                ))}
              </select>
            </span>
          )}
        </label>
        <label>
          Delay Buffer (min)
          <span className="int-input">
            <input value={draft.delay} onChange={(e) => onDraftChange({ delay: e.target.value })} />
            <span className="unit-hint">min</span>
          </span>
        </label>
      </div>

      {current && !hasToken && (
        <p className="panel-note">
          #<b>{current.name}</b> can't post yet — save an <b>account token</b> above first.
        </p>
      )}

      {current && minSec > 0 && (
        <p className="panel-note">
          Minimum interval for #<b>{current.name}</b>: {fmtSec(minSec)}
          {slowSec > 0
            ? ` (slowmode ${fmtSec(slowSec)}${parseFloat(draft.delay) > 0 ? ` + ${draft.delay}m delay` : ''})`
            : parseFloat(draft.delay) > 0
              ? ` (60m minimum + ${draft.delay}m delay)`
              : ' (60m minimum)'} —
          the queued interval is never set below this
        </p>
      )}

      <div className="editor-toolbar">
        <button type="button" className="tb" title="Bold" onClick={() => exec('bold')}>
          <b>B</b>
        </button>
        <button type="button" className="tb" title="Italic" onClick={() => exec('italic')}>
          <i>I</i>
        </button>
        <button type="button" className="tb" title="Strikethrough" onClick={() => exec('strikeThrough')}>
          <s>S</s>
        </button>
        <button type="button" className="tb" title="Underline" onClick={() => exec('underline')}>
          <u>U</u>
        </button>
      </div>

      <div
        ref={editorRef}
        className="md-editor"
        contentEditable
        suppressContentEditableWarning
        onInput={() => {
          if (editorRef.current) onDraftChange({ html: editorRef.current.innerHTML })
        }}
      />

      {note && <p className="panel-note ok">{note}</p>}
      {error && <div className="panel-error">{error}</div>}

      <div className="composer-foot">
        <button className="btn primary" onClick={add} disabled={busy || !hasToken || !acc}>
          {busy ? 'Queuing…' : 'Add to Queue'}
        </button>
      </div>
    </section>
  )
}

export default MessagePanel
