"""Emplacements des données utilisateur.

Toutes les données (configuration, journaux, mémoire musicale) sont rangées
dans un dossier par utilisateur du système. La variable d'environnement
ORCHESTRE_IA_HOME permet de rediriger ce dossier (tests, installation portable).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "OrchestreIA"


def user_data_dir() -> Path:
    override = os.environ.get("ORCHESTRE_IA_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_DIR_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "orchestre_ia"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return user_data_dir() / "config.json"


def recordings_dir() -> Path:
    """Enregistrements de voix : privés, jamais transmis automatiquement."""
    return user_data_dir() / "enregistrements"


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
