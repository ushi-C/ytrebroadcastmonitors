import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSearchStore = defineStore('search', () => {
  const csvChannels = ref([])
  const fuse = ref(null)
  const checkCache = ref(new Map())
  const checking = ref(new Set())

  return { csvChannels, fuse, checkCache, checking }
})
