#!/usr/bin/env python3
"""
build_jarvis_viz.py — generate a self-contained, living 3D "Jarvis-like" visualization
of the Canvas world-map graph: THE WORLD at the top, Canvas's plug-ins beneath it, the
UI->OS survivability spine, and the implementation foundation it stands on.

This generator IS the engine described in viz-data/SCHEMA.md (graph-schema/2). Section
references (§0..§8) in comments below cite that contract — it is the source of truth.
Updating the map = appending JSON to the data files; the generator does creation (§0/§1),
provenance (§1), merging (§3), link roles + direction (§2), world routing (§4), the math
(§5), the why framework (§6), the math/schema overlay (§7), and the self-contained
export canvas-context-export/2 (§8).

Reads:
  ~/logicalworks-/vision/notes/*.jsonl          (living research — world nodes, edges, os_hooks, directives, claims)
  ~/logicalworks-/vision/viz-data/manual.jsonl         (NEW §9: hand-placed real-world nodes + same_as/merge; optional)
  ~/logicalworks-/vision/viz-data/incumbents.jsonl     (level-1 incumbent OS frameworks + benchmarks links)
  ~/logicalworks-/vision/viz-data/implementation.jsonl (level-4 foundation impl nodes + implements links)
  ~/logicalworks-/vision/viz-data/gh-issues.jsonl      (level-4 GH issues + addresses links)
  ~/logicalworks-/vision/viz-data/why-map.json         (per-node why/tag/maturity/distance/feature/priority overrides)
Writes:
  ~/logicalworks-/vision/artifacts/viz/jarvis-world-map.html  (single self-contained file)

Conforms to viz-data/SCHEMA.md (graph-schema/2 + canvas-context-export/2).
"""
import json, glob, os, datetime, html, sys, re

