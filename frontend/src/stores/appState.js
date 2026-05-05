import { reactive } from 'vue'

export const appState = reactive({
  MAX_PLAYERS: 6,
  cardCount: 0,
  layoutCols: 1,
  layout: [],      // array of player IDs in order
  GAP: 6,
  PAD: 8,
  ratioMode: {},   // { [id]: 'landscape' | 'portrait' }

  // Monitor scan
  scanRenderedKeys: new Set(),
  searchRenderedKeys: new Set(),
  monItems: [],          // live channel cards from scan
  scanRunning: false,
  scanProgress: 0,
  scanTotal: 0,
  scanStatusText: '',

  // Search
  csvChannels: [],
  fuse: null,
  checkCache: new Map(),  
  checking: new Set(),

  // Toast
  toastMsg: '',
  toastVisible: false,

  // Scale
  scalePct: 100,
  scaleVisible: false,

  // Theme
  theme: 'neon-purple',         // 当前主题 id
  themeList: [],                // 由 initTheme() 填入完整列表
  themeInitialized: false,      // 防止组件在初始化前渲染主题选择器
})
