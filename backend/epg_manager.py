import gzip
import os
import sqlite3
import threading
import urllib.request
from collections import OrderedDict
from functools import lru_cache
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from utils.helpers import normalize_name, parse_xmltv_time
from utils.app_paths import user_epg_dir


class EPGManager:
    def __init__(self, epg_dir=None):
        self.epg_dir = os.path.abspath(str(epg_dir or user_epg_dir()))
        if not os.path.exists(self.epg_dir):
            os.makedirs(self.epg_dir)

        self.index_db_path = os.path.join(self.epg_dir, "epg_index.sqlite3")
        self.epg_channel_map = {}
        self.epg_data = {}
        self.session_downloaded_epgs = set()

        self._lock = threading.RLock()
        self._program_cache = OrderedDict()
        self._cache_limit = 32
        self._build_lock = threading.Lock()
        self._refresh_event = threading.Event()
        self._resolve_cache_version = 0

    def _list_xml_files(self):
        try:
            return [
                os.path.join(self.epg_dir, f)
                for f in os.listdir(self.epg_dir)
                if f.lower().endswith(".xml")
            ]
        except OSError:
            return []

    def _index_is_fresh(self):
        if not os.path.exists(self.index_db_path):
            return False

        try:
            db_mtime = os.path.getmtime(self.index_db_path)
            for xml_path in self._list_xml_files():
                if os.path.getmtime(xml_path) > db_mtime:
                    return False
            return True
        except OSError:
            return False

    def _connect(self):
        os.makedirs(self.epg_dir, exist_ok=True)
        conn = sqlite3.connect(self.index_db_path, timeout=30)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                # Some user data locations/security tools reject WAL sidecar files.
                # EPG is a cache, so falling back is better than failing playback.
                conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA temp_store=MEMORY")
        except Exception:
            conn.close()
            raise
        return conn

    def _index_sidecar_files(self):
        return [
            self.index_db_path,
            f"{self.index_db_path}-wal",
            f"{self.index_db_path}-shm",
            f"{self.index_db_path}-journal",
        ]

    def _remove_index_cache(self):
        """Remove the derived EPG index database and SQLite sidecar files."""
        for path in self._index_sidecar_files():
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def _clear_runtime_cache(self):
        """Clear in-memory EPG caches after an unrecoverable index error."""
        with self._lock:
            self.epg_channel_map = {}
            self.epg_data = {}
            self._program_cache.clear()
        self._resolve_cache_version += 1
        self._resolve_channel_id_cached.cache_clear()

    def _format_load_error(self, error):
        detail = str(error) or error.__class__.__name__
        if isinstance(error, sqlite3.Error):
            if "disk i/o error" in detail.lower():
                reason = "EPG 索引数据库读写失败，可能是磁盘空间不足、目录不可写、索引文件损坏，或被安全软件/同步软件占用。"
            else:
                reason = "EPG 索引数据库异常。"
            return (
                f"{reason}\n"
                "程序已临时禁用 EPG 信息，不影响直播或本地媒体播放。\n"
                f"索引路径：{self.index_db_path}\n"
                f"错误详情：{detail}"
            )
        return (
            "本地节目单加载失败，程序已临时禁用 EPG 信息，不影响播放。\n"
            f"错误详情：{detail}"
        )

    def _reset_index(self):
        with self._connect() as conn:
            conn.execute("DROP TABLE IF EXISTS channels")
            conn.execute("DROP TABLE IF EXISTS programs")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    alias TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS programs (
                    channel_id TEXT NOT NULL,
                    start REAL NOT NULL,
                    stop REAL NOT NULL,
                    title TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_programs_channel_start ON programs(channel_id, start)"
            )

    def _load_channel_map_from_db(self):
        channel_map = {}
        if not os.path.exists(self.index_db_path):
            return channel_map

        with self._connect() as conn:
            for alias, channel_id in conn.execute("SELECT alias, channel_id FROM channels"):
                channel_map[alias] = channel_id
        return channel_map

    def _load_stats_from_db(self):
        if not os.path.exists(self.index_db_path):
            return 0, 0

        with self._connect() as conn:
            channel_count = conn.execute(
                "SELECT COUNT(DISTINCT channel_id) FROM channels"
            ).fetchone()[0] or 0
            program_count = conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0] or 0
        return channel_count, program_count

    def _insert_aliases(self, conn, aliases):
        rows = [(alias, channel_id) for alias, channel_id in aliases if alias and channel_id]
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO channels(alias, channel_id) VALUES (?, ?)",
                rows,
            )

    def _rebuild_index(self):
        valid_files_count = 0
        total_programs = 0

        self._reset_index()

        with self._connect() as conn:
            channel_rows = []
            program_rows = []

            for xml_path in self._list_xml_files():
                try:
                    root = None
                    valid_file = False
                    context = ET.iterparse(xml_path, events=("end",))

                    for event, elem in context:
                        tag = elem.tag.lower()
                        if tag == "channel":
                            c_id = (elem.attrib.get("id") or "").strip()
                            if c_id:
                                valid_file = True
                                aliases = {(c_id, c_id), (normalize_name(c_id), c_id)}
                                for dn in elem.findall("display-name"):
                                    if dn.text:
                                        exact_name = dn.text.strip()
                                        aliases.add((exact_name, c_id))
                                        aliases.add((normalize_name(exact_name), c_id))
                                channel_rows.extend(list(aliases))
                                if len(channel_rows) >= 1000:
                                    self._insert_aliases(conn, channel_rows)
                                    channel_rows.clear()

                        elif tag == "programme":
                            channel_id = (elem.attrib.get("channel") or "").strip()
                            start_str = (elem.attrib.get("start") or "").strip()
                            stop_str = (elem.attrib.get("stop") or "").strip()
                            title_elem = elem.find("title")
                            title = title_elem.text.strip() if title_elem is not None and title_elem.text else "未知节目"
                            if channel_id and start_str and stop_str:
                                valid_file = True
                                program_rows.append(
                                    (
                                        channel_id,
                                        parse_xmltv_time(start_str),
                                        parse_xmltv_time(stop_str),
                                        title,
                                    )
                                )
                                total_programs += 1
                                if len(program_rows) >= 3000:
                                    conn.executemany(
                                        "INSERT INTO programs(channel_id, start, stop, title) VALUES (?, ?, ?, ?)",
                                        program_rows,
                                    )
                                    program_rows.clear()

                        # 优化：清除元素并从父节点中移除，释放内存
                        if root is None:
                            root = elem
                        elem.clear()
                        # 移除已处理的前序兄弟节点
                        while elem.getprevious() is not None:
                            parent = elem.getparent()
                            if parent is not None:
                                del parent[0]

                    # 清理根节点
                    if root is not None:
                        root.clear()

                    if channel_rows:
                        self._insert_aliases(conn, channel_rows)
                        channel_rows.clear()
                    if program_rows:
                        conn.executemany(
                            "INSERT INTO programs(channel_id, start, stop, title) VALUES (?, ?, ?, ?)",
                            program_rows,
                        )
                        program_rows.clear()

                    if valid_file:
                        valid_files_count += 1
                    conn.commit()
                except Exception:
                    conn.rollback()

        return valid_files_count, total_programs

    def _load_local_epg_once(self):
        """Load or rebuild the local EPG index once."""
        if not self._index_is_fresh():
            valid_files_count, _ = self._rebuild_index()
        else:
            valid_files_count = len(self._list_xml_files())

        self.epg_channel_map = self._load_channel_map_from_db()
        channel_count, _ = self._load_stats_from_db()

        with self._lock:
            self.epg_data = {}
            self._program_cache.clear()

        self._resolve_cache_version += 1
        self._resolve_channel_id_cached.cache_clear()
        return valid_files_count, channel_count

    def load_local_epg(self, on_finish=None, on_error=None):
        def task():
            # 尝试获取锁（非阻塞）
            acquired = self._build_lock.acquire(blocking=False)
            if not acquired:
                # 另一个构建正在运行，标记需要刷新
                self._refresh_event.set()
                return

            try:
                while True:
                    self._refresh_event.clear()

                    try:
                        valid_files_count, channel_count = self._load_local_epg_once()
                    except sqlite3.Error:
                        self._remove_index_cache()
                        valid_files_count, channel_count = self._load_local_epg_once()

                    if on_finish:
                        on_finish(valid_files_count, channel_count)

                    # 检查构建期间是否有刷新请求
                    if not self._refresh_event.is_set():
                        break
            except Exception as exc:
                self._clear_runtime_cache()
                if on_error:
                    on_error(self._format_load_error(exc))
            finally:
                self._build_lock.release()

        threading.Thread(target=task, daemon=True).start()

    def _resolve_channel_id(self, tvg_id="", tvg_name="", ch_name=""):
        return self._resolve_channel_id_cached(
            tvg_id, tvg_name, ch_name, self._resolve_cache_version
        )

    @lru_cache(maxsize=512)
    def _resolve_channel_id_cached(self, tvg_id, tvg_name, ch_name, _version):
        """优化的频道解析，使用 LRU 缓存避免重复计算"""
        # 优先尝试精确匹配（最常见的情况）
        if tvg_id and tvg_id in self.epg_channel_map:
            return self.epg_channel_map[tvg_id]
        if tvg_name and tvg_name in self.epg_channel_map:
            return self.epg_channel_map[tvg_name]

        # 只有在精确匹配失败时才进行标准化
        if tvg_name:
            norm_tvg_name = normalize_name(tvg_name)
            if norm_tvg_name and norm_tvg_name in self.epg_channel_map:
                return self.epg_channel_map[norm_tvg_name]

        if ch_name:
            if ch_name in self.epg_channel_map:
                return self.epg_channel_map[ch_name]
            norm_ch_name = normalize_name(ch_name)
            if norm_ch_name and norm_ch_name in self.epg_channel_map:
                return self.epg_channel_map[norm_ch_name]

        return None

    def get_programs(self, tvg_id="", tvg_name="", ch_name=""):
        channel_id = self._resolve_channel_id(tvg_id=tvg_id, tvg_name=tvg_name, ch_name=ch_name)
        if not channel_id:
            return []

        with self._lock:
            cached = self._program_cache.get(channel_id)
            if cached is not None:
                self._program_cache.move_to_end(channel_id)
                return cached

        if not os.path.exists(self.index_db_path):
            return []

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT start, stop, title FROM programs WHERE channel_id = ? ORDER BY start",
                    (channel_id,),
                ).fetchall()
            programs = [{"start": row[0], "stop": row[1], "title": row[2]} for row in rows]
        except Exception:
            return []

        with self._lock:
            self._program_cache[channel_id] = programs
            self._program_cache.move_to_end(channel_id)
            while len(self._program_cache) > self._cache_limit:
                self._program_cache.popitem(last=False)
        return programs

    def download_epg(self, url, auto=False, on_success=None, on_error=None):
        def task():
            try:
                parsed = urlparse(url)
                base_name = os.path.basename(parsed.path) or "epg_download.xml"

                if base_name.lower().endswith(".gz"):
                    base_name = base_name[:-3]
                if not base_name.lower().endswith(".xml"):
                    base_name += ".xml"

                save_path = os.path.join(self.epg_dir, base_name)
                if auto and os.path.exists(save_path):
                    self.session_downloaded_epgs.add(url)
                    if on_success:
                        on_success(save_path, True)
                    return

                counter = 1
                root_name, ext = os.path.splitext(base_name)
                while os.path.exists(save_path):
                    save_path = os.path.join(self.epg_dir, f"{root_name}_{counter}{ext}")
                    counter += 1

                req = urllib.request.Request(url, headers={"User-Agent": "Televizo/1.3.0"})
                with urllib.request.urlopen(req, timeout=60) as response:
                    data = response.read()
                    content_encoding = response.info().get("Content-Encoding", "")

                if url.endswith(".gz") or content_encoding == "gzip" or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)

                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(data.decode("utf-8", errors="ignore"))

                if auto:
                    self.session_downloaded_epgs.add(url)
                if on_success:
                    on_success(save_path, False)
            except Exception as e:
                if on_error:
                    on_error(str(e))

        threading.Thread(target=task, daemon=True).start()
