"""VU-mètre horizontal segmenté (vert / jaune / rouge) avec maintien de crête."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from orchestre_ia.interface import theme

MIN_DB = -60.0
MAX_DB = 0.0
SEGMENTS = 48


class LevelMeterWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rms_db = MIN_DB
        self.peak_db = MIN_DB
        self.held_db = MIN_DB
        self.clipping = False
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_levels(self, rms_db: float, peak_db: float, held_db: float, clipping: bool) -> None:
        self.rms_db, self.peak_db, self.held_db, self.clipping = rms_db, peak_db, held_db, clipping
        self.update()

    def reset(self) -> None:
        self.set_levels(MIN_DB, MIN_DB, MIN_DB, False)

    @staticmethod
    def _ratio(db: float) -> float:
        return max(0.0, min(1.0, (db - MIN_DB) / (MAX_DB - MIN_DB)))

    @staticmethod
    def _segment_color(ratio: float) -> QColor:
        db = MIN_DB + ratio * (MAX_DB - MIN_DB)
        if db >= -6:
            return QColor(theme.DANGER)
        if db >= -18:
            return QColor(theme.WARN)
        return QColor(theme.OK)

    def paintEvent(self, event) -> None:  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.PANEL_ALT))
        p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)
        gap = 3.0
        seg_w = (w - 12 - gap * (SEGMENTS - 1)) / SEGMENTS
        lit_rms = self._ratio(self.rms_db)
        lit_peak = self._ratio(self.peak_db)
        for i in range(SEGMENTS):
            ratio = (i + 0.5) / SEGMENTS
            color = self._segment_color(ratio)
            if ratio <= lit_rms:
                pass
            elif ratio <= lit_peak:
                color.setAlpha(110)
            else:
                color.setAlpha(24)
            x = 6 + i * (seg_w + gap)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, 7, seg_w, h - 14), 2, 2)
        held_x = 6 + self._ratio(self.held_db) * (w - 12)
        p.setBrush(QColor(theme.TEXT))
        p.drawRoundedRect(QRectF(held_x - 1, 4, 2, h - 8), 1, 1)
        if self.clipping:
            p.setBrush(QColor(theme.DANGER))
            p.drawRoundedRect(QRectF(w - 10, 4, 6, h - 8), 3, 3)
        p.end()
