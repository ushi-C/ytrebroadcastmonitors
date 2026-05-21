/**
 * useTheme.js
 * 主题管理 composable —— 负责加载、应用、切换、持久化皮肤。
 *
 * 用法：
 *   import { useTheme } from './composables/useTheme'
 *   const { currentTheme, themeList, setTheme } = useTheme()
 */

import { computed } from 'vue'
import { appState } from '../stores/appState' 

const THEMES = [
  // ── 幻
  {
    id: 'neon-purple',
    label: '幻',
    accent: ['#e8005a', '#9b30ff'],
    vars: {
      '--primary':               '#e8005a',
      '--primary2':              '#9b30ff',
      '--bg':                    '#0a080f',
      '--surface':               '#13101a',
      '--surface2':              '#1e1828',
      '--border':                '#2e2640',
      '--text':                  '#f0ebff',
      '--muted':                 '#7a6d9a',
      '--card-bg':               'rgba(30,10,55,.55)',
      '--card-border-a':         'rgba(255,180,220,.5)',
      '--card-border-b':         'rgba(160,100,255,.4)',
      '--card-border-c':         'rgba(255,200,230,.45)',
      '--grad-title-a':          '#ff80b0',
      '--grad-title-b':          '#b06fff',
      '--tabbar-bg-a':           'rgba(20,10,40,.98)',
      '--tabbar-bg-b':           'rgba(15,8,30,.98)',
      '--toolbar-bg-a':          'rgba(18,10,38,.97)',
      '--toolbar-bg-b':          'rgba(12,8,28,.97)',
      '--avatar-ring-a':         '#ff4488',
      '--avatar-ring-b':         '#9b30ff',
      '--avatar-ring-c':         '#ff80b0',
      '--icon-grad-a':           '#ffb3d9',
      '--icon-grad-b':           '#d86fff',
      '--live-color':            '#ff4466',
      '--color-error':           '#ff6666',
      '--send-arrow':            '#ff8fab',
      '--mon-btn-bg':            'rgba(100,40,180,.2)',
      '--mon-btn-border':        'rgba(160,100,255,.3)',
      '--mon-btn-color':         'rgba(220,190,255,.9)',
      '--mon-btn-hover-bg':      'rgba(120,50,200,.3)',
      '--mon-btn-hover-border':  'rgba(220,140,255,.6)',
    },
  },

  // ── 青
  {
    id: 'cyber-teal',
    label: '海',
    accent: ['#00c8a0', '#0090ff'],
    vars: {
      '--primary':               '#00c8a0',
      '--primary2':              '#0090ff',
      '--bg':                    '#050f12',
      '--surface':               '#081820',
      '--surface2':              '#0d2530',
      '--border':                '#0f3545',
      '--text':                  '#d8f5ff',
      '--muted':                 '#4a8a9a',
      '--card-bg':               'rgba(5,30,50,.55)',
      '--card-border-a':         'rgba(0,200,200,.45)',
      '--card-border-b':         'rgba(0,120,255,.35)',
      '--card-border-c':         'rgba(0,220,180,.4)',
      '--grad-title-a':          '#00e5c0',
      '--grad-title-b':          '#00aaff',
      '--tabbar-bg-a':           'rgba(5,20,30,.98)',
      '--tabbar-bg-b':           'rgba(4,14,22,.98)',
      '--toolbar-bg-a':          'rgba(6,18,28,.97)',
      '--toolbar-bg-b':          'rgba(4,12,20,.97)',
      '--avatar-ring-a':         '#00c8a0',
      '--avatar-ring-b':         '#0090ff',
      '--avatar-ring-c':         '#00e5c0',
      '--icon-grad-a':           '#80ffe8',
      '--icon-grad-b':           '#40b0ff',
      '--live-color':            '#00d4a0',
      '--color-error':           '#ff6060',
      '--send-arrow':            '#00e5c0',
      '--mon-btn-bg':            'rgba(0,100,120,.25)',
      '--mon-btn-border':        'rgba(0,180,180,.35)',
      '--mon-btn-color':         'rgba(160,240,230,.9)',
      '--mon-btn-hover-bg':      'rgba(0,130,150,.35)',
      '--mon-btn-hover-border':  'rgba(0,220,200,.6)',
    },
  },

  // ── 红蓝
  {
    id: 'blaze-red',
    label: '燃',
    accent: ['#ff3030', '#1a6fff'],
    vars: {
      '--primary':               '#ff3030',
      '--primary2':              '#1a6fff',
      '--bg':                    '#080508',
      '--surface':               '#120810',
      '--surface2':              '#1c0f1a',
      '--border':                '#2e1830',
      '--text':                  '#ffe8f0',
      '--muted':                 '#8a5070',
      '--card-bg':               'rgba(40,5,20,.55)',
      '--card-border-a':         'rgba(255,80,80,.45)',
      '--card-border-b':         'rgba(30,100,255,.35)',
      '--card-border-c':         'rgba(255,120,120,.4)',
      '--grad-title-a':          '#ff7070',
      '--grad-title-b':          '#5090ff',
      '--tabbar-bg-a':           'rgba(20,5,15,.98)',
      '--tabbar-bg-b':           'rgba(14,4,12,.98)',
      '--toolbar-bg-a':          'rgba(18,6,14,.97)',
      '--toolbar-bg-b':          'rgba(12,4,10,.97)',
      '--avatar-ring-a':         '#ff3030',
      '--avatar-ring-b':         '#1a6fff',
      '--avatar-ring-c':         '#ff7070',
      '--icon-grad-a':           '#ffaaaa',
      '--icon-grad-b':           '#80aaff',
      '--live-color':            '#ff4040',
      '--color-error':           '#ff8080',
      '--send-arrow':            '#ff8888',
      '--mon-btn-bg':            'rgba(160,20,40,.2)',
      '--mon-btn-border':        'rgba(255,80,80,.3)',
      '--mon-btn-color':         'rgba(255,200,210,.9)',
      '--mon-btn-hover-bg':      'rgba(200,30,50,.3)',
      '--mon-btn-hover-border':  'rgba(255,120,120,.6)',
    },
  },
]

const STORAGE_KEY = 'yvision-theme'

function applyThemeVars(themeId) {
  const theme = THEMES.find(t => t.id === themeId) ?? THEMES[0]
  const root = document.documentElement

  Object.entries(theme.vars).forEach(([k, v]) => {
    root.style.setProperty(k, v)
  })

  root.setAttribute('data-theme', themeId)
}

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY) ?? THEMES[0].id
  const valid = THEMES.find(t => t.id === saved) ? saved : THEMES[0].id

  applyThemeVars(valid)

  appState.theme = valid
  appState.themeList = THEMES
  appState.themeInitialized = true
}

export function useTheme() {
  function setTheme(themeId) {
    const valid = THEMES.find(t => t.id === themeId) ? themeId : THEMES[0].id

    applyThemeVars(valid)
    appState.theme = valid
    localStorage.setItem(STORAGE_KEY, valid)
  }

  return {
    currentTheme: computed(() => appState.theme), 
    themeList: THEMES,
    setTheme,
  }
}
