import { useEffect, useRef, useState } from 'react'
import * as api from './api'

function HumanizerPanel({ settings, onSaved, num = '03' }) {
  const [typing, setTyping] = useState(true)
  const [minHrs, setMinHrs] = useState('1.0')
  const [maxHrs, setMaxHrs] = useState('3.0')
  const [sleep, setSleep] = useState(false)
  const [error, setError] = useState('')
  const synced = useRef(false)

  // Sync once when settings first arrive (never clobber in-progress edits).
  useEffect(() => {
    if (synced.current || !settings) return
    synced.current = true
    setTyping(settings.simulate_typing ?? true)
    setMinHrs(String(settings.cooldown_buffer_min_hrs ?? 1.0))
    setMaxHrs(String(settings.cooldown_buffer_max_hrs ?? 3.0))
    setSleep(settings.sleep_hours_enabled ?? false)
  }, [settings])

  const save = () => {
    api
      .saveHumanizer({
        simulate_typing: typing,
        cooldown_buffer_min_hrs: minHrs,
        cooldown_buffer_max_hrs: maxHrs,
        sleep_hours_enabled: sleep,
      })
      .then((res) => {
        setError('')
        setMinHrs(String(res.humanizer_settings.cooldown_buffer_min_hrs))
        setMaxHrs(String(res.humanizer_settings.cooldown_buffer_max_hrs))
        onSaved()
      })
      .catch((e) => setError(e.message))
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="section-label">{num} — humanizer</div>
          <h2 className="panel-title">Random Gap Settings</h2>
        </div>
        <span className="panel-hint">past cooldown</span>
      </div>

      <div className="form-row">
        <label className="check-label">
          <input type="checkbox" checked={typing} onChange={(e) => setTyping(e.target.checked)} />
          Simulate 'is typing...'
        </label>
        <label>
          Extra Random Gap Past Timeout
          <span className="int-input">
            <input value={minHrs} onChange={(e) => setMinHrs(e.target.value)} />
            <span className="unit-hint">to</span>
            <input value={maxHrs} onChange={(e) => setMaxHrs(e.target.value)} />
            <span className="unit-hint">hours extra</span>
          </span>
        </label>
        <label className="check-label">
          <input type="checkbox" checked={sleep} onChange={(e) => setSleep(e.target.checked)} />
          Sleep (1AM-8AM)
        </label>
      </div>

      {error && <div className="panel-error">{error}</div>}

      <div className="panel-foot">
        <button className="btn primary" onClick={save}>Save Settings</button>
      </div>
    </section>
  )
}

export default HumanizerPanel
