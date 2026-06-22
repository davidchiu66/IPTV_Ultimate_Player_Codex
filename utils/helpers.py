import base64
import urllib.request
from datetime import datetime, timedelta, timezone

# 用于 normalize_name 的字符转换表
_NORMALIZE_TRANS = str.maketrans("", "", " -")

def b64url_to_hex(b64_str):
    if not b64_str: return ""
    padded = b64_str + '=' * (4 - len(b64_str) % 4)
    padded = padded.replace('-', '+').replace('_', '/')
    try:
        return base64.b64decode(padded).hex()
    except Exception:
        return ""

def parse_xmltv_time(t_str):
    try:
        dt_str = t_str[:14]
        dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
        tz_str = t_str[15:20] if len(t_str) >= 20 else "+0800"
        sign = 1 if tz_str[0] == '+' else -1
        hrs = int(tz_str[1:3])
        mns = int(tz_str[3:5])
        tz = timezone(sign * timedelta(hours=hrs, minutes=mns))
        dt = dt.replace(tzinfo=tz)
        return dt.timestamp()
    except:
        return 0

def normalize_name(name):
    """优化的名称标准化，使用 str.translate 提升性能"""
    if not name: return ""
    return name.lower().translate(_NORMALIZE_TRANS).strip()

def robust_fetch(url):
    """强大的防盗链网络请求探针"""
    user_agents = [
        "Televizo/1.3.0",
        "TiviMate/2.8.0",
        "VLC/3.0.16 LibVLC/3.0.16",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Dalvik/2.11.0 (Linux; U; Android 10; SM-G975F)",
        "Kodi/19.3 (Windows NT 10.0; Win64; x64)"
    ]
    for ua in user_agents:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': '*/*', 'Connection': 'keep-alive'})
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    data = response.read()
                    try: text = data.decode('utf-8')
                    except UnicodeDecodeError: text = data.decode('gbk', errors='ignore')
                    return text, ua 
        except Exception:
            continue
    return None, None