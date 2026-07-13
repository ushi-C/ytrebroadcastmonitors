import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useBackgroundStore = defineStore('background', () => {
  const userBackgroundUrl = ref('')

  return { userBackgroundUrl }
})
