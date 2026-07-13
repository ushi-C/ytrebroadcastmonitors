import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useScanStore = defineStore('scan', () => {
  // 仅保留通过 appState Proxy 跨组件共享的字段
  // (MonitorView.vue 的 scanRunning/statusText/monItems 等使用组件本地 ref)
  const scanRenderedKeys = ref(new Set())
  const searchRenderedKeys = ref(new Set())

  function resetScan() {
    scanRenderedKeys.value = new Set()
    searchRenderedKeys.value = new Set()
  }

  return { scanRenderedKeys, searchRenderedKeys, resetScan }
})
