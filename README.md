# YTReBroadcastMonitors

一个用于多窗口播放 YouTube 频道直播/回放的桌面应用：
- 后端使用 **FastAPI + Uvicorn** 。
- 前端使用 **Vue 3 + Vite** 。
- 桌面端通过 **pywebview (WebView2)** 承载 UI。

## 仓库结构

- `backend/`：后端入口、API、网络测试、频道扫描、缓存与配置管理。
- `frontend/`：前端源码。
- `core/`：播放器管理等核心脚本。
- `requirements.txt`：Python 依赖。
- `build.bat` / `build_installer.bat`：Windows 构建脚本。

## 环境要求

- Python 3.10+
- Node.js 18+
- Windows 桌面运行时建议安装 WebView2 Runtime

## 更新计划

- channels推荐会保持更新，本地改动时注意不可改变第一行的列名
- debug

## License

本项目采用 [MIT License](./LICENSE)。
