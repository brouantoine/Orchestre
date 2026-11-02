from orchestre_ia.analysis.echo import EchoGuard


def test_everything_is_voice_when_orchestra_silent():
    g = EchoGuard(lambda a, b: -100.0)
    assert g.is_voice(1.0, -50.0)


def test_learns_coupling_and_rejects_leak():
    # l'orchestre joue à -20 dBFS ; le micro capte la fuite à -45 dBFS (couplage -25 dB)
    g = EchoGuard(lambda a, b: -20.0)
    t = 0.0
    for _ in range(30):  # 3 s de fuite seule (pause du chanteur)
        t += 0.1
        g.is_voice(t, -45.0)
    assert g.coupling_db == -25.0
    assert not g.is_voice(t + 0.1, -44.0)  # fuite : rejetée
    assert g.is_voice(t + 0.2, -30.0)  # voix 15 dB au-dessus de la fuite : retenue


def test_coupling_window_forgets_old_values():
    g = EchoGuard(lambda a, b: -20.0, window_s=2.0)
    g.is_voice(0.0, -60.0)
    for i in range(1, 40):
        g.is_voice(i * 0.1, -40.0)
    assert g.coupling_db == -20.0
