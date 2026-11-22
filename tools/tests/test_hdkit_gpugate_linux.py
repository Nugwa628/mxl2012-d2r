"""Exercise the Linux GPU gate with fake sysfs files, load averages and shared slot locks."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit import gpugate  # noqa: E402


class FakeSys:
    def __init__(self, cards):
        self.root = tempfile.mkdtemp()
        self.paths = []
        for i, v in enumerate(cards):
            d = os.path.join(self.root, f"card{i}", "device")
            os.makedirs(d)
            p = os.path.join(d, "gpu_busy_percent")
            with open(p, "w") as f:
                f.write(f"{v}\n")
            self.paths.append(p)
        self.glob = os.path.join(self.root, "card*", "device", "gpu_busy_percent")
        self.stat = os.path.join(self.root, "stat")

    def set(self, card, value):
        with open(self.paths[card], "w") as f:
            f.write(f"{value}\n")

    def write_stat(self, user, idle):
        with open(self.stat, "w") as f:  # user nice system idle iowait irq softirq steal guest guest_nice
            f.write(f"cpu  {user} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 0 0 1 0 0 0 0 0 0\n")


class ReadLinux(unittest.TestCase):
    def test_median_of_busiest_card_and_normalized_load(self):
        fs = FakeSys([10, 25, "nan", 101, "unreadable"])
        samples = iter([50, 15, 90, 5])

        def sleep(_):
            fs.set(0, next(samples))

        with mock.patch.object(os, "getloadavg", return_value=(2.5, 80, 40), create=True), \
                mock.patch.object(os, "cpu_count", return_value=4):
            self.assertEqual(gpugate.read_linux(drm_glob=fs.glob, sleep=sleep), (25.0, "amdgpu", 62.5))

    def test_missing_gpu_counter_still_reports_cpu_load(self):
        fs = FakeSys([])
        with mock.patch.object(os, "getloadavg", return_value=(6, 0, 0), create=True), \
                mock.patch.object(os, "cpu_count", return_value=4):
            self.assertEqual(gpugate.read_linux(samples=1, drm_glob=fs.glob), (None, "", 150.0))

    def test_unavailable_cpu_load(self):
        fs = FakeSys([3])
        with mock.patch.object(os, "getloadavg", side_effect=OSError, create=True), \
                mock.patch.object(os, "cpu_count", return_value=4):
            self.assertEqual(gpugate.read_linux(samples=1, drm_glob=fs.glob), (3.0, "amdgpu", None))
        with mock.patch.object(os, "cpu_count", return_value=None):
            self.assertEqual(gpugate.read_linux(samples=1, drm_glob=fs.glob), (3.0, "amdgpu", None))

    def test_median_of_busiest_card_and_cpu_share(self):
        fs = FakeSys([10, 3])
        fs.write_stat(1000, 9000)
        values = iter([90, 15, 25, 30])  # card 0 over the next samples: 10 (first read), 90, 15, 25, 30
        stat_after = {"done": False}

        def sleep(_):
            fs.set(0, next(values))
            if not stat_after["done"]:
                fs.write_stat(1000 + 300, 9000 + 700)  # 30 % busy between the two readings
                stat_after["done"] = True
        gpu, eng, cpu = gpugate.read_linux(samples=5, every=0, drm_glob=fs.glob, proc_stat=fs.stat, sleep=sleep)
        self.assertEqual(gpu, 25.0)  # median of 10, 90, 15, 25, 30
        self.assertEqual(eng, "amdgpu")
        self.assertAlmostEqual(cpu, 30.0)

    def test_no_amdgpu_file_means_cpu_only(self):
        fs = FakeSys([])
        fs.write_stat(10, 10)
        gpu, eng, cpu = gpugate.read_linux(samples=2, every=0, drm_glob=fs.glob, proc_stat=fs.stat, sleep=lambda _: None)
        self.assertEqual((gpu, eng), (None, ""))
        self.assertIsNone(cpu)  # no time passed between the readings: unknown, not 0

    def test_unreadable_proc_stat(self):
        self.assertIsNone(gpugate._cpu_times("/nonexistent/stat"))

    def test_read_counters_uses_linux_path_on_linux(self):
        with mock.patch.object(gpugate.sys, "platform", "linux"), \
                mock.patch.object(gpugate, "read_linux", return_value=(5.0, "amdgpu", 7.0)) as rl:
            self.assertEqual(gpugate.read_counters(), (5.0, "amdgpu", 7.0))
        rl.assert_called_once()


class CheckOnLinux(unittest.TestCase):
    def test_runtime_check_uses_machine_locks_then_linux_limits(self):
        fs = FakeSys([20])
        read_linux = gpugate.read_linux
        with tempfile.TemporaryDirectory() as root:
            lock = Path(root, "game.lock.5")
            lock.mkdir()
            config = Path(root, "machine.json")
            config.write_text(json.dumps({"shared_lock_dir": root}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"MXL_MACHINE": str(config), "MXL_LOCKS": "", "HDKIT_LOCK_GLOBS": ""}), \
                    mock.patch.object(gpugate.sys, "platform", "linux"), \
                    mock.patch.object(gpugate, "read_linux", side_effect=lambda: read_linux(samples=1, drm_glob=fs.glob)) as read, \
                    mock.patch.object(os, "getloadavg", return_value=(3, 0, 0), create=True), \
                    mock.patch.object(os, "cpu_count", return_value=5):
                self.assertEqual(gpugate.check().as_dict(), {
                    "free": False, "why": "lock held: game.lock.5", "locks": ["game.lock.5"],
                    "gpu_percent": None, "gpu_engine": "", "cpu_percent": None,
                })
                read.assert_not_called()
                lock.rmdir()
                self.assertTrue(gpugate.check().why.startswith("GPU busy"))
                fs.set(0, 19)
                self.assertTrue(gpugate.check().why.startswith("CPU busy"))
                self.assertEqual(gpugate.check(cpu_max=61).as_dict(), {
                    "free": True, "why": "free", "locks": [],
                    "gpu_percent": 19.0, "gpu_engine": "amdgpu", "cpu_percent": 60.0,
                })

    def test_windows_thresholds_allow_equality(self):
        with mock.patch.object(gpugate.sys, "platform", "win32"):
            self.assertTrue(gpugate.check([], counters=lambda: (20.0, "3D", 60.0)).free)

    def test_lock_first_then_gpu_then_cpu(self):
        locks = tempfile.mkdtemp()
        lock = os.path.join(locks, "game.lock.5")
        os.makedirs(lock)
        pattern = os.path.join(locks, "game.lock*")
        with mock.patch.object(gpugate, "read_counters", side_effect=AssertionError("not read while a lock is held")):
            rd = gpugate.check([pattern])
        self.assertFalse(rd.free)
        self.assertIn("game.lock.5", rd.why)
        os.rmdir(lock)
        for reading, free in (((50.0, "amdgpu", 5.0), False), ((5.0, "amdgpu", 80.0), False), ((5.0, "amdgpu", 5.0), True),
                              ((None, "", 5.0), True), ((None, "", None), False)):
            with mock.patch.object(gpugate, "read_counters", return_value=reading):
                self.assertEqual(gpugate.check([pattern]).free, free, reading)


if __name__ == "__main__":
    unittest.main()
