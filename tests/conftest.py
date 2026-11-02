import os
import tempfile

# Avant tout import Qt / application : environnement isolé et sans écran.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ORCHESTRE_IA_HOME"] = tempfile.mkdtemp(prefix="orchestre_ia_test_")

import pytest  # noqa: E402

from orchestre_ia.core.events import EventBus  # noqa: E402


@pytest.fixture
def bus() -> EventBus:
    return EventBus()
