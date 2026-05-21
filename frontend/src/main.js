import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import { initTheme } from './composables/useTheme'

// 在 Vue 挂载前初始化主题，避免页面闪白/闪色
initTheme()

createApp(App).mount('#app')

window.__notifyPywebviewReady = async function notifyPywebviewReady() {
  try {
    if (window.pywebview?.api?.notify_ready) {
      await window.pywebview.api.notify_ready()
    }
  } catch (_error) {
    // 启动时通知失败不影响主界面运行
  }
}
