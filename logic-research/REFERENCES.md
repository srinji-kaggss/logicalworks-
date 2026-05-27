# References — skills & repos (public GH + local symlinks)

Agents on this machine read the symlink (`~/logic-research/skills/...`).
Agents elsewhere fetch the public GitHub URL. Same source, two doors.

| Ref | Local symlink | Public GitHub |
|-----|---------------|---------------|
| AI research skills (98 skills, 22 cats) | `skills/ai-research-skills` | https://github.com/Orchestra-Research/AI-Research-SKILLs |
| The Startup (specify/implement Factory tier) | `skills/the-startup` | https://github.com/rsmdt/the-startup |
| Thinking skills (red-team, first-principles, systems…) | `skills/thinking-skills` | https://github.com/tjboudreaux/cc-thinking-skills |
| Claude local skills (full installed set) | `skills/claude-local-skills` | (local; mixed sources) |

## Skill pointers by track
- **stack / ecosystems (facts)** → `ai-research-skills/15-rag`, `/17-observability`; research methodology.
- **ai-layer / build** → `ai-research-skills/14-agents`, `/15-rag`, `01-model-architecture/nanogpt` (Karpathy ML fundamentals); **Factory**: `the-startup` `specify-factory`→`implement-factory`.
- **wedge (architecture/security)** → `ai-research-skills/04-mechanistic-interpretability`, `/06-post-training`, `/07-safety-alignment`, `/11-evaluation`; `thinking-skills` red-team / inversion / first-principles / systems.
- **strategy** → `thinking-skills` steel-manning / second-order / opportunity-cost / pre-mortem / lindy-effect.

Rule: if a referenced skill is public, the prompt cites its GH URL so any agent can load it.

---

## Firecrawl — the grounding engine (every track)

Source of truth: https://github.com/firecrawl/firecrawl#sdks · docs https://docs.firecrawl.dev
Firecrawl is how `PROTOCOL.md §5` turns "ground every claim" into real fetches. Prefer it over
a model's built-in browse for clean/structured pulls and JS-heavy, login-gated, or non-English
sources.

### Official SDKs (use these, not raw curl)
| Lang | Package / coordinate | Install | Track that uses it |
|------|----------------------|---------|--------------------|
| Python | `firecrawl-py` (import `firecrawl.Firecrawl`) | `pip install firecrawl-py` | research/ML (ai-layer), Codex |
| Node.js / TS | `@mendable/firecrawl-js` (default `Firecrawl`) | `npm install @mendable/firecrawl-js` | landing/CRM, Copilot |
| Rust | `firecrawl` (`Client`) | `firecrawl = "2"` + tokio | backend-rust (wedge) |
| Java | `com.github.firecrawl:firecrawl-java-sdk:2.0` | Gradle/Maven via jitpack | JVM services (if any) |
| Elixir | `:firecrawl` | `{:firecrawl, "~> 1.0"}` | optional |
| Go (community) | `apps/go-sdk` in the monorepo | `go get` from repo | optional |

All SDKs auto-handle polling for async ops (crawl/batch). API base: `https://api.firecrawl.dev/v2`.
Models: `agent` uses `spark-1-mini` (default, 60% cheaper) or `spark-1-pro` (complex/critical).

### Access routes (in priority order for a Claude-run agent)
1. **Skill tools** — `firecrawl:firecrawl-search/-scrape/-map/-crawl/-agent` (in Claude Code).
2. **CLI** — `firecrawl search|scrape|map|crawl|agent|parse|interact`. Verify first: `firecrawl --status`.
3. **MCP server** — registered in `.mcp.json` as `npx -y firecrawl-mcp`.
4. **SDK** — in product/prototype code (build tracks), per table above.

### Auth model (fixed 2026-05-26)
`FIRECRAWL_API_KEY` lives in `~/.zshrc` (interactive) AND now `~/.zshenv` (so non-interactive
shells + spawned subagents + the MCP `npx` process all inherit it). The MCP block intentionally
does **not** hardcode the key — it inherits from `.zshenv`, keeping the secret out of git. Verify
any shell with `firecrawl --status` (expect "Authenticated via FIRECRAWL_API_KEY").

### Live limits on this account (design around them)
Concurrency **2** parallel jobs; ~**1,200** credits/cycle. Search = 2 credits (refund 1 via
`search-feedback`). So: fan grounding out at most 2-wide, cache pulls in `.firecrawl/`, and reserve
the deep dialectic (PROTOCOL §3) for high-weight×high-contest claims only.
