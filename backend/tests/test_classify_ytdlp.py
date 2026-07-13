"""
test_classify_ytdlp.py — 测试 classify_ytdlp_exception 异常分类
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.services.scanner_utils import classify_ytdlp_exception


class TestClassifyYtdlp:
    """直接异常消息分类"""

    def test_offline_not_currently_live(self):
        e = Exception("This channel is not currently live")
        assert classify_ytdlp_exception(e) == "offline"

    def test_offline_variant_no_live_streams(self):
        e = Exception("not currently live stream found")
        assert classify_ytdlp_exception(e) == "offline"

    def test_upcoming_will_begin(self):
        e = Exception("Premiere will begin in 15 minutes")
        assert classify_ytdlp_exception(e) == "upcoming"

    def test_ended_has_ended(self):
        e = Exception("This live event has ended")
        assert classify_ytdlp_exception(e) == "ended"

    def test_terminated_account(self):
        e = Exception("This account has been terminated due to violation")
        assert classify_ytdlp_exception(e) == "terminated"

    def test_js_error_no_runtime(self):
        e = Exception("No supported JavaScript runtime was found")
        assert classify_ytdlp_exception(e) == "js_error"

    def test_rate_limited_429(self):
        e = Exception("HTTP Error 429: Too Many Requests")
        assert classify_ytdlp_exception(e) == "rate_limited"

    def test_rate_limited_too_many(self):
        e = Exception("too many requests, please slow down")
        assert classify_ytdlp_exception(e) == "rate_limited"

    def test_rate_limited_mixed_case(self):
        e = Exception("TOO MANY REQUESTS detected")
        assert classify_ytdlp_exception(e) == "rate_limited"

    def test_unknown_generic(self):
        e = Exception("Some random network error")
        assert classify_ytdlp_exception(e) == "unknown"

    def test_unknown_empty_message(self):
        e = Exception()
        assert classify_ytdlp_exception(e) == "unknown"


class TestClassifyEdgeCases:
    """边界情况"""

    def test_string_contains_multiple_keywords(self):
        """ended 优先于 offline? 当前实现按顺序匹配，第一个命中即返回"""
        e = Exception("This live event has ended (not currently live)")
        # "not currently live" 出现在前面，所以走 offline
        assert classify_ytdlp_exception(e) == "offline"

    def test_custom_exception_type(self):
        """非标准 Exception 子类也应正常处理"""

        class YtdlpError(Exception):
            pass

        e = YtdlpError("Video unavailable. This live event has ended")
        assert classify_ytdlp_exception(e) == "ended"

    def test_exception_with_str_method(self):
        """str(e) 的行为由异常基类保证"""

        class CustomError(Exception):
            def __str__(self):
                return "not currently live"

        assert classify_ytdlp_exception(CustomError()) == "offline"
