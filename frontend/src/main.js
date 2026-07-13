import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './style.css'
import { initTheme } from './composables/useTheme'
import { initAppStateProxy } from './stores/appState'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

// 必须在 initTheme() 之前调用 —— initTheme 会通过 appState 写入
// theme/themeList/themeInitialized，Proxy 需要 Pinia 已就绪才能路由
initAppStateProxy()

// 在 Vue 挂载前初始化主题，避免页面闪白/闪色
// initTheme 内部直接操作 DOM CSS 变量（同步），所以仍在 mount 之前完成
initTheme()

app.mount('#app')

window.__notifyPywebviewReady = async function notifyPywebviewReady() {
  try {
    if (window.pywebview?.api?.notify_ready) {
      await window.pywebview.api.notify_ready()
    }
  } catch (_error) {
    // 启动时通知失败不影响主界面运行
  }
}
