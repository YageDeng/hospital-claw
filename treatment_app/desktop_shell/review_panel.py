"""Expandable review panel that renders treatment-case fields in a profile-driven layout.

Opens as a slide-out from the hover pill and displays fields grouped by section,
using the control types defined in the profile's review layout. The operator
reviews, edits, approves, or blocks each field before committing to auto-fill.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from treatment_app.schemas import (
    CaseField,
    CaseSection,
    FieldReviewState,
    ReviewControlType,
    ReviewFieldLayout,
    ReviewSectionLayout,
    TargetAppProfile,
    TreatmentPlanCase,
)

logger = logging.getLogger(__name__)

PANEL_MIN_WIDTH = 380
PANEL_MAX_WIDTH = 520


class FieldWidget(QFrame):
    """Single field row: label + editor + approve/block toggle."""

    value_changed = Signal(str, object)  # field_id, new_value
    state_changed = Signal(str, str)     # field_id, new_state

    def __init__(
        self,
        case_field: CaseField,
        control_type: ReviewControlType,
        label_override: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._field = case_field
        self._control_type = control_type

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("FieldWidget { background: #FAFAFA; border-radius: 4px; padding: 4px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        label_text = label_override or case_field.label
        conf_text = ""
        if case_field.confidence is not None:
            conf_text = f"  ({case_field.confidence:.0%})"
        header = QLabel(f"<b>{label_text}</b>{conf_text}")
        header.setFont(QFont("Segoe UI", 9))
        layout.addWidget(header)

        self._editor = self._build_editor(control_type, case_field)
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._approve_btn = QPushButton("Approve")
        self._approve_btn.setFixedHeight(22)
        self._approve_btn.setStyleSheet("QPushButton { background: #198754; color: white; border-radius: 3px; font-size: 11px; }")
        self._approve_btn.clicked.connect(lambda: self._set_state(FieldReviewState.APPROVED))

        self._block_btn = QPushButton("Block")
        self._block_btn.setFixedHeight(22)
        self._block_btn.setStyleSheet("QPushButton { background: #DC3545; color: white; border-radius: 3px; font-size: 11px; }")
        self._block_btn.clicked.connect(lambda: self._set_state(FieldReviewState.BLOCKED))

        btn_row.addWidget(self._approve_btn)
        btn_row.addWidget(self._block_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._apply_review_state(case_field.review_state)

    def _build_editor(self, control_type: ReviewControlType, field: CaseField) -> QWidget:
        if control_type == ReviewControlType.MULTI_LINE:
            editor = QPlainTextEdit()
            editor.setPlainText(str(field.value or ""))
            editor.setMaximumHeight(80)
            editor.textChanged.connect(
                lambda: self.value_changed.emit(field.field_id, editor.toPlainText())
            )
            return editor

        if control_type == ReviewControlType.CHECKBOX:
            editor = QCheckBox()
            editor.setChecked(bool(field.value))
            editor.stateChanged.connect(
                lambda state: self.value_changed.emit(field.field_id, state == Qt.CheckState.Checked.value)
            )
            return editor

        if control_type == ReviewControlType.READ_ONLY:
            editor = QLabel(str(field.value or ""))
            editor.setStyleSheet("color: #555;")
            return editor

        editor = QLineEdit(str(field.value or ""))
        editor.textChanged.connect(
            lambda text: self.value_changed.emit(field.field_id, text)
        )
        return editor

    def _set_state(self, state: FieldReviewState) -> None:
        self._field.review_state = state
        self._apply_review_state(state)
        self.state_changed.emit(self._field.field_id, state.value)

    def _apply_review_state(self, state: FieldReviewState) -> None:
        border_colors = {
            FieldReviewState.PENDING: "#DEE2E6",
            FieldReviewState.APPROVED: "#198754",
            FieldReviewState.BLOCKED: "#DC3545",
            FieldReviewState.SKIPPED: "#6C757D",
            FieldReviewState.FILLED: "#0D6EFD",
        }
        color = border_colors.get(state, "#DEE2E6")
        self.setStyleSheet(
            f"FieldWidget {{ background: #FAFAFA; border: 2px solid {color}; border-radius: 4px; padding: 4px; }}"
        )
        self._approve_btn.setEnabled(state != FieldReviewState.APPROVED)
        self._block_btn.setEnabled(state != FieldReviewState.BLOCKED)

    def refresh(self, field: CaseField) -> None:
        """Reload the widget from an updated CaseField."""
        self._field = field
        if isinstance(self._editor, QLineEdit):
            self._editor.setText(str(field.value or ""))
        elif isinstance(self._editor, QPlainTextEdit):
            self._editor.setPlainText(str(field.value or ""))
        elif isinstance(self._editor, QCheckBox):
            self._editor.setChecked(bool(field.value))
        elif isinstance(self._editor, QLabel):
            self._editor.setText(str(field.value or ""))
        self._apply_review_state(field.review_state)


class ReviewPanel(QWidget):
    """Scrollable review surface that displays grouped fields.

    Signals
    -------
    approve_all_clicked : operator pressed "Approve All".
    fill_clicked : operator pressed "Fill" to start auto-fill.
    """

    approve_all_clicked = Signal()
    fill_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setMinimumWidth(PANEL_MIN_WIDTH)
        self.setMaximumWidth(PANEL_MAX_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("ReviewPanel { background: white; }")

        self._field_widgets: dict[str, FieldWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        title_bar = QFrame()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet("background: #212529; border-top-left-radius: 6px; border-top-right-radius: 6px;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 0, 10, 0)
        self._title_label = QLabel("Review")
        self._title_label.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()
        close_btn = QPushButton("x")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("QPushButton { color: white; background: transparent; font-weight: bold; } QPushButton:hover { color: #DC3545; }")
        close_btn.clicked.connect(self.hide)
        title_layout.addWidget(close_btn)
        outer.addWidget(title_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(8, 8, 8, 8)
        self._scroll_layout.setSpacing(6)
        scroll.setWidget(self._scroll_content)
        outer.addWidget(scroll, stretch=1)

        footer = QFrame()
        footer.setFixedHeight(40)
        footer.setStyleSheet("background: #F8F9FA;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 4, 8, 4)
        approve_all_btn = QPushButton("Approve All")
        approve_all_btn.setStyleSheet("QPushButton { background: #198754; color: white; border-radius: 4px; padding: 4px 12px; }")
        approve_all_btn.clicked.connect(self.approve_all_clicked.emit)
        fill_btn = QPushButton("Fill")
        fill_btn.setStyleSheet("QPushButton { background: #0D6EFD; color: white; border-radius: 4px; padding: 4px 12px; }")
        fill_btn.clicked.connect(self.fill_clicked.emit)
        footer_layout.addWidget(approve_all_btn)
        footer_layout.addStretch()
        footer_layout.addWidget(fill_btn)
        outer.addWidget(footer)

        self._warnings_label = QLabel()
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setStyleSheet("color: #856404; background: #FFF3CD; padding: 6px; border-radius: 4px;")
        self._warnings_label.hide()

    def load_case(
        self,
        case: TreatmentPlanCase,
        profile: TargetAppProfile,
    ) -> None:
        """Populate the panel from a case and its profile layout."""
        self._clear()
        self._title_label.setText(f"Review — {profile.name}")

        section_map: dict[str, ReviewSectionLayout] = {
            s.section_id: s for s in profile.review_sections
        }
        field_layout_map: dict[str, ReviewFieldLayout] = {
            fl.field_id: fl for fl in profile.review_fields
        }
        field_def_map = profile.field_definition_map()

        sorted_sections = sorted(section_map.values(), key=lambda s: s.order)
        field_map = case.field_map()

        for sec_layout in sorted_sections:
            group = QGroupBox(sec_layout.title)
            group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #DEE2E6; border-radius: 6px; margin-top: 8px; padding-top: 14px; }")
            grid = QGridLayout(group)
            grid.setSpacing(6)

            section_fields = [
                fl
                for fl in profile.review_fields
                if fl.section_id == sec_layout.section_id
            ]
            section_fields.sort(key=lambda fl: (fl.row, fl.column))

            for fl in section_fields:
                cf = field_map.get(fl.field_id)
                if cf is None:
                    continue
                fdef = field_def_map.get(fl.field_id)
                control = fdef.review_control if fdef else ReviewControlType.SINGLE_LINE
                fw = FieldWidget(cf, control, label_override=fl.label_override)
                fw.value_changed.connect(self._on_value_changed)
                fw.state_changed.connect(self._on_state_changed)
                grid.addWidget(fw, fl.row, fl.column, fl.row_span, fl.column_span)
                self._field_widgets[fl.field_id] = fw

            if not sec_layout.collapsed:
                self._scroll_layout.addWidget(group)
            else:
                group.hide()
                self._scroll_layout.addWidget(group)

        if case.warnings:
            self._warnings_label.setText("\n".join(case.warnings))
            self._warnings_label.show()
            self._scroll_layout.addWidget(self._warnings_label)

        self._scroll_layout.addStretch()

    def _clear(self) -> None:
        self._field_widgets.clear()
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _on_value_changed(self, field_id: str, value: object) -> None:
        logger.debug("Field '%s' value changed: %s", field_id, value)

    def _on_state_changed(self, field_id: str, state: str) -> None:
        logger.debug("Field '%s' state changed: %s", field_id, state)

    def get_field_widget(self, field_id: str) -> Optional[FieldWidget]:
        return self._field_widgets.get(field_id)
