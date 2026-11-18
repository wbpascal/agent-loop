# agent-loop

One agent loop works one GitHub issue through planner, executor and reviewer agents until the reviewer is satisfied.

## Language

**Host**:
The agent runtime the plugin runs inside: Claude Code or GitHub Copilot (CLI and VS Code). One plugin serves every host.
_Avoid_: harness, runtime, platform, target

**Dispatcher**:
The session that invoked the run skill; it spawns agents, routes on their reply, and alone talks to GitHub.
_Avoid_: orchestrator, main agent

**Reply**:
The one-line final message an agent returns to the dispatcher (`PLAN`, `GREEN`, `RED`, `BLOCKED`, `DONE`, `FIX`, `REPLAN`).
_Avoid_: result, status

**Report**:
The timeline and cost summary posted as a comment when a run ends, measured in the host's own cost unit.
_Avoid_: summary, metrics
