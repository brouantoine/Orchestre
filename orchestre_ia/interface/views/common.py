"""Éléments de mise en page partagés par les vues."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from orchestre_ia.interface import theme
from orchestre_ia.interface.icons import pixmap


def icon_label(name: str, color: str = theme.TEXT_DIM, size: int = 16) -> QLabel:
    label = QLabel()
    label.setPixmap(pixmap(name, color, size * 2))
    label.setFixedSize(size, size)
    label.setScaledContents(True)
    return label


def make_card(title: str, icon: str | None = None, parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 16, 20, 18)
    layout.setSpacing(12)
    header = QHBoxLayout()
    header.setSpacing(8)
    if icon:
        header.addWidget(icon_label(icon, theme.ACCENT, 15))
    label = QLabel(title.upper())
    label.setObjectName("CardTitle")
    header.addWidget(label)
    header.addStretch(1)
    layout.addLayout(header)
    frame.header = header  # type: ignore[attr-defined]  # pour ajouter des éléments à droite du titre
    return frame, layout


class Tile(QFrame):
    """Case d'information : icône + titre, grande valeur, précision."""

    def __init__(self, title: str, icon: str | None = None, accent: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setProperty("accent", accent)
        self.setMinimumHeight(118)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(8)
        if icon:
            head.addWidget(icon_label(icon, theme.ACCENT if accent else theme.TEXT_DIM, 15))
        caption = QLabel(title.upper())
        caption.setObjectName("CardTitle")
        head.addWidget(caption)
        head.addStretch(1)
        self.head = head
        layout.addLayout(head)
        self.value = QLabel("—")
        self.value.setObjectName("ChordValue" if accent else "TileValue")
        self.detail = QLabel("")
        self.detail.setObjectName("Dim")
        self.detail.setWordWrap(True)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        layout.addStretch(1)
        self.body = layout

    def set(self, value: str, detail: str = "", color: str | None = None) -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        self.value.setStyleSheet(f"color: {color};" if color else "")


class Pill(QLabel):
    """Pastille d'état colorée : neutral | ok | warn | error."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.set_state("neutral", text)

    def set_state(self, state: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(f"●  {text}")
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)


class BeatIndicator(QWidget):
    """Quatre points : le temps courant de la mesure s'allume (le premier temps en or)."""

    def __init__(self, beats: int = 4, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.beats = beats
        self.current = -1
        self.setFixedSize(beats * 18, 14)

    def set_beat(self, beat: int) -> None:
        if beat != self.current:
            self.current = beat
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(self.beats):
            if i == self.current:
                color = QColor(theme.ACCENT if i == 0 else theme.OK)
            else:
                color = QColor(theme.PANEL_HI)
            p.setBrush(color)
            p.drawEllipse(QRectF(i * 18 + 2, 2, 10, 10))
        p.end()


def view_title(text: str, subtitle: str = "", right: QWidget | None = None) -> QWidget:
    box = QWidget()
    outer = QHBoxLayout(box)
    outer.setContentsMargins(0, 0, 0, 6)
    texts = QVBoxLayout()
    texts.setSpacing(2)
    title = QLabel(text)
    title.setObjectName("ViewTitle")
    texts.addWidget(title)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("ViewSubtitle")
        sub.setWordWrap(True)
        texts.addWidget(sub)
    outer.addLayout(texts, 1)
    if right is not None:
        outer.addWidget(right, 0, Qt.AlignmentFlag.AlignTop)
    return box


def scrollable(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(content)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    return area


def page() -> tuple[QWidget, QVBoxLayout]:
    """Contenu d'un espace : marges et espacements communs à tous les écrans."""
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(36, 28, 36, 28)
    layout.setSpacing(16)
    return content, layout