# ROOT is the vault this script lives in (vision/scripts/build_jarvis_viz.py -> vision/).
# Was hardcoded to ~/logic-research, now a STALE pre-rename copy; script-relative keeps the
# generator reading the canonical vault wherever it is moved/renamed. Override with VISION_ROOT.
ROOT = os.environ.get("VISION_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES = sorted(glob.glob(os.path.join(ROOT, "notes", "*.jsonl")))
VIZ = os.path.join(ROOT, "viz-data")
OUT = os.path.join(ROOT, "artifacts", "viz", "jarvis-world-map.html")

LEVELS = 5  # 0 world-root (top) .. 4 foundation (bottom)

# ---- §5 MATH constants (mirror of SCHEMA §5; tuning = editing here) ----
# level(node) by band
LEVEL_BY_BAND = {"world-root": 0, "incumbent": 1, "layer-hub": 1, "world": 2, "os_hook": 2,
                 "bin": 3, "primitive": 3, "impl": 4, "gh_issue": 4, "actor": 2}
# val base[band]
VAL_BASE = {"world-root": 18, "layer-hub": 13, "incumbent": 11, "bin": 11, "primitive": 7,
            "world": 3, "os_hook": 4, "impl": 5, "gh_issue": 4, "actor": 3}
# weight per rel
WREL = {"implements": .7, "depends_on": .6, "gates": .8, "controls": .7, "contains": .3,
        "ascends": .9, "addresses": .5, "benchmarks": .6, "reaches_world": .4, "peer": .5}
# gh_issue priority points P0=3,P1=2,P2=1 ; op flag => +1 (cap 3)
PRI_POINTS = {"P0": 3, "P1": 2, "P2": 1, "": 0, None: 0, 3: 3, 2: 2, 1: 1, 0: 0}
COLLECTOR_INBOUND_N = 6   # §4: ≥6 inbound links => collector

# ---- palettes (per SCHEMA) ----
LAYER_COLOR = {
    "distribution": "#f59e0b", "identity": "#a78bfa", "cloud": "#38bdf8",
    "regulation": "#34d399", "ecosystem": "#f472b6", "stack": "#94a3b8",
}
FEATURE_COLOR = {
    "broker": "#22d3ee", "memory": "#38bdf8", "identity": "#a78bfa", "capability": "#818cf8",
    "governance": "#34d399", "ml": "#f472b6", "distribution": "#f59e0b", "security": "#f43f5e",
    "payments": "#fbbf24", "ui": "#94a3b8", "protocol": "#2dd4bf", "none": "#64748b",
}
# priority heat 0..3 (none -> hot P0)
PRIORITY_COLOR = {0: "#475569", 1: "#fbbf24", 2: "#fb923c", 3: "#f43f5e"}
BIN_GLOW = {"bin0": "#1e3a4f", "bin1": "#1f6f8f", "bin2": "#22a5c4",
            "bin3": "#2bc7d6", "bin4": "#22d3ee", "bin5": "#67e8f9"}
WORLD_ROOT_COLOR = "#e2e8f0"
INCUMBENT_COLOR = "#cbd5e1"

# ---- canonical config: world-root, bins, primitives ----
BINS = [
    ("bin0", "Bin 0 · UI / Surface", "render · theming · view injection · widgets — cloneable, ~0 durability"),
    ("bin1", "Bin 1 · State / Memory", "append-only tape · local-first store · cross-session persistence"),
    ("bin2", "Bin 2 · Brokerage", "single signal authority: envelope stamp · capability · fan-out (the kernel test)"),
    ("bin3", "Bin 3 · Identity / Capability", "tenant/user · least-privilege gate"),
    ("bin4", "Bin 4 · Governance / Sovereignty", "compliance-mode gate · statutory ledger · residency · intent-auth"),
    ("bin5", "Bin 5 · Economic Rail", "payments-as-infra · transaction tax · cross-service optimization"),
]
# id, name, bin, feature, summary, status, linked world layer hub
PRIMITIVES = [
    ("cv-broker", "Canvas Broker", "bin2", "broker", "Single authority every signal passes through — envelope stamping, capability enforcement, fan-out, telemetry tap.", "live", "distribution"),
    ("cv-tape", "Tape / governed memory", "bin1", "memory", "Append-only E2EE governance log; the memory + audit substrate.", "live", None),
    ("cv-capability", "Capability gate", "bin3", "capability", "Least-privilege capability enum enforced at the bus.", "live", None),
    ("cv-identity", "Identity / tenant", "bin3", "identity", "RS256 JWT vs JWKS, tenant row-isolation.", "live", "identity"),
    ("cv-widgets", "Widgets / view injection", "bin0", "ui", "WidgetDescriptor + zones — the surface, cloneable.", "live", None),
    ("cv-compliance", "Compliance-mode gate", "bin4", "governance", "Jurisdiction x context legal-basis selected BEFORE execution (Canada A-01).", "build", "regulation"),
    ("cv-ledger", "Statutory control ledger", "bin4", "governance", "Every high-risk signal -> statute/section, consent, disclosure, incident clock (Canada A-02).", "build", "regulation"),
    ("cv-intent", "Intent authorization", "bin4", "governance", "Authorize agent intent vs contextual memory + active compliance mode (gen-2 security).", "build", "ecosystem"),
    ("cv-residency", "Residency boundary", "bin4", "governance", "Data crosses only with a logged transfer-PIA (GDPR Art.44 / QC P-39.1).", "build", "cloud"),
    ("cv-inference", "Hybrid inference router", "bin2", "ml", "On-device for light/privacy, cheap cloud for bulk, frontier for hard reasoning.", "post-v1", "cloud"),
    ("cv-payments", "Economic rail (separated)", "bin5", "payments", "Payments-as-governance — structurally separated / licensed (RPAA/AML).", "future", "ecosystem"),
]
STATUS_COLOR = {"live": "#10b981", "build": "#f59e0b", "post-v1": "#8b5cf6", "future": "#64748b",
                "open": "#f43f5e", "step": "#f59e0b", "ships": "#10b981", "deferred": "#64748b",
                "mapped": "#475569"}

# directive target -> bin
BINMAP = {"widget": "bin0", "tape": "bin1", "protocol": "bin2", "ml": "bin2",
          "gate": "bin3", "sovereignty": "bin4", "distribution": "bin5"}
# directive pri -> priority int
PRI_INT = {"P0": 3, "P1": 2, "P2": 1, "": 0, None: 0}

def short(s, n=320):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"

def clamp01(x):
    return max(0.0, min(1.0, x))

def norm_label(s):
    """Normalized label key for natural-key merge (§3)."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def heat(t, cold="#1f6f8f", warm="#f43f5e"):
    """interpolate cold->warm by t in 0..1, return #rrggbb."""
    t = clamp01(t)
    c0 = tuple(int(cold[i:i + 2], 16) for i in (1, 3, 5))
    c1 = tuple(int(warm[i:i + 2], 16) for i in (1, 3, 5))
    r = tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return "#%02x%02x%02x" % r

nodes, links = {}, []
claims_by_about = {}
# referenced-but-undeclared ids accumulate here -> auto-emit derived nodes (§0/§1 law 1)
referenced = set()

def add_node(nid, **kw):
    # §1 PROVENANCE: every node carries origin; default 'derived' unless caller sets it.
    if nid not in nodes:
        nodes[nid] = {"id": nid, "claims": [], "refs": [], "origin": kw.pop("origin", "derived"),
                      "manual": False, "collector": False, "touches_internet": False, **kw}
    else:
        # later passes may upgrade fields; never clobber a stronger origin with a weaker one
        order = {"derived": 0, "merged": 1, "seed": 2, "manual": 3}
        for k, v in kw.items():
            if k in ("claims", "refs"):
                continue
            if k == "origin" and order.get(v, 0) <= order.get(nodes[nid].get("origin", "derived"), 0):
                continue
            nodes[nid][k] = v
    return nodes[nid]

def note_ref(rid):
    """§0/§1 law 1: record a referenced id so an undeclared one becomes a derived node."""
    if rid:
        referenced.add(rid)

def add_link(provider, dependent, rel, dir="uni", weight=None, origin="derived"):
    """§2 LINK ROLES: provider=source (creates/serves), dependent=target (needs).
    Particles flow provider->dependent. weight defaults to §5 wrel[rel]*derived-penalty."""
    if weight is None:
        weight = WREL.get(rel, 0.5) * (1.0 if origin != "derived" else 0.85)
    note_ref(provider)
    note_ref(dependent)
    links.append({"source": provider, "target": dependent, "rel": rel,
                  "dir": dir, "weight": weight, "origin": origin})

# =====================================================================
# PASS 1 — load living notes (world nodes, edges, os_hooks, directives, claims)
# =====================================================================
raw = []
for path in NOTES:
    if path.endswith("blindspots.jsonl"):
        continue  # honesty layer rendered as referenced risk nodes, not the graph backbone
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("std"):
                continue
            raw.append(o)

for o in raw:
    if o.get("k") == "claim" and o.get("ab"):
        claims_by_about.setdefault(o["ab"], []).append(
            {"stmt": short(o.get("stmt", ""), 320),
             "url": (o.get("s", [["", ""]])[0][0] if o.get("s") else "")})

# Map legacy world-edge relations onto §2 rels (role-correct provider/dependent).
# competes is lateral -> peer-style but between non-collectors, so we render uni controls-ish.
LEGACY_REL = {"controls": "controls", "gates": "gates", "competes": "controls",
              "depends_on": "depends_on", "contains": "contains"}

for o in raw:
    k = o.get("k")
    if k == "node":
        # §1 world node: origin derived (came from research). layer drives the hub it joins (§4).
        ly = o.get("ly", "stack")
        add_node(o["i"], label=o.get("l", o["i"]), band="world",
                 layer=ly, feature="none", bin=None, maturity=0.0, origin="derived",
                 kind="node", summary=short(o.get("sm", "")), status="mapped", refs=[])
    elif k == "os_hook":
        # §4: an os_hook is BY DEFINITION an internet/world touchpoint -> touches_internet.
        add_node(o["i"], label="hook · " + o.get("tp", "os_hook"), band="os_hook",
                 layer="canvas", feature="protocol", bin=None, maturity=0.4, origin="derived",
                 kind="os_hook", summary=short(o.get("mech", "")), status="os_hook",
                 touches_internet=True, refs=([o["wr"]] if o.get("wr") else []))
        # §2 depends_on: the world node provides the surface the hook depends on (provider=world node).
        if o.get("wr"):
            add_link(o["wr"], o["i"], "depends_on", origin="derived")
            note_ref(o["wr"])
    elif k == "arch_directive":
        tgt = o.get("tgt", "protocol")
        b = BINMAP.get(tgt, "bin2")
        pri = o.get("pri", "")
        add_node(o["i"], label="directive · " + tgt, band="impl",
                 layer="impl", feature="governance", bin=b, priority=PRI_INT.get(pri, 0),
                 maturity=0.3, kind="arch_directive", origin="derived",
                 summary=short(o.get("rec", "")), status="directive (" + pri + ")",
                 refs=list(o.get("wy", [])))
        # §2 addresses: gh_issue/work feeds the feature -> directive (provider) addresses bin (dependent).
        add_link(o["i"], b, "addresses", origin="derived")
        # directive wy -> evidence: the evidence node provides grounding the directive depends on.
        for ev in o.get("wy", []):
            add_link(ev, o["i"], "depends_on", origin="derived")
            note_ref(ev)

# explicit world edges (§2 role-correct; particles flow provider->dependent)
for o in raw:
    if o.get("k") == "edge" and o.get("f") and o.get("to"):
        f, t = o["f"], o["to"]
        for x in (f, t):
            if x not in nodes:
                add_node(x, label=x, band="actor", kind="actor", layer="actor",
                         feature="none", bin=None, maturity=0.0, origin="derived",
                         summary="", status="actor")
        rel = LEGACY_REL.get(o.get("r", "rel"), "controls")
        # controls/gates: source already the controller/gatekeeper (provider) in the data.
        add_link(f, t, rel, origin="derived")

# =====================================================================
# PASS 2 — Canvas survivability spine (bins + primitives, level 3)
# =====================================================================
# bins + primitives are SEED (§0/§1). bins are collectors-by-band? no — bins aggregate primitives
# but §4 collector set is {world-root,layer-hub,incumbent}; bins survive via inbound>=N if reached.
for i, (bid, label, desc) in enumerate(BINS):
    add_node(bid, label=label, band="bin", kind="bin", layer="spine", origin="seed",
             feature="none", bin=bid, priority=0, maturity=0.0,
             summary=desc, status="survivability bin %d" % i, binIndex=i)
    # §2 ascends: lower bin (provider) -> higher bin (dependent); survivability accrues upward.
    if i > 0:
        add_link(BINS[i - 1][0], bid, "ascends", origin="seed")

prim_meta = {}  # pid -> {feature, maturity}
for pid, label, b, feat, summ, status, hub in PRIMITIVES:
    add_node(pid, label=label, band="primitive", kind="primitive",
             layer="spine", feature=feat, bin=b, priority=0, maturity=0.5,
             summary=summ, status=status, origin="seed", layer_hint=hub)
    # §2 contains: the bin (collector hub) contains the primitive (member). provider=bin.
    add_link(b, pid, "contains", origin="seed")
    # the primitive's layer linkage is created NATURALLY in pass 3b once we know which
    # layer-hubs actually exist (don't force a hub here).
    prim_meta[pid] = {"feature": feat, "layer_hint": hub}

# =====================================================================
# PASS 3 — world-root (level 0) + hub/os_hook plumbing to the world
# =====================================================================
add_node("world-root", label="THE INTERNET / WORLD", band="world-root",
         kind="world-root", layer="world", feature="none", bin=None, priority=0,
         maturity=1.0, summary="The shared substrate every OS plugs into — the top of the map.",
         status="world", origin="seed", collector=True)
# §4: NO blanket layer->world or hub->world links here. world-routing is emitted PER NODE
# later (pass 3b) only for touches_internet:true OR band==os_hook, via rel "reaches_world".

# =====================================================================
# PASS 4 — load viz-data: incumbents, implementation, gh-issues
# =====================================================================
incumbent_strength = {}  # feature -> max strength across incumbents

def load_jsonl(fname):
    out = []
    p = os.path.join(VIZ, fname)
    if not os.path.exists(p):
        return out
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                print("WARN bad json in %s: %s" % (fname, e), file=sys.stderr)
    return out

# merge declarations collected during ingest, applied in pass 4b (§3)
merge_decls = []   # list of (alias_id, canonical_id)

def ingest(fname, kind, default_origin="derived"):
    for o in load_jsonl(fname):
        if o.get("_link"):
            # §2: accept legacy {source,target} as {provider,dependent}; pass through dir.
            prov = o.get("provider", o.get("source"))
            dep = o.get("dependent", o.get("target"))
            if prov is None or dep is None:
                continue
            origin = o.get("origin", "derived" if o.get("derived") else "manual")
            add_link(prov, dep, o.get("rel", "depends_on"), dir=o.get("dir", "uni"),
                     weight=o.get("weight"), origin=origin)
            continue
        nid = o["id"]
        # §1 origin: explicit field wins; else manual flag => manual; else file default.
        origin = o.get("origin") or ("manual" if o.get("manual") else default_origin)
        add_node(nid, label=o.get("label", nid),
                 band=o.get("band", kind), kind=kind, layer=o.get("layer", "impl"),
                 feature=o.get("feature", "none"), bin=o.get("bin"),
                 priority=o.get("priority", 0), maturity=o.get("maturity", 0.0),
                 distance=o.get("distance", 0.0), status=o.get("status", ""),
                 summary=short(o.get("summary", "")), why=o.get("why", ""),
                 origin=origin, manual=bool(o.get("manual")), by=o.get("by", ""),
                 touches_internet=bool(o.get("touches_internet")),
                 collector=bool(o.get("collector")),
                 refs=list(o.get("refs", [])))
        for r in o.get("refs", []):
            note_ref(r)
        # carry curated claims
        if o.get("claims"):
            nodes[nid]["claims"] = o["claims"][:5]
        # §3 merge declarations
        for sa in (o.get("same_as") or []):
            merge_decls.append((nid, sa))   # this node asserts identity with sa -> fold nid into sa
        if o.get("merge_into"):
            merge_decls.append((nid, o["merge_into"]))
        if kind == "incumbent":
            for feat, s in (o.get("feature_strength") or {}).items():
                incumbent_strength[feat] = max(incumbent_strength.get(feat, 0.0), float(s))

ingest("incumbents.jsonl", "incumbent", default_origin="derived")
ingest("implementation.jsonl", "impl", default_origin="derived")
ingest("gh-issues.jsonl", "gh_issue", default_origin="derived")
# §9 manual.jsonl: human editing surface (optional — another agent may be adding it).
ingest("manual.jsonl", "world", default_origin="manual")

LOG = {"derived_created": 0, "hubs_created": [], "merges": [], "natural_merges": [],
       "bi_downgraded": 0, "world_routed": 0}

# =====================================================================
# PASS 4a — NATURAL CREATION (§0/§1 law 1)
# A node exists iff declared OR referenced. Auto-emit a `derived` node for any
# referenced-but-undeclared id (refs / wy / ab / wr / link endpoints).
# =====================================================================
# include current link endpoints in the referenced set
for l in links:
    note_ref(l["source"]); note_ref(l["target"])
for rid in list(referenced):
    if rid and rid not in nodes:
        add_node(rid, label=rid, band="world", kind="node", layer="stack",
                 feature="none", bin=None, maturity=0.0, origin="derived",
                 summary="", status="referenced", refs=[])
        LOG["derived_created"] += 1

# =====================================================================
# PASS 4b — NATURAL LAYER-HUB collectors (§0/§1 + §4)
# Auto-emit a `layer-hub` collector for a layer ONLY if >=1 node declares it.
# =====================================================================
declared_layers = set()
for n in nodes.values():
    ly = n.get("layer")
    if ly in LAYER_COLOR and n.get("band") not in ("layer-hub",):
        declared_layers.add(ly)
for ly in sorted(declared_layers):
    hid = "hub-" + ly
    if hid not in nodes:
        add_node(hid, label=ly.upper(), band="layer-hub", kind="hub",
                 layer=ly, feature="none", bin=None, maturity=0.0, origin="seed",
                 summary="World layer collector: " + ly, status="layer", collector=True)
        LOG["hubs_created"].append(ly)
    # §2 contains: hub (collector/provider) contains its member world nodes (dependent).
    for nid, n in list(nodes.items()):
        if n.get("layer") == ly and n.get("band") == "world":
            add_link(hid, nid, "contains", origin="seed")
# spine primitives engage the layer-hub their layer_hint names, IF that hub now exists (natural).
for pid, meta in prim_meta.items():
    h = meta.get("layer_hint")
    if h and ("hub-" + h) in nodes:
        # §2 depends_on: the layer (provider, in the world) is what the primitive depends on.
        add_link("hub-" + h, pid, "depends_on", origin="seed")

# =====================================================================
# PASS 4c — MERGE (§3): fold same_as / merge_into; then natural-key merge.
# Re-point links to canonical, union, prefer canonical summary/why, longer claims,
# origin="merged", record merged_from + aliases. Manual nodes never auto-merge.
# =====================================================================
def repoint(old, new):
    for l in links:
        if l["source"] == old: l["source"] = new
        if l["target"] == old: l["target"] = new

def fold(alias_id, canon_id, logbucket):
    if alias_id == canon_id:
        return
    alias = nodes.get(alias_id)
    canon = nodes.get(canon_id)
    if alias is None:
        return
    if canon is None:
        # canonical not present: promote alias to be the canonical id.
        nodes[canon_id] = {**alias, "id": canon_id}
        del nodes[alias_id]
        repoint(alias_id, canon_id)
        return
    if alias.get("manual") and canon.get("manual"):
        # two manual nodes only merge by explicit declaration (this IS explicit) — allowed.
        pass
    # prefer canonical summary/why; fall back to alias if canonical empty
    canon["summary"] = canon.get("summary") or alias.get("summary", "")
    canon["why"] = canon.get("why") or alias.get("why", "")
    # keep the longer claims list
    if len(alias.get("claims") or []) > len(canon.get("claims") or []):
        canon["claims"] = alias.get("claims")
    # union refs, touches_internet, collector
    canon["refs"] = list(dict.fromkeys((canon.get("refs") or []) + (alias.get("refs") or [])))
    canon["touches_internet"] = bool(canon.get("touches_internet") or alias.get("touches_internet"))
    canon["collector"] = bool(canon.get("collector") or alias.get("collector"))
    # provenance markers
    canon["origin"] = "merged"
    mf = list(dict.fromkeys((canon.get("merged_from") or []) + (alias.get("merged_from") or []) + [alias_id]))
    canon["merged_from"] = mf
    al = list(dict.fromkeys((canon.get("aliases") or []) + [alias.get("label", alias_id)]))
    canon["aliases"] = al
    repoint(alias_id, canon_id)
    del nodes[alias_id]
    logbucket.append("%s -> %s" % (alias_id, canon_id))

# explicit declarations (§3)
for alias_id, canon_id in merge_decls:
    fold(alias_id, canon_id, LOG["merges"])

# natural-key merge: two DERIVED nodes, identical normalized label + same layer (§3). Manual never.
by_key = {}
for nid, n in list(nodes.items()):
    if n.get("origin") != "derived" or n.get("manual"):
        continue
    if n.get("band") != "world":
        continue  # only real-world nodes auto-merge by label; directive/os_hook/impl labels are
                  # generic (e.g. "directive · ml") and would collapse distinct nodes. They merge
                  # only via explicit same_as/merge_into.
    key = (norm_label(n.get("label")), n.get("layer"))
    if not key[0]:
        continue
    if key in by_key:
        fold(nid, by_key[key], LOG["natural_merges"])
    else:
        by_key[key] = nid

# =====================================================================
# PASS 5 — why-map overrides + templated why for un-authored nodes
# =====================================================================
why_map = {}
wmp = os.path.join(VIZ, "why-map.json")
if os.path.exists(wmp):
    with open(wmp) as f:
        why_map = json.load(f)

for nid, ov in why_map.items():
    if nid in nodes:
        n = nodes[nid]
        for key in ("why", "tag", "maturity", "distance", "feature", "priority"):
            if key in ov:
                n[key] = ov[key]

TAGS = ("build", "ride", "avoid", "separate", "gate", "measure")

def derive_tag(why, fallback="build"):
    if why and why.strip().startswith("["):
        t = why[1:why.find("]")].strip()
        if t in TAGS:
            return t
    return fallback

def template_why(n):
    """Decision-framework templated why for nodes without an authored one."""
    feat = n.get("feature", "none")
    b = n.get("bin") or "the spine"
    cl = n.get("claims") or []
    gap = cl[0]["stmt"] if cl else "we lose this branch's grounding"
    serve = ("%s (%s)" % (b, feat)) if feat != "none" else b
    tag = "ride" if n.get("layer") in LAYER_COLOR else "build"
    return "[%s] serves %s; without it %s; lets us hold this part of the survivability map." % (
        tag, serve, short(gap, 160))

for nid, n in nodes.items():
    cl = claims_by_about.get(nid, [])
    if cl and not n.get("claims"):
        n["claims"] = cl[:5]
    if not n.get("why"):
        n["why"] = template_why(n)
    n["tag"] = derive_tag(n.get("why", ""), "build")

# =====================================================================
# PASS 5b — derived links from refs (referential integrity, §1)
# A node's refs id is the thing it derives from -> that ref PROVIDES, this node DEPENDS.
# provider = ref, dependent = node.
# =====================================================================
existing_pairs = {(l["source"], l["target"]) for l in links}
for nid, n in nodes.items():
    for ref in n.get("refs", []):
        if ref in nodes and ref != nid and (ref, nid) not in existing_pairs and (nid, ref) not in existing_pairs:
            add_link(ref, nid, "depends_on", origin="derived")
            existing_pairs.add((ref, nid))

# =====================================================================
# PASS 5c — LEVEL assignment (§5: level(node) = LEVEL_BY_BAND[band])
# =====================================================================
for n in nodes.values():
    n["level"] = LEVEL_BY_BAND.get(n.get("band"), 2)

# =====================================================================
# PASS 6 — §5 MATH: priority / maturity / distance / frontier / val / weight /
#          flow_speed / collector. All formulas mirror SCHEMA §5 exactly.
# =====================================================================
# inbound counts (for collector(node): inbound>=N) — count distinct providers into a node.
inbound = {}
for l in links:
    inbound[l["target"]] = inbound.get(l["target"], 0) + 1

# (a) collector(node) = band in {world-root,layer-hub,incumbent} OR feature=="broker" OR inbound>=N
for nid, n in nodes.items():
    band = n.get("band")
    is_col = (band in ("world-root", "layer-hub", "incumbent")
              or n.get("feature") == "broker"
              or inbound.get(nid, 0) >= COLLECTOR_INBOUND_N
              or n.get("collector"))
    n["collector"] = bool(is_col)

# (b) priority: primitives INHERIT max priority of addressing gh_issues; pri pts + op:1 => +1, cap 3.
#     Build map primitive/bin -> max gh_issue priority points via `addresses` links.
addressing_pri = {}
for l in links:
    if l["rel"] == "addresses":
        prov = nodes.get(l["source"])   # gh_issue / directive (provider)
        dep = l["target"]               # primitive / bin (dependent)
        if prov is None:
            continue
        pts = PRI_POINTS.get(prov.get("priority", 0), int(prov.get("priority", 0) or 0))
        if prov.get("op"):
            pts = min(3, pts + 1)
        addressing_pri[dep] = max(addressing_pri.get(dep, 0), pts)
for nid, n in nodes.items():
    seed_pri = PRI_POINTS.get(n.get("priority", 0), int(n.get("priority", 0) or 0))
    if n.get("op"):
        seed_pri = min(3, seed_pri + 1)
    n["priority"] = min(3, max(seed_pri, addressing_pri.get(nid, 0)))

# (c) distance(prim) = clamp(max_incumbent_strength[feature] - maturity, 0, 1)
#     frontier_distance = mean over primitives.
prim_distances = []
for pid in prim_meta:
    n = nodes.get(pid)
    if n is None:   # may have been merged away
        continue
    feat = n.get("feature", "none")
    inc = incumbent_strength.get(feat, 0.0)
    mat = n.get("maturity", 0.5)
    dist = clamp01(inc - mat)
    n["distance"] = round(dist, 3)
    prim_distances.append(dist)
FRONTIER = round(sum(prim_distances) / len(prim_distances), 3) if prim_distances else 0.0

# (d) val(node) = base[band] + 1.4*len(claims) + 2*priority   (§5 render size)
for nid, n in nodes.items():
    base = VAL_BASE.get(n.get("band"), 4)
    n["val"] = round(base + 1.4 * len(n.get("claims") or []) + 2.0 * (n.get("priority", 0) or 0), 2)

# (e) weight(link) = wrel[rel] * (1.0 if origin!="derived" else 0.85);
#     flow_speed(link) = 0.002 + 0.010*weight
for l in links:
    rel = l.get("rel", "depends_on")
    w = WREL.get(rel, 0.5) * (1.0 if l.get("origin") != "derived" else 0.85)
    l["weight"] = round(w, 4)
    l["flow_speed"] = round(0.002 + 0.010 * w, 5)

# =====================================================================
# PASS 6b — WORLD ROUTING (§4): emit reaches_world (node->world-root) ONLY for
# nodes with touches_internet:true OR band=="os_hook". No blanket layer->world.
# provider = internet-touching node, dependent = world-root.
# =====================================================================
for nid, n in list(nodes.items()):
    if nid == "world-root":
        continue
    if n.get("touches_internet") or n.get("band") == "os_hook":
        add_link(nid, "world-root", "reaches_world", origin="derived")
        n["touches_internet"] = True
        LOG["world_routed"] += 1

# =====================================================================
# PASS 6c — BIDIRECTIONAL validation (§4): dir:"bi" allowed ONLY if an endpoint
# is a collector. Downgrade others to uni and LOG. bi links flow both ways.
# =====================================================================
for l in links:
    if l.get("dir") == "bi":
        s, t = nodes.get(l["source"]), nodes.get(l["target"])
        ok = (s and s.get("collector")) or (t and t.get("collector"))
        if not ok:
            l["dir"] = "uni"
            LOG["bi_downgraded"] += 1

# =====================================================================
# PASS 8 — colors + size; emit BOTH directions for dir:"bi"
# =====================================================================
def node_color(n):
    if n.get("kind") == "world-root":
        return WORLD_ROOT_COLOR
    if n.get("kind") == "incumbent":
        return INCUMBENT_COLOR
    if n.get("kind") == "bin":
        return BIN_GLOW.get(n.get("bin"), "#22d3ee")
    if n.get("layer") in LAYER_COLOR:
        return LAYER_COLOR[n["layer"]]
    if n.get("feature") and n.get("feature") != "none":
        return FEATURE_COLOR.get(n["feature"], "#64748b")
    return STATUS_COLOR.get(n.get("status"), "#64748b")

# §6/§5 precompute color channels for the color-mode toggle (val already set in §5(d)).
for nid, n in nodes.items():
    feat = n.get("feature", "none")
    n["featureColor"] = FEATURE_COLOR.get(feat, "#64748b")
    n["priorityColor"] = PRIORITY_COLOR.get(int(n.get("priority", 0) or 0), "#475569")
    n["distanceColor"] = heat(n.get("distance", 0.0))
    n["color"] = node_color(n)

# §4: bi links flow both ways — emit a reverse twin so particles run both directions.
bi_extra = []
for l in links:
    if l.get("dir") == "bi":
        bi_extra.append({"source": l["target"], "target": l["source"], "rel": l["rel"],
                         "dir": "bi", "weight": l["weight"], "origin": l.get("origin", "derived"),
                         "flow_speed": l.get("flow_speed", 0.005), "reverse": True})
links.extend(bi_extra)

# =====================================================================
# referential integrity: drop self-links + links to missing nodes; dedupe
# =====================================================================
valid = set(nodes)
clean, seen = [], set()
for l in links:
    s, t = l["source"], l["target"]
    if s not in valid or t not in valid or s == t:
        continue
    key = (s, t, l["rel"], l.get("reverse", False))
    if key in seen:
        continue
    seen.add(key)
    clean.append(l)
links = clean

graph = {"nodes": list(nodes.values()), "links": links}

# band + origin counts for the run report (§1 provenance visibility)
by_band, by_origin = {}, {}
for n in graph["nodes"]:
    by_band[n.get("band", "?")] = by_band.get(n.get("band", "?"), 0) + 1
    by_origin[n.get("origin", "?")] = by_origin.get(n.get("origin", "?"), 0) + 1

# §5 math constants exposed to the overlay (§7) + §8 glossary, so the JS shows the real formulas.
MATH_FORMULAS = {
    "level": "level(node) = LEVEL_BY_BAND[band]  (world-root:0, incumbent/layer-hub:1, world/os_hook/actor:2, bin/primitive:3, impl/gh_issue:4)",
    "priority": "priority = min(3, max(seedPriority, max gh_issue priority addressing it)); P0=3 P1=2 P2=1; op:1 => +1",
    "maturity": "maturity ∈ [0,1] authored in why-map / seed (ships-today-ness)",
    "distance": "distance(prim) = clamp(max_incumbent_strength[feature] − maturity, 0, 1)",
    "frontier_distance": "frontier_distance = mean(distance over primitives)",
    "val": "val = base[band] + 1.4·len(claims) + 2·priority",
    "weight": "weight(link) = wrel[rel] · (1.0 if origin≠derived else 0.85)",
    "flow_speed": "flow_speed(link) = 0.002 + 0.010·weight",
    "collector": "collector = band∈{world-root,layer-hub,incumbent} ∨ feature==broker ∨ inbound≥6",
}
GLOSSARY = {
    "bands": {b: LEVEL_BY_BAND.get(b) for b in LEVEL_BY_BAND},
    "features": list(FEATURE_COLOR.keys()),
    "rels": WREL,
    "bins": {bid: desc for bid, _l, desc in BINS},
    "math": MATH_FORMULAS,
    "provenance": {"seed": "structural config", "manual": "a human placed it",
                   "derived": "research/refs derived it", "merged": "folded from aliases"},
}

meta = {
    "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "nodes": len(graph["nodes"]), "links": len(links),
    "frontier": FRONTIER, "levels": LEVELS,
    "incumbentStrength": incumbent_strength, "byBand": by_band, "byOrigin": by_origin,
    "featureColor": FEATURE_COLOR, "layerColor": LAYER_COLOR,
    "valBase": VAL_BASE, "wrel": WREL, "formulas": MATH_FORMULAS, "glossary": GLOSSARY,
    "schema": "graph-schema/2", "export": "canvas-context-export/2",
}

# validate the emitted graph JSON parses (Apple-level robustness)
try:
    json.loads(json.dumps(graph))
    json.loads(json.dumps(meta))
except (TypeError, ValueError) as e:
    print("FATAL: emitted graph JSON does not round-trip:", e, file=sys.stderr)
    sys.exit(1)

# =====================================================================
# HTML TEMPLATE — self-contained, 3d-force-graph (CDN + offline fallback)
# =====================================================================
TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CANVAS // World-Map — living frontier graph</title>
<style>
 :root{--bg:#02030a;--fg:#cfeffd;--dim:#5b7a90;--accent:#22d3ee;}
 *{box-sizing:border-box} html,body{margin:0;height:100%;background:var(--bg);overflow:hidden;
   font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:var(--fg)}
 #graph{position:fixed;inset:0}
 .panel{position:fixed;background:rgba(4,10,20,.86);border:1px solid rgba(34,211,238,.25);
   backdrop-filter:blur(10px);border-radius:12px;padding:13px 15px;box-shadow:0 0 40px rgba(34,211,238,.08)}
 #title{top:16px;left:16px;max-width:340px}
 #title h1{margin:0;font-size:15px;letter-spacing:.18em;font-weight:700;color:#eafbff;text-transform:uppercase}
 #title .sub{font-size:11px;color:var(--dim);margin-top:4px;line-height:1.5}
 #title .frontier{margin-top:8px;font-size:11px;color:#eafbff;letter-spacing:.04em}
 #title .frontier b{color:#f59e0b;font-size:13px}
 #controls{top:16px;left:16px;margin-top:0}
 #ctrlbar{top:16px;left:374px;display:flex;gap:8px;flex-wrap:wrap;max-width:46vw}
 #ctrlbar button{background:rgba(4,10,20,.86);border:1px solid rgba(34,211,238,.3);color:var(--fg);
   font:11px Inter;padding:6px 10px;border-radius:8px;cursor:pointer;letter-spacing:.04em}
 #ctrlbar button:hover{border-color:var(--accent);color:#eafbff}
 #ctrlbar button.on{background:rgba(34,211,238,.18);border-color:var(--accent);color:#eafbff}
 #legend{top:64px;right:16px;max-width:240px;font-size:11px;line-height:1.65;max-height:72vh;overflow:auto}
 #legend h2{margin:8px 0 5px;font-size:10px;letter-spacing:.14em;color:var(--accent);text-transform:uppercase}
 .row{display:flex;align-items:center;gap:7px;cursor:pointer;opacity:.95;user-select:none}
 .row.off{opacity:.3}
 .dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto;box-shadow:0 0 8px currentColor}
 .sep{height:1px;background:rgba(34,211,238,.15);margin:8px 0}
 #detail{bottom:16px;left:16px;max-width:440px;display:none;max-height:74vh;overflow:auto}
 #detail h3{margin:0 0 2px;font-size:14px;color:#eafbff;padding-right:18px}
 #detail .tags{margin:6px 0}
 #detail .tag{display:inline-block;font-size:10px;letter-spacing:.06em;text-transform:uppercase;
   padding:2px 8px;border-radius:20px;border:1px solid rgba(34,211,238,.4);color:var(--accent);margin:2px 4px 2px 0}
 #detail .sm{font-size:12px;color:#bcdcec;line-height:1.5;margin:7px 0}
 .barwrap{margin:8px 0;font-size:10px;color:var(--dim);letter-spacing:.08em;text-transform:uppercase}
 .bar{height:7px;border-radius:4px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:3px}
 .bar>div{height:100%;border-radius:4px}
 #detail .claims{margin-top:8px}
 #detail .cl{font-size:11px;color:#9fc4d8;border-left:2px solid rgba(34,211,238,.35);
   padding:3px 0 3px 9px;margin:6px 0;line-height:1.45}
 #detail a{color:var(--accent);text-decoration:none;font-size:10px} #detail a:hover{text-decoration:underline}
 .why{margin-top:10px;border-top:1px dashed rgba(34,211,238,.3);padding-top:9px}
 .why .lbl{font-size:10px;letter-spacing:.14em;color:#f59e0b;text-transform:uppercase}
 .why .txt{font-size:12px;color:#e7f4fb;line-height:1.5;margin-top:4px}
 .decbadge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
   padding:2px 9px;border-radius:6px;margin-top:6px;color:#02030a}
 #detail .btns{margin-top:11px;display:flex;gap:8px}
 #detail .btns button{flex:1;background:rgba(34,211,238,.14);border:1px solid var(--accent);color:#eafbff;
   font:11px Inter;padding:7px;border-radius:8px;cursor:pointer;letter-spacing:.05em}
 #detail .btns button:hover{background:rgba(34,211,238,.28)}
 #detail #d-orphan{font-size:11px;color:#f59e0b;margin-top:8px;min-height:1em}
 #mathpanel{display:none;top:64px;left:16px;max-width:330px;max-height:78vh;overflow:auto;font-size:11px;line-height:1.55}
 #mathpanel h2{margin:6px 0 5px;font-size:10px;letter-spacing:.14em;color:#f59e0b;text-transform:uppercase}
 #mathpanel .f{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#bcdcec;border-left:2px solid rgba(245,158,11,.4);padding:2px 0 2px 8px;margin:4px 0;line-height:1.4}
 #mathpanel .v{color:#eafbff} #mathpanel .v b{color:#f59e0b}
 #mathpanel .gl{display:flex;align-items:center;gap:6px;margin:2px 0}
 #mathpanel .gl span.g{font-size:13px;width:16px;text-align:center}
 #foot{bottom:16px;right:16px;font-size:10px;color:var(--dim);text-align:right;line-height:1.6}
 .close{position:absolute;top:11px;right:13px;cursor:pointer;color:var(--dim);font-size:18px;line-height:1}
 #hint{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);font-size:10px;color:var(--dim);
   letter-spacing:.1em;text-transform:uppercase;opacity:.55}
 #err{position:fixed;inset:0;display:none;align-items:center;justify-content:center;text-align:center;padding:40px}
