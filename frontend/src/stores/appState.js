/**
 * appState.js — 向后兼容代理（A2 重构产物，已修复）
 * ─────────────────────────────────────────────────────────
 *
 * 旧的 appState 是一个巨大的 Vue reactive({...}) 对象。
 * 现已按功能域拆分到 Pinia store 中。
 *
 * 本文件通过 reactive(Proxy) 保持旧 API 签名完全不变：
 * - appState.theme           → useThemeStore().theme
 * - appState.userBackgroundUrl → useBackgroundStore().userBackgroundUrl
 * - appState.csvChannels     → useSearchStore().csvChannels
 * - ...以此类推
 *
 * 【兼容性保证】
 * 1. 所有旧代码 `import { appState } from '../stores/appState'` 无需修改
 * 2. Proxy 使用 reactive() 包裹，Vue 模板中的 {{ appState.xxx }} 仍然响应式
 * 3. set 操作被路由到 Pinia store 的 ref 上，触发正确的响应式更新
 * 4. 若某个时刻 Pinia 尚未初始化（模块加载期），返回 undefined 不崩溃
 *
 * 【修复记录 2026-07-12】
 * - 将 require() (CJS) 替换为静态 ESM import — 修复 ReferenceError
 * - 移除 3 个完全未使用的 store: usePlayerStore / useToastStore / useScaleStore
 *   (PlayerView.vue 管理自己的本地 ref; App.vue 同理)
 * - initAppStateProxy 不再需要 pinia 参数，Pinia 激活后 useStore() 自动解析
 *
 * ═══════════════════════════════════════════════════════
 * 初始化约定：
 * main.js 必须在 app.use(createPinia()) 之后调用
 * initAppStateProxy() 来标记 Pinia 已就绪。
 * initTheme() 必须在 initAppStateProxy() 之后调用。
 * ═══════════════════════════════════════════════════════
 */

import { reactive } from 'vue'

// ── Store 引入（静态 ESM import，避免循环依赖）─────────
import { useThemeStore } from './useThemeStore'
import { useBackgroundStore } from './useBackgroundStore'
import { useScanStore } from './useScanStore'
import { useSearchStore } from './useSearchStore'

// ── 就绪标志 ──────────────────────────────────────────
let _initialized = false

/**
 * 由 main.js 在 Pinia 安装完成后调用。
 * 标记 Pinia 已就绪，后续 useStore() 调用将自动解析到活跃实例。
 */
export function initAppStateProxy() {
  _initialized = true
}

/**
 * 字段 → Store 路由映射表。
 *
 * 每个条目定义了一个旧 appState 字段应该路由到哪个 store 的哪个 key。
 * 格式：{ store: 'theme', key: 'theme' }
 */
const FIELD_ROUTES = {
  // ── Scan Store ──
  scanRenderedKeys:  { store: 'scan', key: 'scanRenderedKeys' },
  searchRenderedKeys:{ store: 'scan', key: 'searchRenderedKeys' },

  // ── Theme Store ──
  theme:            { store: 'theme', key: 'theme' },
  themeList:        { store: 'theme', key: 'themeList' },
  themeInitialized: { store: 'theme', key: 'themeInitialized' },

  // ── Background Store ──
  userBackgroundUrl: { store: 'background', key: 'userBackgroundUrl' },

  // ── Search Store ──
  csvChannels: { store: 'search', key: 'csvChannels' },
  fuse:        { store: 'search', key: 'fuse' },
  checkCache:  { store: 'search', key: 'checkCache' },
  checking:    { store: 'search', key: 'checking' },
}

/**
 * 根据路由配置获取对应的 Pinia store 实例。
 */
function _getStore(route) {
  if (!_initialized) return null
  switch (route.store) {
    case 'scan':       return useScanStore()
    case 'theme':      return useThemeStore()
    case 'background': return useBackgroundStore()
    case 'search':     return useSearchStore()
    default:           return null
  }
}

/**
 * ═══════════════════════════════════════════════════════
 * 向后兼容 Proxy — 对外 API 完全等价于旧的 appState
 * ═══════════════════════════════════════════════════════
 *
 * 隔离层原理：
 * - get: 拦截所有属性读取，按 FIELD_ROUTES 路由到对应 Pinia store
 * - set: 拦截所有属性写入，路由到 Pinia store 的 ref 值
 *
 * 被 reactive() 包裹后，Vue 模板中的访问会被正确追踪，
 * 当通过 appState.xxx = value 写入时，Vue 响应式代理触发更新。
 */
export const appState = reactive(new Proxy({}, {
  get(_target, prop) {
    // 处理 Symbol / 内部属性（Vue 响应式系统会访问这些）
    if (typeof prop === 'symbol') return undefined

    const route = FIELD_ROUTES[prop]
    if (!route) {
      if (prop !== '__v_isRef' && prop !== '__v_raw' &&
          prop !== '__v_isReactive' && prop !== '__v_skip') {
        console.warn(
          `[appState Proxy] 未路由的字段访问: "${String(prop)}"`,
          '请添加到 FIELD_ROUTES 中'
        )
      }
      return undefined
    }

    const store = _getStore(route)
    if (!store) return undefined

    return store[route.key]
  },

  set(_target, prop, value) {
    if (typeof prop === 'symbol') return true

    const route = FIELD_ROUTES[prop]
    if (!route) {
      console.warn(
        `[appState Proxy] 未路由的字段写入: "${String(prop)}" =`,
        value,
        '请添加到 FIELD_ROUTES 中'
      )
      return true
    }

    const store = _getStore(route)
    if (!store) return true

    store[route.key] = value
    return true
  },

  // Vue 响应式系统需要能枚举到所有 key
  ownKeys(_target) {
    return Object.keys(FIELD_ROUTES)
  },

  getOwnPropertyDescriptor(_target, prop) {
    if (typeof prop === 'symbol') return undefined
    const route = FIELD_ROUTES[prop]
    if (!route) return undefined
    return {
      enumerable: true,
      configurable: true,
    }
  },

  has(_target, prop) {
    if (typeof prop === 'symbol') return false
    return prop in FIELD_ROUTES
  },
}))
