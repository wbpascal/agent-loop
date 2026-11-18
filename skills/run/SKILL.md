---
name: run
description: Run one agent loop (planner, executor, reviewer) on a GitHub issue or a prompt until the reviewer says done.
argument-hint: [flags] <issue-number> | <prompt> | --resume <slug>   flags: --executor <model> --planner-effort E --executor-effort E --reviewer-effort E --max-passes N
disable-model-invocation: true
---

# Agent loop: one task

Arguments: `$ARGUMENTS`

Flags come first:

- `--executor <model>`: pass the string unchanged as the executor model. Omitted: use the agent default.
- `--planner-effort <E>`: planner effort. Default `medium`.
- `--executor-effort <E>`: executor effort. Default `medium`.
- `--reviewer-effort <E>`: reviewer effort. Default `high`.
- `--max-passes <P>`: maximum executor calls. Default 3.

After the flags, the task:

- `N`, all digits: **issue mode**, GitHub issue N.
- `--resume <slug>`: **prompt mode**, continue the run in `.agent-loop/<slug>`.
- Anything else: **prompt mode**; the rest of the arguments, verbatim, is the prompt.

You are the **dispatcher**. Three agents do all reading, thinking and coding. You spawn them one at a time, route on their one-line reply, and run `git` and `gh`. You carry paths, not content: every file under `D` stays unread by you, because the reply line already holds everything routing needs.

Substitute placeholders. Issue mode: `D` is `.agent-loop/N`, `ID` is `#N`. Prompt mode: `D` and `BASE` are the `Dir:` and `Base:` lines printed by `REPORT init`, `ID` is the last part of `D`. `REPORT` is `python "${CLAUDE_PLUGIN_ROOT}/scripts/report.py"` (use `python3` if that is your Python 3 command; if `${CLAUDE_PLUGIN_ROOT}` is not filled in, the plugin root is two levels above this skill's base directory).

## 1. Preflight

Stop and tell the user which check failed. Both modes: `git status --porcelain` prints nothing.

Issue mode:

- `gh issue view N --json state -q .state` prints `OPEN`.
- `BASE` = `git branch --show-current`, and `git ls-remote --heads origin BASE` finds it (it becomes the PR base).
- Branch `agent/issue-N` exists neither locally nor on origin. If it exists, ask the user: resume or abort. Resume means `git switch agent/issue-N`, keep the files in `D`, continue their numbering, and enter the loop at the planner with the newest review or exec report as extra input.

Then run in order, stopping on failure:

```text
REPORT init --dir D --base BASE --session=${CLAUDE_SESSION_ID}
git switch -c agent/issue-N
```

Prompt mode, new run: choose `SLUG`, a summary of the prompt in at most 40 characters of `a-z`, `0-9` and `-`. Run `REPORT init --dir .agent-loop/SLUG --prompt --session=${CLAUDE_SESSION_ID}`, then write the prompt verbatim to `D/task.md` with your file-writing tool.

Prompt mode, resume: run `REPORT init --dir .agent-loop/<slug> --resume --session=${CLAUDE_SESSION_ID}`. Keep the files in `D`, continue their numbering, and enter the loop at the planner with the newest review or exec report as extra input.

Prompt mode works on the current branch: no new branch, no `gh`, no push.

Done when `D/run.json` and the task file exist, and in issue mode the current branch is `agent/issue-N`.

## 2. Loop

Spawn this plugin's `planner`, `executor` or `reviewer` in the foreground with the host's subagent tool. On every spawn pass the role's effort unchanged, without validation (`effort` on Claude Code, `reasoning_effort` on Copilot). Pass `model` only to the executor when `--executor` was given. Description: `<role> ID call <k>`. Prompt (the `Issue number` line in issue mode only; `Task` is `D/issue.json` or `D/task.md`):

```
Issue number: N
Task: <task file>
Base: BASE
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

Issue mode, outcome `done` (the reviewer has written `D/pr-body.md`):

```text
git push -u origin agent/issue-N
gh pr create --base BASE --head agent/issue-N --title '<issue title> (#N)' --body-file D/pr-body.md
REPORT report --dir D --outcome done --out D/report.md
gh pr comment PR_URL --body-file D/report.md
git switch BASE
```

Issue mode, outcome `cap` or `aborted` (branch stays local, for the user to inspect):

```text
REPORT report --dir D --outcome OUTCOME --out D/report.md
gh issue comment N --body-file D/report.md
```

Get the issue title with `gh issue view N --json title -q .title`; escape it for the shell. Use the URL from `gh pr create` as `PR_URL`.

Prompt mode, every outcome: run `REPORT report --dir D --outcome OUTCOME --out D/report.md --print`. The commits stay on the current branch.

Done when the report is posted (issue mode) or printed (prompt mode). Tell the user the outcome and the total line printed by `REPORT report`. Issue mode: add the PR URL if any. Prompt mode: first repeat the whole printed report, then add `BASE` with `git reset --hard BASE` as the way to undo the run, and on `done` the path `D/pr-body.md`.
