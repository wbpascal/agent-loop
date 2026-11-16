---
name: run
description: Run one agent loop on a GitHub issue (planner, executor, reviewer) until the reviewer says done.
argument-hint: <issue-number> [--executor sonnet|haiku|opus|fable] [--max-passes N]
disable-model-invocation: true
---

# Agent loop: one issue

Arguments: `$ARGUMENTS`

- `N`: issue number, required.
- `--executor <alias>`: model for the executor. Omitted: the executor's own default.
- `--max-passes <P>`: maximum executor calls. Default 3.

You are the **dispatcher**. Three agents do all reading, thinking and coding. You spawn them one at a time, route on their one-line reply, and run `git` and `gh`. You carry paths, not content: every file under `.agent-loop/N/` stays unread by you, because the reply line already holds everything routing needs.

`D` below is `.agent-loop/N`. `REPORT` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/report.py"`.

## 1. Preflight

Stop and tell the user which check failed:

- `git status --porcelain` prints nothing.
- `gh issue view N --json state -q .state` prints `OPEN`.
- `BASE` = `git branch --show-current`, and `git ls-remote --heads origin BASE` finds it (it becomes the PR base).
- Branch `agent/issue-N` exists neither locally nor on origin. If it exists, ask the user: resume or abort. Resume means `git switch agent/issue-N`, keep the files in `D`, continue their numbering, and enter the loop at the planner with the newest review or exec report as extra input.

Then set up:

```bash
mkdir -p D
ex="$(git rev-parse --git-path info/exclude)"; grep -qxF '.agent-loop/' "$ex" 2>/dev/null || echo '.agent-loop/' >> "$ex"
gh issue view N --json number,title,body,comments,labels > D/issue.json
REPORT init --dir D --session ${CLAUDE_SESSION_ID} --base BASE
git switch -c agent/issue-N
```

Done when `D/issue.json` and `D/run.json` exist and the current branch is `agent/issue-N`.

## 2. Loop

Spawn with the Agent tool, `subagent_type` `agent-loop:planner`, `agent-loop:executor` or `agent-loop:reviewer`. Pass `model` only to the executor, and only when `--executor` was given. `description`: `<role> #N call <k>`. The prompt is this block and nothing else:

```
Issue number: N
Issue: D/issue.json
Base branch: BASE
Read: <input files from the table>
Write: <output file from the table>
```

Output files are numbered per role, starting at 1: `plan-k.md`, `exec-k.md`, `review-k.md`. "Latest" means the highest number.

| Reply | Next agent | Read |
| --- | --- | --- |
| (start) | planner | (issue only) |
| `PLAN` | executor | latest plan |
| `GREEN` or `RED` | reviewer | latest plan, latest exec |
| `BLOCKED` | planner | latest plan, latest exec |
| `FIX` | executor | latest plan, latest review |
| `REPLAN` | planner | latest plan, latest review |
| `DONE` | none: go to step 3, outcome `done` | |

Two exits besides `DONE`:

- **Cap**: the next agent is the executor and it has already run `P` times. Outcome `cap`.
- **Abort**: an agent ends without a reply from the table. Spawn it once more with the same prompt; a second failure is outcome `aborted`.

## 3. Finish

Outcome `done` (the reviewer has written `D/pr-body.md`):

```bash
git push -u origin agent/issue-N
gh pr create --base BASE --head agent/issue-N --title "<issue title> (#N)" --body-file D/pr-body.md
REPORT report --dir D --outcome done > D/report.md
gh pr comment <pr-url> --body-file D/report.md
git switch BASE
```

Outcome `cap` or `aborted` (branch stays local, for the user to inspect):

```bash
REPORT report --dir D --outcome <outcome> > D/report.md
gh issue comment N --body-file D/report.md
```

Take the issue title from `gh issue view N --json title -q .title`.

Done when the report comment is posted. Tell the user the outcome, the PR URL if any, and the output of `tail -n 1 D/report.md`.