</style>
<script src="https://unpkg.com/3d-force-graph@1.73.4/dist/3d-force-graph.min.js"></script>
</head><body>
<div id="graph"></div>
<div id="title" class="panel"><h1>Canvas // World-Map</h1>
 <div class="sub">THE WORLD at the top &rarr; Canvas's plug-ins &rarr; the UI&rarr;OS survivability spine &rarr; the implementation it stands on. Click a node to trace its branch up to the world &amp; read its WHY.</div>
 <div class="frontier" id="frontier"></div></div>
<div id="ctrlbar">
 <button id="cmode" title="cycle color mode">COLOR: LAYER</button>
 <button id="mathmode" title="overlay the math + schema engine (§7)">MATH / SCHEMA</button>
 <button id="orbit" title="survey orbit (off by default)">SURVEY ORBIT: OFF</button>
 <button id="reset" title="clear highlight">RESET VIEW</button>
</div>
<div id="mathpanel" class="panel"></div>
<div id="legend" class="panel"></div>
<div id="detail" class="panel"><span class="close" onclick="document.getElementById('detail').style.display='none'">&times;</span>
 <h3 id="d-name"></h3><div id="d-tags" class="tags"></div><div id="d-sm" class="sm"></div>
 <div class="barwrap">distance to incumbent parity <div class="bar"><div id="d-dist"></div></div></div>
 <div id="d-claims" class="claims"></div>
 <div class="why"><div class="lbl">Why it is in the map</div><div class="txt" id="d-why"></div>
   <span id="d-dec" class="decbadge"></span></div>
 <div id="d-orphan"></div>
 <div class="btns"><button id="d-dl">⬇ Extract context</button><button id="d-toggle">⊘ Disable node</button></div>
