/**
 * useWebSocket.js
 * ───────────────
 * WebSocket 长连接 composable，支持自动断线重连和心跳保活。
 *
 * 用于替代前端 HTTP 轮询，接收后端主动推送的状态更新。
 *
 * 用法：
 *   const { wsConnected, connect, disconnect, send } = useWebSocket({
 *     onMessage: (msg) => { ... },
 *     onStatusChange: (connected) => { ... },
 *   })
 *   connect()
 */

import { ref } from 'vue'

const RECONNECT_BASE_DELAY = 1000   // 初始重连延迟
const RECONNECT_MAX_DELAY = 15000   // 最大重连延迟
const HEARTBEAT_INTERVAL = 25000    // 心跳间隔

export function useWebSocket(options = {}) {
  const { onMessage, onStatusChange } = options

  const wsConnected = ref(false)
  let ws = null
  let reconnectTimer = null
  let heartbeatTimer = null
  let reconnectAttempts = 0
  let manuallyClosed = false

  function _buildUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}/api/ws/status`
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    manuallyClosed = false
    const url = _buildUrl()

    try {
      ws = new WebSocket(url)
    } catch (e) {
      console.error('[ws] create failed:', e)
      _scheduleReconnect()
      return
    }

    ws.onopen = () => {
      wsConnected.value = true
      reconnectAttempts = 0
      onStatusChange?.(true)
      _startHeartbeat()
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        onMessage?.(msg)
      } catch (e) {
        // 非 JSON 消息（如 pong），忽略
      }
    }

    ws.onclose = () => {
      wsConnected.value = false
      onStatusChange?.(false)
      _stopHeartbeat()
      if (!manuallyClosed) {
        _scheduleReconnect()
      }
    }

    ws.onerror = () => {
      // 不在此处重连，由 onclose 统一处理
    }
  }

  function disconnect() {
    manuallyClosed = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    _stopHeartbeat()
    if (ws) {
      ws.onclose = null
      ws.onerror = null
      try {
        ws.close()
      } catch (_) { /* ws may already be closed */ }
      ws = null
    }
    wsConnected.value = false
  }

  function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }

  function _scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    // 指数退避 + 随机抖动
    const delay = Math.min(
      RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts),
      RECONNECT_MAX_DELAY
    ) + Math.random() * 500
    reconnectAttempts++
    reconnectTimer = setTimeout(() => connect(), delay)
  }

  function _startHeartbeat() {
    _stopHeartbeat()
    heartbeatTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, HEARTBEAT_INTERVAL)
  }

  function _stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  return { wsConnected, connect, disconnect, send }
}
