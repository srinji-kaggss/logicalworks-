"""
lgwks_refactor — deterministic AST-based refactoring engine.

Provides code transformations using Python's native `ast` module:
- Rename symbols (classes, functions, variables).
- Add type annotations to function arguments.
- Remove unused imports.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any

import lgwks_ui as ui


class RefactorEngine:
    def __init__(self, source: str, filename: str = "<unknown>"):
        self.source = source
        self.filename = filename
        self.tree = ast.parse(source, filename=filename)
        self.changes: list[dict[str, Any]] = []

    def rename_symbol(self, old_name: str, new_name: str) -> RefactorEngine:
        """Rename all occurrences of a class, function, or variable name."""
        class RenameTransformer(ast.NodeTransformer):
            def __init__(self, engine: RefactorEngine):
                self.engine = engine

            def visit_Name(self, node: ast.Name) -> ast.Name:
                if node.id == old_name:
                    node.id = new_name
                    self.engine.changes.append({
                        "type": "rename_name",
                        "old": old_name,
                        "new": new_name,
                        "line": getattr(node, "lineno", 0)
                    })
                return self.generic_visit(node)

            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
                if node.name == old_name:
                    node.name = new_name
                    self.engine.changes.append({
                        "type": "rename_func",
                        "old": old_name,
                        "new": new_name,
                        "line": node.lineno
                    })
                return self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
                if node.name == old_name:
                    node.name = new_name
                    self.engine.changes.append({
                        "type": "rename_async_func",
                        "old": old_name,
                        "new": new_name,
                        "line": node.lineno
                    })
                return self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
                if node.name == old_name:
                    node.name = new_name
                    self.engine.changes.append({
                        "type": "rename_class",
                        "old": old_name,
                        "new": new_name,
                        "line": node.lineno
                    })
                return self.generic_visit(node)

            def visit_arg(self, node: ast.arg) -> ast.arg:
                if node.arg == old_name:
                    node.arg = new_name
                    self.engine.changes.append({
                        "type": "rename_arg",
                        "old": old_name,
                        "new": new_name,
                        "line": getattr(node, "lineno", 0)
                    })
                return self.generic_visit(node)

        RenameTransformer(self).visit(self.tree)
        # Fix line numbers and missing parent links if any node structure changed
        ast.fix_missing_locations(self.tree)
        return self

    def add_type_annotations(self, type_map: dict[str, str]) -> RefactorEngine:
        """Add type annotations to function/method arguments based on parameter name."""
        class AnnotationTransformer(ast.NodeTransformer):
            def __init__(self, engine: RefactorEngine):
                self.engine = engine

            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
                self._annotate_args(node)
                return self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
                self._annotate_args(node)
                return self.generic_visit(node)

            @staticmethod
            def _is_safe_type_node(n: ast.AST) -> bool:
                # Allow: int, str, List[int], dict[str, Any], int | str
                if isinstance(n, ast.Name): return True
                if isinstance(n, ast.Attribute): return AnnotationTransformer._is_safe_type_node(n.value)
                if isinstance(n, ast.Subscript):
                    return AnnotationTransformer._is_safe_type_node(n.value) and AnnotationTransformer._is_safe_type_node(n.slice)
                if isinstance(n, ast.Constant) and n.value is None: return True
                if isinstance(n, ast.Constant) and isinstance(n.value, str): return True
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
                    return AnnotationTransformer._is_safe_type_node(n.left) and AnnotationTransformer._is_safe_type_node(n.right)
                if isinstance(n, ast.Tuple):
                    return all(AnnotationTransformer._is_safe_type_node(elt) for elt in n.elts)
                if isinstance(n, ast.List):
                    return all(AnnotationTransformer._is_safe_type_node(elt) for elt in n.elts)
                return False

            def _annotate_args(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
                for argument in node.args.args:
                    if argument.arg in type_map and argument.annotation is None:
                        type_str = type_map[argument.arg]
                        try:
                            # HARDEN: Validate type_str AST to prevent code execution (H12)
                            parsed_expr = ast.parse(type_str, mode="eval").body

                            if not self._is_safe_type_node(parsed_expr):
                                raise ValueError(f"dangerous type annotation: {type_str}")

                            argument.annotation = parsed_expr
                            self.engine.changes.append({
                                "type": "add_annotation",
                                "name": argument.arg,
                                "annotation": type_str,
                                "line": getattr(argument, "lineno", node.lineno)
                            })
                        except Exception:
                            # Fallback: only reached when the first ast.parse raised (malformed
                            # syntax) or _is_safe_type_node rejected the parsed expression as
                            # dangerous. Never build ast.Name(id=type_str) here -- type_str may be
                            # a composite annotation like "list[str]" or "dict[str, Any]", which is
                            # not a valid identifier and would silently produce a malformed AST.
                            # Re-parse defensively and re-validate with the same safety check;
                            # only accept a real expression node, and only if it is provably safe.
                            if not re.fullmatch(r"[a-zA-Z0-9_\[\],\. |]+", type_str):
                                continue  # too risky to even try parsing again

                            try:
                                fallback_expr = ast.parse(type_str, mode="eval").body
                            except SyntaxError:
                                continue

                            if not self._is_safe_type_node(fallback_expr):
                                continue  # confirmed dangerous (or unparseable) -- skip entirely

                            argument.annotation = fallback_expr

        AnnotationTransformer(self).visit(self.tree)
        ast.fix_missing_locations(self.tree)
        return self

    def remove_unused_imports(self) -> RefactorEngine:
        """Remove imports that are never referenced in the module."""
        # Step 1: Walk to collect all imported names, alias objects, and their node references
        imported_names: dict[str, tuple[ast.Import | ast.ImportFrom, ast.alias]] = {}
        
        class ImportCollector(ast.NodeVisitor):
            def visit_Import(self, node: ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names[name] = (node, alias)
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    name = alias.asname or alias.name
                    imported_names[name] = (node, alias)
                self.generic_visit(node)

        ImportCollector().visit(self.tree)

        if not imported_names:
            return self

        # Step 2: Walk to collect all referenced names in the module (excluding inside imports)
        used_names: set[str] = set()

        class NameUsageVisitor(ast.NodeVisitor):
            def visit_Name(self, node: ast.Name):
                used_names.add(node.id)
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import):
                # Skip visiting import statements to avoid self-referencing
                pass

            def visit_ImportFrom(self, node: ast.ImportFrom):
                # Skip visiting import statements
                pass

        NameUsageVisitor().visit(self.tree)

        # Step 3: Identify unused imports
        unused = set(imported_names.keys()) - used_names
        if not unused:
            return self

        # Step 4: Rebuild/Filter import nodes using a NodeTransformer
        class ImportFilter(ast.NodeTransformer):
            def __init__(self, engine: RefactorEngine):
                self.engine = engine

            def visit_Import(self, node: ast.Import) -> ast.Import | None:
                new_names = [alias for alias in node.names if (alias.asname or alias.name) not in unused]
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name in unused:
                        self.engine.changes.append({
                            "type": "remove_import",
                            "name": name,
                            "line": node.lineno
                        })
                if not new_names:
                    return None
                node.names = new_names
                return node

            def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom | None:
                new_names = [alias for alias in node.names if (alias.asname or alias.name) not in unused]
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name in unused:
                        self.engine.changes.append({
                            "type": "remove_import",
                            "name": name,
                            "line": node.lineno
                        })
                if not new_names:
                    return None
                node.names = new_names
                return node

        self.tree = ImportFilter(self).visit(self.tree)
        ast.fix_missing_locations(self.tree)
        return self

    def apply(self) -> str:
        """Return the refactored code as a string."""
        return ast.unparse(self.tree)

    def preview(self) -> list[dict[str, Any]]:
        """Return the list of recorded changes."""
        return self.changes


def refactor_file(path_or_at: str | Path, operations: list[dict], dry_run: bool = False) -> dict:
    """Apply refactoring operations to a file or inlined payload."""
    import lgwks_inline
    try:
        source = lgwks_inline.resolve_payload(str(path_or_at) if isinstance(path_or_at, Path) else f"@{path_or_at}")
        engine = RefactorEngine(source, filename=str(path_or_at))
    except Exception as e:
        return {"ok": False, "error": f"Failed to resolve or parse source: {e}"}


    for op in operations:
        op_type = op.get("op")
        if op_type == "rename":
            engine.rename_symbol(op["old"], op["new"])
        elif op_type == "add_types":
            engine.add_type_annotations(op["type_map"])
        elif op_type == "remove_unused_imports":
            engine.remove_unused_imports()

    changes = engine.preview()
    if not changes:
        return {"ok": True, "path": str(path_or_at), "changes_count": 0, "changes": []}

    if not dry_run:
        try:
            new_source = engine.apply()
            # If path_or_at is a Path object, use it; otherwise, wrap string as Path
            file_path = path_or_at if isinstance(path_or_at, Path) else Path(path_or_at)
            file_path.write_text(new_source, encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"Failed to write refactored file: {e}"}

    return {
        "ok": True,
        "path": str(path_or_at),
        "changes_count": len(changes),
        "changes": changes
    }


def refactor_command(args: argparse.Namespace) -> int:
    path_or_at = args.file
    ops = []
    if args.op == "rename":
        if not args.old or not args.new:
            print("[refactor] Error: rename requires --old and --new", file=sys.stderr)
            return 1
        ops.append({"op": "rename", "old": args.old, "new": args.new})
    elif args.op == "add_types":
        if not args.type_map:
            print("[refactor] Error: add_types requires --type-map JSON", file=sys.stderr)
            return 1
        try:
            type_map = json.loads(args.type_map)
            ops.append({"op": "add_types", "type_map": type_map})
        except Exception as e:
            print(f"[refactor] Error: invalid type-map JSON: {e}", file=sys.stderr)
            return 1
    elif args.op == "remove_unused_imports":
        ops.append({"op": "remove_unused_imports"})

    res = refactor_file(path_or_at, ops, dry_run=args.preview)
    
    if not res["ok"]:
        print(f"[refactor] FAILED: {res.get('error')}", file=sys.stderr)
        return 1

    on = ui.color_on()
    out = [""]
    p_obj = Path(path_or_at)
    title = f"{p_obj.name} — REFACTORED" if not args.preview else f"{p_obj.name} — PREVIEW"
    out += ui.band("lgwks · refactor", title, on=on)
    out.append(ui.spine(on=on))
    
    if res["changes_count"] == 0:
        out.append(ui.spine(ui.fg("No changes identified.", ui.CREAM_DIM, on=on), on=on))
    else:
        out.append(ui.spine(ui.fg(f"✓ {res['changes_count']} changes identified", ui.EMERALD, on=on), on=on))
        for change in res["changes"]:
            ctype = change["type"]
            line = change["line"]
            if ctype.startswith("rename"):
                detail = f"Rename: {change['old']} → {change['new']}"
            elif ctype == "add_annotation":
                detail = f"Annotate: {change['name']}: {change['annotation']}"
            elif ctype == "remove_import":
                detail = f"Remove unused import: {change['name']}"
            else:
                detail = str(change)
            out.append(ui.twig(f"Line {line}: {detail}", 1, "refactor", on=on))
            
    out.append("")
    print("\n".join(out))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("refactor", help="deterministic AST-based code refactoring")
    p.add_argument("--file", required=True, help="target Python source file")
    p.add_argument("--preview", action="store_true", help="preview changes without modifying file")
    
    sub_ops = p.add_subparsers(dest="op", required=True)
    
    rename = sub_ops.add_parser("rename", help="rename a symbol")
    rename.add_argument("--old", required=True, help="original name")
    rename.add_argument("--new", required=True, help="new name")
    
    add_types = sub_ops.add_parser("add_types", help="annotate function arguments")
    add_types.add_argument("--type-map", required=True, help="JSON string maps parameter names to type names")
    
    sub_ops.add_parser("remove_unused_imports", help="strip unused imports")
    
    p.set_defaults(func=refactor_command)
