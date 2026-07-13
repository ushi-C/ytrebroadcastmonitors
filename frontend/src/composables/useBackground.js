/**
 * useBackground.js
 * ─────────────────
 * 背景图片/视频持久化 composable。
 *
 * 存储策略（双轨，优先后端）：
 *   1. 后端 API（pywebview 环境）：
 *        PUT /api/background   上传（multipart/form-data）
 *        GET /api/background   获取背景元信息（返回 static URL）
 *        DELETE /api/background  清除
 *      背景文件通过 /static/ 流式加载（HTTP Range 支持）
 *   2. IndexedDB（浏览器 / 降级）：存完整 base64 作为兜底
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

/** 上传文件到后端（multipart/form-data），返回 static URL */
async function backendSave(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch('/api/background', {
    method: 'PUT',
    body: formData,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || `backend save failed: ${res.status}`)
  }
  const json = await res.json()
  return json.url  // e.g. "/static/user_background.jpg"
}

/** 从后端读取背景，返回 static URL 或 null */
async function backendLoad() {
  const res = await fetch('/api/background')
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`backend load failed: ${res.status}`)
  const json = await res.json()
  return json.url || null
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
        const staticUrl = await backendLoad()
        if (staticUrl) {
          appState.userBackgroundUrl = staticUrl
          return
        }
      }

      // 降级：IndexedDB
      const dataUrl = await idbGet(IDB_KEY)
      if (dataUrl) {
        appState.userBackgroundUrl = dataUrl
        // 如果后端可用，迁移到后端（data URL → blob → file → upload）
        if (await isBackendAvailable()) {
          try {
            const resp = await fetch(dataUrl)
            const blob = await resp.blob()
            const file = new File([blob], 'background.jpg', { type: blob.type || 'image/jpeg' })
            const staticUrl = await backendSave(file)
            appState.userBackgroundUrl = staticUrl
            await idbDelete(IDB_KEY)
          } catch {
            // 迁移失败保留 IDB 兜底
          }
        }
      }
    } catch (err) {
      console.warn('[useBackground] restoreBackground failed:', err)
    }
  }

  /**
   * 处理文件选择事件，保存背景。
   * @param {File} file  - 用户选择的图片/视频文件
   * @returns {Promise<boolean>} 是否成功
   */
  async function saveBackground(file) {
    if (!file) return false
    saving.value = true
    error.value = ''

    try {
      // 先更新界面（立即生效：用 data URL / blob URL 预览）
      const previewUrl = await fileToDataUrl(file)
      appState.userBackgroundUrl = previewUrl

      // 持久化
      if (await isBackendAvailable()) {
        const staticUrl = await backendSave(file)
        // 上传成功后切换为持久化静态 URL（支持 HTTP Range 流式加载）
        appState.userBackgroundUrl = staticUrl
      } else {
        await idbSet(IDB_KEY, previewUrl)
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
