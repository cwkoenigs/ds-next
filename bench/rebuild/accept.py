"""Acceptance checks for the rebuild, fixed before it ran. Run: python accept.py <repo> <console-script>

Static checks read the repo; driven checks run the built terminal in a pseudo-terminal the way a
person would. Each check passes or fails; nothing is judged by eye."""
from __future__ import annotations

import os
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

REPO, SCRIPT = Path(sys.argv[1]).resolve(), sys.argv[2]
DS_NEXT = shutil.which("ds-next") or str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "ds-next")
results: list[tuple[str, bool, str]] = []
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]")


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def run(*cmd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout, check=False)


class Term:
    """The built terminal in a pty: send keys, wait for text."""

    def __init__(self, cwd: Path):
        exe = str(REPO / ".venv" / "bin" / SCRIPT)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(cwd)
            os.environ.update(COLUMNS="120", LINES="40", PROMPT_TOOLKIT_NO_CPR="1")
            os.execv(exe, [exe])
        self.buf = ""

    def read(self, secs: float) -> bool:
        end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if r:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    return False
                if not data:
                    return False
                self.buf += ANSI.sub("", data.decode("utf8", "replace"))
        return True

    def send(self, keys: str) -> None:
        for ch in keys:
            os.write(self.fd, ch.encode())
            time.sleep(0.02)

    def wait(self, pattern: str, secs: float) -> str | None:
        start, end = len(self.buf), time.time() + secs
        while time.time() < end:
            if not self.read(0.5):
                break
            m = re.search(pattern, self.buf[start:], re.IGNORECASE | re.DOTALL)
            if m:
                self.read(0.8)
                return self.buf[start:]
        return None

    def alive(self) -> bool:
        return os.waitpid(self.pid, os.WNOHANG) == (0, 0)

    def close(self) -> None:
        try:
            os.kill(self.pid, 9)
        except ProcessLookupError:
            pass


# ---- static
check("uv sync", run("uv", "sync", "-q").returncode == 0)
t = run("uv", "run", "pytest", "-q")
check("tests pass", t.returncode == 0, (t.stdout.strip().splitlines() or [""])[-1])
lint = run("uv", "run", "ruff", "check", ".")
check("ruff clean", lint.returncode == 0, (lint.stdout.strip().splitlines() or [""])[-1])
rec = run(DS_NEXT, "reconcile")
check("ds-next reconcile: no errors", rec.returncode == 0, rec.stdout.strip().splitlines()[0] if rec.stdout else "")
manifest = tomllib.loads((REPO / ".ds" / "manifest.toml").read_text())
used = sorted(manifest.get("blocks", {}))
core = ["block-cortex-session", "block-approver", "block-claude-render", "block-tui-widgets"]
check("uses the UI blocks", all(b in used for b in core), f"blocks: {', '.join(used) or 'none'}")
src = "\n".join(p.read_text() for p in (REPO / "src").rglob("*.py"))
check("gotcha: no allowed_tools allowlist", not re.search(r"allowed_tools\s*=", src))
check("gotcha: no ensure_ascii=True", "ensure_ascii=True" not in src)

# ---- driven
work = Path(tempfile.mkdtemp(prefix="accept-"))
term = Term(work)
try:
    out = term.wait(r"›", 60)
    check("launches to a prompt", out is not None)
    check("welcome counts the canon", bool(out and re.search(r"standard", out) and re.search(r"block", out)))
    term.send("/help\r")
    out = term.wait(r"/exit", 20) or ""
    check("/help lists the commands", all(c in out for c in ("/canon", "/blocks", "/status", "/new", "/clear", "/exit")))
    term.send("/canon\r")
    out = term.wait(r"gotcha-cortex-sdk|testing", 20) or ""
    check("/canon lists standards", bool(out))
    term.send("/canon testing\r")
    check("/canon <id> prints it", term.wait(r"Testing and QA|Risk-Based Test Mix", 20) is not None)
    term.send("/blocks\r")
    check("/blocks lists blocks", term.wait(r"block-cortex-session", 20) is not None)
    term.send("/no-such-command\r")
    check("unknown command says so", term.wait(r"unknown", 20) is not None)
    term.send("Run this shell command and show its output: echo approval-test-42\r")
    out = term.wait(r"allow|approve|\by/n\b|\[y", 180)
    asked_first = bool(out) and "approval-test-42\n" not in (out or "").split("allow")[0].lower()
    check("a shell command asks first", asked_first)
    if out:
        term.send("y\r")
    check("then runs after approval", term.wait(r"approval-test-42", 180) is not None)
    term.wait(r"›", 60)
    term.send("/new\r")
    picked = term.wait(r"python|scaffold", 30)
    term.send("\r")                              # first scaffold
    term.wait(r"name|purpose", 20)
    term.send("made-by-rebuild\tA repository created by the rebuilt terminal\r")
    for _ in range(6):                           # approve whatever it asks, up to six times
        out = term.wait(r"allow|approve|\by/n\b|\[y|created|›", 240) or ""
        if re.search(r"allow|approve|\by/n\b|\[y", out, re.IGNORECASE):
            term.send("y\r")
        made = work / "made-by-rebuild"
        if (made / "pyproject.toml").is_file():
            break
    made = work / "made-by-rebuild"
    check("/new creates the repo from a scaffold", (made / "pyproject.toml").is_file() and bool(picked),
          ", ".join(sorted(p.name for p in made.iterdir())) if made.is_dir() else "no folder")
    log = subprocess.run(["git", "-C", str(made), "log", "--oneline"], capture_output=True, text=True, check=False)
    check("/new commits it", made.is_dir() and log.returncode == 0 and bool(log.stdout.strip()))
    term.send("/exit\r")
    term.read(5)
    check("/exit leaves", not term.alive())
finally:
    term.close()
    (work / "transcript.txt").write_text(term.buf)
    print(f"transcript: {work / 'transcript.txt'}")

passed = sum(ok for _, ok, _ in results)
print(f"\n{passed}/{len(results)} checks passed")
