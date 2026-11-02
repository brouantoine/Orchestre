"""Courbe de mélodie défilante (10 dernières secondes) sur une grille de notes."""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from orchestre_ia.analysis.theory import note_name
from orchestre_ia.interface import theme

WINDOW_S = 10.0


class PitchRollWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.points: deque[tuple[float, float]] = deque(maxlen=2000)  # (monotonic, midi ou 0)
        self.setMinimumHeight(260)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(50)

    def add(self, midi: float, t: float | None = None) -> None:
        self.points.append((t if t is not None else time.monotonic(), midi))

    def clear(self) -> None:
        self.points.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.PANEL_ALT))
        now = time.monotonic()
        voiced = [m for t, m in self.points if m > 0 and now - t < WINDOW_S]
        center = sorted(voiced)[len(voiced) // 2] if voiced else 60
        lo, hi = int(center) - 12, int(center) + 12
        w, h = self.width(), self.height()
        margin = 46

        def y_of(m: float) -> float:
            return h - (m - lo) / (hi - lo) * h

        p.setFont(QFont("Segoe UI", 7))
        for m in range(lo, hi + 1):
            y = y_of(m)
            natural = m % 12 in (0, 2, 4, 5, 7, 9, 11)
            p.setPen(QPen(QColor(theme.BORDER if natural else "#23262d"), 1))
            p.drawLine(margin, int(y), w, int(y))
            if m % 12 in (0, 4, 7):
                p.setPen(QColor(theme.TEXT_DIM))
                p.drawText(QRectF(0, y - 7, margin - 4, 14), Qt.AlignmentFlag.AlignRight, note_name(m))

        pen = QPen(QColor(theme.ACCENT), 3)
        p.setPen(pen)
        prev: QPointF | None = None
        prev_m = 0.0
        for t, m in self.points:
            if prev is not None and abs(m - prev_m) > 7:
                prev = None  # saut de plus d'une quinte : pas de trait vertical
            prev_m = m
            age = now - t
            if age > WINDOW_S or m <= 0:
                prev = None
                continue
            pt = QPointF(margin + (1 - age / WINDOW_S) * (w - margin), y_of(m))
            if prev is not None:
                p.drawLine(prev, pt)
            prev = pt
        p.end()