</div>
<div id="foot" class="panel"></div>
<div id="hint">living world-map &middot; click = trace branch + WHY &middot; shift-click = disable node</div>
<div id="err" class="panel"><div><h2 style="color:var(--accent)">3D engine offline</h2>
 <p style="color:var(--dim);font-size:13px;max-width:420px">This view loads the 3d-force-graph engine from a CDN and needs an internet connection the first time. Re-open online, or vendor the library locally.</p></div></div>
<script>
const GRAPH = __GRAPH__;
const META = __META__;
if(typeof ForceGraph3D === "undefined"){document.getElementById('err').style.display='flex';}
else { boot(); }
function boot(){
 const LEVELS=META.levels, GAP=150;
 // §2 rel palette (provider->dependent). reaches_world emphasized in overlay (§7).
 const relColor={gates:'#f43f5e',depends_on:'#38bdf8',controls:'#fbbf24',
   contains:'rgba(120,160,180,.22)',reaches_world:'rgba(16,185,129,.45)',
   ascends:'#22d3ee',implements:'#818cf8',addresses:'#34d399',benchmarks:'#f43f5e',
   peer:'#a78bfa',rel:'#64748b'};
 const nodeById={}; GRAPH.nodes.forEach(n=>nodeById[n.id]=n);
 const disabled=new Set();           // nodes toggled off
 let colorMode='layer';              // layer|feature|priority|distance
 let mathMode=false;                 // §7 MATH/SCHEMA overlay
 let highlightNodes=new Set(), highlightLinks=new Set();
 const colorKey={layer:'color',feature:'featureColor',priority:'priorityColor',distance:'distanceColor'};
 // §7 provenance glyphs (seed ◇ / manual ▣ / derived ● / merged ⬡)
 const PROV_GLYPH={seed:'◇',manual:'▣',derived:'●',merged:'⬡'};

 const G=ForceGraph3D()(document.getElementById('graph'))
   .backgroundColor('#02030a')
   .graphData(GRAPH)
   .nodeId('id').nodeVal('val').nodeOpacity(0.94).nodeResolution(14)
   .nodeColor(n=> disabled.has(n.id)?'#1b2430'
      : (highlightNodes.size && !highlightNodes.has(n.id))?'rgba(70,90,110,.18)'
      : n[colorKey[colorMode]]||'#64748b')
   .nodeVisibility(n=> !bandOff(n))
   .nodeLabel(n=>{
      const g=mathMode?(PROV_GLYPH[n.origin]||'')+' ':'';   // §7 provenance glyph
      const ring=(mathMode&&n.collector)?' <span style="color:#22d3ee">◯ collector</span>':'';
      const by=(n.origin==='manual'&&n.by)?` by ${esc(n.by)}`:'';
      return `<div style="font:12px Inter;background:#04101e;border:1px solid #22d3ee55;padding:4px 8px;border-radius:6px;color:#eafbff">${g}${esc(n.label)}<br><span style="color:#5b7a90;font-size:10px">L${n.level} · ${esc(n.band)} · ${esc(n.origin||'')}${by} · ${esc(n.status||'')}${ring}</span></div>`;})
   .linkColor(l=> (highlightLinks.size && !highlightLinks.has(l))?'rgba(60,80,100,.08)'
      :((mathMode&&l.rel==='reaches_world')?'#34d399':(relColor[l.rel]||'#475569')))
   .linkOpacity(0.5)
   .linkWidth(l=> highlightLinks.has(l)?2.4
      :((mathMode&&l.rel==='reaches_world')?3.0:(l.rel==='ascends'?2.0:(l.rel==='contains'?0.4:0.8))))
   .linkVisibility(l=> !disabled.has(srcId(l)) && !disabled.has(tgtId(l)))
   // §2: arrowheads on (flow provider->dependent). contains = membership, no arrow.
   .linkDirectionalArrowLength(l=> l.rel==='contains'?0:2.8)
   .linkDirectionalArrowRelPos(1)
   .linkDirectionalParticles(l=> particleRel(l.rel)?Math.max(1,Math.round((l.weight||0.4)*4)):0)
   .linkDirectionalParticleWidth(1.7)
   // §5 flow_speed(link) = 0.002 + 0.010*weight (precomputed server-side)
   .linkDirectionalParticleSpeed(l=> l.flow_speed!=null ? l.flow_speed : (0.002 + (l.weight||0.4)*0.010))
   .linkDirectionalParticleColor(l=> relColor[l.rel]||'#22d3ee')
   .onNodeClick((n,e)=>{ if(e&&e.shiftKey){toggleNode(n);} else {focusNode(n);traceBranch(n);showDetail(n);} });

 // VERTICAL LAYOUT: pin Y by level (top→bottom); x/z free.
 G.d3Force('y', a=>{ GRAPH.nodes.forEach(n=>{
    const targetY=(LEVELS-n.level)*GAP - (LEVELS*GAP/2);
    n.vy = (n.vy||0) + (targetY - n.y)*0.085*a; }); });
 G.d3Force('charge').strength(-130);

 function srcId(l){return typeof l.source==='object'?l.source.id:l.source;}
 function tgtId(l){return typeof l.target==='object'?l.target.id:l.target;}
 function particleRel(r){return !['contains'].includes(r);}
 function esc(s){return (s==null?'':String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;');}

 // ---- P0 (priority 3) subtle pulse ----
 const p0=GRAPH.nodes.filter(n=>n.priority===3);
 setInterval(()=>{const t=Date.now()*0.004; p0.forEach(n=>{n.__pulse=1+0.18*Math.sin(t);});
   G.nodeVal(n=> n.priority===3 ? n.val*(n.__pulse||1) : n.val);},60);

 // ---- adjacency (uses original GRAPH.links; bi already doubled server-side) ----
 const up={},down={};   // up: toward lower level (parents) ; down: dependents
 GRAPH.links.forEach(l=>{const s=srcId(l),t=tgtId(l);const a=nodeById[s],b=nodeById[t];if(!a||!b)return;
   // parent = the endpoint with the LOWER level (closer to world-root)
   if(b.level<a.level){(up[s]=up[s]||[]).push({id:t,rel:l.rel,link:l});(down[t]=down[t]||[]).push({id:s,rel:l.rel,link:l});}
   else if(a.level<b.level){(up[t]=up[t]||[]).push({id:s,rel:l.rel,link:l});(down[s]=down[s]||[]).push({id:t,rel:l.rel,link:l});}
   else {/* same level: treat as lateral dependency, not branch */}
 });

 // ---- CLICK: trace ALL branches UP to world-root + collect downstream ----
 function traceBranch(n){
   highlightNodes=new Set([n.id]); highlightLinks=new Set();
   // walk UP (toward level 0)
   const stack=[n.id],seen=new Set([n.id]);
   while(stack.length){const cur=stack.pop();(up[cur]||[]).forEach(e=>{highlightNodes.add(e.id);highlightLinks.add(e.link);
     if(!seen.has(e.id)){seen.add(e.id);stack.push(e.id);}});}
   // walk DOWN (dependents)
   const ds=[n.id],seen2=new Set([n.id]);
   while(ds.length){const cur=ds.pop();(down[cur]||[]).forEach(e=>{highlightNodes.add(e.id);highlightLinks.add(e.link);
     if(!seen2.has(e.id)){seen2.add(e.id);ds.push(e.id);}});}
   G.nodeColor(G.nodeColor()); G.linkColor(G.linkColor()); G.linkWidth(G.linkWidth());
 }
 function focusNode(n){const d=Math.hypot(n.x,n.y,n.z)||1,r=1+120/d;
   G.cameraPosition({x:n.x*r,y:n.y*r,z:n.z*r},n,900);}
 // sensible DEFAULT camera (used on load + on background-click reset, §7 camera fix a)
 const DEFAULT_CAM={x:0,y:0,z:Math.max(560,GRAPH.nodes.length*3)};
 function resetCamera(){ G.cameraPosition(DEFAULT_CAM,{x:0,y:0,z:0},700); }

 // ---- branch_to_top: ordered path n -> world-root (shortest by BFS up) ----
 function branchToTop(id){
   const prev={},q=[id],seen=new Set([id]);let hit=null;
   while(q.length){const c=q.shift();if(c==='world-root'){hit=c;break;}
     (up[c]||[]).forEach(e=>{if(!seen.has(e.id)){seen.add(e.id);prev[e.id]={from:c,rel:e.rel};q.push(e.id);}});}
   const path=[];let c=hit; if(!c) return path;
   while(c){const n=nodeById[c];path.unshift({id:c,label:n.label,level:n.level,rel_from_child:prev[c]?prev[c].rel:''});
     c=prev[c]?prev[c].from:null;}
   return path; // ordered top(world-root) ... clicked
 }
 function dependencies(id){
   const out=[],q=[{id,depth:0}],seen=new Set([id]);
   while(q.length){const {id:c,depth}=q.shift();(down[c]||[]).forEach(e=>{if(!seen.has(e.id)){seen.add(e.id);
     out.push({id:e.id,rel:e.rel,dir:e.link.dir||'uni',depth:depth+1});q.push({id:e.id,depth:depth+1});}});}
   return out;
 }
 // §8 role-based closures over link direction (provider=source -> dependent=target).
 // providers[x] = links where x is the DEPENDENT (target); what x depends on.
 // dependents[x] = links where x is the PROVIDER (source); what depends on x.
 const providers={},dependents={};
 GRAPH.links.forEach(l=>{const s=srcId(l),t=tgtId(l);
   (dependents[s]=dependents[s]||[]).push({id:t,rel:l.rel}); // s provides to t
   (providers[t]=providers[t]||[]).push({id:s,rel:l.rel});   // t depends on s
 });
 function fullNode(id,extra){const n=nodeById[id]||{id};
   return Object.assign({id:n.id,label:n.label,origin:n.origin,band:n.band,layer:n.layer,
     feature:n.feature,bin:n.bin,priority:n.priority,maturity:n.maturity,distance:n.distance,
     collector:n.collector,touches_internet:n.touches_internet,summary:n.summary,why:n.why,
     tag:n.tag,claims:n.claims||[]},extra||{});}
 function closure(adj,id){ // BFS, returns FULL inlined nodes w/ rel_to_focus + depth (§8)
   const out=[],q=[{id,depth:0}],seen=new Set([id]);
   while(q.length){const {id:c,depth}=q.shift();(adj[c]||[]).forEach(e=>{if(!seen.has(e.id)){seen.add(e.id);
     out.push(fullNode(e.id,{rel_to_focus:e.rel,depth:depth+1}));q.push({id:e.id,depth:depth+1});}});}
   return out;
 }
 // ---- impact_if_disabled: which nodes lose ALL paths to world-root if `id` removed ----
 function impactIfDisabled(id){return orphansAfter(new Set([id])).filter(x=>x!==id);}
 function orphansAfter(off){
   // BFS from world-root over links whose endpoints are not in `off`; any reachable=alive
   const alive=new Set();const q=['world-root'];if(off.has('world-root'))return GRAPH.nodes.map(n=>n.id).filter(x=>!off.has(x));
   alive.add('world-root');
   const adj={};GRAPH.links.forEach(l=>{const s=srcId(l),t=tgtId(l);
     (adj[s]=adj[s]||[]).push(t);(adj[t]=adj[t]||[]).push(s);});
   while(q.length){const c=q.shift();(adj[c]||[]).forEach(nb=>{if(off.has(nb)||off.has(c))return;
     if(!alive.has(nb)){alive.add(nb);q.push(nb);}});}
   return GRAPH.nodes.map(n=>n.id).filter(x=>!off.has(x)&&!alive.has(x));
 }

 // ---- NODE ON/OFF (neural-impact map) ----
 function toggleNode(n){
   disabled.has(n.id)?disabled.delete(n.id):disabled.add(n.id);
   const orphans=orphansAfter(new Set(disabled));
   document.getElementById('d-orphan').textContent =
     disabled.size? `${disabled.size} disabled · ${orphans.length} nodes orphaned (lost path to world)`:'';
   G.nodeColor(n2=> disabled.has(n2.id)?'#1b2430': orphans.includes(n2.id)?'rgba(120,60,60,.35)'
      : (highlightNodes.size && !highlightNodes.has(n2.id))?'rgba(70,90,110,.18)'
      : n2[colorKey[colorMode]]||'#64748b');
   G.linkVisibility(l=> !disabled.has(srcId(l)) && !disabled.has(tgtId(l)));
   const tb=document.getElementById('d-toggle'); tb.textContent = disabled.has(n.id)?'⦿ Re-enable node':'⊘ Disable node';
 }

 // ---- DETAIL CARD ----
 const decColor={build:'#34d399',ride:'#22d3ee',avoid:'#94a3b8',separate:'#f59e0b',gate:'#f43f5e',measure:'#a78bfa'};
 let current=null;
 function showDetail(n){current=n;const el=document.getElementById('detail');
   document.getElementById('d-name').textContent=n.label;
   const tags=[];tags.push('L'+n.level+' · '+n.band);
   tags.push((PROV_GLYPH[n.origin]||'')+' '+(n.origin||'derived'));   // §1 provenance
   if(n.origin==='manual'&&n.by)tags.push('by '+n.by);
   if(n.collector)tags.push('◯ collector');
   if(n.merged_from&&n.merged_from.length)tags.push('⬡ merged ×'+n.merged_from.length);
   if(n.feature&&n.feature!=='none')tags.push('feat: '+n.feature);
   if(n.bin)tags.push(n.bin);
   if(n.priority)tags.push('P'+(3-n.priority)); // priority 3->P0, 2->P1, 1->P2
   if(n.status)tags.push(n.status);
   document.getElementById('d-tags').innerHTML=tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('');
   document.getElementById('d-sm').textContent=n.summary||'(no summary)';
   const db=document.getElementById('d-dist');const dpc=Math.round((n.distance||0)*100);
   db.style.width=dpc+'%';db.style.background=n.distanceColor;
   const c=document.getElementById('d-claims');c.innerHTML=(n.claims&&n.claims.length)?
     '<div style="font-size:10px;letter-spacing:.1em;color:#22d3ee;text-transform:uppercase">Claims grounding this node</div>'+
     n.claims.map(x=>`<div class="cl">${esc(x.stmt)}${x.url?` <a href="${esc(x.url)}" target="_blank">[source]</a>`:''}</div>`).join(''):'';
   document.getElementById('d-why').textContent=n.why||'(no why authored)';
   const dec=document.getElementById('d-dec');dec.textContent='decision: '+(n.tag||'build');
   dec.style.background=decColor[n.tag]||'#34d399';
   document.getElementById('d-orphan').textContent = disabled.size?
     `${disabled.size} disabled · ${orphansAfter(new Set(disabled)).length} nodes orphaned`:'';
   document.getElementById('d-toggle').textContent = disabled.has(n.id)?'⦿ Re-enable node':'⊘ Disable node';
   el.style.display='block'; renderMathPanel();}   // §7 live math panel tracks selection
 document.getElementById('d-toggle').onclick=()=>{if(current)toggleNode(current);};
 document.getElementById('d-dl').onclick=()=>{if(current)downloadBranch(current);};

 // ---- §8 EXPORT: canvas-context-export/2 (self-contained, AI-decodable) ----
 function downloadBranch(n){
   const branch=branchToTop(n.id).map(b=>fullNode(b.id,{rel_from_child:b.rel_from_child}));
   const impact=impactIfDisabled(n.id).map(id=>({id,label:(nodeById[id]||{}).label||id,
     reason:'loses its only path to world-root if '+n.id+' is disabled'}));
   const exp={
     $schema:'canvas-context-export/2',
     generated_from:'graph-schema/2',
     exported:new Date().toISOString(),
     how_to_read:'This is one node and its world-slice. Every id referenced here resolves INSIDE '+
       'this file (closures + branch inline full node content). The glossary defines every band, '+
       'feature, rel, bin and formula used. An AI needs nothing else to decode this node.',
     glossary:META.glossary,
     focus:fullNode(n.id,{}),                 // FULL focal node
     provider_closure:closure(providers,n.id),   // what focus depends on (inlined)
     dependent_closure:closure(dependents,n.id),  // what depends on focus (inlined)
     branch_to_world:branch,                  // ancestors up to world-root (inlined)
     impact_if_disabled:impact,               // with reasons
     math:{ frontier_distance:META.frontier, focus_distance:(n.distance||0),
            val_breakdown:{base:(META.valBase[n.band]||4),claims:(n.claims||[]).length,
              claims_term:1.4*((n.claims||[]).length),priority:(n.priority||0),
              priority_term:2*(n.priority||0),val:n.val},
            formulas:META.formulas },
     decision:{why:n.why||'',tag:n.tag||''}
   };
   const blob=new Blob([JSON.stringify(exp,null,2)],{type:'application/json'});
   const a=document.createElement('a');a.href=URL.createObjectURL(blob);
   a.download='canvas-context-'+n.id+'.json';document.body.appendChild(a);a.click();
   setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},100);
 }

 // ---- COLOR-MODE toggle ----
 const cmodes=['layer','feature','priority','distance'];
 document.getElementById('cmode').onclick=function(){
   colorMode=cmodes[(cmodes.indexOf(colorMode)+1)%cmodes.length];
   this.textContent='COLOR: '+colorMode.toUpperCase();
   G.nodeColor(n=> disabled.has(n.id)?'#1b2430'
      :(highlightNodes.size && !highlightNodes.has(n.id))?'rgba(70,90,110,.18)'
      : n[colorKey[colorMode]]||'#64748b'); };

 // ---- §7 MATH / SCHEMA overlay ----
 const LEVEL_RULE={0:'world-root',1:'incumbent · layer-hub',2:'world · os_hook · actor',
   3:'bin · primitive',4:'impl · gh_issue'};
 const mp=document.getElementById('mathpanel');
 function renderMathPanel(){
   if(!mathMode){mp.style.display='none';return;}
   mp.style.display='block';
   let h='<h2>The engine (§5 math · §1-2 schema)</h2>';
   // provenance legend (§7)
   h+='<h2>Provenance</h2>';
   [['seed','◇ structural config'],['manual','▣ a human placed it'],
    ['derived','● research/refs'],['merged','⬡ folded aliases']].forEach(([k,d])=>{
     h+=`<div class="gl"><span class="g">${PROV_GLYPH[k]}</span>${d}</div>`;});
   // direction legend (§2)
   h+='<h2>Direction</h2><div class="f">provider &rarr; dependent (particle flows toward the consumer)</div>';
   h+='<div class="f" style="border-color:rgba(52,211,153,.5)">reaches_world: internet-touching node &rarr; world-root (§4, emphasized)</div>';
   // level bands (§5)
   h+='<h2>Level bands (§5)</h2>';
   Object.keys(LEVEL_RULE).forEach(k=>{h+=`<div class="f">L${k}: ${LEVEL_RULE[k]}</div>`;});
   // live math
   h+='<h2>Live math</h2>';
   h+=`<div class="f v">frontier_distance = <b>${META.frontier.toFixed(3)}</b> <span style="color:#5b7a90">(mean distance over primitives)</span></div>`;
   if(current){const n=current;
     h+=`<div class="f v">selected: <b>${esc(n.label)}</b></div>`;
     h+=`<div class="f v">distance = clamp(incStrength[${esc(n.feature)}] − maturity ${(n.maturity||0).toFixed(2)}) = <b>${(n.distance||0).toFixed(3)}</b></div>`;
     h+=`<div class="f v">priority = <b>${n.priority||0}</b> (P${3-(n.priority||0)})</div>`;
     const base=(META.valBase[n.band]||4),cl=(n.claims||[]).length;
     h+=`<div class="f v">val = ${base} + 1.4·${cl} + 2·${n.priority||0} = <b>${n.val}</b></div>`;
   } else { h+='<div class="f" style="color:#5b7a90">click a node for its val/priority/distance breakdown</div>'; }
   h+='<h2>Formulas (§5)</h2>';
   Object.values(META.formulas).forEach(f=>{h+=`<div class="f">${esc(f)}</div>`;});
   mp.innerHTML=h;
 }
 document.getElementById('mathmode').onclick=function(){ mathMode=!mathMode;
   this.classList.toggle('on',mathMode);
   // force node/link re-render so glyphs, collector rings, reaches_world emphasis update
   G.nodeColor(G.nodeColor()); G.linkColor(G.linkColor()); G.linkWidth(G.linkWidth());
   G.nodeLabel(G.nodeLabel());
   renderMathPanel(); };

 // ---- SURVEY ORBIT (off by default; starts after 30s idle; stops on interaction) ----
 let orbitOn=false,lastInteract=Date.now(),orbiting=false;const dist=DEFAULT_CAM.z;
 G.cameraPosition(DEFAULT_CAM);
 // §7 camera fix b: SMOOTH + CONSISTENT zoom — OrbitControls damping, single zoomSpeed, distance clamps.
 const ctr=G.controls();
 ctr.enableDamping=true; ctr.dampingFactor=0.12;
 ctr.zoomSpeed=0.9;                       // one consistent zoom speed at all depths
 ctr.minDistance=80; ctr.maxDistance=Math.max(2400,dist*2.2);   // even feel, clamped
 // background-click -> smooth reset to DEFAULT camera + lookAt origin (§7 camera fix a)
 G.onBackgroundClick(()=>{ highlightNodes=new Set(); highlightLinks=new Set();
   G.nodeColor(G.nodeColor()); G.linkColor(G.linkColor()); G.linkWidth(G.linkWidth());
   document.getElementById('detail').style.display='none'; resetCamera(); lastInteract=Date.now(); });
 ['start','change'].forEach(ev=>ctr.addEventListener(ev,()=>{lastInteract=Date.now();orbiting=false;}));
 document.getElementById('orbit').onclick=function(){orbitOn=!orbitOn;
   this.classList.toggle('on',orbitOn);this.textContent='SURVEY ORBIT: '+(orbitOn?'ON':'OFF');lastInteract=Date.now();};
 let ang=0;
 setInterval(()=>{ if(!orbitOn)return;
   if(Date.now()-lastInteract<30000){orbiting=false;return;}
   orbiting=true;ang+=0.0006;const p=G.cameraPosition();const d=Math.hypot(p.x,p.z)||dist;
   G.cameraPosition({x:d*Math.sin(ang),z:d*Math.cos(ang)}); },40);

 document.getElementById('reset').onclick=()=>{highlightNodes=new Set();highlightLinks=new Set();
   G.nodeColor(n=> disabled.has(n.id)?'#1b2430':n[colorKey[colorMode]]||'#64748b');
   G.linkColor(G.linkColor());G.linkWidth(G.linkWidth());
   document.getElementById('detail').style.display='none';resetCamera();};

 // ---- LEGEND = band + feature filters ----
 const bandOffSet=new Set();
 function bandOff(n){
   if(bandOffSet.has('band:'+n.band))return true;
   if(bandOffSet.has('feat:'+n.feature))return true;
   return false;
 }
 const lg=document.getElementById('legend');
 const bandItems=[['world-root',META.layerColor.cloud||'#e2e8f0','#e2e8f0'],
   ['incumbent','#cbd5e1','#cbd5e1'],['layer-hub','#a78bfa','#a78bfa'],['world','#475569','#64748b'],
   ['os_hook','#10b981','#10b981'],['bin','#22d3ee','#22d3ee'],['primitive','#10b981','#10b981'],
   ['impl','#818cf8','#818cf8'],['gh_issue','#34d399','#34d399']];
 lg.innerHTML='<h2>Bands (click to dim)</h2>';
 bandItems.forEach(([b,c])=>{const id='b_'+b.replace(/[^a-z0-9]/gi,'');
   lg.innerHTML+=`<div class="row" data-band="${b}" id="${id}"><span class="dot" style="color:${c};background:${c}"></span>${b}</div>`;});
 lg.innerHTML+='<div class="sep"></div><h2>Features</h2>';
 Object.entries(META.featureColor).forEach(([f,c])=>{const id='ft_'+f;
   lg.innerHTML+=`<div class="row" data-feat="${f}" id="${id}"><span class="dot" style="color:${c};background:${c}"></span>${f}</div>`;});
 lg.querySelectorAll('[data-band]').forEach(row=>{row.onclick=()=>{const key='band:'+row.dataset.band;
   bandOffSet.has(key)?bandOffSet.delete(key):bandOffSet.add(key);row.classList.toggle('off');
   G.nodeVisibility(n=>!bandOff(n));};});
 lg.querySelectorAll('[data-feat]').forEach(row=>{row.onclick=()=>{const key='feat:'+row.dataset.feat;
   bandOffSet.has(key)?bandOffSet.delete(key):bandOffSet.add(key);row.classList.toggle('off');
   G.nodeVisibility(n=>!bandOff(n));};});

 // ---- HUD ----
 document.getElementById('frontier').innerHTML=
   `FRONTIER DISTANCE <b>${META.frontier.toFixed(2)}</b><br><span style="color:#5b7a90">how far Canvas is from incumbent parity (mean over primitives)</span>`;
 document.getElementById('foot').innerHTML=
   `${META.nodes} nodes &middot; ${META.links} links<br>generated ${META.generated}<br>${esc(META.schema)} &middot; ${esc(META.export)}`;
}
</script></body></html>"""

def embed(obj):
    # escape "</" so research text containing "</script>" can never break the inline <script>
    return json.dumps(obj).replace("</", "<\\/")

out_html = (TEMPLATE
            .replace("__GRAPH__", embed(graph))
            .replace("__META__", embed(meta)))

# robustness: no leftover placeholders
for ph in ("__GRAPH__", "__META__"):
    if ph in out_html:
        print("FATAL: placeholder %s not substituted" % ph, file=sys.stderr)
        sys.exit(1)
assert "</script>" not in embed(graph), "unescaped </script> leaked into inlined data"
assert "</script>" not in embed(meta), "unescaped </script> leaked into inlined meta"

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    f.write(out_html)

# ---- RUN REPORT (§ visibility: counts, provenance, routing, merges, downgrades) ----
print("wrote", OUT)
print("nodes:", len(graph["nodes"]), "links:", len(links))
print("by origin:", json.dumps(by_origin))
print("by band:", json.dumps(by_band))
print("frontier_distance:", FRONTIER)
print("incumbent feature strengths:", json.dumps(incumbent_strength))
print("derived nodes auto-created (referenced-but-undeclared):", LOG["derived_created"])
print("layer-hubs auto-created:", LOG["hubs_created"])
print("world routed (reaches_world links):", LOG["world_routed"])
print("merges (explicit same_as/merge_into):", len(LOG["merges"]), LOG["merges"])
print("natural-key merges (derived label+layer):", len(LOG["natural_merges"]), LOG["natural_merges"])
print("bi-links downgraded to uni (no collector endpoint):", LOG["bi_downgraded"])
