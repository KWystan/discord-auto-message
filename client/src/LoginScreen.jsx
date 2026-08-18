import { useState } from 'react'
import * as api from './api'

function LoginScreen({ onAuthed }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const isLogin = mode === 'login'

  const submit = () => {
    if (!username.trim() || !password) {
      setError('Username and password are required.')
      return
    }
    setBusy(true)
    setError('')
    const p = isLogin
      ? api.login(username.trim(), password)
      : api.register(username.trim(), password)
    p.then(() => onAuthed(username.trim()))
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="login-wrap">
      <div className="panel login-card">
        <div className="login-brand">
          <div>
            <h1 className="login-title">ihelmo auto msg</h1>
            <span className="login-sub">scheduler — control panel</span>
          </div>
        </div>

        <div className="login-mode-row">
          <span className={`login-mode ${isLogin ? 'active' : ''}`} onClick={() => setMode('login')}>
            Sign in
          </span>
          <span className="login-mode-sep">/</span>
          <span className={`login-mode ${!isLogin ? 'active' : ''}`} onClick={() => setMode('register')}>
            Create account
          </span>
        </div>

        <label className="login-field">
          <span className="login-field-label">Username</span>
          <input
            className="login-input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="your username"
            spellCheck={false}
            autoFocus
          />
        </label>

        <label className="login-field">
          <span className="login-field-label">Password</span>
          <span className="login-pw-wrap">
            <input
              className="login-input"
              type={showPw ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
              placeholder="••••••••"
            />
            <button
              type="button"
              className="login-eye"
              title={showPw ? 'Hide password' : 'Show password'}
              onClick={() => setShowPw((s) => !s)}
            >
              {showPw ? '🙈' : '👁'}
            </button>
          </span>
        </label>

        {error && <div className="login-error">{error}</div>}

        <button className="btn primary login-submit" onClick={submit} disabled={busy}>
          {busy ? '…' : isLogin ? 'Sign in' : 'Create account'}
        </button>

        <p className="login-foot">
          Your tokens, jobs and settings are private to this account.
        </p>
      </div>
    </div>
  )
}

export default LoginScreen
