# HARDEN-NOTES

Design questions and open follow-ups surfaced during spec→implement→harden. Each bullet is a
decision the Director should make before a future round. Bugs already fixed in the same branch
are not listed here — see the commit log.

## 2026-06-01 — fix/home-quick-hints-live (DiD T7: home launcher)

- **Silent introspection failure** — `_live_hints()` swallows ALL exceptions and emits an
  empty quick block with no diagnostic. The spec said "emit nothing," which is the correct
  default, but a user who upgrades the binary and breaks parser loading has no breadcrumb.
  Options: (a) print a one-line `lgwks-home: quick hints unavailable — run \`lgwks --help\``
  to stderr; (b) keep silent (status quo); (c) emit hints from a cached snapshot when
  introspection fails. Director call.
- **Cap=6 vs. fair-share across buckets** — current implementation fills bucket 0 (read)
  first, so a new verb added to the mutate bucket might never appear. With 9 read verbs
  and a cap of 6, mutate/orchestrator buckets are currently invisible. Spec said "cap at
  6" with order "read → mutate → orchestrator," which the implementation honors literally.
  Future option: `min(N, ceil(6/3))=2` per bucket, or a weighted fair-share. Director call.
- **Unknown verbs default to mutate band** — `_bucket_order` returns `(1, name)` for verbs
  not in the hardcoded maps, so a new verb is visible by default. This is the right call
  (silently hiding a new verb is worse than ordering it slightly off), but the maps must
  be kept in sync with the parser as new verbs land. The fix could be a code-review
  checklist: any new `sub.add_parser(...)` should be added to one of the three lists, or
  left in the mutate band deliberately.
- **sys.modules cache leak** — `_live_hints` registers `lgwks_cli` in `sys.modules` for
  Python 3.14's `@dataclass` introspection. Repeated calls reuse the cached module. Fine
  for the runtime (home runs once per process) and tests, but worth knowing if the launcher
  is ever invoked from a long-lived process where the cached parser could go stale.
- **Test coverage for `jarvis` (parent verb)** — `jarvis` is in `_MUTATE_NEXT` and is a
  parent for `crawl`/`remap-db`, so the rendered hint `lgwks jarvis` will dispatch to
  argparse's "choose a subcommand" error. The hint is technically correct (it IS a
  registered verb), but a user typing `lgwks jarvis` gets a usage error rather than a
  runnable example. Consider preferring a leaf verb (`jarvis crawl`) in the quick block.
