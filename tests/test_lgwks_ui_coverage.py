from __future__ import annotations

import os
import lgwks_ui


def test_fg_color():
    # When on=False, fg must return s unchanged
    assert lgwks_ui.fg("hello", 67, on=False) == "hello"
    assert lgwks_ui.fg("world", 230, on=False, bold=True) == "world"

    # When on=True, fg must return a string containing \x1b[ and the original s inside it
    res = lgwks_ui.fg("hello", 67, on=True)
    assert "\x1b[" in res
    assert "hello" in res

    res_bold = lgwks_ui.fg("world", 230, on=True, bold=True)
    assert "\x1b[" in res_bold
    assert "world" in res_bold


def test_machine_mode(monkeypatch):
    # Set LGWRS_MACHINE to "1" and assert machine_mode() is True
    monkeypatch.setenv("LGWRS_MACHINE", "1")
    assert lgwks_ui.machine_mode() is True

    # Unset LGWRS_MACHINE and assert machine_mode() is False
    monkeypatch.delenv("LGWRS_MACHINE", raising=False)
    assert lgwks_ui.machine_mode() is False

    # Set to empty string and assert machine_mode() is False
    monkeypatch.setenv("LGWRS_MACHINE", "")
    assert lgwks_ui.machine_mode() is False


def test_rule_width():
    # With on=False, assert the returned string has length equal to width
    res = lgwks_ui.rule(width=20, ch="*", on=False)
    assert res == "*" * 20
    assert len(res) == 20

    # With default width=64, ch="━", and on=False
    res_default = lgwks_ui.rule(on=False)
    assert res_default == "━" * 64
    assert len(res_default) == 64
