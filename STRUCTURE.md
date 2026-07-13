# YVmonitor 项目结构

YouTube 多窗口直播监控桌面应用 — FastAPI + Vue 3 + pywebview + PyInstaller

---

## 顶层

```
code/
├── backend/             # Python 后端
├── frontend/            # Vue 3 前端 (SPA)
├── channels/            # 频道 CSV 数据源 
├── requirements.txt     # Python 依赖 (fastapi, yt-dlp, pywebview...)
├── pyproject.toml       # ruff lint 配置
├── mypy.ini             # Python 类型检查配置
├── build.bat            # PyInstaller 打包脚本
├── build_installer.bat  # Inno Setup 安装包构建
├── installer.iss        # Inno Setup 配置
├── icon.ico             # 应用图标
└── version_info.txt     # Windows 文件版本元信息
```

---

## backend/ — Python 后端

```
backend/
├── main.py                      # 入口: FastAPI 启动 + pywebview 桌面壳
├── api/
│   ├── api.py                   # 核心 REST 路由 (scan, refresh, monitor, avatar)
│   └── background_api.py        # 后台任务 API (网络探测等)
├── services/
│   ├── scanner.py               # 核心扫描引擎: yt-dlp 检测直播状态 + 并发调度
│   ├── scanner_utils.py         # 纯函数工具: URL 标准化 + yt-dlp 异常分类 (零依赖, 可测试)
│   ├── scan_service.py          # 扫描生命周期管理 (启动/停止 monitor 协程)
│   └── youtube_probe.py         # YouTube 网络可达性探测 (443/HTTP)
├── cache/
│   ├── avatar_cache.py          # 头像缓存读写入口
│   ├── avatar_cache_components.py # 缓存组件: 过期策略 + 损坏恢复
│   └── avatar_innertube.py      # YouTube InnerTube API 获取频道头像
├── models/
│   ├── scan_state_store.py      # 扫描状态存储器 (channel_id → status dict)
│   └── network_state_store.py   # 网络连接状态存储器
├── websocket/
│   └── manager.py               # WebSocket 管理器: 向所有前端推送事件
├── utils/
│   ├── channel_csv_reader.py    # 读取 channels/*.csv 频道列表
│   └── config_manager.py        # 应用配置读写 (JSON)
└── tests/
    ├── test_normalize_url.py    # URL 标准化测试 (16 cases)
    ├── test_classify_ytdlp.py   # yt-dlp 异常分类测试 (10 cases)
    └── test_scan_state_store.py # 扫描状态存储测试 (15 cases)
```


---

## frontend/ — Vue 3 前端 (SPA)

```
frontend/
├── index.html               # Vite 入口 HTML
├── package.json             # 依赖: vue 3.4, pinia 2.1, fuse.js 7, vite 5
├── vite.config.js           # Vite 构建配置 (含 hash 命名)
├── tsconfig.json            # TypeScript 配置 (allowJs, checkJs: false)
├── .eslintrc.cjs            # ESLint 配置
├── .prettierrc              # Prettier 格式化配置
└── src/
    ├── main.js              # 入口: createApp → Pinia → appState proxy → theme → mount
    ├── App.vue              # 根组件: 路由切换 Monitor/Player 视图
    ├── style.css            # 全局样式
    ├── env.d.ts             # Vue SFC TypeScript 声明
    ├── components/
    │   ├── MonitorView.vue  # 监控面板: 多窗口网格布局 + 频道列表
    │   ├── MonCard.vue      # 频道卡片: 缩略图、标题、直播状态标签
    │   ├── PlayerView.vue   # 播放器面板: iframe 网格 + refreshAll 并行刷新
    │   ├── PlayerCard.vue   # 播放器卡片: 单个 iframe 包装
    │   └── SearchDropdown.vue # 搜索下拉: fuse.js 模糊匹配 + SVG 渐变图标
    ├── composables/
    │   ├── useApiClient.js     # axios API 客户端封装
    │   ├── useWebSocket.js     # WebSocket 连接管理
    │   ├── useTheme.js         # 主题切换 (亮色/暗色)
    │   ├── useBackground.js    # 后台/前台状态检测
    │   ├── useNetworkProbe.js  # 网络连通性探测
    │   ├── useDomUtils.js      # DOM 操作工具
    │   └── useInputContextMenu.js # 输入框右键菜单
    └── stores/
        ├── appState.js         # 向后兼容 Proxy 代理 (路由旧全局状态 → Pinia)
        ├── useThemeStore.js    # 主题状态 (真正使用)
        ├── useScanStore.js     # 扫描状态 (真正使用)
        ├── useSearchStore.js   # 搜索状态 (真正使用)
        └── useBackgroundStore.js # 后台状态 (真正使用)
```

### 关键架构
- 初始化顺序: `createApp → createPinia → app.use(pinia) → initAppStateProxy() → initTheme() → app.mount()`
- `appState.js` 是 Proxy 兼容层，将旧的全局 state 调用路由到 Pinia store
- `PlayerView.vue` 布局状态 (layout/cardCount/layoutCols) 为组件本地 ref，不通过 Pinia
- `MonitorView.vue` 中 `AVATAR_RETRY_COOLDOWN_MS = 1500` 避免频繁重试
- Vite 构建输出带 `[hash:8]` 防缓存

---

## channels/ — 频道数据源

15 个 CSV 文件，格式: `频道名称,URL,备注`
包含日语和中文文件名 (UTF-8 编码)。

## 测试

```
cd backend && pytest tests/         # 41 tests, 零依赖
cd frontend && npm run lint         # ESLint 检查
ruff check backend/                 # Python 代码风格
mypy backend/                       # Python 类型检查
npx tsc --noEmit --project frontend # 前端类型检查
```
