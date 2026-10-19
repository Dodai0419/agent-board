"""Build synthetic Claude Code and Codex session folders whose states are known.

Times are relative to `now`, so the same states come out whenever it is run.
"""
import json, os, sys, time

CWD = "/home/dev/shop"
PROJ = "-home-dev-shop"


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z"


def _write(path, records, mtime):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")  # compact, as the real tools write
    os.utime(path, (mtime, mtime))


def user(t, text, sid):
    return {"type": "user", "sessionId": sid, "timestamp": _iso(t), "cwd": CWD, "message": {"role": "user", "content": text}}


def asst(t, sid, mid, blocks, stop, usage):
    return {"type": "assistant", "sessionId": sid, "timestamp": _iso(t), "cwd": CWD, "requestId": "req_" + mid,
            "message": {"id": "msg_" + mid, "role": "assistant", "model": "claude-sonnet-5-5", "content": blocks,
                        "stop_reason": stop, "usage": usage}}


def result(t, sid, tid):
    return {"type": "user", "sessionId": sid, "timestamp": _iso(t), "cwd": CWD,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": "ok"}]}}


U = lambda i, o, cr=0, cw=0: {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}

# id -> (records builder, mtime offset in seconds before now)
CLAUDE = {
    "11111111-1111-4111-8111-111111111111": "working",   # Bash call pending, 5 s ago
    "22222222-2222-4222-8222-222222222222": "blocked",   # Edit waiting for approval 60 s
    "33333333-3333-4333-8333-333333333333": "turn",      # answered, end_turn
    "44444444-4444-4444-8444-444444444444": "waiting",   # Task sub-agent running
    "55555555-5555-4555-8555-555555555555": "idle",      # 2 h old
    "66666666-6666-4666-8666-666666666666": "turn",      # Esc by the person
}


def build(root, now=None):
    now = now or time.time()
    proj = os.path.join(root, "claude", "projects", PROJ)
    ids = list(CLAUDE)

    s = ids[0]; t = now - 40
    _write(os.path.join(proj, s + ".jsonl"), [
        user(t, "Fix the failing checkout test", s),
        asst(t + 5, s, "a1", [{"type": "text", "text": "Looking."}, {"type": "tool_use", "id": "tu1", "name": "Read", "input": {"file_path": "a.py"}}], "tool_use", U(1200, 80, 9000, 400)),
        result(t + 6, s, "tu1"),
        asst(t + 30, s, "a2", [{"type": "tool_use", "id": "tu2", "name": "Bash", "input": {"command": "pytest"}}], "tool_use", U(300, 40, 10200, 0)),
    ], now - 5)

    s = ids[1]; t = now - 120
    _write(os.path.join(proj, s + ".jsonl"), [
        {"type": "custom-title", "customTitle": "Refactor cart", "sessionId": s},
        user(t, "Refactor the cart module", s),
        asst(t + 60, s, "b1", [{"type": "tool_use", "id": "tu3", "name": "Edit", "input": {"file_path": "cart.py"}}], "tool_use", U(2000, 300, 0, 5000)),
    ], now - 60)

    s = ids[2]; t = now - 300
    # the same message streamed as two records with identical usage: must be counted once
    _write(os.path.join(proj, s + ".jsonl"), [
        user(t, "What does the payment service do?", s),
        asst(t + 10, s, "c1", [{"type": "thinking", "thinking": "..."}], None, U(500, 120, 0, 0)),
        asst(t + 11, s, "c1", [{"type": "text", "text": "It charges cards."}], "end_turn", U(500, 120, 0, 0)),
    ], now - 280)

    s = ids[3]; t = now - 200
    _write(os.path.join(proj, s + ".jsonl"), [
        user(t, "Audit the repo for secrets", s),
        asst(t + 20, s, "d1", [{"type": "tool_use", "id": "tu4", "name": "Task", "input": {"prompt": "scan"}}], "tool_use", U(700, 60, 0, 0)),
    ], now - 120)
    sub = os.path.join(proj, s, "subagents", "agent-abc.jsonl")
    _write(sub, [asst(t + 30, s, "d2", [{"type": "text", "text": "scanning"}], None, U(100, 10))], now - 20)

    s = ids[4]; t = now - 7300
    _write(os.path.join(proj, s + ".jsonl"), [
        user(t, "Write release notes", s),
        asst(t + 20, s, "e1", [{"type": "text", "text": "Done."}], "end_turn", U(900, 400)),
    ], now - 7200)

    s = ids[5]; t = now - 100
    _write(os.path.join(proj, s + ".jsonl"), [
        user(t, "Rename every helper", s),
        asst(t + 10, s, "f1", [{"type": "tool_use", "id": "tu5", "name": "Bash", "input": {"command": "grep"}}], "tool_use", U(400, 30)),
        {"type": "user", "sessionId": s, "timestamp": _iso(t + 20), "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}},
    ], now - 80)

    codex = os.path.join(root, "codex")
    day = time.strftime("%Y/%m/%d", time.localtime(now))
    def roll(cid, recs, mt):
        _write(os.path.join(codex, "sessions", day, f"rollout-2026-10-16T10-00-00-{cid}.jsonl"), recs, mt)
    meta = lambda cid, t: {"timestamp": _iso(t), "type": "session_meta", "payload": {"id": cid, "cwd": CWD, "source": "cli", "originator": "codex_cli_rs"}}
    ev = lambda t, p: {"timestamp": _iso(t), "type": "event_msg", "payload": p}
    tok = lambda t, i, c, o: ev(t, {"type": "token_count", "info": {"total_token_usage": {"input_tokens": i, "cached_input_tokens": c, "output_tokens": o, "total_tokens": i + o}}})
    c1, c2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    t = now - 90
    roll(c1, [meta(c1, t), ev(t, {"type": "task_started"}), ev(t + 1, {"type": "user_message", "message": "Add dark mode to settings"}),
              tok(t + 30, 5000, 3000, 200), tok(t + 60, 9000, 6000, 450)], now - 10)
    t = now - 600
    roll(c2, [meta(c2, t), ev(t, {"type": "task_started"}), ev(t + 1, {"type": "user_message", "message": "Bump the API version"}),
              tok(t + 30, 4000, 1000, 300), ev(t + 40, {"type": "task_complete"})], now - 560)
    with open(os.path.join(codex, "session_index.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"id": c2, "thread_name": "API version bump"}, separators=(",", ":")) + "\n")
    return {"claude": os.path.join(root, "claude"), "projects": os.path.join(root, "claude", "projects"), "codex": codex}


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1])))
