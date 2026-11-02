import threading
import time

import numpy as np
import pytest

from orchestre_ia.audio.ring_buffer import AudioRingBuffer


def test_write_then_read_in_order():
    rb = AudioRingBuffer(16)
    rb.write(np.arange(10, dtype=np.float32))
    assert rb.available == 10
    np.testing.assert_array_equal(rb.read(4), [0, 1, 2, 3])
    np.testing.assert_array_equal(rb.read(6), [4, 5, 6, 7, 8, 9])
    assert rb.available == 0


def test_wraparound():
    rb = AudioRingBuffer(8)
    rb.write(np.arange(6, dtype=np.float32))
    rb.read(6)
    rb.write(np.arange(6, 12, dtype=np.float32))  # traverse la fin du tampon
    np.testing.assert_array_equal(rb.read(6), np.arange(6, 12))


def test_overrun_drops_oldest_and_counts():
    rb = AudioRingBuffer(8)
    rb.write(np.arange(6, dtype=np.float32))
    rb.write(np.arange(6, 12, dtype=np.float32))
    assert rb.overruns == 1
    assert rb.available == 8
    np.testing.assert_array_equal(rb.read(8), np.arange(4, 12))


def test_write_larger_than_capacity_keeps_latest():
    rb = AudioRingBuffer(4)
    rb.write(np.arange(10, dtype=np.float32))
    np.testing.assert_array_equal(rb.latest(4), [6, 7, 8, 9])
    np.testing.assert_array_equal(rb.read(4), [6, 7, 8, 9])


def test_latest_does_not_consume():
    rb = AudioRingBuffer(8)
    rb.write(np.arange(5, dtype=np.float32))
    np.testing.assert_array_equal(rb.latest(3), [2, 3, 4])
    np.testing.assert_array_equal(rb.latest(100), [0, 1, 2, 3, 4])
    assert rb.available == 5


def test_read_timeout_returns_none():
    rb = AudioRingBuffer(8)
    rb.write(np.zeros(2, dtype=np.float32))
    assert rb.read(4, timeout=0.05) is None
    assert rb.available == 2  # rien n'a été consommé


def test_close_wakes_blocked_reader():
    rb = AudioRingBuffer(8)
    result = []
    t = threading.Thread(target=lambda: result.append(rb.read(4, timeout=5)))
    t.start()
    rb.close()
    t.join(timeout=1)
    assert not t.is_alive()
    assert result == [None]


def test_producer_consumer_threads_preserve_samples():
    rb = AudioRingBuffer(4096)
    total = 48000
    out = []

    def consumer():
        while sum(len(x) for x in out) < total:
            block = rb.read(480, timeout=2)
            assert block is not None
            out.append(block)

    t = threading.Thread(target=consumer)
    t.start()
    data = np.arange(total, dtype=np.float32)
    for i in range(0, total, 480):
        # comme une carte son : le producteur ne dépasse pas le consommateur de plus d'un tampon
        while rb.available > rb.capacity - 480:
            time.sleep(0.0005)
        rb.write(data[i : i + 480])
    t.join(timeout=5)
    np.testing.assert_array_equal(np.concatenate(out), data)
    assert rb.overruns == 0


def test_invalid_capacity():
    with pytest.raises(ValueError):
        AudioRingBuffer(0)
