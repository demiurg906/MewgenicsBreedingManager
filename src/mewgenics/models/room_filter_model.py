"""RoomFilterModel: proxy model for filtering and multi-column sorting."""
from PySide6.QtCore import Qt, QSortFilterProxyModel

from save_parser import Cat
from mewgenics.constants import COL_ABIL, COL_MUTS, COL_TAGS, COL_ROOM, COL_STAT
from mewgenics.utils.tags import _cat_tags, _cat_tag_labels
from mewgenics.utils.cat_analysis import _is_exceptional_breeder, _is_donation_candidate, _relations_summary
from mewgenics.utils.abilities import _mutation_display_name

# Columns that support the right-click "filter by value" header popup.
VALUE_FILTER_COLUMNS = (COL_TAGS, COL_ROOM, COL_STAT)
EMPTY_FILTER_VALUE = "—"


class RoomFilterModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self._room = None
        self._name_filter = ""
        self._abilities_filter = ""
        self._mutations_filter = ""
        self._pinned_only = False
        self._tag_filter: set[str] = set()  # empty = show all
        self._column_value_filters: dict[int, set[str]] = {}  # column -> allowed display values
        self._sort_columns: list[tuple[int, Qt.SortOrder]] = []  # list of (column, order) for multi-column sort
        self._accessible_cat_keys: set[int] = set()
        self._allowed_keys: set[int] | None = None  # None = no restriction
        self.setSortRole(Qt.UserRole)

    def set_room(self, key):
        self._room = key
        self.invalidate()

    def set_accessible_cats(self, keys: set[int]):
        self._accessible_cat_keys = set(keys or [])
        self.invalidate()

    def set_allowed_keys(self, keys: set[int] | None):
        """Restrict rows to cats whose db_key is in *keys* (None = no restriction)."""
        self._allowed_keys = None if keys is None else set(keys)
        self.invalidate()

    @property
    def allowed_keys(self) -> set[int] | None:
        return None if self._allowed_keys is None else set(self._allowed_keys)

    def set_name_filter(self, text: str):
        self._name_filter = text.strip().lower()
        self.invalidate()

    def set_abilities_filter(self, text: str):
        self._abilities_filter = text.strip().lower()
        self.invalidate()

    def set_mutations_filter(self, text: str):
        self._mutations_filter = text.strip().lower()
        self.invalidate()

    def set_pinned_only(self, enabled: bool):
        self._pinned_only = enabled
        self.invalidate()

    @property
    def tag_filter(self) -> set[str]:
        return self._tag_filter

    def set_tag_filter(self, tag_ids: set[str]):
        self._tag_filter = tag_ids
        self.invalidate()

    @property
    def column_value_filters(self) -> dict[int, set[str]]:
        return {col: set(values) for col, values in self._column_value_filters.items()}

    def set_column_value_filter(self, column: int, values: set[str]):
        """Show only rows whose value in *column* is one of *values* (empty = no filter)."""
        values = set(values or ())
        if values:
            self._column_value_filters[column] = values
        else:
            self._column_value_filters.pop(column, None)
        self.invalidate()

    def clear_column_value_filters(self):
        if self._column_value_filters:
            self._column_value_filters.clear()
            self.invalidate()

    def column_filter_values_for_row(self, source_row: int, column: int) -> list[str]:
        """Values a source row contributes to a value-filtered column.

        Tags is multi-valued (game tag + custom tags); other columns use
        their display text.
        """
        source_model = self.sourceModel()
        if source_model is None:
            return []
        if column == COL_TAGS:
            cat = source_model.cat_at(source_row)
            if cat is None:
                return []
            return _cat_tag_labels(cat) or [EMPTY_FILTER_VALUE]
        value = source_model.data(source_model.index(source_row, column), Qt.DisplayRole)
        text = str(value or "").strip()
        return [text or EMPTY_FILTER_VALUE]

    def available_column_values(self, column: int) -> list[str]:
        """Values present in rows that pass every filter except this column's own.

        Currently-selected values are always included so they can be unchecked.
        """
        source_model = self.sourceModel()
        values: set[str] = set(self._column_value_filters.get(column, ()))
        if source_model is not None:
            for row in range(source_model.rowCount()):
                if self._accepts_row(row, ignore_column=column):
                    values.update(self.column_filter_values_for_row(row, column))
        return sorted(values, key=lambda v: (v == EMPTY_FILTER_VALUE, v.lower()))

    def set_sort_columns(self, columns: list[tuple[int, Qt.SortOrder]]):
        """Set multi-column sort order. columns is a list of (column_index, order) tuples."""
        self._sort_columns = columns
        self.invalidate()

    def sort(self, column: int, order: Qt.SortOrder):
        """Override sort to clear multi-column sort when user clicks a column header."""
        self._sort_columns = []
        super().sort(column, order)

    def _matches_text_filter(self, cat: Cat) -> bool:
        if not self._name_filter:
            return True

        terms = [cat.name]
        terms.extend(cat.abilities)
        terms.extend(cat.passive_abilities)
        terms.extend(_mutation_display_name(p) for p in cat.passive_abilities)
        terms.extend(cat.disorders)
        terms.extend(_mutation_display_name(d) for d in cat.disorders)
        terms.extend(cat.mutations)
        terms.extend(_mutation_display_name(m) for m in cat.mutations)
        terms.extend(cat.defects)
        terms.extend(text for text, _ in getattr(cat, "mutation_chip_items", []))
        terms.extend(text for text, _ in getattr(cat, "defect_chip_items", []))
        terms.extend(other.name for other in cat.lovers)
        terms.extend(other.name for other in cat.haters)
        terms.append(_relations_summary(cat))

        haystack = " ".join(
            str(term).lower()
            for term in terms
            if term
        )
        return self._name_filter in haystack

    def _column_text(self, source_row: int, column: int) -> str:
        source_model = self.sourceModel()
        if source_model is None:
            return ""
        value = source_model.data(source_model.index(source_row, column), Qt.DisplayRole)
        return str(value or "").lower()

    def filterAcceptsRow(self, source_row, source_parent):
        return self._accepts_row(source_row)

    def _accepts_row(self, source_row: int, ignore_column: int | None = None) -> bool:
        cat = self.sourceModel().cat_at(source_row)
        if cat is None:
            return False
        if self._allowed_keys is not None and cat.db_key not in self._allowed_keys:
            return False
        if not self._matches_text_filter(cat):
            return False
        if self._pinned_only and not cat.is_pinned:
            return False
        if self._tag_filter:
            cat_tags = set(_cat_tags(cat))
            if not (cat_tags & self._tag_filter):
                return False
        for column, allowed in self._column_value_filters.items():
            if column == ignore_column:
                continue
            if not allowed.intersection(self.column_filter_values_for_row(source_row, column)):
                return False
        if self._room == "__all__":
            return True
        if self._room is None:
            return cat.status != "Gone"
        if self._room == "__exceptional__":
            return cat.status != "Gone" and _is_exceptional_breeder(cat)
        if self._room == "__donation__":
            return cat.status != "Gone" and _is_donation_candidate(cat)
        if self._room == "__gone__":
            return cat.status == "Gone"
        if self._room == "__fight_club__":
            accessible_keys = getattr(self, "_accessible_cat_keys", set())
            if cat.status == "Gone" or cat.db_key not in accessible_keys:
                return False
            if cat.has_adventured:
                return False
            if self._abilities_filter and self._abilities_filter not in self._column_text(source_row, COL_ABIL):
                return False
            if self._mutations_filter and self._mutations_filter not in self._column_text(source_row, COL_MUTS):
                return False
            return True
        if self._room == "__adventure__":
            return cat.status == "Adventure"
        return cat.room == self._room

    def lessThan(self, left_index, right_index):
        """Compare two rows for sorting, supporting multi-column sort."""
        if not self._sort_columns:
            # Fall back to default single-column sort
            return super().lessThan(left_index, right_index)

        # Multi-column sort: compare by each column in order
        for col, order in self._sort_columns:
            left_data = self.sourceModel().data(self.sourceModel().index(left_index.row(), col), Qt.UserRole)
            right_data = self.sourceModel().data(self.sourceModel().index(right_index.row(), col), Qt.UserRole)

            # Handle None/empty values
            left_val = left_data if left_data is not None else ""
            right_val = right_data if right_data is not None else ""

            # Try numeric comparison for numbers, string comparison for strings
            if isinstance(left_val, (int, float)) and isinstance(right_val, (int, float)):
                if left_val != right_val:
                    result = left_val < right_val
                    if order == Qt.DescendingOrder:
                        result = not result
                    return result
            else:
                # String comparison (case-insensitive)
                left_str = str(left_val).lower() if left_val else ""
                right_str = str(right_val).lower() if right_val else ""
                if left_str != right_str:
                    result = left_str < right_str
                    if order == Qt.DescendingOrder:
                        result = not result
                    return result

        # All columns equal, maintain original order
        return False
