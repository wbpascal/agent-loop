# agent-loop

One agent loop works one task through planner, executor and reviewer agents until the reviewer is satisfied.

## Language

**Host**:
The agent runtime the plugin runs inside: Claude Code or GitHub Copilot (CLI and VS Code). One plugin serves every host.
_Avoid_: harness, runtime, platform, target

**Dispatcher**:
The session that invoked the run skill; it spawns agents, routes on their reply, and alone talks to GitHub.
_Avoid_: orchestrator, main agent

**Task**:
The work one run carries out. Its source is either a GitHub issue or a prompt typed by the user.
_Avoid_: request, job, ad-hoc issue

**Reply**:
The one-line final message an agent returns to the dispatcher (`PLAN`, `GREEN`, `RED`, `BLOCKED`, `DONE`, `FIX`, `REPLAN`).
_Avoid_: result, status

**Report**:
The timeline and cost summary produced when a run ends, measured in the host's own cost unit. An issue's report is posted as a comment; a prompt's report is shown to the user.
_Avoid_: summary, metrics

**Worktree**:
A separate checkout of the target repository on the run's own branch, so the user's checkout stays untouched and runs can go in parallel. An issue run uses one by default; a prompt run works in place unless asked. In Herdr it is a Herdr worktree, shown as its own space.
_Avoid_: sandbox, clone, copy

**Handoff**:
The invoking session creates the worktree, starts a fresh dispatcher inside it, and steps back. The new session is the run's dispatcher.
_Avoid_: relaunch, fork
