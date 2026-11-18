# agent-plugins

A plugin for Claude Code and GitHub Copilot (CLI and VS Code) that runs one agent loop on one GitHub issue:

```
planner -> executor -> reviewer -> DONE | FIX | REPLAN
```

The session that invokes the skill is the dispatcher: it spawns the three agents one at a time, routes on their one-line reply, and is the only one that runs `gh` and `git push`. Agents start fresh and hand over through files in `.agent-loop/<issue>/`.

## Use

From the repository whose issue you want worked on (clean tree, `gh` authenticated, current branch pushed):

### Claude Code

```
claude --plugin-dir /path/to/agent-plugins
/model haiku                       # a cheap dispatcher is enough
/agent-loop:run 42
```

Or install it:

```
claude plugin marketplace add /path/to/agent-plugins
claude plugin install agent-loop@agent-plugins
```

### Copilot

```
copilot --plugin-dir /path/to/agent-plugins
/model claude-haiku-5.5
/agent-loop:run 42
```

The slash command may appear as `/run`. Or install the same plugin:

```
copilot plugin marketplace add /path/to/agent-plugins
copilot plugin install agent-loop@agent-plugins
```

Copilot requires `gpt-6.2-astra` (planner; fallback `claude-opus-5.5`), `gpt-6.2-sol` (executor) and `claude-opus-5.5` (reviewer). If your Copilot plan doesn't provide a required model, the run aborts rather than substituting another model.

To override the executor, pass a model supported by your host, e.g. `/agent-loop:run 42 --executor gpt-6.2-sol --max-passes 5` on Copilot. The model string is passed through unchanged.

## What a run does

1. Creates `agent/issue-<N>` from the current branch.
2. Planner writes `plan-k.md`; executor implements, tests and commits, writing `exec-k.md`; reviewer reviews the whole branch for functionality, security and maintainability, writing `review-k.md`.
3. Reviewer verdict routes the loop: `FIX` back to the executor, `REPLAN` to a fresh planner, `DONE` ends it. An executor that cannot follow the plan returns `BLOCKED`, which also goes to a fresh planner.
4. `DONE`: pushes the branch, opens a PR against the branch you started from, and posts the report as a PR comment.
5. `--max-passes` executor calls used up (default 3), or an agent failing twice: no PR, branch stays local, report goes to the issue as a comment.

`.agent-loop/` is added to `.git/info/exclude`, so the target repository's `.gitignore` is untouched. The files stay after the run for you to study.

## Report

The report shows a timeline (model, start, duration, result), plus tokens and cost per call, per role and in total, including the dispatcher.

- **Claude Code** reads transcripts under `~/.claude/projects/`. Cost is an API-equivalent estimate from `scripts/prices.json`; unknown models show `n/a`.
- **Copilot** reads transcripts under `~/.copilot/session-state/` and reports tokens and premium requests, with no plan-usage line.

### Plan usage (optional)

Claude Code only exposes plan usage to the status line command. To add a "Plan usage: 5h +X%, 7d +Y%" line to the report, wrap your status line command in `~/.claude/settings.json`:

```json
"statusLine": { "type": "command", "command": "sh /path/to/agent-plugins/scripts/statusline-wrapper.sh <your existing command>" }
```

The number is account-wide, so other sessions running at the same time are included.

## Tests

```
python3 -m unittest discover -s tests
```
