"""
test_normalize_url.py — 测试 normalize_channel_live_url 纯函数
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.services.scanner_utils import normalize_channel_live_url


class TestNormalizeChannelId:
    """纯 channel_id 输入"""

    def test_bare_channel_id(self):
        url, cid = normalize_channel_live_url("UCXuqSBlHAE6Xw-yeJA0Tunw")
        assert url == "https://www.youtube.com/channel/UCXuqSBlHAE6Xw-yeJA0Tunw/live"
        assert cid == "UCXuqSBlHAE6Xw-yeJA0Tunw"

    def test_channel_id_with_whitespace(self):
        url, cid = normalize_channel_live_url("  UC1234567890123456789012  ")
        assert url == "https://www.youtube.com/channel/UC1234567890123456789012/live"
        assert cid == "UC1234567890123456789012"


class TestNormalizeHttpUrl:
    """HTTP URL 输入的各种变体"""

    def test_full_live_url(self):
        url, cid = normalize_channel_live_url(
            "https://www.youtube.com/channel/UCXuqSBlHAE6Xw-yeJA0Tunw/live"
        )
        assert url == "https://www.youtube.com/channel/UCXuqSBlHAE6Xw-yeJA0Tunw/live"
        assert cid == "UCXuqSBlHAE6Xw-yeJA0Tunw"

    def test_live_url_trailing_slash(self):
        url, cid = normalize_channel_live_url(
            "https://www.youtube.com/channel/UCXuqSBlHAE6Xw-yeJA0Tunw/live/"
        )
        assert url == "https://www.youtube.com/channel/UCXuqSBlHAE6Xw-yeJA0Tunw/live"
        assert cid == "UCXuqSBlHAE6Xw-yeJA0Tunw"

    def test_channel_base_url(self):
        url, cid = normalize_channel_live_url(
            "https://www.youtube.com/channel/UCXuqSBlHAE6Xw-yeJA0Tunw"
        )
        assert url == "https://www.youtube.com/channel/UCXuqSBlHAE6Xw-yeJA0Tunw/live"
        assert cid == "UCXuqSBlHAE6Xw-yeJA0Tunw"

    def test_handle_url_with_at(self):
        url, cid = normalize_channel_live_url("https://www.youtube.com/@LinusTechTips")
        assert url == "https://www.youtube.com/@LinusTechTips/live"
        assert cid == ""

    def test_handle_url_with_at_subpath(self):
        url, cid = normalize_channel_live_url(
            "https://www.youtube.com/@LinusTechTips/videos"
        )
        assert url == "https://www.youtube.com/@LinusTechTips/videos/live"
        assert cid == ""

    def test_bare_url_no_channel_no_handle(self):
        url, cid = normalize_channel_live_url("https://www.youtube.com/watch?v=abc123")
        assert url == "https://www.youtube.com/watch?v=abc123/live"
        assert cid == ""


class TestNormalizeHandle:
    """@handle 输入"""

    def test_bare_at_handle(self):
        url, cid = normalize_channel_live_url("@LinusTechTips")
        assert url == "https://www.youtube.com/@LinusTechTips/live"
        assert cid == ""

    def test_bare_at_handle_with_spaces(self):
        url, cid = normalize_channel_live_url("  @TestChannel  ")
        assert url == "https://www.youtube.com/@TestChannel/live"
        assert cid == ""


class TestNormalizePlainName:
    """纯文字名称输入"""

    def test_plain_name(self):
        url, cid = normalize_channel_live_url("LinusTechTips")
        assert url == "https://www.youtube.com/@LinusTechTips/live"
        assert cid == ""

    def test_plain_name_with_spaces(self):
        url, cid = normalize_channel_live_url("  SomeChannelName  ")
        assert url == "https://www.youtube.com/@SomeChannelName/live"
        assert cid == ""
