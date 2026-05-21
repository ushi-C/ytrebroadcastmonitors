(function (global) {
  const S = global.AppState;
  const U = global.DomUtils;

  let _showToast = function () {};
  let _switchTab = function () {};

  function setUiHooks(hooks) {
    _showToast = hooks.showToast;
    _switchTab = hooks.switchTab;
  }

  function calcSlots(n, cols, deskW, deskH) {
    if (n === 0) return [];
    const rows = Math.ceil(n / cols);
    const w = (deskW - S.PAD * 2 - S.GAP * (cols - 1)) / cols;
    const h = (deskH - S.PAD * 2 - S.GAP * (rows - 1)) / rows;
    return Array.from({ length: n }, (_, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      return { left: S.PAD + col * (w + S.GAP), top: S.PAD + row * (h + S.GAP), width: w, height: h };
    });
  }

  function relayout() {
    const desk = document.getElementById('desk');
    const dW = desk.clientWidth;
    const dH = desk.clientHeight;
    const n = S.layout.length;
    const cols = Math.min(S.layoutCols, n) || 1;
    const slots = calcSlots(n, cols, dW, dH);

    S.layout.forEach((id, i) => {
      const win = document.getElementById('card-' + id);
      if (!win) return;
      const s = slots[i];
      win.style.transition = 'none';
      win.style.width = s.width + 'px';
      win.style.height = s.height + 'px';
      void win.offsetWidth;
      win.style.transition = '';
      win.style.left = s.left + 'px';
      win.style.top = s.top + 'px';

      const ifr = document.getElementById('iframe-' + id);
      if (ifr) {
        const titleH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--title-h'))
          * parseFloat(getComputedStyle(document.documentElement).fontSize);
        const ctrlH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ctrl-h'))
          * parseFloat(getComputedStyle(document.documentElement).fontSize);
        const viewportH = Math.max(40, s.height - titleH - ctrlH);

        let baseW = 1280, baseH = 720;
        if (S.ratioMode[id] === 'portrait') { baseW = 720; baseH = 1280; }

        const scaleX = s.width / baseW;
        const scaleY = viewportH / baseH;
        const scale = Math.min(scaleX, scaleY);
        const realW = baseW * scale;
        const realH = baseH * scale;
        const offsetX = s.left + (s.width - realW) / 2;
        const offsetY = s.top + titleH + (viewportH - realH) / 2;

        ifr.style.width = baseW + 'px';
        ifr.style.height = baseH + 'px';
        ifr.style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
      }
    });
    document.getElementById('empty-hint').style.display = n === 0 ? 'block' : 'none';
  }

  function setLayoutCols(c) {
    S.layoutCols = c;
    ['1', '2', '3'].forEach(n =>
      document.getElementById('btn-col' + n).classList.toggle('active', Number(n) === c)
    );
    relayout();
  }

  function setStatus(id, msg, isErr) {
    const bar = document.getElementById('titlebar-' + id);
    if (!bar) return;
    bar.querySelector('.wm-title-text').textContent = '监测窗口 #' + id + (msg ? '  · ' + msg : '');
    bar.style.color = isErr ? '#ff6666' : '';
  }

  function updateBadge() {
    const n = S.layout.length;
    document.getElementById('countBadge').textContent = n + ' / ' + S.MAX_PLAYERS + ' 个窗口';
    document.getElementById('addBtn').disabled = n >= S.MAX_PLAYERS;
  }

  function loadVideo(id) {
    const url = (document.getElementById('url-' + id) || {}).value || '';
    const vid = U.extractVideoID(url);
    if (!vid) { setStatus(id, '无效链接', true); return; }
    const host = id % 2 === 0 ? 'https://www.youtube-nocookie.com' : 'https://www.youtube.com';
    const src = `${host}/embed/${vid}?autoplay=1&enablejsapi=1&playsinline=1`;
    document.getElementById('iframe-' + id).src = src;
    document.getElementById('placeholder-' + id).classList.add('hidden');
    setStatus(id, '播放中');
  }

  function refreshOne(id) {
    const ifr = document.getElementById('iframe-' + id);
    if (!ifr) return;
    const src = ifr.src;
    if (!src || src === 'about:blank' || (!src.includes('youtube.com') && !src.includes('youtube-nocookie.com'))) {
      setStatus(id, '未加载视频', true); return;
    }
    ifr.src = 'about:blank';
    requestAnimationFrame(() => requestAnimationFrame(() => {
      ifr.src = src;
      setStatus(id, '已刷新');
    }));
  }

  function refreshAll() {
    if (!S.layout.length) { _showToast('没有播放窗口'); return; }
    S.layout.forEach((id, i) => setTimeout(() => refreshOne(id), i * 300));
    _showToast('正在刷新全部窗口…');
  }

  function setVolume(id, val) {
    const v = parseInt(val);
    const icon = document.getElementById('vol-icon-' + id);
    if (icon) icon.textContent = v === 0 ? '🔇' : v < 50 ? '🔉' : '🔊';
    const ifr = document.getElementById('iframe-' + id);
    if (!ifr || !ifr.src || ifr.src === 'about:blank') return;
    try {
      ifr.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: 'setVolume', args: [v] }), '*');
    } catch (e) {}
  }

  function addPlayer(initUrl) {
    if (S.layout.length >= S.MAX_PLAYERS) return null;
    const id = ++S.cardCount;
    S.ratioMode[id] = 'landscape';

    const win = document.createElement('div');
    win.className = 'wm-window';
    win.id = 'card-' + id;
    win.style.cssText = 'left:100%;top:100%;width:0;height:0';

    win.innerHTML = `
    <div class="wm-titlebar" id="titlebar-${id}">
      <span class="wm-drag-handle" title="换位">⠿</span>
      <span class="wm-title-text">播放窗口 #${id}</span>
    </div>
    <div class="wm-viewport">
      <div id="placeholder-${id}" class="video-placeholder">
        <svg width="40" height="40" viewBox="0 0 24 24">
          <rect width="24" height="24" rx="4" fill="#ff0000"/>
          <polygon points="10,8 16,12 10,16" fill="#fff"/>
        </svg>
        <span>YouTube Live</span>
      </div>
    </div>
    <div class="card-controls">
      <input class="url-input" id="url-${id}" type="text" placeholder="输入 YouTube 直播链接…">
      <button class="c-btn play" type="button">播放</button>
      <button class="c-btn ref" type="button" title="窗口刷新">↻</button>
      <button class="c-btn ratio" type="button" title="横竖切换">纵</button>
      <div class="vol-wrap">
        <span class="vol-icon" id="vol-icon-${id}">🔊</span>
        <input class="vol-slider" type="range" min="0" max="100" value="100">
      </div>
      <button class="c-btn cls" type="button" title="关闭">✕</button>
    </div>`;

    document.getElementById('desk').appendChild(win);

    const iframeLayer = document.createElement('iframe');
    iframeLayer.id = 'iframe-' + id;
    iframeLayer.className = 'wm-iframe-layer';
    iframeLayer.src = 'about:blank';
    iframeLayer.setAttribute('allow', 'autoplay; fullscreen');
    iframeLayer.setAttribute('referrerpolicy', 'origin');
    iframeLayer.setAttribute('allowfullscreen', 'true');
    document.getElementById('desk').appendChild(iframeLayer);

    win.querySelector('.c-btn.play').addEventListener('click', () => loadVideo(id));
    win.querySelector('.c-btn.ref').addEventListener('click', () => refreshOne(id));
    win.querySelector('.c-btn.ratio').addEventListener('click', function () {
      if (S.ratioMode[id] === 'portrait') {
        S.ratioMode[id] = 'landscape'; this.textContent = '纵'; setStatus(id, '横屏模式');
      } else {
        S.ratioMode[id] = 'portrait'; this.textContent = '横'; setStatus(id, '竖屏模式');
      }
      relayout();
    });
    win.querySelector('.c-btn.cls').addEventListener('click', () => removePlayer(id));
    win.querySelector('.url-input').addEventListener('keydown', e => {
      if (e.key === 'Enter') loadVideo(id);
    });
    win.querySelector('.vol-slider').addEventListener('input', function () {
      setVolume(id, this.value);
    });

    win.querySelector('.wm-drag-handle').addEventListener('mousedown', function (e) {
      e.preventDefault();
      const fromIndex = S.layout.indexOf(id);
      if (fromIndex === -1) return;
      function onMouseUp(ev) {
        document.removeEventListener('mouseup', onMouseUp);
        const desk = document.getElementById('desk');
        const deskRect = desk.getBoundingClientRect();
        const x = ev.clientX - deskRect.left;
        const y = ev.clientY - deskRect.top;
        const total = S.layout.length;
        const cols = Math.min(S.layoutCols, total) || 1;
        const slots = calcSlots(total, cols, desk.clientWidth, desk.clientHeight);
        let targetIndex = fromIndex;
        for (let i = 0; i < slots.length; i++) {
          const s = slots[i];
          if (x >= s.left && x <= s.left + s.width && y >= s.top && y <= s.top + s.height) {
            targetIndex = i; break;
          }
        }
        if (targetIndex !== fromIndex) {
          const moved = S.layout.splice(fromIndex, 1)[0];
          S.layout.splice(targetIndex, 0, moved);
          relayout();
        }
      }
      document.addEventListener('mouseup', onMouseUp);
    });

    S.layout.push(id);
    relayout();
    updateBadge();

    if (initUrl) {
      document.getElementById('url-' + id).value = initUrl;
      loadVideo(id);
    }
    return id;
  }

  function removePlayer(id) {
    const idx = S.layout.indexOf(id);
    if (idx !== -1) S.layout.splice(idx, 1);
    const win = document.getElementById('card-' + id);
    if (win) win.remove();
    const ifr = document.getElementById('iframe-' + id);
    if (ifr) ifr.remove();
    relayout();
    updateBadge();
  }

  function sendToPlayer(url, name) {
    if (S.layout.length >= S.MAX_PLAYERS) {
      _showToast('播放器limit (最多 ' + S.MAX_PLAYERS + ' 个窗口)'); return;
    }
    addPlayer(url);
    _switchTab('player');
    _showToast('已添加: ' + (name || url));
  }

  global.PlayerManager = {
    setUiHooks, calcSlots, relayout, setLayoutCols,
    setStatus, updateBadge, loadVideo, refreshOne, refreshAll,
    setVolume, addPlayer, removePlayer, sendToPlayer,
  };
})(window);
