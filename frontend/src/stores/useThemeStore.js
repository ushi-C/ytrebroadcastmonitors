import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref('neon-purple')
  const themeList = ref([])
  const themeInitialized = ref(false)

  return { theme, themeList, themeInitialized }
})
