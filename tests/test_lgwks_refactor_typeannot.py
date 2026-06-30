from __future__ import annotations

import ast

from lgwks_refactor import RefactorEngine


def _annotation_str_for(source: str, arg_name: str, type_map: dict[str, str]) -> str | None:
    """Helper: run add_type_annotations and return the unparsed annotation for arg_name,
    or None if no annotation was attached."""
    engine = RefactorEngine(source)
    engine.add_type_annotations(type_map)
    refactored = engine.apply()
    tree = ast.parse(refactored)
    func = next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    arg = next(a for a in func.args.args if a.arg == arg_name)
    if arg.annotation is None:
        return None
    return ast.unparse(arg.annotation)


def test_simple_type_annotation():
    """A plain identifier type (int) is parsed and attached as a real ast.Name node."""
    source = """
def f(x):
    pass
"""
    annotation = _annotation_str_for(source, "x", {"x": "int"})
    assert annotation == "int"


def test_composite_subscript_type_annotation():
    """A composite type string like list[str] must become a real Subscript expression
    node (via ast.parse + safety re-check), not ast.Name(id='list[str]') -- which would
    not be a valid Python identifier."""
    source = """
def f(data):
    pass
"""
    engine = RefactorEngine(source)
    engine.add_type_annotations({"data": "list[str]"})
    refactored = engine.apply()

    tree = ast.parse(refactored)
    func = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    annotation = func.args.args[0].annotation

    assert isinstance(annotation, ast.Subscript)
    assert isinstance(annotation.value, ast.Name)
    assert annotation.value.id == "list"
    assert ast.unparse(annotation) == "list[str]"


def test_composite_dict_type_annotation():
    """dict[str, Any] -- a Subscript whose slice is a Tuple of two Name nodes -- must
    round-trip through the safety check (covers the Tuple branch in _is_safe_type_node)."""
    source = """
def f(mapping):
    pass
"""
    annotation = _annotation_str_for(source, "mapping", {"mapping": "dict[str, Any]"})
    assert annotation == "dict[str, Any]"


def test_union_none_type_annotation():
    """int | None -- a BinOp(BitOr) of a Name and a Constant(None) -- exercises the
    BinOp/BitOr branch and the Constant-is-None branch of _is_safe_type_node."""
    source = """
def f(optional):
    pass
"""
    annotation = _annotation_str_for(source, "optional", {"optional": "int | None"})
    assert annotation == "int | None"


def test_multiple_composite_annotations_in_one_pass():
    """Regression test for the comprehension-variable shadowing bug: annotating several
    arguments with composite types (including a Tuple-shaped slice) in a single
    add_type_annotations call must not raise NameError/UnboundLocalError from inside
    _is_safe_type_node's Tuple/List branches."""
    source = """
def process(data, mapping, optional, pair):
    pass
"""
    engine = RefactorEngine(source)
    engine.add_type_annotations({
        "data": "list[str]",
        "mapping": "dict[str, Any]",
        "optional": "int | None",
        "pair": "tuple[int, str]",
    })
    refactored = engine.apply()

    tree = ast.parse(refactored)
    func = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    annotated = {arg.arg: ast.unparse(arg.annotation) for arg in func.args.args if arg.annotation}

    assert annotated["data"] == "list[str]"
    assert annotated["mapping"] == "dict[str, Any]"
    assert annotated["optional"] == "int | None"
    assert annotated["pair"] == "tuple[int, str]"


def test_dangerous_type_string_is_rejected_not_executed():
    """A malicious type string must never be turned into an executable/invalid AST node.
    add_type_annotations must silently decline to annotate the argument rather than
    raising the string into ast.Name(id=...) (which crosses from a data string into
    code-like AST shape) or letting the call expression survive."""
    source = """
def unsafe_func(x):
    pass
"""
    annotation = _annotation_str_for(
        source, "x", {"x": "__import__('os').system('x')"}
    )
    # Must be skipped entirely: no annotation attached, and definitely no ast.Call /
    # ast.Name(id="__import__('os').system('x')") leaking into the tree.
    assert annotation is None


def test_dangerous_type_string_leaves_no_call_node_in_tree():
    """Belt-and-suspenders: walk the whole refactored tree and assert no Call node
    (e.g. __import__(...) or .system(...)) was ever spliced in as an annotation."""
    source = """
def unsafe_func(x):
    pass
"""
    engine = RefactorEngine(source)
    engine.add_type_annotations({"x": "__import__('os').system('x')"})
    refactored = engine.apply()
    tree = ast.parse(refactored)

    func = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    assert func.args.args[0].annotation is None

    for node in ast.walk(tree):
        assert not isinstance(node, ast.Call)


def test_malformed_type_string_does_not_crash():
    """A syntactically invalid type string (not parseable at all) must be skipped
    cleanly, not raise out of add_type_annotations."""
    source = """
def f(x):
    pass
"""
    annotation = _annotation_str_for(source, "x", {"x": "int[[["})
    assert annotation is None


def test_existing_annotation_is_not_overwritten():
    """add_type_annotations must only fill in missing annotations, never replace one
    a developer already wrote."""
    source = """
def f(x: str):
    pass
"""
    annotation = _annotation_str_for(source, "x", {"x": "int"})
    assert annotation == "str"
