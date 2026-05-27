---
id: viz.world-map
title: World-Map — First-Pass Visualization
model: opus
provenance: mixed (measured facts from notes/*; elicited synthesis marked)
generated: 2026-05-27
reads: notes/*.jsonl, claims/*.json, artifacts/blindspots.register.json
status: FIRST PASS — robustness scores and the wedge are elicited (p:E); facts are sourced
---

# The Map of the Mountain — where an AI-native OS-layer plugs in

> One picture of the seven layers we mapped, who controls each, the must-pass chokepoints
> (`op:1`), and the narrow wedge a small team can actually win. Facts trace to `notes/<layer>.jsonl`;
> robustness scores and the wedge are **my elicited synthesis** — read with the blindspots register.

## 1. The layered world + where Canvas rides

```mermaid
flowchart TB
    subgraph WORLD["The world as it is (mapped)"]
        direction TB
        DIST["DISTRIBUTION<br/>App stores · browsers · registries · OS gates<br/><i>owners: Apple, Google, Microsoft</i>"]
        IDEN["IDENTITY<br/>OAuth/OIDC · passkeys/WebAuthn · federated IdPs<br/><i>owners: Apple, Google, Microsoft</i>"]
        CLOUD["CLOUD / COMPUTE<br/>Hyperscalers 63% · egress tax · inference cost<br/><i>owners: AWS 29 / Azure 20 / GCP 13</i>"]
        REG["REGULATION<br/>DMA · GDPR · EU AI Act · PIPEDA + CA federal/provincial<br/><i>owners: EU, US, Canada (fed+prov)</i>"]
        ECO["ECOSYSTEMS<br/>Super-app / OS-layer playbook (7 cases)<br/><i>owners: WeChat, Alipay, Grab, Jio, LINE, Kakao, Yandex</i>"]
        STACK["STACK<br/>cables · IXPs · CDNs · BGP · DNS · TLS/PKI<br/><i>owners: carriers, CAs, registries</i>"]
    end

    subgraph CANVAS["Our wedge — Canvas AI-native OS-layer"]
        BROKER["CANVAS BROKER (native engine)<br/>envelope stamp · capability gate · fan-out · tape tap"]
        ENG["+ compliance gate · intent-auth · residency boundary<br/>(recommended — see canvas-architecture-recommendation.md)"]
    end

    DIST -->|"gates → developers"| BROKER
    IDEN -->|"depends_on"| BROKER
    CLOUD -->|"controls compute · egress tax"| BROKER
    REG -->|"gates personal-data processing"| BROKER
    ECO -->|"playbook + failure modes"| BROKER
    STACK -->|"carries / can throttle"| BROKER
    BROKER --- ENG
```

## 2. Must-pass chokepoints (`op:1` flags from the sweeps)

| Layer | `op:1` | The chokepoint(s) we must ride or route around |
|---|---:|---|
| identity | 9 | Apple/Google FIDO tunnel servers, federated IdP capture, passkey sync lock-in |
| moats | 9 | Apple/Google/MS distribution + switching-cost + network-effect moats |
| distribution | 2 | Chrome Web Store (MV3), macOS Gatekeeper/notarization |
| stack | 2 | DNS / TLS-PKI control points |
| cloud | 1 | **on-device ⇄ cloud inference cost crossover** (~$7.15/M local ≈ $6.90/M OpenAI; open-weight $1.97/M) |
| ecosystems | 1 | mini-program runtime → **agentic runtime** shift |
| regulation | 0* | *no `op:1`, but 2 **P0 arch_directives**: compliance-mode router (gate), statutory control ledger (tape)* |

> `op:1` = flagged for the expensive T9 adversarial dialectic. 23 claims are queued; only a subset
> has been red-teamed. The identity + moats clusters (18 of 23) are the least-tested, highest-stakes.

## 3. Robustness per layer (0–5, elicited) + biggest gap

```mermaid
flowchart LR
    subgraph SCORE["How solid is each layer's grounding? (0=guess, 5=primary+triangulated)"]
        R1["distribution  ████░ 4/5<br/>gap: iOS web-dist 1M-install floor"]
        R2["regulation    ████░ 4/5<br/>gap: AI Act high-risk boundary (unsettled)"]
        R3["ecosystems    ████░ 4/5<br/>gap: messaging→success is correlational"]
        R4["identity      ███░░ 3/5<br/>gap: is decentralized identity real?"]
        R5["moats         ███░░ 3/5<br/>gap: where AI-native layer actually breaks them"]
        R6["stack         ███░░ 3/5<br/>gap: thin scale figures on cables/IXPs"]
        R7["cloud         ██░░░ 2/5<br/>gap: consumer-device $/token UNGROUNDED"]
    end
```

*Scores reflect source tier × triangulation, not importance. Cloud is newest/thinnest; regulation
and distribution are best-grounded (primary law text + dev docs). See `blindspots.register.json`.*

## 4. The wedge — where a small AI-native team wins

```mermaid
flowchart TB
    LOSE["WHERE WE LOSE<br/>• capital-intensive frontier model training<br/>• owning distribution (app stores)<br/>• payment-rail licensing at scale<br/>• beating hyperscalers on raw compute"]
    WIN["WHERE WE WIN — the wedge<br/>• <b>governance-as-engine</b>: compliance + intent-auth + residency native in the broker<br/>• <b>local-first sovereignty</b>: data never leaves the boundary (dodges egress tax + transfer law)<br/>• <b>agentic runtime</b>: intent-level authz replaces the mini-program sandbox<br/>• <b>hybrid inference router</b>: on-device for privacy/light, cheap cloud for bulk"]
    RIDE["WHAT WE RIDE (not fight)<br/>• Chrome MV3 + native messaging daemon<br/>• macOS Developer ID / PWA web-dist<br/>• open-weight cloud APIs as commodity compute<br/>• existing IdPs without becoming captive"]
    LOSE -.avoid.-> WIN
    RIDE -.leverage.-> WIN
```

**The thesis in one line:** *the technical wedge is easy; the governance wall is where OS-layers
die (T6). So the wedge is to make the governance wall a **native engine primitive** — the one thing
incumbents bolt on late and small teams can build in from line one.*

## 5. Honesty layer — what this map cannot yet see

- 🔴 **High severity:** the cloud inference crossover is a *model*, not measured; the consumer-device
  cost curve (the input our hybrid-router depends on) is **ungrounded**.
- 🟡 Most facts are **single-sourced**; the T9 dialectic has cleared only a subset of the 23 `op:1`.
- 🟡 "messaging → super-app success" is **correlational** (T6 base-rate caveat; the C01 myth).
- 🟡 EU AI Act high-risk classification for OS AI features is **unsettled in law** — not closeable by research.

→ full register: [`artifacts/blindspots.register.json`](../blindspots.register.json)

---
*Next viz: [`01-t6-assumptions-understandings.md`](01-t6-assumptions-understandings.md) — the picture
of what we assume vs. what we now understand. Then the build bridge:
[`canvas-architecture-recommendation.md`](../canvas-architecture-recommendation.md).*
