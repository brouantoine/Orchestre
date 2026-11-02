import threading
from dataclasses import dataclass

from orchestre_ia.core.events import Event, EventBus


@dataclass(frozen=True, slots=True)
class Ping(Event):
    value: int


@dataclass(frozen=True, slots=True)
class SubPing(Ping):
    pass


def test_publish_reaches_subscriber(bus: EventBus):
    received = []
    bus.subscribe(Ping, received.append)
    bus.publish(Ping(value=3))
    assert [e.value for e in received] == [3]
    assert received[0].timestamp > 0


def test_subclass_events_reach_parent_subscribers(bus: EventBus):
    received = []
    bus.subscribe(Ping, received.append)
    bus.publish(SubPing(value=1))
    assert len(received) == 1


def test_unsubscribe(bus: EventBus):
    received = []
    unsubscribe = bus.subscribe(Ping, received.append)
    unsubscribe()
    unsubscribe()  # idempotent
    bus.publish(Ping(value=1))
    assert received == []


def test_failing_handler_does_not_block_others(bus: EventBus):
    received = []

    def broken(_):
        raise RuntimeError("boom")

    bus.subscribe(Ping, broken)
    bus.subscribe(Ping, received.append)
    bus.publish(Ping(value=7))
    assert len(received) == 1


def test_concurrent_publish_is_safe(bus: EventBus):
    counter = []
    lock = threading.Lock()

    def handler(_):
        with lock:
            counter.append(1)

    bus.subscribe(Ping, handler)
    threads = [threading.Thread(target=lambda: [bus.publish(Ping(value=i)) for i in range(500)]) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(counter) == 4000
