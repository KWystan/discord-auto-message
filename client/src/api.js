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
export const authMe = () => api('/api/auth/me')
export const login = (username, password) =>
  api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
export const register = (username, password) =>
  api('/api/auth/register', { method: 'POST', body: JSON.stringify({ username, password }) })
export const logout = () => api('/api/auth/logout', { method: 'POST' })
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
export const getServer = (tokenNick) =>
  api('/api/server' + (tokenNick ? `?token=${encodeURIComponent(tokenNick)}` : ''))
export const getServerChannel = (id) => api(`/api/server/channels/${id}`)

export function fmtSlow(sec) {
  if (!sec) return null
  if (sec % 3600 === 0) {
    const h = sec / 3600
    return `${h} hr${h === 1 ? '' : 's'} / msg`
  }
  if (sec % 60 === 0) {
    const m = sec / 60
    return `${m} min / msg`
  }
  return `${sec} sec / msg`
}
