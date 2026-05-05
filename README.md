# YTReBroadcastMonitors

一个用于监控 YouTube 频道直播/回放状态的桌面应用：
- 后端使用 **FastAPI + Uvicorn** 提供 API 与扫描服务。
- 前端使用 **Vue 3 + Vite** 提供监控界面。
- 桌面端通过 **pywebview (WebView2)** 承载 UI。

## 仓库结构

- `backend/`：后端入口、API、扫描服务、缓存与配置管理。
- `frontend/`：Vue 前端源码。
- `core/`：播放器管理等核心脚本。
- `requirements.txt`：Python 依赖。
- `build.bat` / `build_installer.bat`：Windows 构建脚本。

## 环境要求

- Python 3.10+
- Node.js 18+
- npm 9+
- Windows 桌面运行时建议安装 WebView2 Runtime

## 开发启动

### 1. 安装后端依赖

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 3. 启动应用

#### 方式 A：直接启动桌面应用（推荐）

```bash
python -m backend.main
```

该方式会启动后端服务并拉起 WebView2 窗口。

#### 方式 B：前后端分离开发

终端 1（后端）：
```bash
python -m backend.main --mode browser
```

终端 2（前端）：
```bash
cd frontend
npm run dev
```

## 常用命令

```bash
# 前端开发
cd frontend && npm run dev

# 前端构建
cd frontend && npm run build

# 前端预览
cd frontend && npm run preview
```

## 产物与运行时文件

运行后会在项目目录（或打包目录）生成如下运行时文件：
- `app.log`
- `channel_avatar_cache.json`
- `avatar_cache/`
- `window_config.json`
- `webview_data/`

## 更新计划
- 自定义图片/视频背景。
- 全屏设置
- 多预设频道表读取

## License

本项目采用 [MIT License](./LICENSE)。
