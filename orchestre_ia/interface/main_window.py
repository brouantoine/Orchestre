"""Fenêtre principale : barre latérale (logo, navigation, état) + pile de vues."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from orchestre_ia import APP_NAME, __version__
from orchestre_ia.app.session import MusicSession
from orchestre_ia.audio.devices import AudioDevice, list_input_devices, list_output_devices
from orchestre_ia.audio.events import CaptureState, CaptureStateChanged
from orchestre_ia.conductor.conductor import ConductorState, ConductorUpdate
from orchestre_ia.core.config import AppConfig
from orchestre_ia.core.events import EventBus
from orchestre_ia.interface import theme
from orchestre_ia.interface.bridge import QtEventBridge
from orchestre_ia.interface.icons import icon, logo_icon, logo_pixmap
from orchestre_ia.interface.views.analysis_view import AnalysisView
from orchestre_ia.interface.views.orchestra_view import OrchestraView
from orchestre_ia.interface.views.settings_view import SettingsView
from orchestre_ia.interface.views.studio_view import StudioView
from orchestre_ia.interface.views.upcoming_view import UpcomingView

VIEW_KEYS = ("studio", "analyse", "orchestre", "bibliotheque", "apprentissage", "parametres")
VIEW_LABELS = ("Studio", "Analyse", "Orchestre", "Bibliothèque", "Apprentissage", "Paramètres")
SIDEBAR_WIDTH = 232


class MainWindow(QMainWindow):
    def __init__(
        self,
        bus: EventBus,
        session: MusicSession,
        config: AppConfig,
        save_config: Callable[[], None],
        list_devices: Callable[[], list[AudioDevice]] = list_input_devices,
        list_outputs: Callable[[], list[AudioDevice]] = list_output_devices,
    ) -> None:
        super().__init__()
        self.session = session
        self._config = config
        self._save_config = save_config
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(logo_icon())
        self.resize(1320, 900)
        self.setMinimumSize(1000, 660)

        self.bridge = QtEventBridge(bus, self)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.studio = StudioView(session, self.bridge, config, save_config, list_devices, list_outputs)
        self.analysis = AnalysisView(self.bridge)
        self.orchestra = OrchestraView(session, config, save_config)
        self.settings = SettingsView(config, save_config, list_outputs)
        self.views: dict[str, QWidget] = {
            "studio": self.studio,
            "analyse": self.analysis,
            "orchestre": self.orchestra,
            "bibliotheque": UpcomingView(
                "Bibliothèque",
                "Les chansons que vous chantez, reconnues et mémorisées.",
                "phase 6 (reconnaissance musicale)",
                "bibliotheque",
                ["Reconnaître une chanson même chantée dans une autre tonalité",
                 "Retrouver les accords et le tempo de vos chansons",
                 "Trois réponses honnêtes : reconnue, plusieurs candidates ou inconnue"],
            ),
            "apprentissage": UpcomingView(
                "Apprentissage",
                "Le musicien apprend vos goûts, chanson après chanson.",
                "phase 7 (apprentissage)",
                "apprentissage",
                ["Vos tonalités, tempos et styles préférés",
                 "Vos corrections d'accords, retenues pour la prochaine fois",
                 "Partage collectif uniquement avec votre accord ; vos voix restent privées"],
            ),
            "parametres": self.settings,
        }
        for key in VIEW_KEYS:
            self.stack.addWidget(self.views[key])
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.sidebar.currentRowChanged.connect(self._on_view_changed)
        start = VIEW_KEYS.index(config.ui.last_view) if config.ui.last_view in VIEW_KEYS else 0
        self.sidebar.setCurrentRow(start)

        self.statusBar().showMessage("Prêt. Cliquez sur « Écouter et accompagner » puis chantez.")
        self.bridge.capture_state.connect(self._on_capture_state)
        self.bridge.conductor.connect(self._on_conductor)

    # ------------------------------------------------------------ construction
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setFixedWidth(SIDEBAR_WIDTH)
        col = QVBoxLayout(side)
        col.setContentsMargins(0, 22, 0, 18)
        col.setSpacing(0)

        brand = QHBoxLayout()
        brand.setContentsMargins(20, 0, 16, 0)
        brand.setSpacing(11)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(88))
        logo.setFixedSize(44, 44)
        logo.setScaledContents(True)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(3)
        title = QLabel("ORCHESTRE")
        title.setObjectName("Brand")
        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)
        tag = QLabel("IA")
        tag.setObjectName("BrandTag")
        subtitle = QLabel("musicien virtuel")
        subtitle.setObjectName("Version")
        tag_row.addWidget(tag)
        tag_row.addWidget(subtitle)
        tag_row.addStretch(1)
        names.addWidget(title)
        names.addLayout(tag_row)
        brand.addLayout(names, 1)
        col.addLayout(brand)
        col.addSpacing(28)

        section = QLabel("ESPACES")
        section.setObjectName("NavSection")
        col.addWidget(section)
        col.addSpacing(6)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Nav")
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        for key, label in zip(VIEW_KEYS, VIEW_LABELS):
            item = QListWidgetItem(icon(key, theme.TEXT_DIM, theme.ACCENT, 18), f"  {label}")
            item.setSizeHint(QSize(SIDEBAR_WIDTH - 24, 44))
            self.sidebar.addItem(item)
        col.addWidget(self.sidebar, 1)

        self.side_mic = QLabel()
        self.side_mic.setObjectName("SideStatus")
        self.side_orchestra = QLabel()
        self.side_orchestra.setObjectName("SideStatus")
        for w in (self.side_mic, self.side_orchestra):
            w.setContentsMargins(22, 2, 12, 2)
            col.addWidget(w)
        self._set_side_status(self.side_mic, "Micro", "arrêté", theme.TEXT_FAINT)
        self._set_side_status(self.side_orchestra, "Orchestre", "arrêté", theme.TEXT_FAINT)
        col.addSpacing(10)
        version = QLabel(f"Version {__version__}")
        version.setObjectName("Version")
        version.setContentsMargins(22, 0, 0, 0)
        col.addWidget(version)
        return side

    @staticmethod
    def _set_side_status(label: QLabel, name: str, state: str, color: str) -> None:
        label.setText(f"<span style='color:{color}; font-size:11pt'>●</span>&nbsp; {name} : {state}")

    # ------------------------------------------------------------ événements
    def _on_view_changed(self, row: int) -> None:
        if 0 <= row < len(VIEW_KEYS):
            self.stack.setCurrentIndex(row)
            self._config.ui.last_view = VIEW_KEYS[row]

    def _on_capture_state(self, event: CaptureStateChanged) -> None:
        msg = f"Capture : {event.state.value}"
        if event.message:
            msg += f" — {event.message}"
        self.statusBar().showMessage(msg)
        color = {CaptureState.RUNNING: theme.OK, CaptureState.ERROR: theme.DANGER,
                 CaptureState.STARTING: theme.WARN}.get(event.state, theme.TEXT_FAINT)
        self._set_side_status(self.side_mic, "Micro", event.state.value, color)

    def _on_conductor(self, u: ConductorUpdate) -> None:
        color = {ConductorState.PLAYING: theme.OK, ConductorState.ENDING: theme.OK,
                 ConductorState.LISTENING: theme.WARN}.get(u.state, theme.TEXT_FAINT)
        self._set_side_status(self.side_orchestra, "Orchestre", u.state.value, color)

    def closeEvent(self, event) -> None:  # noqa: N802 (API Qt)
        self.studio.shutdown()
        self.bridge.disconnect_bus()
        self._save_config()
        super().closeEvent(event)
