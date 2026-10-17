#!/usr/bin/env python3
"""A stand-in for the `cortex` CLI that speaks the SDK's stream-json protocol with scripted
replies, so acceptance never spends a Cortex request and scores the same every run.

Point an app at it with CORTEX_CODE_CLI_PATH. What it does, by the prompt it gets:
  "Reply with the single word ok"    -> ok
  a shell command ("echo …")         -> asks to run it (Bash), prints its output when allowed
  "Read the file <path>"             -> asks to Read it (kind Read, absolute path), quotes line 1
  "Without using any tools … question" -> a plain-text question
  a review of a draft                -> reads a standard, then gives a verdict: it objects to a
                                        draft that mentions passwords, approves anything else.
                                        If the app offers a verdict tool it answers through it;
                                        otherwise in prose, stating the concern without a "?"
  anything else                      -> a one-line reply
Every tool it calls on the app's own MCP servers goes through can_use_tool first, the way
Cortex does: kind "MCP" with the tool name on the first line of `resource`."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid

if "-v" in sys.argv[1:2] or "--version" in sys.argv[1:2]:
    print("0.0.0 (fake cortex)")
    sys.exit(0)

SESSION = str(uuid.uuid4())
MODEL = "fake-cortex"
tools: dict[str, list[dict]] = {}          # server -> tool definitions from initialize
counter = 0


class Interrupted(Exception):
    pass


def out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    line = line.strip()
    return json.loads(line) if line else None


def respond(req: dict, payload: dict | None = None) -> None:
    out({"type": "control_response", "response": {"subtype": "success", "request_id": req["request_id"],
                                                   "response": payload or {}}})


def request(body: dict) -> dict:
    """Send a control request to the SDK and wait for its answer, serving interrupts meanwhile."""
    global counter
    counter += 1
    rid = f"fake_{counter}"
    out({"type": "control_request", "request_id": rid, "request": body})
    while True:
        msg = read()
        if not msg:
            continue
        if msg.get("type") == "control_response" and msg["response"].get("request_id") == rid:
            r = msg["response"]
            if r.get("subtype") == "error":
                raise RuntimeError(r.get("error"))
            return r.get("response", {})
        if msg.get("type") == "control_request":
            respond(msg)
            if msg["request"].get("subtype") == "interrupt":
                raise Interrupted


def say(text: str) -> None:
    out({"type": "assistant", "message": {"id": str(uuid.uuid4()), "model": MODEL, "role": "assistant",
                                          "content": [{"type": "text", "text": text}]},
         "parent_tool_use_id": None, "session_id": SESSION})


def use(name: str, args: dict, permission: tuple[str, dict]) -> tuple[bool, str]:
    """Announce a tool call, ask permission, run it, and report the result."""
    tid = "toolu_" + uuid.uuid4().hex[:20]
    out({"type": "assistant", "message": {"id": str(uuid.uuid4()), "model": MODEL, "role": "assistant",
                                          "content": [{"type": "tool_use", "id": tid, "name": name, "input": args}]},
         "parent_tool_use_id": None, "session_id": SESSION})
    kind, inp = permission
    verdict = request({"subtype": "can_use_tool", "tool_name": kind, "input": inp, "tool_use_id": tid,
                       "permission_suggestions": []})
    if verdict.get("behavior") != "allow":
        text, ok = "ERROR: " + (verdict.get("message") or "denied by the user"), False
    elif kind == "Read":
        try:
            with open(args["file_path"]) as f:
                text, ok = f.read(), True
        except OSError as e:
            text, ok = f"ERROR: {e}", False
    elif kind == "Bash":
        r = subprocess.run(args["command"], shell=True, capture_output=True, text=True, timeout=60, check=False)
        text, ok = (r.stdout + r.stderr).strip(), r.returncode == 0
    else:
        server, tool = name.split("__")[1], name.split("__", 2)[2]
        res = request({"subtype": "mcp_message", "server_name": server,
                       "message": {"jsonrpc": "2.0", "id": counter, "method": "tools/call",
                                   "params": {"name": tool, "arguments": args}}})
        result = res.get("mcp_response", {}).get("result", {})
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))
        ok = not result.get("isError")
    out({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": not ok}]},
         "parent_tool_use_id": None, "session_id": SESSION})
    return ok, text


def mcp(server: str, tool: str, args: dict) -> tuple[bool, str]:
    name = f"mcp__{server}__{tool}"
    resource = f"{name}\nInput: {json.dumps(args, indent=1)}"
    return use(name, args, ("MCP", {"action": "call_tool", "resource": resource}))


def find(pattern: str) -> tuple[str, dict] | None:
    for server, defs in tools.items():
        for d in defs:
            if re.search(pattern, d["name"]):
                return server, d
    return None


def verdict_args(schema: dict, ok: bool, concerns: list[str]) -> dict:
    args = {}
    for key, prop in (schema.get("properties") or {}).items():
        t = prop.get("type")
        if t == "boolean":
            args[key] = ok
        elif t == "array":
            args[key] = [] if ok else concerns
        elif prop.get("enum"):
            good = [e for e in prop["enum"] if re.search(r"ok|approve|pass|accept|good|yes", str(e), re.IGNORECASE)]
            bad = [e for e in prop["enum"] if e not in good]
            args[key] = (good or prop["enum"])[0] if ok else (bad or prop["enum"])[0]
        elif t == "string":
            args[key] = "Looks good." if ok else "; ".join(concerns)
    return args


def review(prompt: str) -> str:
    if (s := find(r"(list|read)_?standard")) is not None:
        mcp(s[0], s[1]["name"], {})
    unsafe = re.search(r"password", prompt, re.IGNORECASE)
    concerns = [("The purpose stores customer passwords in plain text on a public share, "
                 "which the security standards forbid.")] if unsafe else []
    if (v := find(r"verdict")) is not None:
        mcp(v[0], v[1]["name"], verdict_args(v[1].get("inputSchema") or {}, not unsafe, concerns))
    if unsafe:
        return "I do not approve this draft. " + concerns[0]
    if (c := find(r"(create|scaffold)_project|new_project")) is not None:
        fields = dict(re.findall(r"\b(name|purpose|owner|scaffold)\b\W{0,3}\s*['\"]?([^'\"\n,]+)", prompt, re.IGNORECASE))
        mcp(c[0], c[1]["name"], {k.lower(): v.strip() for k, v in fields.items()})
    return "The draft looks good against the canon. No concerns."


def turn(prompt: str) -> str:
    if re.search(r"single word ok", prompt, re.IGNORECASE):
        return "ok"
    if re.search(r"without using any tools", prompt, re.IGNORECASE):
        return "Which colour do you like best?"
    if re.search(r"\breview\b", prompt, re.IGNORECASE) and re.search(r"draft|scaffold|project", prompt, re.IGNORECASE):
        return review(prompt)
    r = re.search(r"read the file (\S+?)[.,]?(?:\s|$)", prompt, re.IGNORECASE)
    if r:
        path = os.path.abspath(r.group(1))
        ok, text = use("Read", {"file_path": path}, ("Read", {"action": "read", "resource": path}))
        return f"Its first line is: {text.splitlines()[0] if ok and text else '(could not read it)'}"
    m = re.search(r"(echo\s+[\w.-]+)", prompt)
    if m and re.search(r"shell|command|run", prompt, re.IGNORECASE):
        cmd = m.group(1)
        ok, text = use("Bash", {"command": cmd}, ("Bash", {"action": "execute_command", "resource": cmd}))
        return f"It printed: {text}" if ok else "I did not run it."
    return "Noted."


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))


while True:
    msg = read()
    if not msg:
        continue
    if msg.get("type") == "control_request":
        sub = msg["request"].get("subtype")
        if sub == "initialize":
            tools.update(msg["request"].get("sdkMcpToolDefinitions") or {})
            respond(msg, {"commands": [], "models": [MODEL]})
        else:
            respond(msg)
        continue
    if msg.get("type") != "user":
        continue
    start = time.time()
    out({"type": "system", "subtype": "init", "uuid": str(uuid.uuid4()), "session_id": SESSION,
         "cwd": ".", "model": MODEL, "tools": [], "mcp_servers": [], "permissionMode": "default"})
    try:
        reply, subtype = turn(text_of(msg["message"]["content"])), "success"
        say(reply)
    except Interrupted:
        reply, subtype = "", "error_during_execution"
    out({"type": "result", "subtype": subtype, "is_error": subtype != "success", "num_turns": 1,
         "duration_ms": int((time.time() - start) * 1000) + 1, "duration_api_ms": 1,
         "session_id": SESSION, "result": reply, "uuid": str(uuid.uuid4())})
