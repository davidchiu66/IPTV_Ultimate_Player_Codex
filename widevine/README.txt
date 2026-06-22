程序启动时会优先扫描：

1. `plugins/WidevineCdm/`
2. `plugins/widevine/`
3. 当前这个 `widevine/` 目录

推荐结构：

1. 仅有 DLL 时：
   widevine/widevinecdm.dll

2. 带 manifest 时：
   widevine/manifest.json
   widevine/_platform_specific/win_x64/widevinecdm.dll

3. 也兼容：
   widevine/WidevineCdm/_platform_specific/win_x64/widevinecdm.dll

4. 推荐优先放置：
   plugins/WidevineCdm/manifest.json
   plugins/WidevineCdm/_platform_specific/win_x64/widevinecdm.dll

如果同时提供 manifest.json，程序会尽量读取版本号并传给 Qt WebEngine。
