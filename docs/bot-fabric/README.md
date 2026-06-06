# Bot Fabric

Purpose: define the end-to-end non-AI bot system, the JEPA world-model layer, and the minimal AI synthesis layer for `lgwks`.

This folder is flat on purpose. A cheaper coding agent should be able to enter here, read top to bottom, and take one bounded unit of work without loading the whole repo history.

## Read order

1. [MAP.md](/Users/srinji/logicalworks-/docs/bot-fabric/MAP.md)
2. [JEPA.md](/Users/srinji/logicalworks-/docs/bot-fabric/JEPA.md)
3. [WORLD-DB.md](/Users/srinji/logicalworks-/docs/bot-fabric/WORLD-DB.md)
4. [BOTS.md](/Users/srinji/logicalworks-/docs/bot-fabric/BOTS.md)
5. [RUNTIME.md](/Users/srinji/logicalworks-/docs/bot-fabric/RUNTIME.md)
6. [UNITS.md](/Users/srinji/logicalworks-/docs/bot-fabric/UNITS.md)

## First detailed build units

Bottom-up implementation order:

1. [U1-BOT-RECORD.md](/Users/srinji/logicalworks-/docs/bot-fabric/U1-BOT-RECORD.md)
2. [U2-BOT-PLAN.md](/Users/srinji/logicalworks-/docs/bot-fabric/U2-BOT-PLAN.md)
3. [U3-REDUCER.md](/Users/srinji/logicalworks-/docs/bot-fabric/U3-REDUCER.md)
4. [U4-JEPA-PACKAGE.md](/Users/srinji/logicalworks-/docs/bot-fabric/U4-JEPA-PACKAGE.md)
5. [U11-ARTIFACT-STRENGTH.md](/Users/srinji/logicalworks-/docs/bot-fabric/U11-ARTIFACT-STRENGTH.md)

## Next lane specs

After the schema/reducer/package base:

1. [U5-CODE-HACKER.md](/Users/srinji/logicalworks-/docs/bot-fabric/U5-CODE-HACKER.md)
2. [U6-SLOP-MATH.md](/Users/srinji/logicalworks-/docs/bot-fabric/U6-SLOP-MATH.md)

## One-paragraph thesis

`lgwks` should use deterministic bots to generate evidence, a JEPA-style world model to align and compress evidence across views and time, and one optional high-reasoning LLM synthesis layer that further reduces tokens and improves final judgment without being required for the package to remain useful.

## Hard rules

1. Bots are not AI agents.
2. Bots emit typed findings, not prose.
3. JEPA is a world-model and reduction layer, not a freeform orchestrator.
4. The final LLM should read compiled evidence only.
5. Human and machine outputs must derive from the same canonical package.
6. Prefer Apple-native on-device model/runtime paths before inventing parallel local stacks.
7. Artifacts must remain strong and actionable even when the LLM synthesis layer is skipped.
