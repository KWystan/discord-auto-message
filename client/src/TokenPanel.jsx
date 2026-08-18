import { useEffect, useState } from 'react'
import * as api from './api'

function TokenPanel() {
  const [tokens, setTokens] = useState({})
  const [nick, setNick] = useState('main')
  const [token, setToken] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  const load = () => {
    api.getManager().then((m) => setTokens(m.tokens || {})).catch(() => {})
  }

  useEffect(() => {
    load()
  }, [])

  const save = () => {
    const n = nick.trim()
    const t = token.trim()
    if (!n || !t) {
      setError('Nickname and token are required.')
      return
    }
    setError('')
    setNote('')
    api
      .storeManagerEntry('tokens', n, t)
      .then(() => {
        setToken('')
        setNote(`Token saved as '${n}' — channels without a webhook now post through it.`)
        load()
      })
      .catch((e) => setError(e.message))
  }

  const remove = (n) => {
    api
      .deleteManagerEntry('tokens', n)
      .then(() => {
        setNote(`Removed token '${n}'.`)
        load()
      })
      .catch((e) => setError(e.message))
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Account token</h2>
        </div>
        <span className="panel-hint">legacy posting</span>
      </div>

      <p className="panel-note">
        Used for channels without a webhook. Posts as this account (self-bot — ban risk, same as the legacy
        desktop app).
      </p>

      <div className="form-row">
        <label>
          Nickname
          <input value={nick} onChange={(e) => setNick(e.target.value)} spellCheck={false} />
        </label>
        <label>
          Token
          <input value={token} onChange={(e) => setToken(e.target.value)} type="password" spellCheck={false} />
        </label>
      </div>

      {Object.keys(tokens).length > 0 && (
        <div className="token-list">
          {Object.keys(tokens).map((n) => (
            <span key={n} className="token-chip">
              {n}
              <button className="token-chip-x" onClick={() => remove(n)}>✕</button>
            </span>
          ))}
        </div>
      )}

      {note && <p className="panel-note ok">{note}</p>}
      {error && <div className="panel-error">{error}</div>}

      <div className="composer-foot">
        <button className="btn primary" onClick={save}>Save Token</button>
      </div>
    </section>
  )
}

export default TokenPanel
