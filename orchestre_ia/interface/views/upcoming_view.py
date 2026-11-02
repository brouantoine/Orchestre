"""Vue d'un espace dont le moteur n'est pas encore développé.

Elle présente ce qui viendra, sans aucun bouton ni donnée simulée.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from orchestre_ia.interface import theme
from orchestre_ia.interface.views.common import icon_label, make_card, page, scrollable, view_title


class UpcomingView(QWidget):
    def __init__(
        self,
        title: str,
        purpose: str,
        phase: str,
        icon_name: str = "info",
        features: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        content, root = page()
        root.addWidget(view_title(title, purpose))

        card, layout = make_card("Bientôt disponible", icon_name)
        hero = QHBoxLayout()
        hero.setSpacing(18)
        big = icon_label(icon_name, theme.ACCENT, 56)
        hero.addWidget(big, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        head = QLabel(f"Prévu pour la {phase}")
        head.setObjectName("TileValue")
        texts.addWidget(head)
        note = QLabel("Ce module n'est pas encore opérationnel. Rien n'est simulé ici.")
        note.setObjectName("Dim")
        texts.addWidget(note)
        for feat in features or []:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(icon_label("apprentissage", theme.ACCENT, 13))
            lab = QLabel(feat)
            lab.setWordWrap(True)
            row.addWidget(lab, 1)
            texts.addSpacing(4)
            texts.addLayout(row)
        hero.addLayout(texts, 1)
        layout.addLayout(hero)
        root.addWidget(card)
        root.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))
