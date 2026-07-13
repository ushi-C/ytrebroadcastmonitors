"""
test_scan_state_store.py — 测试 ScanStateStore 线程安全读写
"""

import sys
import os
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.models.scan_state_store import ScanStateStore


class TestScanStateBasic:
    """基本读写操作"""

    def setup_method(self):
        self.store = ScanStateStore()

    def test_initial_state(self):
        s = self.store.get_snapshot()
        assert s["is_running"] is False
        assert s["is_monitoring"] is False
        assert s["progress"] == 0
        assert s["total"] == 0
        assert s["results"] == []

    def test_reset_for_new_scan(self):
        self.store.set_running(False)
        self.store.add_results([{"title": "old"}])
        self.store.reset_for_new_scan()
        s = self.store.get_snapshot()
        assert s["is_running"] is True
        assert s["is_monitoring"] is False
        assert s["progress"] == 0
        assert s["total"] == 0
        assert s["results"] == []

    def test_set_total_and_progress(self):
        self.store.set_total(100)
        self.store.add_progress(30)
        self.store.add_progress(20)
        s = self.store.get_snapshot()
        assert s["total"] == 100
        assert s["progress"] == 50

    def test_set_running_monitoring(self):
        self.store.set_running(True)
        self.store.set_monitoring(True)
        s = self.store.get_snapshot()
        assert s["is_running"] is True
        assert s["is_monitoring"] is True

        self.store.set_running(False)
        self.store.set_monitoring(False)
        s = self.store.get_snapshot()
        assert s["is_running"] is False
        assert s["is_monitoring"] is False

    def test_add_results(self):
        items = [
            {"title": "Channel A", "url": "https://a.com"},
            {"title": "Channel B", "url": "https://b.com"},
        ]
        self.store.add_results(items)
        s = self.store.get_snapshot()
        assert len(s["results"]) == 2
        assert s["results"][0]["title"] == "Channel A"
        assert s["results"][1]["title"] == "Channel B"

    def test_add_empty_results(self):
        self.store.add_results([])
        s = self.store.get_snapshot()
        assert s["results"] == []

    def test_replace_results(self):
        self.store.add_results([{"title": "old"}])
        self.store.replace_results([{"title": "new1"}, {"title": "new2"}])
        s = self.store.get_snapshot()
        assert len(s["results"]) == 2
        assert s["results"][0]["title"] == "new1"


class TestScanStateSnapshotIsolation:
    """快照与内部状态隔离"""

    def setup_method(self):
        self.store = ScanStateStore()

    def test_snapshot_list_isolated(self):
        self.store.add_results([{"title": "orig"}])
        snap = self.store.get_snapshot()
        snap["results"].append({"title": "evil"})
        # 内部状态不应受污染
        s2 = self.store.get_snapshot()
        assert len(s2["results"]) == 1
        assert s2["results"][0]["title"] == "orig"

    def test_snapshot_dict_shallow_copy(self):
        self.store.add_results([{"title": "orig", "url": "https://x.com"}])
        snap = self.store.get_snapshot()
        snap["results"][0]["url"] = "https://hacked.com"
        # dict(r) 浅拷贝: 顶层 key 被替换, 但内部 dict 的 value 被共享
        # 这个测试验证 dict(r) 后外部修改 value 不会影响内部（因为值是 str 不可变）
        s2 = self.store.get_snapshot()
        # 修改后因 url 是 str（不可变），赋值写的是 snapshot dict 的 key，原 dict 不受影响
        assert s2["results"][0]["url"] == "https://x.com"

    def test_progress_snapshot_isolated(self):
        self.store.add_progress(10)
        snap = self.store.get_snapshot()
        snap["progress"] = 999
        assert self.store.get_snapshot()["progress"] == 10


class TestStripAvatar:
    """avatar 字段剥离逻辑"""

    def setup_method(self):
        self.store = ScanStateStore()

    def test_avatar_stripped_on_add(self):
        self.store.add_results([
            {"title": "ch", "avatar": "https://img.example.com/avatar.jpg"}
        ])
        s = self.store.get_snapshot()
        assert "avatar" not in s["results"][0]

    def test_avatar_stripped_on_replace(self):
        self.store.replace_results([
            {"title": "ch", "avatar": "https://img.example.com/avatar.jpg"}
        ])
        s = self.store.get_snapshot()
        assert "avatar" not in s["results"][0]

    def test_no_avatar_key_preserved(self):
        self.store.add_results([{"title": "ch", "url": "https://x.com"}])
        s = self.store.get_snapshot()
        assert s["results"][0]["title"] == "ch"
        assert s["results"][0]["url"] == "https://x.com"


class TestScanStateConcurrency:
    """并发安全性"""

    def setup_method(self):
        self.store = ScanStateStore()

    def test_concurrent_add_results(self):
        """多线程同时追加结果，不应丢失或损坏数据"""
        errors = []

        def append_batch(batch_id, count):
            try:
                items = [{"title": f"batch{batch_id}-{i}"} for i in range(count)]
                self.store.add_results(items)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(10):
            t = threading.Thread(target=append_batch, args=(i, 10))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert not errors, f"concurrent errors: {errors}"
        s = self.store.get_snapshot()
        assert len(s["results"]) == 100

    def test_concurrent_read_write(self):
        """读写并发，读快照应始终一致"""
        self.store.add_results([{"title": f"init-{i}"} for i in range(100)])
        errors = []

        def reader():
            for _ in range(50):
                try:
                    snap = self.store.get_snapshot()
                    # 快照应至少包含初始数据
                    assert len(snap["results"]) >= 100
                except Exception as e:
                    errors.append(str(e))

        def writer():
            for i in range(50):
                try:
                    self.store.add_results([{"title": f"extra-{i}"}])
                    self.store.set_running(i % 2 == 0)
                except Exception as e:
                    errors.append(str(e))

        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=reader))
            threads.append(threading.Thread(target=writer))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"concurrent r/w errors: {errors}"
