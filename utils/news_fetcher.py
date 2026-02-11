# utils/news_fetcher.py
import os
import requests
import hashlib
import base64
import time
import threading
from datetime import datetime, timedelta

# ===== 日志配置 =====
LOG_DIR = os.path.join("logs", "msg")
LOG_PREFIX = "msg"

def _write_log(message: str, level: str = 'info'):
    """封装日志写入"""
    try:
        from utils.logger import write_log
        full_message = f"{level.upper():<8} {message}"
        write_log(full_message, log_dir=LOG_DIR, prefix=LOG_PREFIX)
    except Exception as e:
        # 日志模块异常时回退到 print（避免死循环）
        print(f"[FALLBACK LOG] {level.upper():<8} {message}")

# ===== 钛媒体 API 配置 =====
APP_KEY = "2015042403"
APP_SECRET = "F3x47g39Wc4M96nwA28T"
APP_VERSION = "web1.0"
DEVICE = "pc"
API_URL = "https://api.tmtpost.com/v1/word/list"

# 全局已播报 GUID 集合（线程安全）
_played_guids = set()
_played_lock = threading.Lock()

def generate_headers():
    timestamp_ms = int(time.time() * 1000)
    timestamp_sec = str(timestamp_ms // 1000)
    token = base64.b64encode(timestamp_sec.encode()).decode()
    sign_str = APP_SECRET + timestamp_sec
    sign_md5 = hashlib.md5(sign_str.encode()).hexdigest()
    authorization = f'"13:{timestamp_ms}|44:{sign_md5}"'

    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.tmtpost.com/",
        "Origin": "https://www.tmtpost.com",
        "app-key": APP_KEY,
        "app-secret": APP_SECRET,
        "app-version": APP_VERSION,
        "device": DEVICE,
        "timestamp": str(timestamp_ms),
        "token": token,
        "authorization": authorization,
        "accept": "application/json, text/plain, */*",
    }

def get_news_list(start_ts: int, end_ts: int):
    """内部函数：拉取指定时间窗口内的新闻（含音频）"""
    params = {
        "time_start": start_ts,
        "time_end": end_ts,
        "limit": 20,
        "platform": "pc",
        "fields": "title;time_published;t_audio;guid"
    }

    headers = generate_headers()
    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != "ok":
            _write_log(f"API 返回错误: {data.get('errors')}", 'error')
            return []

        news_items = []
        for item in data.get("data", []):
            guid = item.get("guid")
            t_audio = item.get("t_audio")
            title = item.get("title", "无标题")
            pub_time = int(item["time_published"])

            if not guid or not t_audio:
                continue

            with _played_lock:
                if guid in _played_guids:
                    continue
                _played_guids.add(guid)

            time_str = time.strftime("%H:%M", time.localtime(pub_time))
            news_items.append({
                "guid": guid,
                "title": title,
                "time_str": time_str,
                "audio_url": t_audio
            })

        # 按发布时间升序（旧→新）
        news_items.sort(key=lambda x: int(x["time_str"].replace(":", "")))
        return news_items

    except Exception as e:
        _write_log(f"请求失败: {e}", 'error')
        return []
def play_audio_from_url(url: str):
    """
    播放指定网络 MP3 地址（供外部调用）
    """
    try:
        import pygame
        import io

        _write_log(f"开始加载音频: {url}")
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        audio_data = io.BytesIO(resp.content)
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
        pygame.mixer.music.load(audio_data)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.quit()
        _write_log("音频播放完成", 'info')

    except Exception as e:
        _write_log(f"音频播放失败: {e}", 'error')
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.quit()
        except:
            pass