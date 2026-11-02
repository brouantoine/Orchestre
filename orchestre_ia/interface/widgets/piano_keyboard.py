"""Clavier de piano animé : note chantée (or) et notes jouées par l'orchestre (vert)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from orchestre_ia.interface import theme

LOW, HIGH = 36, 84  # Do2 à Do6
BLACK_PCS = {1, 3, 6, 8, 10}


def _rounded_bottom(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(rect.topLeft())
    path.lineTo(rect.right(), rect.top())
    path.lineTo(rect.right(), rect.bottom() - radius)
    path.quadTo(rect.right(), rect.bottom(), rect.right() - radius, rect.bottom())
    path.lineTo(rect.left() + radius, rect.bottom())
    path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - radius)
    path.closeSubpath()
    return path


class PianoKeyboardWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sung: int | None = None
        self.played: set[int] = set()
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_sung(self, midi: int | None) -> None:
        if midi != self.sung:
            self.sung = midi
            self.update()

    def set_played(self, notes) -> None:
        notes = set(notes)
        if notes != self.played:
            self.played = notes
            self.update()

    def _highlight(self, midi: int) -> QColor | None:
        if midi == self.sung:
            return QColor(theme.ACCENT)
        if midi in self.played:
            return QColor(theme.OK)
        return None

    def paintEvent(self, event) -> None:  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        whites = [m for m in range(LOW, HIGH + 1) if m % 12 not in BLACK_PCS]
        w = (self.width() - 2) / len(whites)
        h = self.height() - 2
        x_of: dict[int, float] = {}

        # touches blanches
        for i, m in enumerate(whites):
            x = 1 + i * w
            x_of[m] = x
            rect = QRectF(x + 0.75, 1, w - 1.5, h)
            hl = self._highlight(m)
            grad = QLinearGradient(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
            if hl is not None:
                grad.setColorAt(0, hl.lighter(125))
                grad.setColorAt(1, hl)
            else:
                grad.setColorAt(0, QColor("#f6f3ec"))
                grad.setColorAt(1, QColor("#d8d3c8"))
            p.setPen(QPen(QColor("#0b0c10"), 1))
            p.setBrush(grad)
            p.drawPath(_rounded_bottom(rect, 5))
            if m % 12 == 0:
                p.setPen(QColor("#1a1c22" if hl is not None else "#8a857a"))
                p.setFont(QFont("Segoe UI", 7, QFont.Weight.DemiBold))
                p.drawText(QRectF(x, h - 18, w, 14), Qt.AlignmentFlag.AlignCenter, f"Do{m // 12 - 1}")

        # touches noires
        for m in range(LOW, HIGH + 1):
            if m % 12 not in BLACK_PCS:
                continue
            x = x_of[m - 1] + w * 0.66
            rect = QRectF(x, 1, w * 0.68, h * 0.6)
            hl = self._highlight(m)
            grad = QLinearGradient(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
            if hl is not None:
                grad.setColorAt(0, hl)
                grad.setColorAt(1, hl.darker(140))
            else:
                grad.setColorAt(0, QColor("#2c303b"))
                grad.setColorAt(1, QColor("#0c0d11"))
            p.setPen(QPen(QColor("#050608"), 1))
            p.setBrush(grad)
            p.drawPath(_rounded_bottom(rect, 3))

        # ombre portée sous le bord supérieur (profondeur)
        shade = QLinearGradient(QPointF(0, 0), QPointF(0, 10))
        shade.setColorAt(0, QColor(0, 0, 0, 120))
        shade.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, 0, self.width(), 10), shade)
        p.end()
