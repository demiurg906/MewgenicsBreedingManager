"""The "Toggle Can Breed" switch gates focus-cat compatibility dimming."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_proj_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_proj_root / "src"))
sys.path.insert(0, str(_proj_root))

import mewgenics_manager  # noqa: F401  — runs package initialisation
from mewgenics.models.cat_table_model import CatTableModel


class _FocusCat:
    pass


def _model_with_compat(monkeypatch):
    model = CatTableModel()
    focus, other = _FocusCat(), _FocusCat()
    # Every non-focus cat is "incompatible" so the test exercises the gate, not the rules.
    monkeypatch.setattr("mewgenics.models.cat_table_model.can_breed", lambda a, b: (False, "blocked"))
    model._focus_cat = focus
    return model, focus, other


def test_dimming_off_by_default(monkeypatch):
    model, focus, other = _model_with_compat(monkeypatch)
    assert model.dim_incompatible() is False
    assert model._compat_for(other) is None


def test_dimming_applies_when_enabled(monkeypatch):
    model, focus, other = _model_with_compat(monkeypatch)
    model.set_dim_incompatible(True)
    assert model._compat_for(other) == "incompatible"
    assert model._compat_for(focus) is None
    model.set_dim_incompatible(False)
    assert model._compat_for(other) is None
