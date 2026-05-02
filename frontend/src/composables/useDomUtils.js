// Mirrors dom-utils.js as pure utility functions

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;')
}

export function extractVideoID(url) {
  url = (url || '').trim()
  if (/^[A-Za-z0-9_-]{11}$/.test(url)) return url
  const pats = [
    /[?&]v=([A-Za-z0-9_-]{11})/,
    /youtu\.be\/([A-Za-z0-9_-]{11})/,
    /youtube\.com\/live\/([A-Za-z0-9_-]{11})/,
    /youtube\.com\/embed\/([A-Za-z0-9_-]{11})/,
    /youtube\.com\/shorts\/([A-Za-z0-9_-]{11})/,
  ]
  for (const re of pats) {
    const m = url.match(re)
    if (m) return m[1]
  }
  return null
}

export function parseLiveTitleBlocks(title) {
  title = title || ''
  title = title
    .replace(/[\s\-\/]*\d{4}[-/]\d{1,2}[-/]\d{1,2}$/, '')
    .replace(/[\s\-\/]*\d{8}$/, '')
    .trim()

  const alnum = 'a-zA-Z0-9\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff'
  const alnumRe = new RegExp(`[${alnum}]+`, 'g')
  const tagRe = new RegExp(`#[${alnum}]+`, 'g')
  const tags = title.match(tagRe) || []
  const block3 = tags.length ? tags.join(' ') : '#LIVE'

  const bracketRe = /([【〖『].*?[】〗』])/g
  const brackets = [...title.matchAll(bracketRe)]
  let block1 = ''

  for (const b of brackets) {
    let content = b[0].slice(1, -1)
    tags.forEach(t => { content = content.replace(t, '') })
    const cleaned = (content.match(alnumRe) || []).join('')
    if (cleaned) { block1 = cleaned; break }
  }
  if (!block1) block1 = 'LIVE'

  let temp = title
  ;[...brackets].reverse().forEach(b => {
    temp = temp.slice(0, b.index) + temp.slice(b.index + b[0].length)
  })
  tags.forEach(t => { temp = temp.replace(t, '') })

  const block2Re = new RegExp(`[${alnum}！？!?]+`, 'g')
  const block2 = ((temp.match(block2Re) || []).join('').trim()).replace(/\d{8,14}$/, '')

  return { block1, block2, block3 }
}

export function monItemKey(i) {
  return (i && (i.url || i.id || (i.name && i.title && (i.name + '|' + i.title)))) || '__unknown__'
}

export function extractHandleFromUrl(url) {
  if (!url) return ''
  const m = url.match(/\/@([^/?#]+)/)
  return m ? '@' + m[1] : ''
}
