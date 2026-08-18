import { useEffect, useMemo, useState } from 'react'
import { fmtSlow } from './api'
import * as api from './api'
import { HARDCODED_CHANNELS } from './channels'
import { channelIcon } from './intervals'

const TYPE_GLYPH = { 0: '#', 2: '🔊', 5: '📢', 13: '🎙', 15: '🧵', 16: '🖼' }

// Server icon shown when no scan credential is saved; a live scan overrides it.
const GUILD_ICON_URL =
  'https://cdn.discordapp.com/icons/571992648190263317/a_9febb694fea75e1039aeefeed4aacca9.gif?size=256'

function fmtCount(n) {
  if (n == null) return null
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

function ServerPanel({ tokenNick, customChannels, onAddCustom, onRemoveCustom, onSelectChannel }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [name, setName] = useState('')
  const [intvH, setIntvH] = useState('0')
  const [intvM, setIntvM] = useState('60')
  const [intvS, setIntvS] = useState('0')
  const [customErr, setCustomErr] = useState('')

  useEffect(() => {
    let alive = true
    setError('')
    api
      .getServer(tokenNick)
      .then((d) => {
        if (alive) setData(d)
      })
      .catch((e) => {
        if (alive && e.message !== 'No account token saved yet.') setError(e.message)
      })
    return () => {
      alive = false
    }
  }, [tokenNick])

  const channels = useMemo(() => {
    const live = new Map()
    for (const c of data?.channels ?? []) {
      if (c && c.id) live.set(String(c.id), c)
    }
    const hardcoded = HARDCODED_CHANNELS.map((hc) => {
      const lv = live.get(hc.id)
      if (!lv) return hc
      const rest = { ...lv }
      rest.icon = channelIcon(rest.name) || hc.icon
      delete rest.name
      return { ...hc, ...rest }
    })
    const custom = customChannels.map((c) => {
      const lv = live.get(String(c.id))
      if (!lv) return { ...c, icon: '📍' }
      const rest = { ...lv }
      rest.icon = channelIcon(rest.name) || '📍'
      delete rest.name
      return { ...c, ...rest }
    })
    return [...custom, ...hardcoded]
  }, [data, customChannels])

  const rowLimit = (ch) =>
    ch.rate_limit_per_user || ch.limit || (customChannels.some((c) => c.id === ch.id) ? ch.intervalSec : 0)

  const openModal = () => {
    setUrl('')
    setName('')
    setIntvH('0')
    setIntvM('60')
    setIntvS('0')
    setCustomErr('')
    setModalOpen(true)
  }

  const submitCustom = () => {
    const err = onAddCustom(url, name, intvH, intvM, intvS)
    if (err) {
      setCustomErr(err)
      return
    }
    setModalOpen(false)
  }

  const guild = data?.guild
  const serverName = guild?.name || 'ihelmo'
  const iconUrl = guild?.icon_url || GUILD_ICON_URL

  return (
    <>
      <section className="panel">
        <div className="server-head">
          <img className="server-icon" src={iconUrl} alt="" />
          <div className="server-head-meta">
            <span className="server-name">{serverName}</span>
            {guild?.member_count != null && (
              <span className="server-sub">
                {fmtCount(guild.member_count)} members · {fmtCount(guild.presence_count)} online
              </span>
            )}
          </div>
        </div>

        <button className="btn custom-channel-add" onClick={openModal}>＋ add custom channel</button>

        <div className="server-groups">
          <div className="server-group">
          {channels.map((ch) => (
            <ChannelRow
              key={ch.id}
              ch={ch}
              limit={rowLimit(ch)}
              onSelectChannel={onSelectChannel}
              onRemove={customChannels.some((c) => c.id === ch.id) ? () => onRemoveCustom(ch.id) : undefined}
            />
          ))}
          </div>
        </div>

        {error && <div className="panel-error">{error}</div>}
      </section>

      {modalOpen && (
        <div className="modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add custom channel</h2>

            <div className="form-row">
              <label>
                Request URL
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://discord.com/api/v9/channels/1234567890/messages"
                  spellCheck={false}
                />
              </label>
            </div>

            <div className="form-row">
              <label>
                Name <span className="unit-hint">(optional)</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="custom-1234567890"
                  spellCheck={false}
                />
              </label>
            </div>

            <div className="form-row">
              <label>
                Base Interval
                <span className="int-input">
                  <input className="int-num" value={intvH} onChange={(e) => setIntvH(e.target.value)} />
                  <span className="unit-hint">h</span>
                  <input className="int-num" value={intvM} onChange={(e) => setIntvM(e.target.value)} />
                  <span className="unit-hint">m</span>
                  <input className="int-num" value={intvS} onChange={(e) => setIntvS(e.target.value)} />
                  <span className="unit-hint">s</span>
                </span>
              </label>
            </div>

            {customErr && <div className="modal-error">{customErr}</div>}

            <div className="modal-actions">
              <button className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
              <button className="btn primary" onClick={submitCustom}>Add</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function ChannelRow({ ch, limit, onSelectChannel, onRemove }) {
  return (
    <button className="server-channel" onClick={() => onSelectChannel(ch)}>
      <span className="server-channel-glyph">{ch.icon || (TYPE_GLYPH[ch.type] ?? '#')}</span>
      <span className="server-channel-name">{ch.name}</span>
      {limit > 0 && (
        <span className="server-channel-slow">{fmtSlow(limit)}</span>
      )}
      {onRemove && (
        <span
          className="server-channel-remove"
          title="Remove custom channel"
          onClick={(e) => { e.stopPropagation(); onRemove() }}
        >
          ✕
        </span>
      )}
    </button>
  )
}

export default ServerPanel
