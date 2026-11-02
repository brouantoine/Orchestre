import numpy as np

from orchestre_ia.audio.vad import VoiceActivityDetector

SR = 48000
BLOCK = 512


def blocks(signal):
    for i in range(0, len(signal) - BLOCK + 1, BLOCK):
        yield signal[i : i + BLOCK]


def run(vad, signal):
    return [vad.process(b) for b in blocks(signal)]


def voice_like(seconds, f0=220.0, amp=0.1):
    """Son harmonique (fondamentale + harmoniques décroissantes) ~ voix chantée."""
    t = np.arange(int(SR * seconds)) / SR
    x = sum(amp / k * np.sin(2 * np.pi * f0 * k * t) for k in range(1, 6))
    return x.astype(np.float32)


def white_noise(seconds, rms_db, seed=0):
    rng = np.random.default_rng(seed)
    amp = 10 ** (rms_db / 20)
    return (rng.standard_normal(int(SR * seconds)) * amp).astype(np.float32)


def test_silence_is_not_voice():
    vad = VoiceActivityDetector(SR)
    assert not any(run(vad, np.zeros(SR, np.float32)))


def test_quiet_room_noise_is_not_voice():
    vad = VoiceActivityDetector(SR)
    assert not any(run(vad, white_noise(2.0, -65)))


def test_loud_broadband_noise_is_rejected():
    # un souffle fort (ventilateur) n'est pas concentré dans la bande vocale
    vad = VoiceActivityDetector(SR)
    assert not any(run(vad, white_noise(2.0, -30)))


def test_voice_detected_after_noise():
    vad = VoiceActivityDetector(SR)
    run(vad, white_noise(1.0, -65))
    result = run(vad, voice_like(0.5) + white_noise(0.5, -65, seed=1))
    assert result[-1] is True
    # attaque ~30 ms : détecté dans les 5 premiers blocs (~53 ms)
    assert any(result[:5])


def test_hangover_keeps_voice_briefly_then_releases():
    vad = VoiceActivityDetector(SR)
    run(vad, voice_like(0.5))
    after = run(vad, np.zeros(int(SR * 0.6), np.float32))
    block_ms = BLOCK / SR * 1000
    still_on = int(250 / block_ms)
    assert all(after[:still_on])  # les respirations courtes ne coupent pas
    assert after[-1] is False  # libéré après ~300 ms


def test_noise_floor_tracks_ambient_level():
    vad = VoiceActivityDetector(SR)
    run(vad, white_noise(1.0, -72))
    assert -76 < vad.noise_floor_db < -68
