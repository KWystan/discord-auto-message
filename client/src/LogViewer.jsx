import { useEffect, useRef, useState } from 'react'

function LogViewer() {
  const [lines, setLines] = useState([])
  const [connected, setConnected] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    const es = new EventSource('/api/logs/stream')
    es.onopen = () => setConnected(true)
    es.onmessage = (e) => {
      try {
        const { line } = JSON.parse(e.data)
        setLines((prev) => [...prev.slice(-499), line])
      } catch {}
    }
    es.onerror = () => setConnected(false)
    return () => es.close()
  }, [])

  useEffect(() => {
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines])

  return (
    <div className="log-viewer-wrap">
      <div className={`log-status ${connected ? 'on' : 'off'}`}>
        {connected ? '● live' : '○ disconnected — retrying…'}
      </div>
      <div className="log-box" ref={boxRef}>
        {lines.length === 0 && <span className="log-empty">No log lines yet.</span>}
        {lines.map((l, i) => (
          <div key={i}>{l}</div>
        ))}
      </div>
    </div>
  )
}

export default LogViewer
