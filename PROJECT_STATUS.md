# État du projet — ORCHESTRE IA

Dernière mise à jour : 2026-11-08 — version 0.2.0 + base de l'apprentissage (phase 7)

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
| Phase 7 (base) — écoute muette d'une séance, étude hors ligne, mémoire SQLite, usage par l'harmonie | `test_learning` + 3 séances de louange réelles |
| Phase 7 — étude d'une bibliothèque de chants (mp3, m4a, webm…), parallèle, reprise, validation croisée | `test_library` + fichiers mp3/webm d'essai |

**159 tests réussis**, dont 2 sur le vrai micro.

## Premières écoutes de louange (2026-11-08, micro intégré, 29 min)

| Séance | Morceaux trouvés | Accord suivant deviné, règles génériques | Avec habitudes apprises |
|---|---|---|---|
| 10 h 49, 11 min | 6 (Ré majeur, La majeur, La et Mi mineur) | 45 % (72 % parmi 3) | 49 % (77 % parmi 3) |
| 11 h 02, 5 min | 1 (Ré majeur, va-et-vient IV–V) | 22 % (95 % parmi 3) | 21 % (95 % parmi 3) |
| 11 h 25, 13 min | 6 (Mi majeur, Mi mineur, Do majeur, Fa majeur) | 31 % (72 % parmi 3) | 30 % (69 % parmi 3) |

- Habitudes en majeur : I 38 %, IV 23 %, V 23 %, puis ii, iii, vi, bVII ; en mineur : i, bIII, iv, bVII.
- Confiance : une séance inédite était moins bien devinée quand la mémoire faisait pleine confiance après
  200 changements d'accord (26 % contre 36 %). Seuil porté à 500 : jamais pire que les règles génériques,
  légèrement meilleur dans l'ordre chronologique. Confiance actuelle : 59 % en majeur, 10 % en mineur.
- 29 minutes ne suffisent pas encore à battre nettement les règles génériques sur des chants nouveaux.
- Lecture de tonalité parfois ambiguë sur les vamps (Lam–Sol : La mineur ou Mi mineur).
- Étude : environ 6 s de calcul par minute écoutée.
- Prise de son : notes peu marquées (platitude du chroma médiane 0,91), quelques saturations. Une sortie de table de mixage donnerait des accords plus sûrs.

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
