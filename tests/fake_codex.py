"""A stand-in for `codex app-server`: the same JSON-RPC, one scripted turn per message. It reasons, says
something, calls the ds tool canon_list, asks to run `npm test`, then finishes (or stops, if the answer
was no). Every message it receives is appended to $FAKE_CODEX_LOG as one JSON line.
FAKE_CODEX_SILENT_TURN: play the turn but never answer turn/start, as a Codex that hangs might."""
import json
import os
import sys
import threading
import time

LOG = os.environ.get("FAKE_CODEX_LOG")
THREAD = "thread-1"
lock = threading.Lock()
replies: dict[int, dict] = {}
answered: dict[int, threading.Event] = {}
next_id = [1000]
turn = [0]
live = {"stopped": False}


def out(m):
    with lock:
        sys.stdout.write(json.dumps(m) + "\n")
        sys.stdout.flush()


def note(method, params):
    out({"method": method, "params": params})


def ask(method, params):
    rid = next_id[0] = next_id[0] + 1
    done = answered[rid] = threading.Event()     # held here: the reply may pop it before wait() is reached
    out({"id": rid, "method": method, "params": params})
    done.wait()
    return replies.pop(rid)


def play(text):
    turn[0] += 1
    n = turn[0]
    turn_id = f"turn-{n}"
    live["stopped"] = False
    note("turn/started", {"threadId": THREAD, "turn": {"id": turn_id, "status": "inProgress", "items": []}})
    note("item/completed", {"threadId": THREAD, "turnId": turn_id, "item": {"type": "reasoning", "id": f"r{n}", "summary": [f"The person said: {text}"], "content": []}})
    note("item/completed", {"threadId": THREAD, "turnId": turn_id, "item": {"type": "agentMessage", "id": f"m{n}", "text": "I'll list the standards, then run the tests."}})
    dt = {"type": "dynamicToolCall", "id": f"dt{n}", "namespace": None, "tool": "canon_list", "arguments": {"tags": "python"}, "status": "inProgress", "contentItems": None, "success": None}
    note("item/started", {"threadId": THREAD, "turnId": turn_id, "item": dt})
    r = ask("item/tool/call", {"threadId": THREAD, "turnId": turn_id, "callId": dt["id"], "namespace": None, "tool": "canon_list", "arguments": {"tags": "python"}})
    note("item/completed", {"threadId": THREAD, "turnId": turn_id, "item": {**dt, "status": "completed", "contentItems": r.get("contentItems"), "success": r.get("success")}})
    if live["stopped"]:
        return
    cmd = {"type": "commandExecution", "id": f"c{n}", "command": "/bin/bash -lc 'npm test'", "cwd": "/work", "status": "inProgress", "aggregatedOutput": None, "exitCode": None}
    note("item/started", {"threadId": THREAD, "turnId": turn_id, "item": cmd})
    a = ask("item/commandExecution/requestApproval", {"threadId": THREAD, "turnId": turn_id, "itemId": cmd["id"], "command": "/bin/bash -lc 'npm test'", "reason": "Run the tests"})
    if a.get("decision") not in ("accept", "acceptForSession"):
        note("item/completed", {"threadId": THREAD, "turnId": turn_id, "item": {**cmd, "status": "declined"}})
        note("turn/completed", {"threadId": THREAD, "turn": {"id": turn_id, "status": "interrupted", "items": [], "error": None, "durationMs": 900}})
        return
    note("item/completed", {"threadId": THREAD, "turnId": turn_id, "item": {**cmd, "status": "completed", "exitCode": 0, "aggregatedOutput": "78 passed in 3.1s\nTest Files 9 passed\n"}})
    note("item/completed", {"threadId": THREAD, "turnId": turn_id, "item": {"type": "agentMessage", "id": f"m{n}b", "text": "The tests pass."}})
    note("thread/tokenUsage/updated", {"threadId": THREAD, "turnId": turn_id, "tokenUsage": {"last": {"totalTokens": 45230}, "total": {"totalTokens": 45230}}})
    note("turn/completed", {"threadId": THREAD, "turn": {"id": turn_id, "status": "completed", "items": [], "error": None, "durationMs": 15200}})


for line in sys.stdin:
    m = json.loads(line)
    if LOG:
        with open(LOG, "a") as f:
            f.write(line if line.endswith("\n") else line + "\n")
    if "method" not in m:
        replies[m["id"]] = m.get("result") or {}
        answered.pop(m["id"]).set()
        continue
    method, rid = m["method"], m.get("id")
    if method == "initialize":
        out({"id": rid, "result": {"userAgent": "fake-codex", "codexHome": "/tmp", "platformFamily": "unix", "platformOs": "linux"}})
    elif method in ("thread/start", "thread/resume"):
        out({"id": rid, "result": {"thread": {"id": THREAD, "model": "gpt-test"}, "model": "gpt-test", "modelProvider": "openai"}})
        note("thread/started", {"thread": {"id": THREAD}})
    elif method == "turn/start":
        if not os.environ.get("FAKE_CODEX_SILENT_TURN"):
            out({"id": rid, "result": {"turn": {"id": f"turn-{turn[0] + 1}", "status": "inProgress", "items": []}}})
        text = " ".join(i.get("text", "") for i in m["params"]["input"])
        threading.Thread(target=play, args=(text,), daemon=True).start()
        time.sleep(0.01)
    elif method == "turn/interrupt":
        live["stopped"] = True
        out({"id": rid, "result": {}})
        note("turn/completed", {"threadId": THREAD, "turn": {"id": m["params"]["turnId"], "status": "interrupted", "items": [], "error": None, "durationMs": 500}})
    elif rid is not None:
        out({"id": rid, "error": {"code": -32601, "message": f"fake-codex: no {method}"}})
