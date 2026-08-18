import { useEffect, useRef, useState } from 'react'
import * as api from './api'

function TokenPanel({ onTokensChange, onTokenSaved, focusRequest }) {
  const [tokens, setTokens] = useState({})
  const [nick, setNick] = useState('main')
  const [token, setToken] = useState('')
  const [editing, setEditing] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const nickRef = useRef(null)
  const tokenRef = useRef(null)

  useEffect(() => {
    if (focusRequest > 0) {
      setEditing(true)
      setToken('')
      nickRef.current?.focus()
    }
  }, [focusRequest])

  const load = () => {
    api.getManager().then((m) => {
      setTokens(m.tokens || {})
      onTokensChange?.()
    }).catch(() => {})
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        setEditing(false)
        setNote(`Token saved as '${n}'.`)
        load()
        onTokenSaved?.(n)
      })
      .catch((e) => setError(e.message))
  }

  const onSaveClick = () => {
    if (!editing && tokens[nick]) {
      setEditing(true)
      setToken('')
      tokenRef.current?.focus()
      return
    }
    save()
  }

  const hasToken = Boolean(tokens[nick])

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Account token</h2>
        </div>
        <span className="panel-hint" title="Posts as this account (self-bot — ban risk)">legacy posting</span>
      </div>

      <div className="token-form">
        <input
          ref={nickRef}
          className="token-nick"
          value={nick}
          onChange={(e) => { setNick(e.target.value); setEditing(false) }}
          placeholder="nickname"
          spellCheck={false}
        />
        <input
          ref={tokenRef}
          className="token-val"
          type={editing ? 'password' : 'text'}
          value={editing ? token : (tokens[nick] || '')}
          onChange={(e) => setToken(e.target.value)}
          onFocus={() => {
            if (!editing) {
              setEditing(true)
              setToken('')
            }
          }}
          placeholder={hasToken ? '••••••••••••••••' : 'token'}
          spellCheck={false}
        />
        <button className="btn primary token-save" onClick={onSaveClick}>
          {hasToken ? 'Update' : 'Save'}
        </button>
      </div>

      {note && <p className="panel-note ok">{note}</p>}
      {error && <div className="panel-error">{error}</div>}
    </section>
  )
}

export default TokenPanel
