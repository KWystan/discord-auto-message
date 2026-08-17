import { useState } from 'react'

function JobEditor({ job, manager, onSave, onStoreReplacer, onClose }) {
  const isEdit = Boolean(job)
  const [acc, setAcc] = useState(job?.acc ?? '')
  const [chan, setChan] = useState(job?.chan ?? '')
  const [web, setWeb] = useState(job?.web ?? 'None')
  const [msg, setMsg] = useState(job?.msg ?? '')
  const [intv, setIntv] = useState(job?.int ?? '120')
  const [unit, setUnit] = useState(job?.unit ?? 'Min')
  const [mode, setMode] = useState('wait')
  const [error, setError] = useState('')
  const [repMode, setRepMode] = useState('store')
  const [findTxt, setFindTxt] = useState('')
  const [repTxt, setRepTxt] = useState('')
  const [repMsg, setRepMsg] = useState('')

  const tokenNames = Object.keys(manager.tokens)
  const channelNames = Object.keys(manager.channels)
  const webhookNames = ['None', ...Object.keys(manager.webhooks)]

  const insert = (text) => setMsg((m) => m + text)

  const execReplacer = () => {
    if (!findTxt) {
      setRepMsg('Find text is required.')
      return
    }
    if (repMode === 'literal') {
      // Verbatim desktop behavior: literal replace on the message text.
      setMsg((m) => m.replace(findTxt, repTxt))
      setRepMsg(`Executed literal replace: '${findTxt}' -> '${repTxt}'`)
      return
    }
    onStoreReplacer(findTxt, repTxt).then((ok) => {
      setRepMsg(ok ? `Saved replacer: ${findTxt}` : 'Failed to save replacer.')
    })
  }

  const submit = () => {
    if (!acc || !chan || !msg) {
      setError('Ensure Account, Channel, and Message are filled.')
      return
    }
    onSave(
      { acc, chan, web, msg, int: intv, unit, mode },
      isEdit,
    ).then((ok) => {
      if (!ok) setError('Save failed — see message above.')
    })
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{isEdit ? `edit task ${job.id}` : 'add to queue'}</h2>

        <label>
          Account
          <select value={acc} onChange={(e) => setAcc(e.target.value)}>
            <option value="">— select —</option>
            {tokenNames.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        <label>
          Channel
          <select value={chan} onChange={(e) => setChan(e.target.value)}>
            <option value="">— select —</option>
            {channelNames.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        <label>
          Log to Webhook
          <select value={web} onChange={(e) => setWeb(e.target.value)}>
            {webhookNames.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

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

        <div className="replacer-strip">
          <span className="replacer-label">Replacer</span>
          <label className="radio-inline">
            <input type="radio" checked={repMode === 'store'} onChange={() => setRepMode('store')} />
            Store Rule
          </label>
          <label className="radio-inline">
            <input type="radio" checked={repMode === 'literal'} onChange={() => setRepMode('literal')} />
            Literal Replace
          </label>
          <input className="replacer-find" placeholder="Find" value={findTxt} onChange={(e) => setFindTxt(e.target.value)} />
          <input className="replacer-rep" placeholder="Replace with" value={repTxt} onChange={(e) => setRepTxt(e.target.value)} />
          <button type="button" className="replacer-exec" onClick={execReplacer}>Execute Replacer</button>
          {repMsg && <span className="replacer-msg">{repMsg}</span>}
        </div>

        <div className="interval-row">
          <label>
            Base Interval
            <span className="int-input">
              <input
                type="text"
                value={intv}
                onChange={(e) => setIntv(e.target.value)}
              />
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                <option value="Sec">Sec</option>
                <option value="Min">Min</option>
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
