"""Tests for the right-click column value filters (Tags / Room / Status)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_proj_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_proj_root / "src"))
sys.path.insert(0, str(_proj_root))

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QPoint
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton

import mewgenics_manager  # noqa: F401  — runs package initialisation
from mewgenics.constants import COL_TAGS, COL_ROOM, COL_STAT
from mewgenics.models.room_filter_model import RoomFilterModel, EMPTY_FILTER_VALUE
from mewgenics.panels.column_filter_popup import ColumnFilterHeader, ColumnValueFilterPopup


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _cat(name, room, status="In House", name_tag=""):
    return SimpleNamespace(name=name, room=room, status=status, name_tag=name_tag,
                           tags=[], is_pinned=False, db_key=hash(name))


class _StubModel(QAbstractTableModel):
    def __init__(self, cats):
        super().__init__()
        self._cats = cats

    def cat_at(self, row):
        return self._cats[row] if 0 <= row < len(self._cats) else None

    def rowCount(self, parent=QModelIndex()):
        return len(self._cats)

    def columnCount(self, parent=QModelIndex()):
        return COL_TAGS + 1

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        cat = self._cats[index.row()]
        if index.column() == COL_ROOM:
            return cat.room
        if index.column() == COL_STAT:
            return cat.status
        return cat.name


@pytest.fixture
def proxy(qt_app):
    cats = [
        _cat("Ann", "Attic", name_tag="Hero"),
        _cat("Bob", "Attic"),
        _cat("Cid", "Floor1", status="Adventure", name_tag="Hero"),
        _cat("Dee", "Floor2", name_tag="Villain"),
    ]
    model = RoomFilterModel()
    model.setSourceModel(_StubModel(cats))
    model._stub = model.sourceModel()  # keep the source alive
    return model


def _visible_names(proxy):
    src = proxy.sourceModel()
    return sorted(src.cat_at(proxy.mapToSource(proxy.index(r, 0)).row()).name for r in range(proxy.rowCount()))


def test_room_filter_multiple_values(proxy):
    proxy.set_column_value_filter(COL_ROOM, {"Attic", "Floor2"})
    assert _visible_names(proxy) == ["Ann", "Bob", "Dee"]


def test_tag_filter_matches_any_tag_and_empty(proxy):
    proxy.set_column_value_filter(COL_TAGS, {"Hero"})
    assert _visible_names(proxy) == ["Ann", "Cid"]
    proxy.set_column_value_filter(COL_TAGS, {EMPTY_FILTER_VALUE})
    assert _visible_names(proxy) == ["Bob"]


def test_filters_combine_across_columns(proxy):
    proxy.set_column_value_filter(COL_TAGS, {"Hero"})
    proxy.set_column_value_filter(COL_STAT, {"In House"})
    assert _visible_names(proxy) == ["Ann"]


def test_available_values_ignore_own_column_but_respect_others(proxy):
    proxy.set_column_value_filter(COL_ROOM, {"Attic"})
    # Own filter ignored: every room still offered.
    assert proxy.available_column_values(COL_ROOM) == ["Attic", "Floor1", "Floor2"]
    # Other columns only offer values from visible rows; empty sorts last.
    assert proxy.available_column_values(COL_TAGS) == ["Hero", EMPTY_FILTER_VALUE]


def test_empty_selection_clears_filter(proxy):
    proxy.set_column_value_filter(COL_ROOM, {"Attic"})
    proxy.set_column_value_filter(COL_ROOM, set())
    assert proxy.column_value_filters == {}
    assert len(_visible_names(proxy)) == 4


def test_popup_toggle_and_reset(qt_app):
    popup = ColumnValueFilterPopup("Room", ["Attic", "Floor1"], {"Attic"})
    emitted = []
    popup.valuesChanged.connect(emitted.append)
    checks = {c.text(): c for c in popup.findChildren(QCheckBox)}
    assert checks["Attic"].isChecked() and not checks["Floor1"].isChecked()
    checks["Floor1"].setChecked(True)
    assert emitted[-1] == {"Attic", "Floor1"}
    reset = next(b for b in popup.findChildren(QPushButton) if b.text() == "Reset")
    reset.click()
    assert emitted[-1] == set()
    assert not any(c.isChecked() for c in checks.values())
    popup.close()


def test_header_emits_only_for_filterable_columns(qt_app):
    header = ColumnFilterHeader([COL_ROOM])
    header.setModel(_StubModel([_cat("Ann", "Attic")]))
    requested = []
    header.filterRequested.connect(lambda col, pos: requested.append(col))
    from PySide6.QtGui import QContextMenuEvent
    for col in (COL_ROOM, COL_STAT):
        pos = QPoint(header.sectionViewportPosition(col) + 2, 2)
        header.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, pos, header.mapToGlobal(pos)))
    assert requested == [COL_ROOM]


def test_allowed_keys_restricts_rows(proxy):
    src = proxy.sourceModel()
    keys = {src.cat_at(0).db_key, src.cat_at(3).db_key}
    proxy.set_allowed_keys(keys)
    assert _visible_names(proxy) == ["Ann", "Dee"]
    # Column filters still apply on top, and only offer values from allowed rows.
    assert proxy.available_column_values(COL_ROOM) == ["Attic", "Floor2"]
    proxy.set_allowed_keys(set())
    assert _visible_names(proxy) == []
    proxy.set_allowed_keys(None)
    assert len(_visible_names(proxy)) == 4
