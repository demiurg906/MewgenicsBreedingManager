"""Right-click "filter by value" support for table column headers.

ColumnFilterHeader paints a highlight on columns with an active value filter
and emits ``filterRequested`` when a filterable section is right-clicked.
ColumnValueFilterPopup is the checkbox list shown in response.
"""
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QScrollArea, QWidget, QApplication,
)

from mewgenics.utils.localization import _tr


_FILTERED_TINT = QColor(224, 160, 64, 60)
_FILTERED_BAR = QColor("#e0a040")


class ColumnFilterHeader(QHeaderView):
    """Horizontal header that highlights value-filtered columns."""

    filterRequested = Signal(int, QPoint)  # logical column, global position

    def __init__(self, filterable_columns, parent=None):
        super().__init__(Qt.Horizontal, parent)
        # Match QTableView's built-in horizontal header defaults.
        self.setSectionsClickable(True)
        self.setHighlightSections(True)
        self._filterable = set(filterable_columns)
        self._active: set[int] = set()

    def set_active_columns(self, columns):
        active = set(columns)
        if active != self._active:
            self._active = active
            self.viewport().update()

    def contextMenuEvent(self, event):
        col = self.logicalIndexAt(event.pos())
        if col in self._filterable:
            event.accept()
            self.filterRequested.emit(col, event.globalPos())
            return
        super().contextMenuEvent(event)

    def paintSection(self, painter, rect, logical_idx):
        super().paintSection(painter, rect, logical_idx)
        if logical_idx not in self._active:
            return
        painter.save()
        painter.fillRect(rect, _FILTERED_TINT)
        painter.fillRect(rect.left(), rect.bottom() - 1, rect.width(), 2, _FILTERED_BAR)
        painter.restore()


class ColumnValueFilterPopup(QFrame):
    """Popup with one checkbox per column value plus a Reset button.

    Emits ``valuesChanged`` with the checked set on every toggle; an empty
    set means "no filter".
    """

    valuesChanged = Signal(set)

    def __init__(self, title: str, values: list[str], selected: set[str], parent=None):
        super().__init__(parent, Qt.Popup)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(
            "ColumnValueFilterPopup { background:#12122a; border:1px solid #3a3a6a; border-radius:4px; }"
            "QLabel { color:#aaa; font-size:11px; font-weight:bold; }"
            "QCheckBox { color:#ddd; font-size:12px; padding:2px 0; }"
            "QPushButton { background:#1a1a32; color:#aaa; border:1px solid #2a2a4a;"
            " border-radius:4px; padding:3px 10px; font-size:11px; font-weight:bold; }"
            "QPushButton:hover { background:#252545; color:#ddd; }"
            "QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; border:none; }"
        )

        vb = QVBoxLayout(self)
        vb.setContentsMargins(8, 8, 8, 8)
        vb.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel(title))
        top.addStretch()
        reset_btn = QPushButton(_tr("column_filter.reset", default="Reset"))
        reset_btn.clicked.connect(self._reset)
        top.addWidget(reset_btn)
        vb.addLayout(top)

        body = QWidget()
        body_vb = QVBoxLayout(body)
        body_vb.setContentsMargins(0, 0, 0, 0)
        body_vb.setSpacing(0)
        self._checks: dict[str, QCheckBox] = {}
        for value in values:
            check = QCheckBox(value)
            check.setChecked(value in selected)
            check.toggled.connect(self._emit_values)
            body_vb.addWidget(check)
            self._checks[value] = check
        if not values:
            body_vb.addWidget(QLabel(_tr("column_filter.no_values", default="No values")))
        body_vb.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        scroll.setMinimumWidth(min(max(body.sizeHint().width() + 24, 160), 360))
        scroll.setFixedHeight(min(body.sizeHint().height() + 4, 320))
        vb.addWidget(scroll)

    def selected_values(self) -> set[str]:
        return {value for value, check in self._checks.items() if check.isChecked()}

    def _emit_values(self, *_args):
        self.valuesChanged.emit(self.selected_values())

    def _reset(self):
        for check in self._checks.values():
            check.blockSignals(True)
            check.setChecked(False)
            check.blockSignals(False)
        self._emit_values()

    def popup_at(self, global_pos: QPoint):
        """Show at *global_pos*, kept inside the screen's available area."""
        self.adjustSize()
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        pos = QPoint(global_pos)
        if screen is not None:
            avail = screen.availableGeometry()
            pos.setX(max(avail.left(), min(pos.x(), avail.right() - self.width())))
            pos.setY(max(avail.top(), min(pos.y(), avail.bottom() - self.height())))
        self.move(pos)
        self.show()
