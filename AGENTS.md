# agent-board

Use this when the user runs several coding-agent sessions in parallel and asks which ones need them, which are still working, or how many tokens a session used.

## Steps
1. Run `python agent_board.py` from the repo root. It reads `~/.claude/projects` and `~/.codex` (override with `--claude`, `--codex`), last 12 hours by default (`--hours`).
2. Read the STATE column:
   - `blocked`: waiting for the person to approve an edit or answer a question. Mention these first.
   - `turn`: the agent finished or was stopped; the person should reply.
   - `waiting`: a sub-agent is running.
   - `working`: a tool call or answer is in progress.
   - `idle`: nothing written for 10+ minutes.
3. Use `--json` when you need ids, project folders or exact token counts.

## Rules
- Read-only: never edit or delete session files.
- Session titles can contain private prompts; summarize, do not paste the whole table into public places.
- `python agent_board.py --demo` shows the output on synthetic sessions.
