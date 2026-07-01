import urllib.request
import urllib.error
import os
from urllib.parse import urlparse, parse_qs, unquote
from http.server import SimpleHTTPRequestHandler
import socketserver
from utils.helpers import normalize_name
from utils.url_cleaning import clean_media_url
from utils.app_paths import resource_path
import json

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

class ProxyHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        if (
            self.path.startswith('/proxy?')
            or self.path.startswith('/api/epg')
            or self.path.startswith('/api/channels')
            or self.path.startswith('/api/resolve')
        ):
            self.send_response(200, "ok")
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD')
            self.send_header('Access-Control-Allow-Headers', '*')
            self.send_header('Access-Control-Expose-Headers', '*')
            self.end_headers()
        else:
            self.send_response(200, "ok")
            self.end_headers()

    def do_GET(self):
        request_path = urlparse(self.path).path
        if self.path.startswith('/api/epg'):
            self.handle_epg()
        elif self.path.startswith('/api/channels'):
            self.handle_channels()
        elif self.path.startswith('/api/resolve'):
            self.handle_resolve()
        elif self.path.startswith('/proxy?'):
            self.handle_proxy(method="GET")
        elif request_path == '/live.html':
            self.handle_live_html(method="GET")
        elif request_path.startswith('/frontend/'):
            self.handle_bundled_static(request_path, method="GET")
        else:
            super().do_GET()

    def do_HEAD(self):
        request_path = urlparse(self.path).path
        if self.path.startswith('/proxy?'):
            self.handle_proxy(method="HEAD")
        elif request_path == '/live.html':
            self.handle_live_html(method="HEAD")
        elif request_path.startswith('/frontend/'):
            self.handle_bundled_static(request_path, method="HEAD")
        else:
            super().do_HEAD()

    def handle_live_html(self, method="GET"):
        app_ref = getattr(self.server, 'app_ref', None)
        html_path = ""
        if app_ref and hasattr(app_ref, 'get_browser_html_path'):
            html_path = app_ref.get_browser_html_path()

        if not html_path or not os.path.exists(html_path):
            self.send_error(404, "Browser player page has not been generated")
            return

        self._send_file(html_path, "text/html; charset=utf-8", method=method)

    def handle_bundled_static(self, request_path, method="GET"):
        relative_path = unquote(request_path.lstrip('/')).replace("\\", "/")
        parts = [part for part in relative_path.split("/") if part]
        if not parts or ".." in parts or parts[0] != "frontend":
            self.send_error(404, "Not found")
            return

        static_path = resource_path(relative_path)
        if not os.path.exists(static_path):
            self.send_error(404, "Not found")
            return

        content_type = "application/octet-stream"
        if static_path.lower().endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
        elif static_path.lower().endswith(".css"):
            content_type = "text/css; charset=utf-8"
        elif static_path.lower().endswith(".html"):
            content_type = "text/html; charset=utf-8"
        self._send_file(static_path, content_type, method=method)

    def _send_file(self, file_path, content_type, method="GET"):
        try:
            file_size = os.path.getsize(file_path)
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(file_size))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != "HEAD":
                with open(file_path, "rb") as handle:
                    while True:
                        chunk = handle.read(128 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            return

    def do_POST(self):
        if self.path.startswith('/proxy?'):
            self.handle_proxy(method="POST")
        else:
            self.send_error(501, "Unsupported method")

    def handle_epg(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        tvg_id = query.get('tvg_id', [''])[0].strip()
        tvg_name = query.get('tvg_name', [''])[0].strip()
        ch_name = query.get('name', [''])[0].strip()

        app_ref = getattr(self.server, 'app_ref', None)
        epg_mgr = app_ref.epg_manager if app_ref else None
        epg_data_dict = epg_mgr.epg_data if epg_mgr else {}
        epg_map = epg_mgr.epg_channel_map if epg_mgr else {}

        epg_list = []
        if epg_mgr and hasattr(epg_mgr, "get_programs"):
            epg_list = epg_mgr.get_programs(tvg_id=tvg_id, tvg_name=tvg_name, ch_name=ch_name)
        else:
            target_cid = None
            norm_tvg_name = normalize_name(tvg_name)
            norm_ch_name = normalize_name(ch_name)

            if tvg_id and tvg_id in epg_data_dict: target_cid = tvg_id
            elif tvg_name and tvg_name in epg_map: target_cid = epg_map[tvg_name]
            elif norm_tvg_name and norm_tvg_name in epg_map: target_cid = epg_map[norm_tvg_name]
            elif ch_name and ch_name in epg_map: target_cid = epg_map[ch_name]
            elif norm_ch_name and norm_ch_name in epg_map: target_cid = epg_map[norm_ch_name]

            if target_cid and target_cid in epg_data_dict:
                epg_list = epg_data_dict[target_cid]

        res = {"programs": epg_list}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(res, ensure_ascii=False).encode('utf-8'))

    def handle_channels(self):
        app_ref = getattr(self.server, 'app_ref', None)
        channels = app_ref.get_frontend_channels() if app_ref and hasattr(app_ref, 'get_frontend_channels') else []
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(channels, ensure_ascii=False).encode('utf-8'))

    def handle_resolve(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        index_text = query.get('index', query.get('sourceIndex', ['']))[0]
        force_text = query.get('force', ['0'])[0]
        probe_text = query.get('probe', query.get('deep', ['0']))[0]
        session_text = query.get('session', query.get('playId', ['']))[0]
        app_ref = getattr(self.server, 'app_ref', None)

        if not app_ref or not hasattr(app_ref, 'resolve_frontend_channel'):
            self._send_json({"ok": False, "status": "error", "message": "resolver unavailable"}, status=503)
            return

        try:
            index = int(index_text)
        except (TypeError, ValueError):
            self._send_json({"ok": False, "status": "error", "message": "missing or invalid channel index"}, status=400)
            return

        try:
            result = app_ref.resolve_frontend_channel(
                index,
                force=str(force_text).lower() in {"1", "true", "yes"},
                probe=str(probe_text).lower() in {"1", "true", "yes"},
                session_id=str(session_text or ""),
            )
        except Exception as exc:
            result = {"ok": False, "status": "error", "message": str(exc)}

        # 解析失败属于业务结果，不应让浏览器 fetch 看到 HTTP 500。
        # 否则前端会把“探测失败”误当成本地 API 异常，HLS 也可能被提前阻断。
        self._send_json(result, status=200)

    def _send_json(self, payload, status=200):
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', '*')
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            # 浏览器刷新、切台或关闭标签页时可能主动中断本地连接，这不是服务端错误。
            return

    def handle_proxy(self, method):
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        target_url = query_params.get('url', [''])[0]
        if not target_url:
            self.send_error(400, "Missing URL parameter")
            return

        # parse_qs has already decoded the outer /proxy query parameter once.
        # Do not unquote again: signed media URLs often contain encoded bytes
        # such as %2F/%2B/%3D inside tokens, and decoding them changes the
        # upstream URL enough for CDNs like GDTV/tcdn to reject it with 403.
        target_url = clean_media_url(target_url)
        ua = query_params.get('ua', [''])[0]
        ref = query_params.get('ref', [''])[0]
        cookie_header = query_params.get('cookie', [''])[0]
        target_lower = target_url.lower()
        gdtv_media = 'tcdn.itouchtv.cn/live/' in target_lower or 'gdtv.cn/live/' in target_lower

        MAX_HEADERS = 50
        MAX_STREAM_SIZE = 500 * 1024 * 1024  # 500MB 上限

        req = urllib.request.Request(target_url, method=method)
        header_count = 0
        passthrough_headers = {
            'accept',
            'accept-language',
            'cache-control',
            'pragma',
            'range',
            'if-none-match',
            'if-modified-since',
            'if-match',
            'if-range',
            'content-type',
        }
        for key, value in self.headers.items():
            lower_key = key.lower()
            if lower_key not in passthrough_headers:
                continue
            if header_count >= MAX_HEADERS:
                break
            req.add_header(key, value)
            header_count += 1

        req.add_header('User-Agent', ua if ua else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        if ref: req.add_header('Referer', ref)
        if cookie_header and not gdtv_media: req.add_header('Cookie', cookie_header)
        origin = query_params.get('origin', [''])[0]
        if origin and not gdtv_media:
            req.add_header('Origin', origin)

        if method == "POST":
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0: req.data = self.rfile.read(content_length)

        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                self.send_response(response.status)
                exclude_headers = ['transfer-encoding', 'connection', 'access-control-allow-origin', 'access-control-allow-methods', 'access-control-allow-headers', 'access-control-allow-credentials']
                for key, value in response.getheaders():
                    if key.lower() not in exclude_headers:
                        self.send_header(key, value)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Expose-Headers', 'Content-Type, X-Final-Url')
                self.send_header('X-Final-Url', response.geturl())
                self.end_headers()
                if method != "HEAD":
                    # 限制流大小，防止内存耗尽
                    total_sent = 0
                    buffer_size = 128 * 1024
                    while True:
                        chunk = response.read(buffer_size)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        total_sent += len(chunk)
                        if total_sent > MAX_STREAM_SIZE:
                            break
                    
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass 
        except urllib.error.HTTPError as e:
            self.send_response(200) 
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Expose-Headers', 'Content-Type, X-Final-Url, X-Proxy-Error-Status')
            self.send_header('X-Proxy-Error-Status', str(e.code))
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            try: 
                if method != "HEAD": self.wfile.write(f"Proxy intercepted HTTP Error: {e.code}".encode('utf-8'))
            except: pass
        except urllib.error.URLError as e:
            self.send_response(200) 
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Expose-Headers', 'Content-Type, X-Final-Url, X-Proxy-Error-Status')
            self.send_header('X-Proxy-Error-Status', '502') 
            self.end_headers()
            try: 
                if method != "HEAD": self.wfile.write(f"Proxy Upstream Connection Error: {e.reason}".encode('utf-8'))
            except: pass
        except Exception as e:
            try:
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Expose-Headers', 'Content-Type, X-Final-Url, X-Proxy-Error-Status')
                self.send_header('X-Proxy-Error-Status', '500')
                self.end_headers()
                if method != "HEAD": self.wfile.write(f"Proxy Internal Error: {e}".encode('utf-8'))
            except: pass
