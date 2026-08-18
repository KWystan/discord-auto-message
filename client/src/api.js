async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

export const getJobs = () => api('/api/jobs')
export const getManager = () => api('/api/manager')
export const createJob = (job) => api('/api/jobs', { method: 'POST', body: JSON.stringify(job) })
export const updateJob = (id, job) => api(`/api/jobs/${id}`, { method: 'PUT', body: JSON.stringify(job) })
export const deleteJob = (id) => api(`/api/jobs/${id}`, { method: 'DELETE' })
export const sendNow = (id) => api(`/api/jobs/${id}/send-now`, { method: 'POST' })
export const startEngine = () => api('/api/engine/start', { method: 'POST' })
export const stopEngine = () => api('/api/engine/stop', { method: 'POST' })
export const storeManagerEntry = (cat, name, value) =>
  api(`/api/manager/${cat}`, { method: 'POST', body: JSON.stringify({ name, value }) })
export const deleteManagerEntry = (cat, name) => api(`/api/manager/${cat}/${name}`, { method: 'DELETE' })
export const saveHumanizer = (settings) =>
  api('/api/settings/humanizer', { method: 'PUT', body: JSON.stringify(settings) })
export const getServer = () => api('/api/server')
export const getServerChannel = (id) => api(`/api/server/channels/${id}`)

export function fmtSlow(sec) {
  if (!sec) return null
  if (sec % 3600 === 0) return `${sec / 3600} msg/hr`
  if (sec % 60 === 0) return `${sec / 60} min`
  return `${sec}s`
}
