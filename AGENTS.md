# agent-loop

A Claude Code plugin: `/agent-loop:run <issue>` works one GitHub issue through planner, executor and reviewer agents. `README.md` describes the behaviour from the user's side. This file holds what the code does not say.

## Where this is going

The plugin is the first step, built to collect experience with loops. The intended end state is a standalone loop manager, parked until that experience exists:

- Elixir/Phoenix service that drives the loop, with a web UI showing the current issue, iteration, running agent and history.
- Runs inside a Kubernetes agent sandbox (https://agent-sandbox.sigs.k8s.io).
- Picks issues itself, one after another, respecting issue dependencies and an optional label filter.

Keep these out of the plugin until the user asks for them.

## Design rules

These were decided with the user; changing one is a design change, so raise it first.

- **The dispatcher carries paths, not content.** The main session spawns agents, waits, and routes on a one-line reply (`PLAN`, `GREEN`, `RED`, `BLOCKED`, `DONE`, `FIX`, `REPLAN`). It reads no plan, report or review file. This keeps it cheap enough to run on a small model.
- **Agents never call or wait on each other.** Only the dispatcher spawns. A waiting agent's prompt cache goes cold and the next turn pays full input price. This is why there is no advisor agent: the executor returns `BLOCKED` and the dispatcher starts a fresh planner.
- **Every agent starts fresh** and hands over through files in `.agent-loop/<issue>/` of the target repository.
- **Only the dispatcher uses `gh` and `git push`.** The executor commits; planner and reviewer write only their own output file.
- **One reviewer, three mandatory sections** (functionality, security, maintainability). Splitting into specialised reviewers is an open option if the security section proves shallow in practice.
- **The reviewer reports, the executor changes code.** Large problems go to a fresh planner (`REPLAN`), small ones to the executor (`FIX`).

## Coupling to keep in sync

- The reply words live in three places: the routing table in `skills/run/SKILL.md`, the last line of each `agents/*.md`, and the first line of the exec and review files (`STATUS:` / `VERDICT:`), which `scripts/report.py` prints in the Result column.
- File names `plan-k.md`, `exec-k.md`, `review-k.md`, `pr-body.md` are shared by the skill, the agents and `report.py` (`RESULT_FILE`).
- `report.py` finds agent calls by the `agentType` in Claude Code's per-subagent metadata, matching the names in `agents/`. Renaming an agent means updating `ROLES`.

## Transcript format facts

`report.py` depends on Claude Code internals, verified on version 2.1.325:

- Main transcript: `~/.claude/projects/<project>/<session-id>.jsonl`. Subagents: `<session-id>/subagents/agent-<id>.jsonl` with `agent-<id>.meta.json` beside it.
- One API response spans several transcript lines that repeat the same `message.id` and usage. Summing lines overcounts; the script keeps the last line per id.
- Usage splits cache writes into 5-minute and 1-hour tokens, priced differently.
- Plan usage (rate limit percentages) reaches only the status line command, hence `scripts/statusline-wrapper.sh`.

When a Claude Code update breaks the report, check these first.

## Working here

- Tests: `python3 -m unittest discover -s tests`. Validate the plugin: `claude plugin validate .`
- `scripts/` is Python standard library only, so the plugin runs in any target repository without installing anything.
- `scripts/prices.json` is copied by hand from https://platform.claude.com/docs/en/about-claude/pricing. Re-read that page before editing prices.
- Editing `skills/run/SKILL.md` or `agents/*.md`: every line is paid for on each run, by the dispatcher or an agent. State the target behaviour, keep one source of truth per rule, and delete sentences the model would follow anyway.
- A real run opens a PR and posts comments. Test changes to the loop in a throwaway repository.
