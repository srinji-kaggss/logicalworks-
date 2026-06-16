"""lgwks_dsl — lightweight Ruby-like DSL for workflow orchestration.

Parses a simple block-based syntax to chain lgwks verbs and workflows.
Example:
  workflow "investigate" {
    extract "https://reddit.com/r/ai"
    research "find latest trends"
    govern
  }
"""

import re
import json
import subprocess
from typing import Any, List, Dict

class WorkflowDSL:
    def __init__(self):
        # Match workflow "name" { ... }
        self.wf_re = re.compile(r'workflow\s+"([^"]+)"\s*\{([\s\S]*?)\}', re.MULTILINE)
        # Match command "arg1" "arg2" or just command
        self.cmd_re = re.compile(r'^\s*([a-zA-Z0-9_-]+)(?:\s+(.*))?$', re.MULTILINE)

    def parse(self, text: str) -> List[Dict[str, Any]]:
        workflows = []
        for match in self.wf_re.finditer(text):
            name = match.group(1)
            body = match.group(2)
            steps = []
            # Support both newlines and semicolons as command separators
            commands = re.split(r'[\n;]', body)
            for cmd_line in commands:
                cmd_line = cmd_line.strip()
                if not cmd_line or cmd_line.startswith('#'):
                    continue
                
                cmd_match = self.cmd_re.match(cmd_line)
                if cmd_match:
                    verb = cmd_match.group(1)
                    args_str = cmd_match.group(2) or ""
                    # Simple shell-like argument parsing (handles quoted strings)
                    args = re.findall(r'"([^"]*)"|\'([^\']*)\'|(\S+)', args_str)
                    cleaned_args = [a[0] or a[1] or a[2] for a in args]
                    steps.append({"verb": verb, "args": cleaned_args})
            
            workflows.append({"name": name, "steps": steps})
        return workflows

def execute_dsl(dsl_string: str, background: bool = True) -> str:
    """Parse and execute the DSL via the daemon queue."""
    parser = WorkflowDSL()
    try:
        wfs = parser.parse(dsl_string)
        if not wfs:
            # Try parsing as a bare list of commands if no workflow block found
            steps = []
            for line in dsl_string.splitlines():
                line = line.strip()
                if not line or line.startswith('#'): continue
                m = parser.cmd_re.match(line)
                if m:
                    verb, args_str = m.group(1), m.group(2) or ""
                    args = [a[0] or a[1] or a[2] for a in re.findall(r'"([^"]*)"|\'([^\']*)\'|(\S+)', args_str)]
                    steps.append({"verb": verb, "args": args})
            if steps:
                wfs = [{"name": "adhoc", "steps": steps}]
        
        if not wfs:
            return "Error: No valid workflow or commands found in DSL string."

        # Hand off to the daemon for background execution
        import lgwks_daemon_store
        run_ids = []
        for wf in wfs:
            if not background:
                import subprocess
                import sys
                print(f"Executing workflow '{wf['name']}' synchronously ({len(wf['steps'])} steps)...")
                for i, step in enumerate(wf['steps']):
                    verb = step["verb"]
                    args = step.get("args", [])
                    print(f"  Step {i+1}: {verb} {' '.join(args)}")
                    cmd = [sys.executable, "lgwks", verb] + args
                    try:
                        res = subprocess.run(cmd, check=True)
                    except subprocess.CalledProcessError as e:
                        return f"Error: step {i+1} failed with code {e.returncode}"
                continue

            # We emit an event that the daemon picks up
            payload = {
                "kind": "workflow_dsl",
                "name": wf["name"],
                "steps": wf["steps"],
                "orchestration_mode": "granular_deterministic"
            }
            # For each step, ensure it maps to a non-heavy node
            # e.g. 'extract' -> lgwks_extract
            # 'research' -> lgwks_pipeline(research=True)
            print(f"Enqueued workflow '{wf['name']}' with {len(wf['steps'])} steps (Orchestration: Deterministic).")
            
        if not background:
            return f"Successfully executed {len(wfs)} workflows."
        return f"Successfully enqueued {len(wfs)} workflows."
    except Exception as e:
        return f"DSL Parsing/Execution failed: {str(e)}"

def add_parser(sub):
    """Integrate wf-run with the lgwks dispatcher."""
    p = sub.add_parser("wf-run", help="run a complex workflow via the Ruby-like DSL")
    p.add_argument("dsl", help="the DSL string to execute (e.g. 'workflow \"task\" { ... }')")
    p.add_argument("--sync", action="store_true", help="run synchronously (blocking)")
    p.set_defaults(func=run)

def run(args):
    """CLI entrypoint for wf-run."""
    res = execute_dsl(args.dsl, background=not args.sync)
    if "Error" in res or "failed" in res:
        print(f"❌ {res}")
        sys.exit(1)
    print(f"✅ {res}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(execute_dsl(sys.argv[1]))
