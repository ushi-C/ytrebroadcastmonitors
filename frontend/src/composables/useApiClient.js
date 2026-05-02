// Mirrors api-client.js as a composable

export function useApiClient() {
  async function refreshScan() {
    return fetch('/api/refresh', { method: 'POST' })
  }

  async function getStatus() {
    const res = await fetch('/api/status')
    return res.json()
  }

  async function checkChannel(query, title) {
    const resp = await fetch('/api/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, title: title || '' }),
    })
    return resp.json()
  }

  async function getChannels() {
    const res = await fetch('/api/channels')
    return res.json()
  }

  return { refreshScan, getStatus, checkChannel, getChannels }
}
