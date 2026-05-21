import { ref } from 'vue'
import { useApiClient } from './useApiClient.js'

const CACHE_MS = 10 * 60 * 1000
const PROBE_TIMEOUT_MS = 10_000
const PLAY_STABLE_MS = 3_000
const TEST_VIDEO_ID = 'M7lc1UVf-VE'

export function useNetworkProbe() {
  const { getNetworkStatus, reportNetworkStatus, requestNetworkCheck } = useApiClient()
  const isChecking = ref(false)
  const networkState = ref({ youtube_available: false, reason: 'UNTESTED', last_check: 0 })

  let timeoutId = null
  let stablePlayId = null
  let player = null
  let containerEl = null

  function cleanup() {
    if (timeoutId) clearTimeout(timeoutId)
    if (stablePlayId) clearTimeout(stablePlayId)
    timeoutId = null
    stablePlayId = null
    if (player && typeof player.destroy === 'function') player.destroy()
    player = null
    if (containerEl && containerEl.parentNode) containerEl.parentNode.removeChild(containerEl)
    containerEl = null
  }

  function inferReasonByBodyText() {
    const txt = (document.body?.innerText || '').toLowerCase()
    if (txt.includes("confirm you're not a bot") || txt.includes('not a bot') || txt.includes('sign in')) return 'BOT_DETECTED'
    if (txt.includes('video unavailable')) return 'VIDEO_UNAVAILABLE'
    if (txt.includes('an error occurred')) return 'PLAYER_ERROR_TEXT'
    return 'TIMEOUT'
  }

  async function loadStatus() {
    networkState.value = await getNetworkStatus()
    return networkState.value
  }

  function ensureApiReady() {
    return new Promise((resolve, reject) => {
      if (window.YT && window.YT.Player) return resolve(window.YT)
      const old = window.onYouTubeIframeAPIReady
      window.onYouTubeIframeAPIReady = () => {
        if (typeof old === 'function') old()
        resolve(window.YT)
      }
      const tag = document.createElement('script')
      tag.src = 'https://www.youtube.com/iframe_api'
      tag.onerror = () => reject(new Error('IFRAME_API_LOAD_FAILED'))
      document.head.appendChild(tag)
    })
  }

  async function runProbe(force = false) {
    if (isChecking.value) return networkState.value
    const curr = await loadStatus()
    if (!force && curr.last_check && Date.now() - curr.last_check * 1000 < CACHE_MS) return curr

    isChecking.value = true
    await requestNetworkCheck()

    const finalize = async (available, reason) => {
      cleanup()
      const latest = await reportNetworkStatus({ youtube_available: available, reason })
      networkState.value = latest
      isChecking.value = false
      return latest
    }

    try {
      await ensureApiReady()
      containerEl = document.createElement('div')
      containerEl.id = 'yt-network-probe'
      containerEl.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;'
      document.body.appendChild(containerEl)

      return await new Promise((resolve) => {
        let enteredPlaying = false
        timeoutId = setTimeout(async () => {
          resolve(await finalize(false, inferReasonByBodyText()))
        }, PROBE_TIMEOUT_MS)

        player = new window.YT.Player('yt-network-probe', {
          width: '1',
          height: '1',
          videoId: TEST_VIDEO_ID,
          playerVars: {
            autoplay: 1, controls: 0, mute: 1, playsinline: 1, rel: 0, modestbranding: 1, enablejsapi: 1,
          },
          events: {
            onReady: (ev) => { try { ev.target.playVideo() } catch (_) {} },
            onError: async () => resolve(await finalize(false, 'PLAYER_ERROR')),
            onStateChange: async (ev) => {
              const ps = window.YT.PlayerState
              if (ev.data === ps.BUFFERING && enteredPlaying) {
                if (!stablePlayId) resolve(await finalize(false, 'BUFFERING_STALL'))
                return
              }
              if (ev.data === ps.PLAYING) {
                enteredPlaying = true
                if (stablePlayId) clearTimeout(stablePlayId)
                stablePlayId = setTimeout(async () => resolve(await finalize(true, 'PLAYABLE')), PLAY_STABLE_MS)
              }
            },
          },
        })
      })
    } catch (_) {
      return finalize(false, 'IFRAME_API_LOAD_FAILED')
    }
  }

  return { isChecking, networkState, loadStatus, runProbe }
}
