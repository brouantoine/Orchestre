from orchestre_ia.core.config import AppConfig


def test_defaults_when_missing(tmp_path):
    cfg = AppConfig.load(tmp_path / "absent.json")
    assert cfg.audio.samplerate == 48000
    assert cfg.audio.blocksize == 512


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = AppConfig()
    cfg.audio.input_device_name = "Microphone (Realtek(R) Audio)"
    cfg.audio.input_hostapi = "Windows WASAPI"
    cfg.audio.gain_db = 6.0
    cfg.ui.last_view = "parametres"
    cfg.save(path)
    loaded = AppConfig.load(path)
    assert loaded == cfg
    assert not list(tmp_path.glob(".config-*"))  # pas de fichier temporaire résiduel


def test_corrupted_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ pas du json", encoding="utf-8")
    assert AppConfig.load(path) == AppConfig()


def test_invalid_values_are_sanitized(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        '{"audio": {"samplerate": 12345, "blocksize": 7, "gain_db": 99, "unknown_key": 1}}',
        encoding="utf-8",
    )
    cfg = AppConfig.load(path)
    assert cfg.audio.samplerate == 48000
    assert cfg.audio.blocksize == 512
    assert cfg.audio.gain_db == 24.0
