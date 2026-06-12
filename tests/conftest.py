import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERP = os.path.join(ROOT, "interpreter.py")


def run_fable(rel_path, *args):
    """Run a Fable program headless and return its stdout."""
    env = dict(os.environ, FABLE_HEADLESS="1")
    cmd = [sys.executable, INTERP, os.path.join(ROOT, rel_path), *args]
    kwargs = dict(capture_output=True, text=True, timeout=120, env=env)
    try:
        proc = subprocess.run(cmd, cwd=ROOT, **kwargs)
    except PermissionError:
        # 일부 샌드박스에서는 이 디렉토리로 chdir가 막혀 있다.
        proc = subprocess.run(cmd, **kwargs)
    assert proc.returncode == 0, f"{rel_path} failed:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout
