# 安装版用户数据目录与在线资源识别修复方案

记录时间：2026-06-24

## 背景

最新安装版暴露两个问题：

1. 创建播放列表时崩溃，报错路径为 `C:\Program Files\IPTV Ultimate Player\config\playlists.json`，普通用户没有安装目录写权限。
2. 使用“打开在线资源”直接播放 `https://php.jdshipin.com:2096/TVOD/iptv.php?id=cctv5p` 失败，界面提示“在线资源已下载，但没有解析出任何频道信息”。

## 分析结论

### 安装目录写入问题

当前部分用户数据仍默认写入相对路径：

- `config/app_settings.json`
- `config/favorites.json`
- `config/playlists.json`
- `EPGs/`
- 在线资源保存默认目录 `Channels/`

安装版运行目录可能位于 `C:\Program Files\IPTV Ultimate Player`。该目录对普通用户默认只读，因此任何初始化、保存设置、收藏、播放专辑、EPG 下载、在线资源保存等写操作都有权限风险。

### 在线资源误判问题

用户提供的 URL 实际响应链为：

```text
https://php.jdshipin.com:2096/TVOD/iptv.php?id=cctv5p
302 -> https://cdn16.163189.xyz/163189/cctv5p
Content-Type: application/vnd.apple.mpegurl
```

响应体是 HLS 媒体播放列表：

```m3u8
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXTINF:10.000000,
/api?h=cctv5p&u=...
```

当前逻辑把“包含 `#EXTINF` 的文本”识别为频道资源文件，并交给频道列表解析器处理。HLS 媒体播放列表不是 IPTV 频道清单，因此解析结果为 0 个频道，最终误报“未解析到频道”。

## 解决方案

### 用户可写目录归一化

统一将运行期用户数据写入：

```text
%LocalAppData%\IPTV_Ultimate_Player_Codex\
```

目录规划：

```text
config\app_settings.json
config\favorites.json
config\playlists.json
Channels\
EPGs\
runtime\
logs\
```

实现策略：

1. 在 `utils.app_paths` 中提供统一路径函数。
2. 设置、收藏、播放专辑、EPG、默认资源目录全部改用用户目录。
3. 用户目录文件不存在时，尝试从旧相对路径复制一份，兼容开发版和旧安装版数据。
4. 首次运行时，如果用户 `Channels` 为空，则从内置 `Channels` 目录复制默认资源文件。
5. 安装目录只作为只读资源来源，不再作为运行期写入目标。

### 在线资源识别修复

新增在线资源类型判断：

1. HLS 媒体播放列表：
   - `Content-Type` 包含 `mpegurl`
   - 或内容包含 `#EXT-X-TARGETDURATION`、`#EXT-X-MEDIA-SEQUENCE`、`#EXT-X-STREAM-INF`
   - 归类为 `direct_media/hls`，直接播放最终 URL。

2. IPTV 频道资源文件：
   - M3U 频道清单需要包含 `#EXTINF`，且不包含 HLS 媒体播放列表特征。
   - JSON/TXT/CFG 仍按现有频道资源规则解析。

3. 接口/`.php` URL：
   - 先探测最终响应和内容类型。
   - 如果最终响应是 HLS/MPD/MP4/FLV/音频/图片/GIF，则直接播放最终 URL。
   - 如果响应体是裸媒体 URL，则提取并直接播放。
   - 只有确认是频道资源文件时才进入频道解析流程。

4. 解析 0 频道时兜底：
   - 如果下载内容其实是 HLS 媒体播放列表或裸媒体 URL，则转为直接播放。
   - 避免错误弹出“未解析到频道”。

## 验收办法

1. 安装版普通用户权限启动，不以管理员身份运行。
2. 创建播放专辑不再写入 `C:\Program Files\...`，`playlists.json` 应出现在 `%LocalAppData%\IPTV_Ultimate_Player_Codex\config\`。
3. 保存设置、收藏资源、收藏频道、下载 EPG 均不写入安装目录。
4. 首次打开资源库时，用户目录 `Channels` 有可用资源文件；后续新增/保存在线资源默认落到用户 `Channels`。
5. “打开在线资源”直接播放以下 URL 时，不应弹“未解析到频道”，应作为 HLS 直播流播放：

```text
https://php.jdshipin.com:2096/TVOD/iptv.php?id=cctv5p
```

6. 在线 M3U 频道清单仍应正常解析为频道列表。
7. 在线 MP4/M3U8/MPD/FLV/音频/图片/GIF URL 仍应按单个在线媒体资源直接播放。
