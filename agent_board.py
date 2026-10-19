#!/usr/bin/env python3
"""agent-board: one table of every Claude Code and Codex session from the last 12 hours.

Who is working, who is blocked on an approval, whose turn it is, and how many tokens each burned.
Session state follows Atoll92/agent-standup (MIT); token totals follow Entelligence-AI/agentplay (Apache-2.0).
Read-only, standard library only, never touches the network.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

HOURS = 12
APPROVAL = re.compile(r"^(Edit|Write|MultiEdit|NotebookEdit)")
ASKS = re.compile(r"^(AskUserQuestion|ExitPlanMode)")
SUBTOOL = re.compile(r"^(Task|Agent)$")
INTERRUPTED = re.compile(r"^\s*\[Request interrupted", re.I)
HARNESS = re.compile(r"<(system-reminder|browser_instruction|ide_selection|ide_opened_file|task-notification|command-name|"
                     r"command-message|command-args|local-command-stdout|local-command-caveat)>[\s\S]*?</\1>\s*")
CODEX_NAME = re.compile(r"^rollout-.*?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$", re.I)
CODEX_TURN = {"task_started", "task_complete", "turn_started", "turn_complete", "turn_aborted"}


def _ms(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
    except (AttributeError, ValueError):
        return 0


def _lines(path, start=0, size=None):
    """Complete JSON records from a byte window of a file; a record cut by the window start is dropped."""
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read(size) if size else f.read()
    lines = data.decode("utf-8", "replace").split("\n")
    if start:
        lines = lines[1:]
    for line in lines:
        if line:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


def _tail(path, size, nbytes):
    return _lines(path, max(0, size - nbytes), nbytes)


def _blocks(rec):
    c = (rec.get("message") or {}).get("content")
    return [{"type": "text", "text": c}] if isinstance(c, str) else [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def _clean(text, n=90):
    return re.sub(r"\s+", " ", text).strip()[:n]


# ---------- Claude Code ----------
def _first_prompt(path):
    for r in _lines(path, 0, 64 * 1024):
        if r.get("type") != "user" or r.get("isMeta") or r.get("isCompactSummary"):
            continue
        t = _clean(HARNESS.sub("", "\n".join(b["text"] for b in _blocks(r) if b.get("type") == "text" and isinstance(b.get("text"), str))))
        if t and t[0] != "<" and not INTERRUPTED.match(t):
            return t
    return None


def _sub_files(session_dir):
    sd = os.path.join(session_dir, "subagents")
    try:
        names = os.listdir(sd)
    except OSError:
        return []
    out = [os.path.join(sd, f) for f in names if f.endswith(".jsonl")]
    wd = os.path.join(sd, "workflows")
    for run in sorted(os.listdir(wd)) if "workflows" in names and os.path.isdir(wd) else []:
        d = os.path.join(wd, run)
        out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if re.match(r"^agent-.*\.jsonl$", f)]
    return out


def _claude_tokens(files):
    """input + output + cache read + cache write, each assistant message once (streamed fragments repeat the usage)."""
    seen, total = set(), 0
    for path in files:
        with open(path, "rb") as f:  # only records that carry usage are worth decoding
            recs = [line for line in f if b'"usage"' in line and b'"assistant"' in line]
        for line in recs:
            try:
                r = json.loads(line)
            except ValueError:  # a record still being written
                continue
            msg = r.get("message") or {}
            u = msg.get("usage")
            if r.get("type") != "assistant" or not isinstance(u, dict):
                continue
            key = msg.get("id") or r.get("requestId") or id(r)
            if key in seen:
                continue
            seen.add(key)
            total += sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return total


def claude_row(path, st, now):
    pend, last_type, last_tool, last_stop, stops, esc, custom, ai = {}, None, False, None, False, False, None, None
    for r in _tail(path, st.st_size, 256 * 1024):
        t = r.get("type")
        if t == "custom-title" and isinstance(r.get("customTitle"), str):
            custom = r["customTitle"]
        elif t == "ai-title" and isinstance(r.get("aiTitle"), str):
            ai = r["aiTitle"]
        ts, bl = _ms(r.get("timestamp")), _blocks(r)
        if t in ("assistant", "user"):
            last_type, last_tool = t, any(b.get("type") == "tool_use" for b in bl)
            last_stop = (r.get("message") or {}).get("stop_reason") if t == "assistant" else None
            stops = stops or bool(last_stop)
            esc = t == "user" and any(b.get("type") == "text" and INTERRUPTED.match(b.get("text") or "") for b in bl)
            if esc:
                pend.clear()
        for b in bl:
            if b.get("type") == "tool_use":
                pend[b.get("id")] = (b.get("name") or "", ts)
            elif b.get("type") == "tool_result":
                pend.pop(b.get("tool_use_id"), None)

    mtime = st.st_mtime * 1000
    age = now - mtime
    state, tool, age_ms = "idle", "", age
    if age < 30 * 60e3:
        if pend:
            name, ts = list(pend.values())[-1]
            age_ms, tool = now - (ts or mtime), name
            state = ("waiting" if SUBTOOL.match(name) else
                     "blocked" if (ASKS.match(name) and age_ms > 4000) or (APPROVAL.match(name) and age_ms > 15000) else "working")
        elif esc:
            state = "turn"
        elif last_type == "assistant" and not last_tool and last_stop != "tool_use" and not (last_stop is None and stops and age < 45000):
            state = "turn"  # a line without stop_reason in a file that has them elsewhere gets 45 s for its tool call
        else:
            state = "working" if age < 10 * 60e3 else "idle"
    sid = os.path.basename(path)[:-6]
    subs = _sub_files(os.path.join(os.path.dirname(path), sid))
    return {"id": sid, "source": "claude", "project": os.path.basename(os.path.dirname(path)),
            "title": custom or ai or _first_prompt(path) or sid, "state": state, "tool": tool, "ageMs": int(age_ms),
            "mtime": mtime, "subTotal": len(subs), "subActive": sum(1 for f in subs if now - os.stat(f).st_mtime * 1000 < 90e3),
            "tokens": _claude_tokens([path] + subs)}


# ---------- Codex ----------
def _typed(t):
    s = re.sub(r"</?send_user_message_question_reply>", "", str(t or ""))
    i = s.find("# Files mentioned by the user:")
    if i >= 0:
        m = re.search(r"\n## My request[^\n]*:[ \t]*\n?", s[i:])
        s = s[:i] + ("\n" + s[i + m.end():] if m else "")
    return s.strip()


def _parts(c):
    return c if isinstance(c, str) else "\n".join(x["text"] for x in c if isinstance(x, dict) and isinstance(x.get("text"), str)) if isinstance(c, list) else ""


def _codex_user_text(r):
    p = r.get("payload") or {}
    if p.get("type") == "user_message":
        return _typed(p.get("message"))
    if p.get("type") == "item_completed" and (p.get("item") or {}).get("type") == "UserMessage":
        return _typed(_parts(p["item"].get("content")))
    return ""


def _codex_names(home):
    names = {}
    try:
        for r in _lines(os.path.join(home, "session_index.jsonl")):
            if r.get("id") and isinstance(r.get("thread_name"), str) and r["thread_name"].strip():
                names[str(r["id"]).lower()] = r["thread_name"].strip()
    except OSError:
        pass
    return names


def codex_rows(home, now, since_ms):
    rows, names = [], None
    for dirpath, _, files in os.walk(os.path.join(home, "sessions")):
        for f in files:
            m = CODEX_NAME.match(f)
            if not m:
                continue
            path = os.path.join(dirpath, f)
            st = os.stat(path)
            mtime = st.st_mtime * 1000
            if now - mtime >= since_ms:
                continue
            head = next(_lines(path, 0, 1024 * 1024), {})
            p = head.get("payload") if head.get("type") == "session_meta" else None
            if not isinstance(p, dict) or p.get("parent_thread_id") or (isinstance(p.get("source"), dict) and p["source"].get("subagent")):
                continue  # not a thread the person started (a review, a sub-agent)
            sid = m.group(1).lower()
            names = names if names is not None else _codex_names(home)
            title = names.get(sid) or next((_clean(t) for t in map(_codex_user_text, _lines(path, 0, 1024 * 1024)) if t), "") or sid
            turn, tokens = "", 0
            for r in _lines(path):  # one pass: turn state from the tail matters most, tokens need the last counter
                if r.get("type") == "event_msg":
                    pt = (r.get("payload") or {}).get("type", "")
                    if pt in CODEX_TURN:
                        turn = "open" if pt.endswith("started") else "closed"
                    elif pt == "token_count":
                        u = ((r["payload"].get("info") or {}).get("total_token_usage") or {})
                        tokens = int(u.get("total_tokens") or (int(u.get("input_tokens") or 0) + int(u.get("output_tokens") or 0)))
            age = now - mtime
            state = "idle" if age >= 30 * 60e3 else "turn" if turn == "closed" else "working" if age < 10 * 60e3 else "idle"
            rows.append({"id": sid, "source": "codex", "project": p.get("cwd", ""), "title": title, "state": state, "tool": "",
                         "ageMs": int(age), "mtime": mtime, "subTotal": 0, "subActive": 0, "tokens": tokens})
    return rows


def board(claude_projects, codex_home, hours=HOURS, now=None):
    now = now or time.time() * 1000
    since = hours * 3600e3
    found = []
    for proj in os.listdir(claude_projects) if claude_projects and os.path.isdir(claude_projects) else []:
        d = os.path.join(claude_projects, proj)
        for f in os.listdir(d) if os.path.isdir(d) else []:
            if f.endswith(".jsonl"):
                path = os.path.join(d, f)
                st = os.stat(path)
                if now - st.st_mtime * 1000 < since:
                    found.append((st.st_mtime, path, st))
    found.sort(key=lambda x: -x[0])
    rows = [claude_row(path, st, now) for _, path, st in found[:40]]
    if codex_home and os.path.isdir(codex_home):
        rows += sorted(codex_rows(codex_home, now, since), key=lambda r: -r["mtime"])[:20]
    return sorted(rows, key=lambda r: -r["mtime"])


def _age(ms):
    s = int(ms / 1000)
    return f"{s}s" if s < 60 else f"{s // 60}m" if s < 3600 else f"{s // 3600}h"


def table(rows):
    if not rows:
        return "No sessions in the window."
    out = [f"{'STATE':<8} {'AGE':>4} {'SOURCE':<6} {'TOKENS':>8}  TITLE"]
    for r in rows:
        extra = f"  [{r['tool']}]" if r["tool"] else ""
        if r["subTotal"]:
            extra += f"  ({r['subActive']}/{r['subTotal']} sub-agents active)"
        out.append(f"{r['state']:<8} {_age(r['ageMs']):>4} {r['source']:<6} {r['tokens']:>8}  {r['title']}{extra}")
    return "\n".join(out)


def main(argv=None):
    home = os.path.expanduser("~")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--claude", default=os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude"), "projects"),
                    help="Claude Code projects folder (default ~/.claude/projects)")
    ap.add_argument("--codex", default=os.environ.get("CODEX_HOME") or os.path.join(home, ".codex"), help="Codex home (default ~/.codex)")
    ap.add_argument("--hours", type=float, default=HOURS, help="only sessions written in the last N hours (default 12)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--demo", action="store_true", help="run on synthetic sessions instead of your own")
    a = ap.parse_args(argv)
    if a.demo:
        import tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))
        import fixture
        with tempfile.TemporaryDirectory() as tmp:
            p = fixture.build(tmp)
            rows = board(p["projects"], p["codex"], a.hours)
    else:
        rows = board(a.claude, a.codex, a.hours)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=1) if a.json else table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
