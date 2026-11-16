# agent-loop

A Claude Code plugin that runs one agent loop on one GitHub issue:

```
planner (fable) -> executor (sonnet) -> reviewer (opus) -> DONE | FIX | REPLAN
```

The session that invokes the skill is the dispatcher: it spawns the three agents one at a time, routes on their one-line reply, and is the only one that runs `gh` and `git push`. Agents start fresh and hand over through files in `.agent-loop/<issue>/`.

## Use

From the repository whose issue you want worked on (clean tree, `gh` authenticated, current branch pushed):

```
claude --plugin-dir /path/to/agent-loop
/model haiku                       # a cheap dispatcher is enough
/agent-loop:run 42
/agent-loop:run 42 --executor haiku --max-passes 5
```

Or install it:

```
claude plugin marketplace add /path/to/agent-loop
claude plugin install agent-loop@agent-loop
```

## What a run does

1. Creates `agent/issue-<N>` from the current branch.
2. Planner writes `plan-k.md`; executor implements, tests and commits, writing `exec-k.md`; reviewer reviews the whole branch for functionality, security and maintainability, writing `review-k.md`.
3. Reviewer verdict routes the loop: `FIX` back to the executor, `REPLAN` to a fresh planner, `DONE` ends it. An executor that cannot follow the plan returns `BLOCKED`, which also goes to a fresh planner.
4. `DONE`: pushes the branch, opens a PR against the branch you started from, and posts the report as a PR comment.
5. `--max-passes` executor calls used up (default 3), or an agent failing twice: no PR, branch stays local, report goes to the issue as a comment.

`.agent-loop/` is added to `.git/info/exclude`, so the target repository's `.gitignore` is untouched. The files stay after the run for you to study.

## Report

`scripts/report.py` reads Claude Code's own transcripts under `~/.claude/projects/`: a timeline of agent calls (model, start, duration, result) and tokens and cost per call, per role and in total, dispatcher included. Cost is an API-equivalent estimate from `scripts/prices.json`; edit that file when prices change. A model missing from it shows tokens with cost `n/a`.

### Plan usage (optional)

Claude Code only exposes plan usage to the status line command. To add a "Plan usage: 5h +X%, 7d +Y%" line to the report, wrap your status line command in `~/.claude/settings.json`:

```json
"statusLine": { "type": "command", "command": "sh /path/to/agent-loop/scripts/statusline-wrapper.sh <your existing command>" }
```

The number is account-wide, so other sessions running at the same time are included.

## Tests

```
python3 -m unittest discover -s tests
```
