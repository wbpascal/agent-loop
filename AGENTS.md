# agent-plugins

One plugin for two hosts, Claude Code and GitHub Copilot (CLI and VS Code; see [ADR 0001](docs/adr/0001-one-plugin-two-hosts.md)): `/agent-loop:run <issue>` works one GitHub issue through planner, executor and reviewer agents. `README.md` describes the behaviour from the user's side. This file holds what the code does not say.

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
- **Effort defaults live in `skills/run/SKILL.md`.** Both hosts accept per-call effort, so pass it with every spawn. Frontmatter would need three spellings (`effort`, `reasoningEffort`, `reasoning-effort`), one unverified. Models stay in frontmatter because their names differ by host.

## Coupling to keep in sync

- Keep reply words in sync across `skills/run/SKILL.md`, the last line of each `agents/*.md`, exec and review headers (`STATUS:` / `VERDICT:`), and `report.py` (`REPLY`).
- File names `plan-k.md`, `exec-k.md`, `review-k.md`, `pr-body.md` are shared by the skill, the agents and `report.py` (`RESULT_FILE`).
- Per-role models live in the same agent file: `model:` for Claude Code, `models:`/`modelPolicy:` for Copilot.
- `report.py` matches Claude Code metadata `agentType` and Copilot `subagent.started` `agentName` against `ROLES`.

## Transcript format facts

`report.py` depends on Claude Code internals, verified on version 2.1.325:

- Main transcript: `~/.claude/projects/<project>/<session-id>.jsonl`. Subagents: `<session-id>/subagents/agent-<id>.jsonl` with `agent-<id>.meta.json` beside it.
- One API response spans several transcript lines that repeat the same `message.id` and usage. Summing lines overcounts; the script keeps the last line per id.
- Usage splits cache writes into 5-minute and 1-hour tokens, priced differently.
- Plan usage (rate limit percentages) reaches only the status line command, hence `scripts/statusline-wrapper.sh`.
- Whether Claude Code transcripts record effort is unverified. The report shows only Copilot effort (`data.usage.reasoningEffort` on `session.usage_record`).

When a Claude Code update breaks the report, check these first.

### Copilot transcript facts

Unverified until the first real plugin run; record the Copilot CLI version and verify the dispatcher session ID then. Schema sampled from VS Code (`copilot-agent` 1.0.108-0):

- `$COPILOT_HOME/session-state/<session-id>/events.jsonl` (`~/.copilot` by default); session id from `COPILOT_AGENT_SESSION_ID`.
- `session.usage_record` stores model, token counts, `cost`, `duration`, `initiator`, `interactionType` and subagent `parentToolCallId` in `data.usage`. `agentId` is top-level on subagent records. Input includes cache reads/writes; output includes reasoning.
- `subagent.started` has `agentName`, `model`, `modelSelectionSource`, `executionMode` and `toolCallId`; `subagent.configured` / `subagent.selected` describe selection. Match `tool.execution_start` / `tool.execution_complete` for `task`. Background completion of `task` can be a launch acknowledgement; `subagent.completed` marks the actual end.
- `session.usage_checkpoint` carries `data.accountingSnapshot` rollups (`modelMetrics`, `agentMetrics`, `totalPremiumRequestCost`); use usage records for run-scoped totals.

## Working here

- Tests: `python3 -m unittest discover -s tests`. Validate the plugin: `claude plugin validate .`
- `scripts/` is Python standard library only, so the plugin runs in any target repository without installing anything.
- `scripts/prices.json` is copied by hand from https://platform.claude.com/docs/en/about-claude/pricing. Re-read that page before editing prices.
- Keep `skills/run/SKILL.md` shell commands portable across Bash and PowerShell.
- Editing `skills/run/SKILL.md` or `agents/*.md`: every line is paid for on each run, by the dispatcher or an agent. State the target behaviour, keep one source of truth per rule, and delete sentences the model would follow anyway.
- A real run opens a PR and posts comments. Test changes to the loop in a throwaway repository.
