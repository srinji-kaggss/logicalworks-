"""lgwks_crawl — unified crawler dispatcher.
Merges fetch, crawl, and legacy jarvis into one canonical verb.
"""

from __future__ import annotations

import argparse
import json
import sys

import lgwks_substrate_io as _io  # canonical filesystem slug (one source of truth)


def crawl_command(args: argparse.Namespace) -> int:
    """Unified crawl command."""
    target = args.target
    engine = getattr(args, "engine", "substrate")
    
    # If it's not a URL, it's likely a keyword crawl, which forces 'jarvis' (legacy)
    is_url = target.startswith(("http://", "https://"))
    if not is_url:
        engine = "jarvis"

    if engine == "substrate":
        import lgwks_substrate as sub
        # Map unified args to substrate args
        sub_args = argparse.Namespace(
            target=target,
            project=getattr(args, "name", f"crawl-{_io._slug(target)[:32]}"),
            source_type="auto",
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            max_files=250,
            max_chars=getattr(args, "max_chars", 120_000),
            chunk_words=getattr(args, "chunk_words", 320),
            chunk_overlap=getattr(args, "chunk_overlap", 48),
            fact_threshold=0.6,
            embed_provider=getattr(args, "embed_provider", "deterministic"),
            embed_model=getattr(args, "embed_model", ""),
            login_if_needed=True,
            login_url="",
            success_selector=None,
            max_auto_bypass_attempts=3,
            max_auth_handoffs=3,
            browser_engine="chromium" if getattr(args, "chromium", False) else "webkit",
            click_discovery=bool(getattr(args, "click_discovery", False)),
            max_clicks_per_page=int(getattr(args, "max_clicks_per_page", 20)),
            crawl_mode=getattr(args, "crawl_mode", "link-then-click"),
        )
        try:
            manifest = sub.build_run(sub_args)
            if getattr(args, "json", False):
                print(json.dumps(manifest, indent=2, ensure_ascii=False))
            else:
                print(f"✅ Crawl complete (substrate). Run dir: {manifest['artifacts']['root']}")
            return 0
        except Exception as e:
            print(f"❌ Substrate crawl failed: {e}", file=sys.stderr)
            return 1

    elif engine == "jarvis":
        import lgwks_jarvis as jarvis
        # Map unified args to jarvis args
        jarvis_args = argparse.Namespace(
            source=target,
            keyword_terms=[],
            keywords=None,
            prompt=getattr(args, "prompt", "map the machine-state understanding"),
            name=getattr(args, "name", None),
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            workers=getattr(args, "workers", 2),
            include_external=getattr(args, "include_external", False),
            search_expansion=getattr(args, "search_expansion", False),
            chunk_words=getattr(args, "chunk_words", 450),
            chunk_overlap=getattr(args, "chunk_overlap", 70),
            max_terms=getattr(args, "max_terms", 120),
            compress_limit=getattr(args, "compress_limit", 96),
            similarity_threshold=getattr(args, "similarity_threshold", 0.72),
            estimate_only=getattr(args, "estimate_only", False),
        )
        return jarvis.crawl_command(jarvis_args)

    else:
        print(f"error: unknown engine {engine}", file=sys.stderr)
        return 1


def add_parser(sub) -> None:
    p = sub.add_parser(
        "crawl",
        help="unified URL/keyword crawler (merges fetch, jarvis, substrate)",
    )
    p.add_argument("target", help="URL to crawl or keyword seed")
    p.add_argument("--engine", choices=["substrate", "jarvis"], default="substrate",
                   help="crawl engine: 'substrate' (auth-aware) or 'jarvis' (legacy deterministic)")
    
    p.add_argument("--max-pages", type=int, default=12)
    p.add_argument("--max-depth", type=int, default=1)
    p.add_argument("--max-chars", type=int, default=120_000)
    p.add_argument("--name", help="project/run name")
    p.add_argument("--json", action="store_true", help="output JSON manifest")
    
    # Engine-specific flags (pass-through)
    p.add_argument("--chromium", action="store_true", help="(substrate) use chromium")
    p.add_argument("--click-discovery", action="store_true", help="(substrate) interactive discovery")
    p.add_argument("--search-expansion", action="store_true", help="(jarvis) use googler")
    
    p.set_defaults(func=crawl_command)
