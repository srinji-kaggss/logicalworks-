# Issue 1 Workpad

This workpad tracks the runtime pieces behind `logicalworks-#1`.

Current implementation surface:
- `lgwks_agent_os.py`: manifest-driven prompt-context bootstrap and fleet doctor.
- `vision/prompts/context/manifest.json`: portable context mapping, no hard-coded symlink assumptions.
- `vision/prompts/agent_cards.json`: role metadata for native cross-spawn.

Exit criteria for `#1`:
- startup prompt bundle is portable across machines with `LGWKS_FLEET_HOME`
- prompt/context layer is self-checking (`python3 lgwks_agent_os.py doctor`)
- role subagents and agent cards are present and verifiable
