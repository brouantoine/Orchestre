from orchestre_ia.audio.devices import find_device, list_input_devices, preferred_default


class FakeBackend:
    def query_hostapis(self):
        return (
            {"name": "MME", "default_input_device": 1},
            {"name": "Windows WASAPI", "default_input_device": 3},
        )

    def query_devices(self):
        return [
            {"name": "Mappeur", "hostapi": 0, "max_input_channels": 2, "default_samplerate": 44100.0},
            {"name": "Micro USB", "hostapi": 0, "max_input_channels": 1, "default_samplerate": 44100.0},
            {"name": "Haut-parleur", "hostapi": 1, "max_input_channels": 0, "default_samplerate": 48000.0},
            {"name": "Micro USB", "hostapi": 1, "max_input_channels": 1, "default_samplerate": 48000.0},
        ]


class BrokenBackend:
    def query_hostapis(self):
        raise OSError("PortAudio absent")


def test_lists_only_inputs_with_wasapi_first():
    devices = list_input_devices(FakeBackend())
    assert [d.index for d in devices] == [3, 1, 0]
    assert devices[0].hostapi == "Windows WASAPI"
    assert devices[0].is_default
    assert all(d.channels > 0 for d in devices)


def test_lists_outputs_separately():
    from orchestre_ia.audio.devices import list_output_devices

    outputs = list_output_devices(FakeBackend())
    assert [d.name for d in outputs] == []  # FakeBackend ne déclare aucune sortie (max_output_channels absent)


def test_find_device_by_name_and_hostapi():
    devices = list_input_devices(FakeBackend())
    assert find_device(devices, "Micro USB", "MME").index == 1
    assert find_device(devices, "Micro USB", "Windows WASAPI").index == 3
    assert find_device(devices, "Inconnu", None) is None
    assert find_device(devices, None, None) is None


def test_preferred_default():
    devices = list_input_devices(FakeBackend())
    assert preferred_default(devices).index == 3
    assert preferred_default([]) is None


def test_backend_failure_returns_empty_list():
    assert list_input_devices(BrokenBackend()) == []
