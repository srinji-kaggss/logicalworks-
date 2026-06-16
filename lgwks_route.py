"""lgwks_route — unified intent routing.
Consolidates map, engine, route, and refine.
"""

from __future__ import annotations

import argparse
import sys
import json
from pathlib import Path

def route_command(args: argparse.Namespace) -> int:
    cmd = getattr(args, "route_cmd", "")
    
    if cmd == "map":
        import lgwks_map
        return lgwks_map.map_command(args)
    
    if cmd == "engine":
        import lgwks_engine
        return lgwks_engine.engine_command(args)
        
    if cmd == "refine":
        import lgwks_machine
        return lgwks_machine.refine_command(args)

    print(f"error: unknown route command {cmd}", file=sys.stderr)
    return 1


def add_parser(sub) -> None:
    p = sub.add_parser("route", help="T3: intent routing and refinement")
    rs = p.add_subparsers(dest="route_cmd", required=True)
    
    # map
    m = rs.add_parser("map", help="rank verbs by relevance")
    m.add_argument("intent")
    m.set_defaults(func=route_command)
    
    # engine
    e = rs.add_parser("engine", help="subconscious engine: produce schema")
    e.add_argument("prompt")
    e.set_defaults(func=route_command)
    
    # refine
    ref = rs.add_parser("refine", help="intent refinement")
    ref.add_argument("intent")
    ref.set_defaults(func=route_command)
