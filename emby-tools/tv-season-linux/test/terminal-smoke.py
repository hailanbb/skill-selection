"""Linux PTY acceptance: actual Chinese menus, no remote services or credentials."""
import os
import pty
import select
import signal
import subprocess
import tempfile
import time
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="tvflow-pty-") as folder:
    env = dict(os.environ, TVFLOW_HOME=folder, TERM="xterm-256color")
    master, slave = pty.openpty()
    app = subprocess.Popen(["node", "bin/tvflow.js"], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
    os.close(slave)
    transcript = bytearray()

    def expect(text):
        start = time.monotonic()
        needle = text.encode("utf-8")
        while time.monotonic() - start < 15:
            if needle in transcript:
                transcript.clear()
                return
            if select.select([master], [], [], 0.1)[0]:
                transcript.extend(os.read(master, 65536))
        raise AssertionError(f"Missing {text}: {transcript.decode('utf-8', errors='replace')}")

    try:
        expect("请选择：")
        os.write(master, b"9\n")
        expect("1 浏览并选择电视剧/动漫分类")
        os.write(master, b"b\n")
        expect("q 退出界面")
        os.write(master, b"8\n")
        expect("7 报告与保存路径")
        os.write(master, b"7\n")
        expect("完整记录目录")
        os.write(master, b"b\n")
        expect("7 报告与保存路径")
        os.write(master, b"b\n")
        expect("q 退出界面")
        os.write(master, b"q\n")
        assert app.wait(timeout=10) == 0
        lock = Path(folder, "daemon.lock")
        assert lock.exists(), "Menu exit must leave daemon running"
        os.kill(int(lock.read_text(encoding="utf-8")), 0)
        print("Linux PTY菜单、中文、返回键和退出后后台存活：通过")
    finally:
        if app.poll() is None:
            app.kill()
            app.wait()
        lock = Path(folder, "daemon.lock")
        if lock.exists():
            try:
                os.kill(int(lock.read_text(encoding="utf-8")), signal.SIGTERM)
            except ProcessLookupError:
                pass
            for _ in range(50):
                if not lock.exists():
                    break
                time.sleep(0.1)
        os.close(master)
