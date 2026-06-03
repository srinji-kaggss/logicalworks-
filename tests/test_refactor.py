from __future__ import annotations

import ast
from pathlib import Path
import pytest

from lgwks_refactor import RefactorEngine, refactor_file


def test_rename_symbol():
    source = """
class OldClass:
    def old_method(self, val):
        return val

def old_func(x):
    obj = OldClass()
    return obj.old_method(x)
"""
    engine = RefactorEngine(source)
    engine.rename_symbol("OldClass", "NewClass")
    engine.rename_symbol("old_func", "new_func")
    refactored = engine.apply()
    
    # Parse back to verify structure and renames
    tree = ast.parse(refactored)
    class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    
    assert "NewClass" in class_names
    assert "OldClass" not in class_names
    assert "new_func" in func_names
    assert "old_func" not in func_names
    assert len(engine.preview()) >= 3


def test_add_type_annotations():
    source = """
def process(data, count, flag):
    pass
"""
    engine = RefactorEngine(source)
    engine.add_type_annotations({"data": "list[str]", "count": "int", "flag": "bool"})
    refactored = engine.apply()
    
    # Parse back and verify annotations
    tree = ast.parse(refactored)
    func = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    
    annotated = {arg.arg: ast.unparse(arg.annotation) for arg in func.args.args if arg.annotation}
    assert annotated["data"] == "list[str]"
    assert annotated["count"] == "int"
    assert annotated["flag"] == "bool"


def test_remove_unused_imports():
    source = """
import os
import sys
from pathlib import Path
from math import sqrt, sin

def compute(x):
    return sqrt(x)
"""
    engine = RefactorEngine(source)
    engine.remove_unused_imports()
    refactored = engine.apply()
    
    # Parse back and check imports
    tree = ast.parse(refactored)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(alias.name for alias in node.names)
            
    assert "sqrt" in imports
    assert "sin" not in imports  # unused
    assert "os" not in imports   # unused
    assert "sys" not in imports  # unused
    assert "Path" not in imports # unused
