# YVmonitor

YouTube 多窗口直播监控桌面应用，支持同时打开多个频道播放窗口并实时检测直播状态。

**技术栈**: FastAPI + Uvicorn / Vue 3 + Vite + Pinia / pywebview (WebView2) / PyInstaller

## 功能

- **频道监控**: 批量扫描channel文件夹中的csv文件
- **多窗口播放**: 可自由调整窗口数量（1~ 6），每个窗口独立输入频道 URL 或点击Card跳转、从搜索下拉选择
- **一键刷新**: 所有播放窗口并行刷新，响应迅速
- **桌面集成**: pywebview 包装为原生 Windows 应用，带系统托盘图标
- **亮暗主题**: 手动切换

## 编译环境要求

桌面安装包仅支持 **Windows x64**。开发服务器可在支持 Python 和 Node.js 的系统上运行，但桌面窗口依赖 Windows 的 WebView2。

| 工具/组件 | 要求 | 用途 |
| --- | --- | --- |
| 操作系统 | Windows 10/11 x64（生成安装包必需） | PyInstaller 打包与 Inno Setup 安装程序 |
| Python | **3.11**（推荐；项目静态检查目标为 3.11） | FastAPI 后端、pywebview 桌面窗口与 PyInstaller |
| Node.js | **18 或更高版本**（建议使用当前 LTS） | Vue/Vite 前端构建；Vite 5 需要 Node.js 18+ |
| npm | 随 Node.js 安装 | 安装和构建前端依赖 |
| Microsoft Edge WebView2 Runtime | Windows 桌面运行/调试必需 | pywebview 使用 WebView2 渲染应用界面；Windows 10/11 通常已预装 |
| Inno Setup 6 | 仅生成安装包时必需 | 将 `YVmonitor.exe` 制作成 `YVmonitor-Setup.exe` |
| 网络连接 | 首次安装依赖及扫描 YouTube 频道时需要 | 下载 npm/Python 依赖，并供 `yt-dlp` 访问 YouTube |

> 建议使用虚拟环境隔离 Python 依赖。`build.bat` 会在打包阶段自动安装 PyInstaller；如需离线构建，请预先在该虚拟环境中安装它。

## 快速开始

### 开发环境初始化

```bash
# 1. 创建并启用 Python 3.11 虚拟环境（Windows PowerShell）
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 安装后端依赖
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. 安装前端依赖（首次安装使用 npm ci 以遵循 package-lock.json）
cd frontend
npm ci
```

### 开发模式运行

在两个终端中分别运行：

```bash
# 终端 1：后端（项目根目录）
python backend/main.py

# 终端 2：前端热更新开发服务器
cd frontend
npm run dev
```

### 构建前端并运行

```bash
# 前端构建产物由后端静态托管
cd frontend
npm run build
cd ..
python backend/main.py
```

## 项目结构

```
backend/           # Python 后端 — FastAPI REST + WebSocket
  api/             #   路由: scan, refresh, monitor, avatar
  services/        #   核心: yt-dlp 扫描引擎
  cache/           #   频道头像缓存 (InnerTube API + 本地文件 + 损坏恢复)
  websocket/       #   实时状态推送
  models/          #   扫描状态 + 网络状态的线程安全存储器
  utils/           #   CSV 频道读取 + 应用配置管理
  tests/           #   41 个 pytest 测试 (零外部依赖)
frontend/          # Vue 3 SPA — 监控面板 + 播放器
  src/components/  #   MonitorView(网格列表), PlayerView(iframe网格)
  src/stores/      #   Pinia: theme, scan, search, background
  src/composables/ #   API客户端, WebSocket, 主题, 网络探测
channels/          # CSV 频道数据源
```

详细结构见 [STRUCTURE.md](./STRUCTURE.md)。


## 构建桌面安装包

```bash
# 1. 先构建前端
cd frontend && npm run build

# 2. PyInstaller 打包 exe
build.bat

# 3. Inno Setup 生成安装包
build_installer.bat
```

## License

MIT License — 详见 [LICENSE](./LICENSE)。
