import { useState } from 'react'
import * as api from './api'

const TYPE_CAT = { Token: 'tokens', Channel: 'channels', Webhook: 'webhooks', Replacer: 'replacers' }

function ManagerPanel({ manager, onChanged, onEditJson, num = '02' }) {
  const [nick, setNick] = useState('')
  const [value, setValue] = useState('')
  const [error, setError] = useState('')

  const rows = [
    ...Object.entries(manager.tokens).map(([n, v]) => ['Token', n, v]),
    ...Object.entries(manager.channels).map(([n, v]) => ['Channel', n, v]),
    ...Object.entries(manager.webhooks).map(([n, v]) => ['Webhook', n, v]),
    ...Object.entries(manager.replacers).map(([n, v]) => ['Replacer', n, v]),
  ]

  const save = (type) => {
    if (!nick || !value) {
      setError('Nick / Find and Value / Replace With are required.')
      return
    }
    api
      .storeManagerEntry(TYPE_CAT[type], nick, value)
      .then(() => {
        setNick('')
        setValue('')
        setError('')
        onChanged()
      })
      .catch((e) => setError(e.message))
  }

  const remove = (type, name) => {
    api
      .deleteManagerEntry(TYPE_CAT[type], name)
      .then(onChanged)
      .catch((e) => setError(e.message))
  }

  const load = (type, name) => {
    if (type === 'Token' || type === 'Webhook') {
      setError(
        'Token/Webhook values are masked in the web app and cannot be loaded back into the field — ' +
          'use Manual Edit (JSON) or type the value again.',
      )
      return
    }
    setNick(name)
    setValue(manager[TYPE_CAT[type]][name])
    setError('')
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="section-label">{num} — accounts</div>
          <h2 className="panel-title">Manager</h2>
        </div>
        <span className="panel-hint">tokens · channels · webhooks · replacers</span>
      </div>

      <div className="form-row">
        <label>
          Nick / Find
          <input value={nick} onChange={(e) => setNick(e.target.value)} />
        </label>
        <label>
          Value / Replace With
          <input value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <div className="btn-row">
          <button className="btn" onClick={() => save('Token')}>Save Token</button>
          <button className="btn" onClick={() => save('Channel')}>Save Channel</button>
          <button className="btn" onClick={() => save('Webhook')}>Save Webhook</button>
          <button className="btn" onClick={() => save('Replacer')}>Execute Replacer</button>
          <button className="btn ghost" onClick={onEditJson}>Manual Edit (JSON)</button>
        </div>
      </div>

      {error && <div className="panel-error">{error}</div>}

      <div className="table-wrap">
        <table className="jobs-table manager-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Nickname / Target</th>
              <th>Value / Replacement</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="empty">No entries saved yet.</td>
              </tr>
            )}
            {rows.map(([type, n, v]) => (
              <tr key={type + n}>
                <td>{type}</td>
                <td>{n}</td>
                <td className="msg-cell" title={v}>{v}</td>
                <td className="row-actions">
                  <button onClick={() => load(type, n)}>load</button>
                  <button className="danger" onClick={() => remove(type, n)}>remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default ManagerPanel
