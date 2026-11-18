# agent-plugins

A plugin for Claude Code and GitHub Copilot (CLI and VS Code) that runs one agent loop on one task, a GitHub issue or a prompt:

```
planner -> executor -> reviewer -> DONE | FIX | REPLAN
```

The session that invokes the skill is the dispatcher: it spawns the three agents one at a time, routes on their one-line reply, and is the only one that runs `gh` and `git push`. Agents start fresh and hand over through files in `.agent-loop/<issue or slug>/`.

## Use

From the repository whose issue you want worked on (clean tree, `gh` authenticated, current branch pushed):

### Claude Code

```
claude --plugin-dir /path/to/agent-plugins
/model haiku                       # a cheap dispatcher is enough
/agent-loop:run 42
```

Or install it from the GitHub marketplace repository without cloning it yourself:

```
claude plugin marketplace add https://github.com/wbpascal/agent-plugins.git
claude plugin install agent-loop@agent-plugins
```

### Copilot

```
copilot --plugin-dir /path/to/agent-plugins
/model claude-haiku-5.5
/agent-loop:run 42
```

The slash command may appear as `/run`. Or install the same plugin from the GitHub marketplace repository:

```
copilot plugin marketplace add https://github.com/wbpascal/agent-plugins.git
copilot plugin install agent-loop@agent-plugins
```

In VS Code, run **Chat: Install Plugin from Source** and enter `https://github.com/wbpascal/agent-plugins.git`, or let VS Code discover the plugin installed by Copilot CLI.

Copilot requires `gpt-6.2-astra` (planner; fallback `claude-opus-5.5`), `gpt-6.2-sol` (executor) and `claude-opus-5.5` (reviewer). If your Copilot plan doesn't provide a required model, the run aborts rather than substituting another model.

To override the executor, pass a model supported by your host, e.g. `/agent-loop:run 42 --executor gpt-6.2-sol --max-passes 5` on Copilot. The model string is passed through unchanged.

Effort defaults to `medium` for `--planner-effort` and `--executor-effort`, and `high` for `--reviewer-effort`. For example: `/agent-loop:run 42 --planner-effort high --executor-effort low --reviewer-effort medium`. Values are passed through unchanged, so the host may reject a level its model does not support. On Claude Code, `CLAUDE_CODE_EFFORT_LEVEL` overrides all three.

### From a prompt

Instead of an issue number, give the task as text. Flags go before it:

```
/agent-loop:run --max-passes 5 add a --dry-run flag to the import command
```

A prompt run needs only a clean tree, not `gh` or a remote. It commits directly on your current branch, opens no PR and posts nothing. At the end the dispatcher prints the report, the commit the run started from (`git reset --hard <sha>` undoes the run) and, on `DONE`, the reviewer's `pr-body.md` for a PR you open yourself. The run lives in `.agent-loop/<slug>/`, where the slug is a short summary of the prompt. Continue an unfinished one with `/agent-loop:run --resume <slug>` from the same branch.

## What a run does

1. Creates `agent/issue-<N>` from the current branch (issue only; a prompt run stays on the current branch).
2. Planner writes `plan-k.md`; executor implements, tests and commits, writing `exec-k.md`; reviewer reviews the whole branch for functionality, security and maintainability, writing `review-k.md`.
3. Reviewer verdict routes the loop: `FIX` back to the executor, `REPLAN` to a fresh planner, `DONE` ends it. An executor that cannot follow the plan returns `BLOCKED`, which also goes to a fresh planner.
4. `DONE` on an issue: pushes the branch, opens a PR against the branch you started from, and posts the report as a PR comment.
5. `--max-passes` executor calls used up (default 3), or an agent failing twice: no PR, branch stays local, report goes to the issue as a comment.
6. A prompt run ends the same three ways, but only prints the report and saves it as `report.md`.

`.agent-loop/` is added to `.git/info/exclude`, so the target repository's `.gitignore` is untouched. The files stay after the run for you to study.

## Report

The report shows a timeline (model, start, duration, result), plus tokens and cost per call, per role and in total, including the dispatcher.

- **Claude Code** reads transcripts under `~/.claude/projects/`. Cost is an API-equivalent estimate from `scripts/prices.json`; unknown models show `n/a`.
- **Copilot** reads transcripts under `~/.copilot/session-state/` and reports tokens and premium requests, with no plan-usage line. The Model column includes reasoning effort when recorded.

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
