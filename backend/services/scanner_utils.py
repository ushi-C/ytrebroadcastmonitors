"""
scanner_utils.py
────────────────
纯函数工具，无外部依赖，可直接导入测试。
从 scanner.py 中抽离以解耦 fastapi/yt-dlp 等重型依赖。
"""

import re


def classify_ytdlp_exception(e: Exception) -> str:
    """
    根据 yt-dlp 抛出的异常消息判断频道状态。

    返回值：
      offline      — 频道当前未开播
      upcoming     — 预定直播尚未开始
      ended        — 直播已结束（转为录播）
      terminated   — 账号已被封禁
      js_error     — 本地缺少 JS 运行时（环境问题）
      rate_limited — YouTube 429 限速
      unknown      — 无法识别的异常
    """
    msg = str(e)

    if "not currently live" in msg:
        return "offline"

    if "will begin in" in msg:
        return "upcoming"

    if "has ended" in msg:
        return "ended"

    if "This account has been terminated" in msg:
        return "terminated"

    if "No supported JavaScript runtime" in msg:
        return "js_error"

    if "429" in msg or "too many requests" in msg.lower():
        return "rate_limited"

    return "unknown"


def normalize_channel_live_url(q: str) -> tuple[str, str]:
    """把各种形式的频道标识统一转成 /live URL，返回 (target_url, channel_id)。"""
    q = q.strip()
    if re.match(r'^UC[A-Za-z0-9_-]{20,}$', q):
        return f"https://www.youtube.com/channel/{q}/live", q
    if q.startswith("http"):
        base = q.rstrip("/")
        if base.endswith("/live"):
            m = re.search(r'/channel/(UC[A-Za-z0-9_-]+)', base)
            return base, (m.group(1) if m else "")
        m = re.search(r'/channel/(UC[A-Za-z0-9_-]+)', base)
        if m:
            cid = m.group(1)
            return f"https://www.youtube.com/channel/{cid}/live", cid
        if re.search(r'/@([^/?#]+)', base):
            return f"{base}/live", ""
        return f"{base}/live", ""
    if q.startswith("@"):
        return f"https://www.youtube.com/{q}/live", ""
    return f"https://www.youtube.com/@{q}/live", ""
