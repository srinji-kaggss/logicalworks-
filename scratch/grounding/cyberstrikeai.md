# CyberStrikeAI — grounding study (read-only)

Source: github.com/Ed1s0nZ/CyberStrikeAI @ commit `11bab83`. Go. Apache-2.0. ~4k★. 404Starlink member.
Method: studied via GitHub read API (clone/shell/web-fetch were sandbox-denied; all findings are from source-of-truth files at the pinned SHA). Self-description: "AI-native security testing platform" — single-agent ReAct loop + CloudWeGo **Eino** multi-agent, exposing 100+ CLI tools as MCP tools, plus a built-in C2.
SCOPE NOTE: this is an offensive autonomy engine. The single-agent system prompt is explicitly engineered to *suppress* authorization checks (see §4). Treat the whole thing as adversary-modeled; reuse selectively.

---

## 1. Integrated tools (100+), by category
Source: README "Tool Overview" + `tools/*.yaml` recipe dir (each tool = one YAML recipe: `name/command/args/parameters[]/enabled`; hot-reloaded from `security.tools_dir`).

- **Network scanners**: nmap, masscan, rustscan, arp-scan, nbtscan
- **Web/app scanners**: sqlmap, nikto, dirb, gobuster, feroxbuster, ffuf, httpx
- **Vuln scanners**: nuclei, wpscan, wafw00f, dalfox, xsser
- **Subdomain enum**: subfinder, amass, findomain, dnsenum, fierce
- **Recon / net-space search engines**: fofa_search, zoomeye_search
- **API security**: graphql-scanner, arjun, api-fuzzer, api-schema-analyzer
- **Container security**: trivy, clair, docker-bench-security, kube-bench, kube-hunter
- **Cloud security**: prowler, scout-suite, cloudmapper, pacu, terrascan, checkov
- **Binary analysis**: gdb, radare2, ghidra, objdump, strings, binwalk
- **Exploitation**: metasploit, msfvenom, pwntools, ropper, ropgadget
- **Password cracking**: hashcat, john, hashpump
- **Forensics**: volatility, volatility3, foremost, steghide, exiftool
- **Post-exploitation**: linpeas, winpeas, mimikatz, bloodhound, impacket, responder
- **CTF utils**: stegsolve, zsteg, hash-identifier, fcrackzip, pdfcrack, cyberchef
- **System helpers (internal)**: `exec` (arbitrary `sh -c`), create-file, delete-file, list-files, modify-file
- **Internal MCP tools** (not CLI): `query_execution_result` (paged/regex search over stored large outputs), `search_knowledge_base`, `record_vulnerability`, `list_knowledge_risk_types`, project-blackboard facts (`upsert_project_fact`/`get_project_fact`/`list_project_facts`/`search_project_facts`/`deprecate_project_fact`), and C2 family `c2_listener/c2_session/c2_task/c2_task_manage/c2_payload/c2_event/c2_profile/c2_file`.
- Tools are *recipes*, not bundled binaries — AI falls back to alternatives when a binary is missing. External MCP federation (HTTP/stdio/SSE) and `mcp-servers/` (e.g. reverse-shell MCP) extend the action space arbitrarily.

## 2. Orchestration engine architecture
Two execution surfaces; both are **LLM-as-planner** (no hardcoded decision tree / no RL policy):

- **Single-agent ReAct** (`internal/agent/agent.go`, ~67KB; `/api/agent-loop/stream`). Classic think→tool-call→observe loop over OpenAI-compatible chat API (GPT/Claude/DeepSeek). The LLM picks the next tool each turn from the MCP tool list; sequencing is emergent from the system prompt (`internal/agent/default_single_system_prompt.go`) + tool-result observations. `memory_compressor.go` compresses history when context fills; `agent_trace.go` records steps. Iteration cap from config (`max_iteration`).
- **Multi-agent (Eino `adk/prebuilt`)** (`internal/multiagent/`, `/api/multi-agent/stream`), chosen per-request via `orchestration` field:
  - `deep` (default): coordinator + `task` sub-agents (markdown specialists in `agents/`).
  - `plan_execute`: planner / executor / replanner loop (`agents/orchestrator-plan-execute.md`). Planner emits structured steps each with target-id + scope + single-action + success-criteria; executor runs MCP tools; replanner revises from evidence. Loop cap `plan_execute_loop_max_iterations`.
  - `supervisor`: orchestrator with `transfer`/`exit` handoffs over markdown specialists (`agents/orchestrator-supervisor.md`).
