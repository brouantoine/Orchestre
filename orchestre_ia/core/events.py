"""Bus d'événements thread-safe.

Les modules (audio, analyse, chef d'orchestre, interface...) ne s'appellent pas
directement : ils publient des événements typés et s'abonnent à ceux qui les
intéressent. Les gestionnaires sont appelés dans le thread de l'émetteur ;
l'interface Qt utilise un pont (interface/bridge.py) qui renvoie les
événements vers le thread graphique.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, TypeVar

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Event:
    """Classe de base de tous les événements. `timestamp` = time.monotonic()."""

    timestamp: float = field(default_factory=time.monotonic, kw_only=True)


E = TypeVar("E", bound=Event)


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[type[Event], list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> Callable[[], None]:
        """Abonne `handler` à `event_type` (et à ses sous-classes).

        Retourne une fonction qui annule l'abonnement.
        """
        with self._lock:
            self._subscribers[event_type].append(handler)  # type: ignore[arg-type]

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers[event_type].remove(handler)  # type: ignore[arg-type]
                except ValueError:
                    pass

        return unsubscribe

    def publish(self, event: Event) -> None:
        """Diffuse l'événement. Une erreur dans un gestionnaire n'affecte pas les autres."""
        with self._lock:
            handlers = [
                h
                for event_type, hs in self._subscribers.items()
                if isinstance(event, event_type)
                for h in hs
            ]
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                log.exception("Erreur dans le gestionnaire %r pour %s", handler, type(event).__name__)
