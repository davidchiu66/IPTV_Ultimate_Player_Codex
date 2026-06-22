import json
import os
import re

from utils.helpers import b64url_to_hex


class PlaylistManager:
    def __init__(self, channels_dir="Channels"):
        self.channels_dir = os.path.abspath(channels_dir)
        self.streams = []
        self.config_data = {}
        self.list_key = "Channels"
        self.current_file_base_name = "Default"

    def _get_empty_channel(self):
        return {
            "Name": "",
            "Category": self.current_file_base_name,
            "Manifest": "",
            "ManifestType": "",
            "LogoUrl": "",
            "TvgId": "",
            "TvgName": "",
            "DrmType": "none",
            "CdmType": "",
            "LicenseUrl": "",
            "Keys": [],
            "UseLocalProxy": False,
            "Proxy": "",
            "ManifestProxy": "",
            "MediaProxy": "",
            "ScriptProxy": "",
            "UserAgent": "",
            "Referer": "",
            "Headers": {},
            "VideoTracks": [],
            "AudioTracks": [],
            "SubtitleTracks": [],
            "DefaultVideo": "",
            "DefaultAudio": "",
            "DefaultSubtitles": "",
        }

    def load_file(self, filepath, on_epg_found=None):
        self.streams = []
        self.config_data = {}
        if not os.path.exists(filepath):
            return False, "文件不存在"

        self.current_file_base_name = os.path.splitext(os.path.basename(filepath))[0]
        ext = os.path.splitext(filepath)[1].lower()

        try:
            if ext in [".cfg", ".json"]:
                self._load_json(filepath)
            elif ext in [".m3u", ".m3u8"]:
                self._load_m3u(filepath, on_epg_found)
            elif ext == ".txt":
                self._load_txt(filepath)
            else:
                self._load_txt(filepath)
            return True, ""
        except Exception as exc:
            self.streams = []
            return False, str(exc)

    def save_file(self, filepath, epg_url=""):
        ext = os.path.splitext(filepath)[1].lower()
        if ext in [".m3u", ".m3u8"]:
            self._write_m3u(filepath, epg_url)
        elif ext == ".txt":
            self._write_txt(filepath)
        else:
            self._write_json(filepath)

    def _clean_text(self, value):
        return value.strip() if isinstance(value, str) else ""

    def _find_first_text(self, data, keys):
        if not isinstance(data, dict):
            return ""
        for key in keys:
            value = self._clean_text(data.get(key))
            if value:
                return value
        return ""

    def _flatten_headers(self, value, prefix=""):
        headers = {}
        if not isinstance(value, dict):
            return headers

        for key, sub_value in value.items():
            if sub_value in (None, "", []):
                continue
            key_name = f"{prefix}{key}" if prefix else str(key)
            if isinstance(sub_value, dict):
                nested_prefix = ""
                if key_name.lower() not in {"manifest", "media", "http", "headers"}:
                    nested_prefix = f"{key_name}-"
                headers.update(self._flatten_headers(sub_value, nested_prefix))
            elif isinstance(sub_value, list):
                joined = "; ".join(str(item).strip() for item in sub_value if str(item).strip())
                if joined:
                    headers[key_name] = joined
            else:
                text = str(sub_value).strip()
                if text:
                    headers[key_name] = text
        return headers

    def _extract_headers(self, data, inherited=None):
        headers = {}
        if isinstance(inherited, dict):
            headers.update(inherited)
        if isinstance(data, dict):
            headers.update(self._flatten_headers(data.get("Headers")))
            headers.update(self._flatten_headers(data.get("Headers2")))
        return headers

    def _first_value(self, data, keys, default=None):
        if not isinstance(data, dict):
            return default
        for key in keys:
            value = data.get(key)
            if value not in (None, "", []):
                return value
        return default

    def _to_number(self, value, default=0):
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else value
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text:
                return default
            try:
                number = float(text)
                return int(number) if number.is_integer() else number
            except ValueError:
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
                if match:
                    number = float(match.group(1))
                    return int(number) if number.is_integer() else number
        return default

    def _parse_bitrate(self, value, desc=""):
        raw = value
        unit_required = False
        if raw in (None, "", 0):
            raw = desc
            unit_required = True
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return int(raw)
        text = str(raw or "").strip().replace(",", "")
        if not text:
            return 0
        pattern = (
            r"([0-9]+(?:\.[0-9]+)?)\s*(mbps|mb/s|mib/s|kbps|kb/s|kib/s|bps|b/s)"
            if unit_required
            else r"([0-9]+(?:\.[0-9]+)?)\s*(mbps|mb/s|mib/s|kbps|kb/s|kib/s|bps|b/s)?"
        )
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            if unit_required:
                return 0
            return int(self._to_number(text, 0) or 0)
        number = float(match.group(1))
        unit = (match.group(2) or "").lower()
        if unit.startswith("m"):
            number *= 1_000_000
        elif unit.startswith("k"):
            number *= 1_000
        return int(number)

    def _parse_resolution(self, item):
        resolution = self._clean_text(
            self._first_value(item, ["Resolution", "resolution", "DisplayResolution"], "")
        )
        width = self._to_number(self._first_value(item, ["Width", "width", "W", "demux-w"]), None)
        height = self._to_number(self._first_value(item, ["Height", "height", "H", "demux-h"]), None)

        if resolution and "x" in resolution.lower():
            parts = re.split(r"\s*x\s*", resolution.lower(), maxsplit=1)
            if len(parts) == 2:
                width = self._to_number(parts[0], width)
                height = self._to_number(parts[1], height)
        elif resolution and resolution.lower().endswith("p"):
            height = self._to_number(resolution[:-1], height)
        elif resolution and str(resolution).isdigit():
            height = self._to_number(resolution, height)

        return resolution, width, height

    def _track_items_from(self, data, keys):
        value = self._first_value(data, keys, [])
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return list(value.values())
        return []

    def _extract_tracks(self, items, track_type):
        if not isinstance(items, list):
            return []

        tracks = []
        for item in items:
            if not isinstance(item, dict):
                continue
            desc = self._clean_text(self._first_value(item, ["Desc", "Description", "Title", "Name"], ""))
            resolution, width, height = self._parse_resolution(item)
            language = self._clean_text(self._first_value(item, ["Lang", "Language", "language", "lang"], ""))
            codec = self._clean_text(self._first_value(item, ["Codec", "Codecs", "codec", "Format"], ""))
            bitrate = self._parse_bitrate(
                self._first_value(item, ["Bandwidth", "Bitrate", "BitRate", "bitrate", "bandwidth"], 0),
                desc,
            )
            fps = self._to_number(self._first_value(item, ["FrameRate", "FPS", "fps", "demux-fps"], 0), 0)
            sampling_rate = self._to_number(
                self._first_value(item, ["SamplingRate", "SampleRate", "sample_rate", "demux-samplerate"], 0),
                0,
            )
            channels = self._to_number(
                self._first_value(item, ["Channels", "AudioChannels", "channel_count", "demux-channel-count"], 0),
                0,
            )

            tracks.append(
                {
                    "id": self._first_value(item, ["Id", "id", "TrackId", "track_id"], ""),
                    "type": track_type,
                    "language": language,
                    "lang": language,
                    "resolution": resolution,
                    "width": width,
                    "height": height,
                    "bitrate": bitrate,
                    "codec": codec,
                    "fps": fps,
                    "sampling_rate": sampling_rate,
                    "channels": channels,
                    "title": desc,
                    "kid": self._clean_text(self._first_value(item, ["Kid", "KID", "kid"], "")),
                    "is_internal": bool(item.get("IsInternal")),
                    "source": "file",
                }
            )
        return tracks

    def _extract_keys(self, data):
        keys = []
        raw_keys = data.get("Keys") if isinstance(data, dict) else None
        if isinstance(raw_keys, list):
            for item in raw_keys:
                text = self._clean_text(item)
                if text:
                    keys.append(text)
        if keys:
            return keys

        manifest = self._find_first_text(data, ["Manifest", "Url", "StreamUrl", "PlaylistUrl"])
        if manifest:
            for kid, key in re.findall(r"decryption_key=([0-9a-fA-F]{32}):([0-9a-fA-F]{32})", manifest):
                keys.append(f"{kid}:{key}")
        return keys

    def _resolve_proxy(self, data, parent=None):
        merged = {}
        if isinstance(parent, dict):
            merged.update(parent)
        if isinstance(data, dict):
            for key in ("Proxy", "ManifestProxy", "MediaProxy", "ScriptProxy"):
                value = self._clean_text(data.get(key))
                if value:
                    merged[key] = value
        return merged

    def _guess_manifest_type(self, manifest, data=None):
        manifest_type = ""
        if isinstance(data, dict):
            manifest_type = self._clean_text(data.get("ManifestType")).lower()
            if not manifest_type:
                info2 = data.get("ManifestInfo2")
                if isinstance(info2, dict):
                    manifest_type = self._clean_text(info2.get("Type")).lower()
        if manifest_type:
            if "dash" in manifest_type or "mpd" in manifest_type:
                return "dash"
            if "hls" in manifest_type or "m3u8" in manifest_type:
                return "hls"
            return manifest_type

        lower_url = (manifest or "").lower()
        if ".mpd" in lower_url or "manifest?" in lower_url or "dash" in lower_url:
            return "dash"
        if ".m3u8" in lower_url or "hls" in lower_url:
            return "hls"
        if lower_url.startswith("rtsp://"):
            return "rtsp"
        if lower_url.startswith("rtmp://"):
            return "rtmp"
        return ""

    def _find_manifest_url(self, data):
        if not isinstance(data, dict):
            return ""

        direct_keys = [
            "Manifest",
            "Url",
            "URL",
            "StreamUrl",
            "StreamingUrl",
            "PlaylistUrl",
            "Mpd",
            "MPD",
            "Hls",
            "HlsUrl",
        ]
        for key in direct_keys:
            value = self._clean_text(data.get(key))
            if value.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                return value

        manifest_info = data.get("ManifestInfo2")
        if isinstance(manifest_info, dict):
            for key in ("Url", "Manifest", "PlaylistUrl", "StreamingUrl"):
                value = self._clean_text(manifest_info.get(key))
                if value.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                    return value

        resolutions = data.get("StreamingResolutions")
        if isinstance(resolutions, list):
            for item in resolutions:
                if isinstance(item, dict):
                    value = self._find_first_text(item, ["Url", "Manifest", "PlaylistUrl", "StreamingUrl"])
                    if value.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                        return value
        return ""

    def _extract_channel_entries(self, data):
        if not isinstance(data, dict):
            return [], ""
        for key in ("Channels", "Streams", "Items", "Entries"):
            value = data.get(key)
            if isinstance(value, list):
                entries = [item for item in value if isinstance(item, dict)]
                if entries:
                    return entries, key
        return [], ""

    def _normalize_channel(self, raw_channel, defaults=None):
        defaults = defaults or {}
        channel = self._get_empty_channel()
        data = raw_channel if isinstance(raw_channel, dict) else {}

        category = (
            self._clean_text(data.get("Category"))
            or self._clean_text(data.get("GroupTitle"))
            or self._clean_text(defaults.get("Category"))
            or self.current_file_base_name
        )
        manifest = self._find_manifest_url(data)
        proxy_fields = self._resolve_proxy(data, defaults.get("_proxy_fields"))
        headers = self._extract_headers(data, defaults.get("Headers"))
        keys = self._extract_keys(data)
        video_items = self._track_items_from(data, ["VideoList", "VideoTracks", "Videos"])
        audio_items = self._track_items_from(data, ["AudioList", "AudioTracks", "Audios"])
        subtitle_items = self._track_items_from(
            data,
            ["SubtitlesList", "SubtitleTracks", "SubtitlesTracks", "Subtitles", "Captions"],
        )
        default_video = (
            self._clean_text(data.get("DefaultVideo"))
            or self._clean_text(data.get("Video"))
            or self._clean_text(defaults.get("DefaultVideo"))
        )
        default_audio = (
            self._clean_text(data.get("DefaultAudio"))
            or self._clean_text(data.get("Audio"))
            or self._clean_text(defaults.get("DefaultAudio"))
        )
        default_subtitles = (
            self._clean_text(data.get("DefaultSubtitles"))
            or self._clean_text(data.get("DefaultSubtitle"))
            or self._clean_text(data.get("Subtitles"))
            or self._clean_text(defaults.get("DefaultSubtitles"))
        )

        drm_type = self._clean_text(data.get("DrmType")).lower()
        cdm_type = self._clean_text(data.get("CdmType")).lower()
        drm_info = data.get("Drm")
        if not drm_type and isinstance(drm_info, dict):
            drm_type = self._clean_text(drm_info.get("Vendor")).lower()
        if not drm_type and cdm_type:
            drm_type = cdm_type
        if not drm_type:
            drm_type = "clearkey" if keys else "none"

        license_url = (
            self._clean_text(data.get("LicenseUrl"))
            or self._find_first_text(data.get("License") if isinstance(data.get("License"), dict) else {}, ["Url", "url"])
        )

        channel.update(
            {
                "Name": (
                    self._find_first_text(data, ["Name", "Title", "ChannelName"])
                    or self._find_first_text(defaults, ["Name"])
                    or "未命名"
                ),
                "Category": category,
                "Manifest": manifest,
                "ManifestType": self._guess_manifest_type(manifest, data),
                "LogoUrl": self._find_first_text(data, ["LogoUrl", "Logo", "Image"]) or self._find_first_text(defaults, ["LogoUrl"]),
                "TvgId": self._find_first_text(data, ["TvgId", "tvg-id", "Id", "ChannelId"]),
                "TvgName": self._find_first_text(data, ["TvgName", "tvg-name"]),
                "DrmType": drm_type or "none",
                "CdmType": cdm_type,
                "LicenseUrl": license_url,
                "Keys": keys,
                "UserAgent": self._clean_text(data.get("UserAgent")) or self._clean_text(defaults.get("UserAgent")),
                "Referer": self._clean_text(data.get("Referer")) or self._clean_text(defaults.get("Referer")),
                "Proxy": proxy_fields.get("Proxy", ""),
                "ManifestProxy": proxy_fields.get("ManifestProxy", ""),
                "MediaProxy": proxy_fields.get("MediaProxy", ""),
                "ScriptProxy": proxy_fields.get("ScriptProxy", ""),
                "UseLocalProxy": bool(
                    data.get("UseLocalProxy")
                    or defaults.get("UseLocalProxy")
                    or proxy_fields.get("Proxy")
                    or proxy_fields.get("ManifestProxy")
                    or proxy_fields.get("MediaProxy")
                    or proxy_fields.get("ScriptProxy")
                ),
                "Headers": headers,
                "VideoTracks": self._extract_tracks(video_items, "video"),
                "AudioTracks": self._extract_tracks(audio_items, "audio"),
                "SubtitleTracks": self._extract_tracks(subtitle_items, "sub"),
                "DefaultVideo": default_video,
                "DefaultAudio": default_audio,
                "DefaultSubtitles": default_subtitles,
            }
        )

        return channel

    def _load_json(self, filepath):
        with open(filepath, "r", encoding="utf-8") as handle:
            self.config_data = json.load(handle)

        if isinstance(self.config_data, list):
            self.list_key = "ROOT_LIST"
            self.streams = [self._normalize_channel(item) for item in self.config_data if isinstance(item, dict)]
            return

        if not isinstance(self.config_data, dict):
            self.list_key = "Channels"
            self.streams = []
            return

        defaults = {
            "Category": self.current_file_base_name,
            "UserAgent": self._clean_text(self.config_data.get("UserAgent")),
            "Referer": self._clean_text(self.config_data.get("Referer")),
            "Headers": self._extract_headers(self.config_data),
            "UseLocalProxy": bool(self.config_data.get("UseLocalProxy")),
            "DefaultVideo": self._clean_text(self.config_data.get("DefaultVideo")) or self._clean_text(self.config_data.get("Video")),
            "DefaultAudio": self._clean_text(self.config_data.get("DefaultAudio")) or self._clean_text(self.config_data.get("Audio")),
            "DefaultSubtitles": (
                self._clean_text(self.config_data.get("DefaultSubtitles"))
                or self._clean_text(self.config_data.get("DefaultSubtitle"))
                or self._clean_text(self.config_data.get("Subtitles"))
            ),
            "_proxy_fields": self._resolve_proxy(self.config_data),
        }

        entries, key = self._extract_channel_entries(self.config_data)
        if entries:
            self.list_key = key
            self.streams = [self._normalize_channel(item, defaults) for item in entries]
            return

        if any(self._clean_text(self.config_data.get(field)) for field in ("Manifest", "Url", "StreamUrl", "PlaylistUrl", "Mpd", "MPD", "HlsUrl")):
            self.list_key = "ROOT_SINGLE"
            self.streams = [self._normalize_channel(self.config_data, defaults)]
            return

        self.list_key = "Channels"
        self.streams = []

    def _decode_license_key_line(self, current_channel, key_val):
        if current_channel["DrmType"] == "clearkey" or "clearkey" in key_val.lower():
            current_channel["DrmType"] = "clearkey"
            if key_val.startswith("{"):
                try:
                    key_data = json.loads(key_val)
                    for key_obj in key_data.get("keys", []):
                        kid_hex = b64url_to_hex(key_obj.get("kid", ""))
                        key_hex = b64url_to_hex(key_obj.get("k", ""))
                        if kid_hex and key_hex:
                            current_channel["Keys"].append(f"{kid_hex}:{key_hex}")
                except Exception:
                    pass
            elif key_val.startswith("http"):
                match = re.search(r"keyid=([a-fA-F0-9]+)&key=([a-fA-F0-9]+)", key_val, re.IGNORECASE)
                if match:
                    current_channel["Keys"].append(f"{match.group(1)}:{match.group(2)}")
                else:
                    current_channel["LicenseUrl"] = key_val
            elif ":" in key_val:
                current_channel["Keys"].append(key_val)
        else:
            current_channel["LicenseUrl"] = key_val

    def _load_m3u(self, filepath, on_epg_found=None):
        self.list_key = "M3U_FORMAT"
        with open(filepath, "r", encoding="utf-8") as handle:
            raw_lines = handle.readlines()

        lines = []
        continuation_buffer = []
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                continue
            if not line.startswith("#") and not re.match(r"^(https?|rtmp|rtsp)://", line, re.IGNORECASE):
                continuation_buffer.append(line)
                continue
            if continuation_buffer and lines:
                lines[-1] = lines[-1] + " " + " ".join(continuation_buffer)
                continuation_buffer.clear()
            lines.append(line)

        if continuation_buffer and lines:
            lines[-1] = lines[-1] + " " + " ".join(continuation_buffer)

        current_channel = self._get_empty_channel()
        for line in lines:
            if line.startswith("#EXTM3U"):
                urls_matches = re.findall(r'(?:x-tvg-url|tvg-url|url-tvg)="([^"]+)"', line, re.IGNORECASE)
                for match in urls_matches:
                    for sub_url in match.split(","):
                        sub_url = sub_url.strip()
                        if sub_url and on_epg_found:
                            on_epg_found(sub_url)
                continue

            if line.startswith("#EXTINF"):
                parts = line.rsplit(",", 1)
                if len(parts) > 1:
                    current_channel["Name"] = parts[1].strip()
                cat_match = re.search(r'group-title="([^"]+)"', line, re.IGNORECASE)
                if cat_match:
                    current_channel["Category"] = cat_match.group(1).strip()
                logo_match = re.search(r'tvg-logo="([^"]+)"', line, re.IGNORECASE)
                if logo_match:
                    current_channel["LogoUrl"] = logo_match.group(1).strip()
                tvg_id_match = re.search(r'tvg-id="([^"]*)"', line, re.IGNORECASE)
                if tvg_id_match:
                    current_channel["TvgId"] = tvg_id_match.group(1).strip()
                tvg_name_match = re.search(r'tvg-name="([^"]*)"', line, re.IGNORECASE)
                if tvg_name_match:
                    current_channel["TvgName"] = tvg_name_match.group(1).strip()
                ua_match = re.search(r'(?:http-)?user-agent="([^"]+)"', line, re.IGNORECASE)
                if ua_match:
                    current_channel["UserAgent"] = ua_match.group(1).strip()
                    current_channel["UseLocalProxy"] = True
                continue

            if line.startswith("#KODIPROP:inputstream.adaptive.manifest_type="):
                current_channel["ManifestType"] = line.split("=", 1)[1].strip().lower()
                continue

            if line.startswith("#KODIPROP:inputstream.adaptive.license_type="):
                license_type = line.split("=", 1)[1].lower()
                if "clearkey" in license_type:
                    current_channel["DrmType"] = "clearkey"
                elif "widevine" in license_type:
                    current_channel["DrmType"] = "widevine"
                elif "playready" in license_type:
                    current_channel["DrmType"] = "playready"
                continue

            if line.startswith("#KODIPROP:inputstream.adaptive.license_key="):
                key_val = line.split("=", 1)[1].strip()
                self._decode_license_key_line(current_channel, key_val)
                continue

            if line.startswith("#KODIPROP:inputstream.adaptive.clearkey="):
                key_val = line.split("=", 1)[1].strip()
                current_channel["DrmType"] = "clearkey"
                if ":" in key_val:
                    current_channel["Keys"].append(key_val)
                continue

            if line.startswith("#EXTVLCOPT:http-user-agent=") or line.startswith("#KODIPROP:inputstream.adaptive.stream_headers=User-Agent="):
                current_channel["UserAgent"] = line.split("=", 1)[1].strip()
                current_channel["UseLocalProxy"] = True
                continue

            if line.startswith("#EXTVLCOPT:http-referrer="):
                current_channel["Referer"] = line.split("=", 1)[1].strip()
                current_channel["UseLocalProxy"] = True
                continue

            if line.startswith("#EXTHTTP:"):
                try:
                    json_data = json.loads(line[9:].strip())
                    current_channel["Headers"] = self._extract_headers({"Headers": json_data}, current_channel.get("Headers"))
                    user_agent = json_data.get("User-agent") or json_data.get("User-Agent")
                    if isinstance(user_agent, str) and user_agent.strip():
                        current_channel["UserAgent"] = user_agent.strip()
                        current_channel["UseLocalProxy"] = True
                    referer = json_data.get("Referer")
                    if isinstance(referer, str) and referer.strip():
                        current_channel["Referer"] = referer.strip()
                        current_channel["UseLocalProxy"] = True
                except Exception:
                    pass
                continue

            if re.match(r"^(https?|rtmp|rtsp)://", line, re.IGNORECASE):
                url = line
                if "|" in url:
                    url, options = url.split("|", 1)
                    user_agent_match = re.search(r"user-agent=([^|]+)", options, re.IGNORECASE)
                    if user_agent_match:
                        current_channel["UserAgent"] = user_agent_match.group(1).strip()
                        current_channel["UseLocalProxy"] = True
                    referer_match = re.search(r"referer=([^|]+)", options, re.IGNORECASE)
                    if referer_match:
                        current_channel["Referer"] = referer_match.group(1).strip()
                        current_channel["UseLocalProxy"] = True
                current_channel["Manifest"] = url.strip()
                current_channel["ManifestType"] = self._guess_manifest_type(current_channel["Manifest"], current_channel)
                if current_channel["Name"] and current_channel["Manifest"]:
                    self.streams.append(self._normalize_channel(current_channel))
                current_channel = self._get_empty_channel()

    def _load_txt(self, filepath):
        self.list_key = "TXT_FORMAT"
        current_cat = self.current_file_base_name
        with open(filepath, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "," not in line:
                    continue
                name, url = line.split(",", 1)
                name = name.strip()
                url = url.strip()
                if url == "#genre#":
                    current_cat = name
                    continue
                channel = self._get_empty_channel()
                channel["Name"] = name
                channel["Category"] = current_cat
                channel["Manifest"] = url
                channel["ManifestType"] = self._guess_manifest_type(url, channel)
                self.streams.append(self._normalize_channel(channel))

    def _prepare_stream_for_save(self, stream):
        data = dict(stream or {})
        for key in list(data.keys()):
            if str(key).startswith("_"):
                data.pop(key, None)
        return data

    def _write_json(self, filepath):
        prepared_streams = [self._prepare_stream_for_save(stream) for stream in self.streams]
        if self.list_key == "ROOT_LIST":
            self.config_data = prepared_streams
        elif self.list_key == "ROOT_SINGLE":
            self.config_data = prepared_streams[0] if len(prepared_streams) == 1 else prepared_streams
        elif self.list_key in ["M3U_FORMAT", "TXT_FORMAT"]:
            self.config_data = {"Channels": prepared_streams}
        else:
            if not isinstance(self.config_data, dict):
                self.config_data = {}
            self.config_data[self.list_key] = prepared_streams
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(self.config_data, handle, ensure_ascii=False, indent=2)

    def _write_m3u(self, filepath, epg_url=""):
        with open(filepath, "w", encoding="utf-8") as handle:
            handle.write("#EXTM3U")
            if epg_url:
                handle.write(f' x-tvg-url="{epg_url}"')
            handle.write("\n")
            for stream in self.streams:
                if not isinstance(stream, dict):
                    continue
                name = stream.get("Name") or "未命名"
                category = stream.get("Category") or self.current_file_base_name
                manifest = stream.get("Manifest")
                if not manifest:
                    continue
                if stream.get("UseLocalProxy"):
                    user_agent = stream.get("UserAgent")
                    referer = stream.get("Referer")
                    if user_agent:
                        handle.write(f"#EXTVLCOPT:http-user-agent={user_agent}\n")
                    if referer:
                        handle.write(f"#EXTVLCOPT:http-referrer={referer}\n")
                ext_props = []
                if stream.get("LogoUrl"):
                    ext_props.append(f'tvg-logo="{stream.get("LogoUrl")}"')
                if stream.get("TvgId"):
                    ext_props.append(f'tvg-id="{stream.get("TvgId")}"')
                if stream.get("TvgName"):
                    ext_props.append(f'tvg-name="{stream.get("TvgName")}"')
                ext_props.append(f'group-title="{category}"')
                handle.write(f'#EXTINF:-1 {" ".join(ext_props)},{name}\n')
                manifest_type = self._clean_text(stream.get("ManifestType"))
                if manifest_type:
                    handle.write(f"#KODIPROP:inputstream.adaptive.manifest_type={manifest_type}\n")
                keys_list = stream.get("Keys", [])
                if not isinstance(keys_list, list):
                    keys_list = []
                drm_type = self._clean_text(stream.get("DrmType")) or ("clearkey" if keys_list else "none")
                license_url = stream.get("LicenseUrl", "")
                if drm_type == "clearkey":
                    for key_val in keys_list:
                        if isinstance(key_val, str) and ":" in key_val:
                            handle.write(f"#KODIPROP:inputstream.adaptive.clearkey={key_val.strip()}\n")
                elif drm_type == "widevine" and license_url:
                    handle.write("#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha\n")
                    handle.write(f"#KODIPROP:inputstream.adaptive.license_key={license_url}\n")
                elif drm_type == "playready" and license_url:
                    handle.write("#KODIPROP:inputstream.adaptive.license_type=com.microsoft.playready\n")
                    handle.write(f"#KODIPROP:inputstream.adaptive.license_key={license_url}\n")
                handle.write(f"{manifest}\n")

    def _write_txt(self, filepath):
        groups = {}
        for stream in self.streams:
            category = stream.get("Category") or self.current_file_base_name
            groups.setdefault(category, []).append(stream)
        with open(filepath, "w", encoding="utf-8") as handle:
            for category, channels in groups.items():
                handle.write(f"{category},#genre#\n")
                for channel in channels:
                    name = channel.get("Name") or "未命名"
                    url = channel.get("Manifest")
                    if url:
                        handle.write(f"{name},{url}\n")
