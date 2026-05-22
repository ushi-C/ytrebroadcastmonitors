import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

export function useInputContextMenu(resolveInput) {
  const menu = ref({ visible: false, x: 0, y: 0 })
  const menuEl = ref(null)
  const menuStyle = computed(() => ({ left: menu.value.x + 'px', top: menu.value.y + 'px' }))

  function closeMenu() {
    menu.value.visible = false
  }

  function onDocClick() {
    closeMenu()
  }

  async function openInputMenu(e) {
    menu.value = { visible: true, x: e.clientX, y: e.clientY }
    await nextTick()

    const el = menuEl.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    const pad = 8
    const vw = window.innerWidth
    const vh = window.innerHeight

    let x = e.clientX
    let y = e.clientY

    if (x + rect.width + pad > vw) x = Math.max(pad, vw - rect.width - pad)
    if (y + rect.height + pad > vh) y = Math.max(pad, vh - rect.height - pad)

    if (x < pad) x = pad
    if (y < pad) y = pad
    menu.value = { visible: true, x: x + window.scrollX, y: y + window.scrollY }
  }

  async function doMenuAction(action) {
    const input = resolveInput()
    if (!input) return
    input.focus()
    if (action === 'paste') {
      try {
        const text = await navigator.clipboard.readText()
        const st = input.selectionStart ?? input.value.length
        const ed = input.selectionEnd ?? input.value.length
        input.value = input.value.slice(0, st) + text + input.value.slice(ed)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      } catch {
        document.execCommand('paste')
      }
    } else if (action === 'clear') {
      input.value = ''
      input.dispatchEvent(new Event('input', { bubbles: true }))
    } else if (action === 'selectAll') {
      input.select()
    } else {
      document.execCommand(action)
    }
    closeMenu()
  }

  onMounted(() => document.addEventListener('click', onDocClick))
  onUnmounted(() => document.removeEventListener('click', onDocClick))

  return { menu, menuEl, menuStyle, openInputMenu, doMenuAction, closeMenu }
}
