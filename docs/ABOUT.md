# About IPTV Ultimate Player

**IPTV Ultimate Player** 是一个基于 **PySide6 + libmpv** 的 Windows 桌面 IPTV 与本地媒体播放器，目标是把直播源管理、本地媒体播放、网页嗅探解析、浏览器播放、收藏管理、播放列表、诊断日志和现代化播放器界面整合到一个可持续演进的桌面应用中。

它面向两类核心场景：

- **复杂直播源播放**：支持 M3U/M3U8/TXT/JSON/CFG 等频道资源，覆盖 HLS、DASH/MPD、FLV、TS 等常见直播格式，并提供浏览器辅助嗅探、请求头处理、代理配置和失败原因分类，帮助定位网页可播但播放器失败、Token 失效、403/404、DRM/CENC 等复杂问题。
- **本地媒体库播放**：支持 libmpv 可播放的视频、音频、GIF 和图片资源，提供资源库、资源收藏、本地播放专辑、自动连播、跳过片头片尾、播放倍率、4K 渲染策略等能力。

项目 UI 使用 PySide6 QWidget 实现，播放器控制栏、顶部条、资源库、播放列表和设置面板采用统一的深色玻璃拟态风格，强调桌面播放器的沉浸感、可读性和可操作性。

项目同时提供：

- 中文/英文 README
- 科技感宣传页 `docs/index.html`
- GPL-3.0-or-later 许可证
- Git LFS 大文件管理
- GitHub Actions Windows 安装包构建工作流

> 本项目仍处于快速迭代阶段，适合个人使用、功能验证和二次开发。直播源可用性会受到源站策略、地区网络、Token 时效、DRM、Referer/User-Agent 和浏览器兼容性等因素影响。

## GitHub About 推荐信息

**Description**

基于 PySide6 + libmpv 的 Windows IPTV/本地媒体播放器，支持直播源管理、网页嗅探解析、本地媒体播放、收藏、播放列表、诊断日志和安装包发布。

**Website**

https://dz.cc.cd/player/

**Topics**

`iptv`, `media-player`, `video-player`, `python`, `pyside6`, `qt`, `libmpv`, `mpv`, `hls`, `dash`, `m3u`, `windows`, `desktop-app`, `github-actions`

## English Summary

**IPTV Ultimate Player** is a Windows desktop IPTV and local media player built with **PySide6 + libmpv**. It combines live channel management, local media playback, browser-assisted stream resolving, favorites, playlists, diagnostics, and a modern glassmorphism player UI into one maintainable desktop application.
