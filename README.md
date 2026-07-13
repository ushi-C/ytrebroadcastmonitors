# YVmonitor

YouTube 多窗口直播监控桌面应用，支持同时打开多个频道播放窗口并实时检测直播状态。

**技术栈**: FastAPI + Uvicorn / Vue 3 + Vite + Pinia / pywebview (WebView2) / PyInstaller

## 功能

- **频道监控**: 批量扫描channel文件夹中的csv文件
- **多窗口播放**: 可自由调整窗口数量（1~ 6），每个窗口独立输入频道 URL 或点击Card跳转、从搜索下拉选择
- **一键刷新**: 所有播放窗口并行刷新，响应迅速
- **桌面集成**: pywebview 包装为原生 Windows 应用，带系统托盘图标
- **亮暗主题**: 手动切换

## 快速开始

```bash
# 后端
pip install -r requirements.txt
python backend/main.py

# 前端 (开发模式)
cd frontend && npm install && npm run dev

# 前端构建后由后端静态托管
cd frontend && npm run build
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