- **State**: per-conversation SQLite (`data/conversations.db`); large tool outputs (>200KB) spilled to artifacts queryable via `query_execution_result`. **Project blackboard** (`internal/project`, "shared facts") persists cross-session context (targets/env/auth/creds/findings) and is auto-injected into agent + MCP context — this is the durable working memory / world-state. Attack-chain graph built post-hoc by LLM parsing the conversation (`internal/attackchain/builder.go`) → interactive graph + severity scoring + step replay.
- "Decides which tool to run next" = the model, conditioned on (system prompt + role prompt + injected blackboard facts + prior tool outputs). There is no symbolic planner or learned controller.

## 3. Role + skills system
- **Roles** (`roles/*.yaml`, 12+ predefined, hot-reload via `/api/roles`): fields `name, description, user_prompt (prepended to user msg), icon, tools (allowlist subset), enabled`. Roles = (a) a system-prompt overlay biasing methodology + (b) an optional **tool restriction list** scoping the action space. Predefined: 渗透测试(pentest), CTF, Web应用扫描, Web框架测试, API安全测试, 二进制分析, 云安全审计, 信息收集(recon), 后渗透测试(post-ex), 容器安全, 数字取证(forensics), 综合漏洞扫描, 默认(default). Dispatch: user selects role in chat UI → role's user_prompt + tool filter applied to that conversation.
- **Skills** (`skills/*/SKILL.md`, ~20 domains): Anthropic "Agent Skills" layout — YAML front-matter (`name`,`description`) + markdown body = a methodology playbook (e.g. `sql-injection-testing/SKILL.md` lists detection payloads, sqlmap invocations, WAF-bypass encodings, verification steps). NOT executable code; they are instruction packs. Loaded only in **multi-agent/Eino** sessions via the official Eino ADK **`skill`** tool with **progressive disclosure** (model calls `skill` with a pack *name* instead of receiving full text up front), configured by `multi_agent.eino_skills` (can grant host filesystem/shell: read/glob/grep/write/edit/execute). Also chunked into `schema.Document` for the RAG retriever. Single-agent ReAct does NOT mount the skill tool.
- Role ≈ persona + scope; Skill ≈ lazily-loaded procedure library. Both are prompt/markdown-defined, no compiled dispatch.

## 4. Sandbox / isolation / authorization / safety model — and the GAPS
Verified against `internal/security/executor.go`, `procattr_unix.go`, `ratelimit.go`, `auth_middleware.go`, `default_single_system_prompt.go`, `agents/orchestrator-plan-execute.md`, `c2/hitl_context.go`.

Gates that EXIST (all weak / web-perimeter only):
- **Web/API auth**: Bearer-token middleware on every route; auto-generated strong password if unset; rate-limiter (per-IP sliding window → 429); optional TLS. Protects the *console*, not the *targets*.
- **Per-tool enabled flag**: only `Enabled: true` tools register as MCP tools. Toggle-only, not a security boundary.
- **HITL (human-in-the-loop)**: optional approval mode + tool allowlist (`config.yaml hitl.tool_whitelist`, editable live). Listed tools SKIP approval. C2 dangerous tasks can wait on human approval via a longer-lived run-context (`c2/hitl_context.go`). **Off by default; opt-in; bypassable per-tool.**
- **Process hygiene**: `ctx` timeout per tool; `Setsid` so cancel/timeout SIGKILLs the whole process group (`terminateCmdTree`). This is cleanup, NOT sandboxing.

Gates that are ABSENT (the safety gaps — design these in for our sandbox):
- **NO command/argument allowlist or sanitization.** `exec` tool runs arbitrary `sh -c <command>` (and `additional_args` is shell-split and appended to any tool). `ExecuteTool` builds argv and calls `exec.CommandContext` directly. The only log on `exec` is a `Warn`. Comment in code literally calls the "safety check" just *logging* the command.
- **NO target / scope enforcement.** Nothing validates target IP/host/CIDR against an authorized scope. The "sandbox guards" the README claims = timeout + Setsid only. Targets are free-text the model fills in.
- **NO OS/process isolation.** No container, namespace, seccomp, chroot, dropped privileges, or non-root user. Tools run as the server's user with full host network + filesystem (helpers create/delete/modify arbitrary files; no path-traversal guard at the executor).
- **NO egress containment.** Built-in C2 (TCP-reverse / HTTP(S) beacon / WebSocket listeners, encrypted, payload one-liners, mimikatz/bloodhound/impacket/responder) actively reaches outbound; nothing pins it to a lab network.
- **Authorization is explicitly DISABLED at the prompt layer (the most dangerous design choice).** The single-agent system prompt and the orchestrator prompts contain a hardcoded "授权状态" (authorization status) block instructing the agent to: never question / verify / request authorization regardless of task sensitivity ("授权已由系统与组织前置裁决"); never wait for approval; act fully autonomously; "fire at full power on all targets," "real vuln hunting needs 2000+ steps," "never give up," bug-bounty "$500+" mindset. i.e. the safety posture is the inverse of a gate — the model is trained-by-prompt to push past hesitation. The Apache disclaimer + "authorized testing only" README text are the ONLY authorization control, and they are advisory, not enforced.

