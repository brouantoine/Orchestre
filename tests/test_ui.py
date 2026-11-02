"""Tests de l'interface (Qt hors écran) avec micro et sortie simulés."""

import numpy as np
import pytest
import soundfile as sf

from orchestre_ia.app.session import MusicSession
from orchestre_ia.audio.capture import AudioCaptureEngine
from orchestre_ia.audio.devices import AudioDevice
from orchestre_ia.audio.events import CaptureState
from orchestre_ia.conductor.conductor import ConductorState
from orchestre_ia.core.config import AppConfig
from orchestre_ia.interface.main_window import VIEW_KEYS, MainWindow
from orchestre_ia.interface.theme import STYLESHEET
from orchestre_ia.synthesis.builtin import BuiltinSynth
from orchestre_ia.synthesis.output import AudioOutputEngine
from tests.fakes import fake_factory, sine
from tests.test_accompaniment import FakeOutputStream

FAKE_DEVICES = [
    AudioDevice(9, "Micro test", "Windows WASAPI", 2, 48000.0, True),
    AudioDevice(1, "Micro test", "MME", 2, 44100.0, True),
]
FAKE_OUTPUTS = [AudioDevice(8, "Haut-parleur test", "Windows WASAPI", 2, 48000.0, True)]


def make_window(qtbot, bus, devices=FAKE_DEVICES, signal=None):
    config = AppConfig()
    saves = []
    capture = AudioCaptureEngine(bus, stream_factory=fake_factory(signal or sine(220, 0.2), speed=1.0))
    output = AudioOutputEngine(bus, backend_factory=BuiltinSynth, stream_factory=lambda **kw: FakeOutputStream(**kw))
    session = MusicSession(bus, capture=capture, output=output)
    win = MainWindow(bus, session, config, lambda: saves.append(1), lambda: devices, lambda: FAKE_OUTPUTS)
    win.setStyleSheet(STYLESHEET)
    qtbot.addWidget(win)
    win.show()
    win._test = {"config": config, "saves": saves, "session": session}
    return win


@pytest.fixture
def window(qtbot, bus):
    win = make_window(qtbot, bus)
    yield win
    win._test["session"].stop()


def test_all_six_spaces_exist(window):
    assert window.sidebar.count() == 6
    for row, key in enumerate(VIEW_KEYS):
        window.sidebar.setCurrentRow(row)
        assert window.stack.currentWidget() is window.views[key]
        assert window._test["config"].ui.last_view == key


def test_device_lists_are_populated(window):
    assert window.studio.device_combo.count() == 2
    assert window.studio.selected_device().hostapi == "Windows WASAPI"
    assert window.settings.output_combo.count() == 1


def test_listen_and_accompany_from_ui(window, qtbot):
    studio = window.studio
    session = window._test["session"]
    studio.start_button.click()
    qtbot.waitUntil(lambda: session.capture.state == CaptureState.RUNNING, timeout=2000)
    assert session.output.running
    qtbot.waitUntil(lambda: studio.stop_button.isEnabled(), timeout=2000)
    qtbot.waitUntil(lambda: "dBFS" in studio.level_value.text(), timeout=2000)
    qtbot.waitUntil(lambda: studio.note_tile.value.text() == "La3", timeout=3000)  # 220 Hz = La3
    assert studio.keyboard.sung == 57
    # le piano entre après ~2,5 s de chant
    qtbot.waitUntil(lambda: studio.piano_tile.value.text() == "Joue", timeout=8000)
    qtbot.waitUntil(lambda: studio.chord_tile.value.text() != "—", timeout=3000)
    assert studio.keyboard.played

    studio.pause_button.click()
    qtbot.waitUntil(lambda: session.conductor.state == ConductorState.PAUSED, timeout=1000)
    qtbot.waitUntil(lambda: "Reprendre" in studio.pause_button.text(), timeout=1000)
    studio.pause_button.click()
    assert session.conductor.state == ConductorState.LISTENING

    studio.stop_button.click()
    qtbot.waitUntil(lambda: studio.start_button.isEnabled(), timeout=2000)
    assert not session.output.running
    assert studio.level_value.text() == "—"


def test_style_change_applies_live(window):
    studio = window.studio
    studio.style_combo.setCurrentIndex(studio.style_combo.findData("gospel"))
    assert window._test["config"].accompaniment.style == "gospel"
    assert window._test["session"].settings.style == "gospel"


def test_headphones_option(window):
    window.studio.headphones_check.setChecked(True)
    assert window._test["session"].analysis.headphones
    assert not window.studio.headphones_hint.isVisibleTo(window.studio)


def test_recording_checkbox_saves_wav(window, qtbot):
    studio = window.studio
    studio.record_check.setChecked(True)
    studio.start_button.click()
    qtbot.waitUntil(lambda: window._test["session"].capture.state == CaptureState.RUNNING, timeout=2000)
    assert "Enregistrement en cours" in studio.record_label.text()
    qtbot.wait(400)
    studio.stop_button.click()
    assert "Enregistré" in studio.record_label.text()
    path = studio._recorder.path
    assert path.exists() and sf.info(str(path)).frames > 0


def test_orchestra_view_controls(window):
    orch = window.orchestra
    session = window._test["session"]
    orch.drums_combo.setCurrentIndex(orch.drums_combo.findData("off"))
    assert session.settings.drums_mode == "off"
    for i, t in enumerate((10.0, 10.6, 11.2, 11.8)):  # 4 tapes à 100 BPM
        orch.tap(t)
    assert orch.bpm_spin.value() == 100
    assert session.settings.tempo_mode == "manual"
    assert session.settings.manual_bpm == 100
    orch.sliders["drums_volume"].setValue(40)
    assert window._test["config"].accompaniment.drums_volume == pytest.approx(0.4)


def test_gain_slider_updates_config(window):
    window.studio.gain_slider.setValue(6)
    assert window._test["config"].audio.gain_db == 6.0
    assert window.studio.gain_value.text() == "+6 dB"


def test_settings_view_saves(window):
    settings = window.settings
    settings.samplerate_combo.setCurrentIndex(settings.samplerate_combo.findData(44100))
    settings.blocksize_combo.setCurrentIndex(settings.blocksize_combo.findData(256))
    settings.highpass_check.setChecked(False)
    before = len(window._test["saves"])
    settings.save_button.click()
    cfg = window._test["config"]
    assert (cfg.audio.samplerate, cfg.audio.blocksize, cfg.audio.highpass_enabled) == (44100, 256, False)
    assert cfg.accompaniment.output_device_name == "Haut-parleur test"
    assert len(window._test["saves"]) == before + 1


def test_analysis_view_receives_notes(window, qtbot):
    window.studio.start_button.click()
    qtbot.waitUntil(lambda: len(window.analysis.roll.points) > 10, timeout=3000)
    window.studio.stop_button.click()


def test_no_devices_disables_start(qtbot, bus):
    win = make_window(qtbot, bus, devices=[])
    assert not win.studio.start_button.isEnabled()
    assert "Aucun micro" in win.studio.status_label.text()


def test_config_roundtrip_with_accompaniment(tmp_path):
    cfg = AppConfig()
    cfg.accompaniment.style = "zouglou"
    cfg.accompaniment.manual_bpm = 104
    cfg.save(tmp_path / "c.json")
    assert AppConfig.load(tmp_path / "c.json").accompaniment.style == "zouglou"
    np.testing.assert_equal(AppConfig.load(tmp_path / "c.json").accompaniment.manual_bpm, 104)
