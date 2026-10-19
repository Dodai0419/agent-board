<div align="center">

# agent-board

**See every Claude Code and Codex session at once: who is working, who is blocked, whose turn, tokens used.**

Running five agents in five terminals means checking five terminals. agent-standup showed the states, agentplay counted the tokens; this is both in one read-only Python file.

Works with **Claude Code** and **Codex**.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg) ![Status: prototype](https://img.shields.io/badge/status-prototype-orange.svg)

</div>

## Quick start
```bash
git clone https://github.com/Dodai0419/agent-board && cd agent-board
python agent_board.py --demo
```
```
STATE     AGE SOURCE   TOKENS  TITLE
working   10s claude    21220  Fix the failing checkout test  [Bash]
working   10s codex      9450  Add dark mode to settings
blocked    1m claude     7300  Refactor cart  [Edit]
...
waiting    3m claude      870  Audit the repo for secrets  [Task]  (1/1 sub-agents active)
turn       9m codex      4300  API version bump
```
Drop `--demo` to read your own `~/.claude/projects` and `~/.codex`.

## The problem
- An Edit waiting for approval in a background terminal stalls a whole task, and nothing tells you.
- Claude Code and Codex keep their sessions in different folders and formats.
- Token counts need a full replay tool, a build step and a second command.

## The solution
| Idea | Fixes |
|------|-------|
| **State from the tail of each transcript**: pending tool calls, stop reasons, Esc, Codex turn events | `blocked` / `turn` / `waiting` / `working` / `idle` without reading whole files |
| **One table for both agents**, newest first, last 12 hours | No more terminal hopping |
| **Tokens per session**, each streamed message counted once, sub-agents included | Know which session is burning the budget |

## Use with Claude Code
```bash
/plugin marketplace add Dodai0419/agent-board
/plugin install agent-board@agent-board
```

## Use with Codex (ChatGPT)
```bash
git clone https://github.com/Dodai0419/agent-board && cp -r agent-board/skills/* ~/.codex/skills/
```
Or copy `AGENTS.md` into your project root.

## Benchmarks
Input: the 8 synthetic sessions from `tests/fixture.py` (6 Claude Code, 2 Codex). Best of 5-7 wall-clock runs, Windows 11, Node 24.20, Python 3.11.1. This machine was under load; two runs are shown where they differed.

| | upstream | agent-board |
|-|-|-|
| session states (agent-standup `boardRows()` via `node`) | 501 / 696 ms | 643 / 854 ms (states and tokens) |
| token totals (agentplay `build` + `list --json`) | 2184 + 1320 ms | included above |
| states + tokens, total | about 4.0-4.2 s, two tools | 0.64-0.85 s, one command |
| lines of code | 1346 (`server.js` + `codex.js`) + 21242 (agentplay Python) | 288 |
| dependencies | Node.js; Python | Python only |

For states alone, agent-standup in Node is as fast or a little faster; the gain is getting states and tokens in one command.
Correctness: `tests/upstream_expected.json` holds agent-standup's state, title, tool and sub-agent count and agentplay's token total for each fixture session; the tests check agent-board matches every field and the order.

## Inspired by
- [Atoll92/agent-standup](https://github.com/Atoll92/agent-standup) — the board: how to tell working, blocked, waiting and your-turn from a transcript tail (MIT).
- [Entelligence-AI/agentplay](https://github.com/Entelligence-AI/agentplay) — per-session token accounting across Claude Code and Codex (Apache-2.0, idea only; see NOTICE).

## Roadmap
- [ ] `--watch` mode that redraws every few seconds
- [ ] Desktop notification when a session turns `blocked`

## License
MIT

## Related tools
- [session-fold](https://github.com/Dodai0419/session-fold): read what your agent did at five zoom levels
- [session-panel](https://github.com/Dodai0419/session-panel): replay a Claude Code session as an animated panel
- All tools, one install pattern: [github.com/Dodai0419](https://github.com/Dodai0419)
