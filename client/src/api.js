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
export const listenerStart = (cfg) => api('/api/listener/start', { method: 'POST', body: JSON.stringify(cfg) })
export const listenerStop = () => api('/api/listener/stop', { method: 'POST' })
export const getData = () => api('/api/data')
export const putData = (data) => api('/api/data', { method: 'PUT', body: JSON.stringify(data) })