Net: trust boundary is the login page. Past auth, it is an autonomous arbitrary-RCE + C2 driver on the host network with prompts that suppress refusal. For our use this MUST be re-architected, not configured.

## 5. Machine-drivable surface (if an ML were to DRIVE it)
It is already ML-driven (by an LLM), so the surface is well-factored — clean to swap the LLM controller for a learned policy:
- **Action space**: the set of registered MCP tools = {CLI-recipe tools (nmap/sqlmap/nuclei/... with typed JSON-schema params built in `buildInputSchema`), `exec` (arbitrary shell — effectively unbounded/continuous action), internal tools (`query_execution_result`, knowledge search, `record_vulnerability`, project-fact CRUD), C2 family, federated external-MCP tools}. Each action = (tool_name, JSON args). Roles/HITL allowlists let you *mask* the action space per episode — useful as a curriculum/safety mask.
- **Observation space**: tool stdout/stderr (streamed in 8KB chunks, combined, optionally PTY), exit code (+ `AllowedExitCodes`), `IsError`; paged/searchable archived outputs for large results; the **project-blackboard fact set** (structured world-state: targets, ports, versions, creds, findings, attack chains) — this is the cleanest structured observation; plus the attack-chain graph (nodes/edges/severity).
- **Reward signal candidates** (none exist today — must be built): count/severity of `record_vulnerability` events (severity-weighted: critical>high>...); new verified facts added to blackboard per step; attack-chain depth/breadth or reaching a goal node; first-blood time / steps-to-finding; binary capture-the-flag success in a CTF target; (for safety RL) negative reward for out-of-scope target contact or denied-action attempts. The repo's bug-bounty "$500+" framing is a human heuristic, not a computed reward.
- Good news for an ML driver: typed schemas, deterministic argv builder, streamed observations, durable structured state (blackboard + SQLite + attack-chain), per-episode action masking (roles/HITL). The ReAct loop in `agent.go` is the seam to replace.

## 6. Reusable for a SANDBOXED self-improving offensive ML vs must-rebuild
REUSABLE (snapshot-and-freeze a vendored copy; cite + Apache-2.0 NOTICE):
- The **tool-recipe abstraction** (`tools/*.yaml` → typed MCP tool with JSON schema): clean, declarative action-space definition. Vendor the schema/format.
- The **observation plumbing**: streamed chunked output + large-result archiving + paged/regex query (`query_execution_result`), exit-code semantics.
- The **project-blackboard / shared-facts** structured world-state model (`internal/project`) — strong fit as RL observation + replay buffer.
- The **attack-chain builder** (post-hoc graph + severity) — usable as episode summary / reward shaping input.
- **Roles + HITL allowlist** as an **action-mask / curriculum** mechanism (repurpose the gate as a safety constraint, not a UX toggle).
- The **Eino plan_execute/supervisor** decomposition pattern as an architecture reference (not the prompts).
- Skills/SKILL.md methodology packs as a knowledge corpus (content, not the loader).

MUST REBUILD for safety (do NOT inherit):
- **All authorization prompts.** Delete the "授权状态/never verify authorization/2000+ steps/full firepower" blocks entirely. Our agent must verify scope, refuse out-of-scope, and be revocable.
- **Hard scope enforcement** at the executor: allowlisted targets (CIDR/host/URL), reject everything else *before* spawn — the layer the original lacks.
- **OS-level sandbox/isolation**: run every tool in a network-isolated container/VM (no host fs/net), non-root, seccomp/namespaces, snapshot-restorable. The "self-improving" loop must run in a frozen, reversible snapshot environment.
- **Command gating**: no raw `exec`/`sh -c`; if shell is needed, gate through an allowlist + arg validation; path-traversal guards on file helpers.
- **Egress containment**: C2 + reverse shells confined to the lab segment; no real outbound. Prefer dropping C2 entirely for a code-red-team use case.
- **Reward + safety-critic**: build the reward signal (none exists) plus a hard negative-reward/abort path for boundary violations; audit every action against scope.
- **Snapshot-and-freeze governance**: deterministic, reproducible target snapshots; freeze model + tool versions per run; full audit trail (they have logging + SQLite + trace — extend it into a tamper-evident governance log).

## 7. License
Apache License 2.0 (`LICENSE`, "Copyright 2025 Ed1s0nZ"). Permissive — vendoring/derivative use OK with license copy + NOTICE + change-marking. README adds a non-binding "educational and authorized testing only" disclaimer.
