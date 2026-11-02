"""Icônes vectorielles (dessinées pour ORCHESTRE IA) et logo, rendus en couleur à la demande."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"
LOGO_PATH = ICON_DIR / "logo.svg"

# Tracés 24×24, trait 2 px, extrémités arrondies. "currentColor" est remplacé par la couleur voulue.
PATHS: dict[str, str] = {
    "studio": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v4M8 22h8"/>',
    "analyse": '<path d="M2 12h3.5l3-8 5 16 3-8H22"/>',
    "orchestre": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "bibliotheque": '<path d="M4 4h4v16H4zM10 4h4v16h-4zM15.5 5.2l3.8-1 3.4 14.6-3.8 1z"/>',
    "apprentissage": '<path d="M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9z"/><path d="M19 14v6M16 17h6"/>',
    "parametres": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "play": '<path d="M7 4.5v15l12.5-7.5z" fill="currentColor"/>',
    "pause": '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor"/>',
    "stop": '<rect x="5.5" y="5.5" width="13" height="13" rx="2" fill="currentColor"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.4-5.7L20 8.5"/><path d="M20 3.5v5h-5"/>',
    "headphones": '<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1v-6h3zM3 19a2 2 0 0 0 2 2h1v-6H3z"/>',
    "record": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3.5" fill="currentColor"/>',
    "note": '<path d="M9 18V5l10-2v4L9 9"/><circle cx="6" cy="18" r="3"/>',
    "key": '<path d="M5 9h15M4 15h15M10 3L8 21M16 3l-2 18"/>',
    "tempo": '<path d="M6.5 21L9.5 3h5l3 18z"/><path d="M12 16l5-9M6 17h12"/>',
    "chord": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/><path d="M3 17.5l9 5 9-5" opacity=".5"/>',
    "piano": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16M13 4v16M18 4v16" opacity=".45"/><path d="M8 4v9M13 4v9" stroke-width="3.5"/>',
    "drums": '<ellipse cx="12" cy="10" rx="8" ry="3"/><path d="M4 10v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7M3 3l6 5M21 3l-6 5"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "level": '<path d="M11 5L6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
    "chip": '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M10 2v4M14 2v4M10 18v4M14 18v4M2 10h4M2 14h4M18 10h4M18 14h4"/>',
    "tap": '<circle cx="12" cy="12" r="3" fill="currentColor"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="10.5" opacity=".4"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
}


def _svg(name: str, color: str) -> bytes:
    body = PATHS[name].replace("currentColor", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode()


def _render(data: bytes, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(data))
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QPixmap.fromImage(image)


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    return _render(_svg(name, color), size)


def icon(name: str, color: str, selected_color: str | None = None, size: int = 20) -> QIcon:
    result = QIcon()
    for scale in (1, 2):
        result.addPixmap(pixmap(name, color, size * scale), QIcon.Mode.Normal)
        result.addPixmap(pixmap(name, color, size * scale), QIcon.Mode.Active)
        result.addPixmap(pixmap(name, selected_color or color, size * scale), QIcon.Mode.Selected)
        result.addPixmap(pixmap(name, "#5c6375", size * scale), QIcon.Mode.Disabled)
    return result


@lru_cache(maxsize=16)
def logo_pixmap(size: int) -> QPixmap:
    return _render(LOGO_PATH.read_bytes(), size)


def logo_icon() -> QIcon:
    result = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        result.addPixmap(logo_pixmap(size))
    return result
