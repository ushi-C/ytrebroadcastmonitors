/**
 * useBackground.js
 * ─────────────────
 * 背景图片持久化 composable。
 *
 * 存储策略（双轨，优先后端）：
 *   1. 后端 API（pywebview 环境）：PUT /api/background  存图片文件
 *                                   GET /api/background  取图片（返回 base64 JSON）
 *                                   DELETE /api/background  清除
 *   2. IndexedDB（浏览器 / 降级）：存完整 base64，无 5 MB 限制
 *
 * localStorage 仅存一个标志位 'yv_bg_source'（'backend' | 'idb'），
 * 用来在启动时决定从哪里恢复，不存图片本体。
 */

import { ref } from 'vue'
import { appState } from '../stores/appState'

// ── IndexedDB helpers ──────────────────────────────────────────────────────

const IDB_NAME = 'yv-store'
const IDB_STORE = 'kv'
const IDB_KEY = 'user_background'

function openIdb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1)
    req.onupgradeneeded = (e) => {
      e.target.result.createObjectStore(IDB_STORE)
    }
    req.onsuccess = (e) => resolve(e.target.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbGet(key) {
  const db = await openIdb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readonly')
    const req = tx.objectStore(IDB_STORE).get(key)
    req.onsuccess = () => resolve(req.result ?? null)
    req.onerror = () => reject(req.error)
  })
}

async function idbSet(key, value) {
  const db = await openIdb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite')
    tx.objectStore(IDB_STORE).put(value, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function idbDelete(key) {
  const db = await openIdb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite')
    tx.objectStore(IDB_STORE).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

// ── Backend API helpers ────────────────────────────────────────────────────

/**
 * 判断是否在 pywebview 环境（有后端 API 可用）。
 * 用 /api/status 响应来判断，避免 import 循环。
 */
let _backendAvailable = null
async function isBackendAvailable() {
  if (_backendAvailable !== null) return _backendAvailable
  try {
    const res = await fetch('/api/status', { method: 'GET' })
    _backendAvailable = res.ok
  } catch {
    _backendAvailable = false
  }
  return _backendAvailable
}

/** 上传图片到后端，接受 base64 data URL */
async function backendSave(dataUrl) {
  const res = await fetch('/api/background', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: dataUrl }),
  })
  if (!res.ok) throw new Error(`backend save failed: ${res.status}`)
}

/** 从后端读取背景，返回 base64 data URL 或 null */
async function backendLoad() {
  const res = await fetch('/api/background')
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`backend load failed: ${res.status}`)
  const json = await res.json()
  return json.data || null
}

/** 清除后端背景 */
async function backendDelete() {
  await fetch('/api/background', { method: 'DELETE' })
}

// ── Composable ─────────────────────────────────────────────────────────────

export function useBackground() {
  const saving = ref(false)
  const error = ref('')

  /**
   * 从持久化存储恢复背景（在 onMounted 中调用）。
   */
  async function restoreBackground() {
    try {
      // 优先尝试后端
      if (await isBackendAvailable()) {
        const dataUrl = await backendLoad()
        if (dataUrl) {
          appState.userBackgroundUrl = dataUrl
          return
        }
      }

      // 降级：IndexedDB
      const dataUrl = await idbGet(IDB_KEY)
      if (dataUrl) {
        appState.userBackgroundUrl = dataUrl
        // 如果后端可用，补传到后端（迁移旧数据）
        if (await isBackendAvailable()) {
          await backendSave(dataUrl)
          await idbDelete(IDB_KEY)
        }
      }
    } catch (err) {
      console.warn('[useBackground] restoreBackground failed:', err)
    }
  }

  /**
   * 处理文件选择事件，保存背景。
   * @param {File} file  - 用户选择的图片文件
   * @returns {Promise<boolean>} 是否成功
   */
  async function saveBackground(file) {
    if (!file) return false
    saving.value = true
    error.value = ''

    try {
      const dataUrl = await fileToDataUrl(file)

      // 先更新界面（立即生效）
      appState.userBackgroundUrl = dataUrl

      // 持久化
      if (await isBackendAvailable()) {
        await backendSave(dataUrl)
      } else {
        await idbSet(IDB_KEY, dataUrl)
      }

      return true
    } catch (err) {
      console.error('[useBackground] saveBackground failed:', err)
      error.value = '背景保存失败，请重试'
      return false
    } finally {
      saving.value = false
    }
  }

  /**
   * 清除背景。
   */
  async function clearBackground() {
    appState.userBackgroundUrl = ''
    try {
      if (await isBackendAvailable()) {
        await backendDelete()
      }
      await idbDelete(IDB_KEY)
    } catch (err) {
      console.warn('[useBackground] clearBackground failed:', err)
    }
  }

  return { saving, error, restoreBackground, saveBackground, clearBackground }
}

// ── Util ───────────────────────────────────────────────────────────────────

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(/** @type {string} */ (reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}
