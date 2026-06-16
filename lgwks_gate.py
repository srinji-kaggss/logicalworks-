"""lgwks_gate — unified safety and governance gate router.
Consolidates AUP, Comprehension, Coherence, and Admission.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

def gate_command(args: argparse.Namespace) -> int:
    cmd = getattr(args, "gate_cmd", "")
    
    if cmd == "aup":
        import lgwks_aup
        # Map args
        return lgwks_aup.main(args)
    
    if cmd == "comprehend":
        import lgwks_comprehend
        return lgwks_comprehend.comprehend_command(args)
        
    if cmd == "cohere":
        import lgwks_cohere
        return lgwks_cohere.cohere_command(args)
        
    if cmd == "admission":
        import lgwks_admission
        # admission uses subcommands too, so we might need a more complex mapping
        # but for now we'll just call the relevant function
        if getattr(args, "admission_cmd", "") == "info":
            return lgwks_admission._cmd_info(args)
        return lgwks_admission._cmd_check(args)

    print(f"error: unknown gate command {cmd}", file=sys.stderr)
    return 1


def add_parser(sub) -> None:
    p = sub.add_parser("gate", help="T8: safety and governance gates (AUP, Cohere, Admission)")
    gs = p.add_subparsers(dest="gate_cmd", required=True)
    
    # aup
    aup = gs.add_parser("aup", help="check platform AUP")
    aup.add_argument("input", nargs="?", default="")
    aup.add_argument("--file")
    aup.set_defaults(func=gate_command)
    
    # comprehend
    comp = gs.add_parser("comprehend", help="intention x understanding gate")
    comp.add_argument("--file", required=True)
    comp.add_argument("--unit", default="U1")
    comp.set_defaults(func=gate_command)
    
    # cohere
    coh = gs.add_parser("cohere", help="coherence engine pipeline")
    coh.add_argument("--file", required=True)
    coh.add_argument("--crate-dir", required=True)
    coh.set_defaults(func=gate_command)
    
    # admission
    adm = gs.add_parser("admission", help="token-bucket admission")
    adm_sub = adm.add_subparsers(dest="admission_cmd", required=False)
    adm_info = adm_sub.add_parser("info")
    adm_chk = adm_sub.add_parser("check")
    adm_chk.add_argument("--tenant", default="guest")
    adm.set_defaults(func=gate_command)
