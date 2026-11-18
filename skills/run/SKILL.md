---
name: run
description: Run one agent loop on a GitHub issue (planner, executor, reviewer) until the reviewer says done.
argument-hint: <issue-number> [--executor <model>] [--planner-effort E] [--executor-effort E] [--reviewer-effort E] [--max-passes N]
disable-model-invocation: true
---

# Agent loop: one issue

Arguments: `$ARGUMENTS`

- `N`: issue number, required.
- `--executor <model>`: pass the string unchanged as the executor model. Omitted: use the agent default.
- `--planner-effort <E>`: planner effort. Default `medium`.
- `--executor-effort <E>`: executor effort. Default `medium`.
- `--reviewer-effort <E>`: reviewer effort. Default `high`.
- `--max-passes <P>`: maximum executor calls. Default 3.

You are the **dispatcher**. Three agents do all reading, thinking and coding. You spawn them one at a time, route on their one-line reply, and run `git` and `gh`. You carry paths, not content: every file under `.agent-loop/N/` stays unread by you, because the reply line already holds everything routing needs.

Substitute placeholders; `D` is `.agent-loop/N`. `REPORT` is `python "${CLAUDE_PLUGIN_ROOT}/scripts/report.py"` (use `python3` if that is your Python 3 command; if `${CLAUDE_PLUGIN_ROOT}` is not filled in, the plugin root is two levels above this skill's base directory).

## 1. Preflight

Stop and tell the user which check failed:

- `git status --porcelain` prints nothing.
- `gh issue view N --json state -q .state` prints `OPEN`.
- `BASE` = `git branch --show-current`, and `git ls-remote --heads origin BASE` finds it (it becomes the PR base).
- Branch `agent/issue-N` exists neither locally nor on origin. If it exists, ask the user: resume or abort. Resume means `git switch agent/issue-N`, keep the files in `D`, continue their numbering, and enter the loop at the planner with the newest review or exec report as extra input.

Then run in order, stopping on failure:

```text
REPORT init --dir D --base BASE --session=${CLAUDE_SESSION_ID}
git switch -c agent/issue-N
```

Done when `D/issue.json` and `D/run.json` exist and the current branch is `agent/issue-N`.

## 2. Loop

Spawn this plugin's `planner`, `executor` or `reviewer` in the foreground with the host's subagent tool. On every spawn pass the role's effort unchanged, without validation (`effort` on Claude Code, `reasoning_effort` on Copilot). Pass `model` only to the executor when `--executor` was given. Description: `<role> #N call <k>`. Prompt:

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

```text
git push -u origin agent/issue-N
gh pr create --base BASE --head agent/issue-N --title '<issue title> (#N)' --body-file D/pr-body.md
REPORT report --dir D --outcome done --out D/report.md
gh pr comment PR_URL --body-file D/report.md
git switch BASE
```

Outcome `cap` or `aborted` (branch stays local, for the user to inspect):

```text
REPORT report --dir D --outcome OUTCOME --out D/report.md
gh issue comment N --body-file D/report.md
```

Get the issue title with `gh issue view N --json title -q .title`; escape it for the shell. Use the URL from `gh pr create` as `PR_URL`.

Done when the report comment is posted. Tell the user the outcome, the PR URL if any, and the total line printed by `REPORT report`.
