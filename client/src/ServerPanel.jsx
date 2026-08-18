import { useEffect, useMemo, useState } from 'react'
import { fmtSlow } from './api'
import * as api from './api'
import { HARDCODED_CHANNELS } from './channels'
import { channelIcon } from './intervals'

const TYPE_GLYPH = { 0: '#', 2: '🔊', 5: '📢', 13: '🎙', 15: '🧵', 16: '🖼' }

function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
}

function fmtCount(n) {
  if (n == null) return null
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

function ServerPanel({ onSelectChannel }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setError('')
    api
      .getServer()
      .then((d) => {
        if (alive) setData(d)
      })
      .catch((e) => {
        if (alive && e.message !== 'Not logged in.') setError(e.message)
      })
    return () => {
      alive = false
    }
  }, [])

  const channels = useMemo(() => {
    const live = new Map()
    for (const c of data?.channels ?? []) {
      if (c && c.id) live.set(String(c.id), c)
    }
    return HARDCODED_CHANNELS.map((hc) => {
      const lv = live.get(hc.id)
      if (!lv) return hc
      const rest = { ...lv }
      rest.icon = channelIcon(rest.name)
      delete rest.name
      return { ...hc, ...rest }
    })
  }, [data])

  const guild = data?.guild
  const serverName = guild?.name || 'ihelmo'

  return (
    <section className="panel">
      <div className="server-head">
        {guild?.icon_url ? (
          <img className="server-icon" src={guild.icon_url} alt="" />
        ) : (
          <span className="server-icon server-icon-fallback">{initials(serverName)}</span>
        )}
        <div className="server-head-meta">
          <span className="server-name">{serverName}</span>
          {guild?.member_count != null && (
            <span className="server-sub">
              {fmtCount(guild.member_count)} members · {fmtCount(guild.presence_count)} online
            </span>
          )}
        </div>
      </div>

      <div className="server-groups">
        <div className="server-group">
          {channels.map((ch) => (
            <ChannelRow
              key={ch.id}
              ch={ch}
              onSelectChannel={onSelectChannel}
            />
          ))}
        </div>
      </div>

      {error && <div className="panel-error">{error}</div>}
    </section>
  )
}

function ChannelRow({ ch, onSelectChannel }) {
  return (
    <button className="server-channel" onClick={() => onSelectChannel(ch)}>
      <span className="server-channel-glyph">{ch.icon || (TYPE_GLYPH[ch.type] ?? '#')}</span>
      <span className="server-channel-name">{ch.name}</span>
      {ch.rate_limit_per_user > 0 && (
        <span className="server-channel-slow">{fmtSlow(ch.rate_limit_per_user)}</span>
      )}
    </button>
  )
}

export default ServerPanel
