# État du projet — ORCHESTRE IA

Dernière mise à jour : 2026-11-02 — version 0.2.0

## Terminé et testé

| Élément | Preuve |
|---|---|
| Phase 1 — environnement, architecture, documentation | arborescence, `pip list` |
| Phase 2 — capture micro temps réel, niveau, voix, enregistrement WAV | `test_capture`, `test_hardware`, `test_recorder` |
| Phase 3 — hauteur YIN, notes, vibrato, diapason personnel, tonalité avec inertie, tempo | `test_analysis` + enregistrement réel |
| Phase 4 — FluidSynth + SoundFont MIT, sortie audio, horloge commune, MIDI à l'échantillon près | `test_music_engine`, `test_accompaniment`, test haut-parleurs réel |
| Phase 4 — piano (renversements, 9 jeux), batterie (10 styles, relances, intensité) | `test_music_engine` |
| Phase 5 (base) — moteur harmonique, chef d'orchestre, entrées, silences, conclusion | `test_accompaniment` |
| Garde anti-réécoute (haut-parleurs) + accord de l'orchestre sur la voix | `test_echo`, test acoustique réel |
| Interface : Studio, Analyse, Orchestre, Paramètres connectés | `test_ui` + captures d'écran |
| Logo (SVG, ICO, PNG), icônes, thème « studio de nuit », indicateur de temps, progression d'accords | captures d'écran, `resources/icons/` |

**133 tests réussis**, dont 2 sur le vrai micro.

## Mesures sur cette machine

| Mesure | Valeur |
|---|---|
| Latence d'entrée (micro) | ≈ 33 ms |
| Latence de sortie (orchestre, WASAPI) | ≈ 22 ms |
| Analyse de hauteur | 2 % du temps réel |
| Précision de hauteur (signaux de test) | < 5 cents jusqu'à 880 Hz |
| Précision de placement des notes jouées | < 1 ms |
| Entrée du piano après le début du chant | ≈ 2,5 s (enregistrement propre), ≈ 9 s (via haut-parleurs) |

## Validé sur l'enregistrement réel de l'utilisateur (60 s, chant libre)

- Tonalité trouvée : Ré# mineur, cohérente avec une analyse pYIN hors ligne indépendante.
- Diapason personnel mesuré : environ +39 cents. L'orchestre s'accorde dessus.
- Tempo : chant libre détecté (régularité 0 %). Le piano joue en mode libre et la batterie attend.
- Accords majoritairement dans la tonalité. Quelques accords hors tonalité pendant les 10 premières secondes.

## Limites connues

- **Haut-parleurs sans casque** : test acoustique réel réussi pour l'arrêt automatique, mais les accords sont moins justes qu'avec un signal propre. Le casque reste recommandé.
- **Tempo automatique** : il ne s'enclenche que si le chant est régulier. Sinon, il faut régler ou taper le tempo pour avoir la batterie.
- **Rythmes de style** : bases conventionnelles, à faire valider par des musiciens de chaque genre (zouglou, afro, gospel en particulier).
- **Pas encore jugé à l'oreille humaine** : la qualité musicale doit être écoutée et commentée par l'utilisateur.

## Restant

Phases 6 à 10 : reconnaissance de chansons, apprentissage, bibliothèque, optimisation, installateur. Voir [TODO.md](TODO.md).
