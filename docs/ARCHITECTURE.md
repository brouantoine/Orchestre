# Architecture d'ORCHESTRE IA

## Paquets

| Paquet | Responsabilité | État |
|---|---|---|
| `core` | Bus d'événements, configuration, chemins, journaux | Fait |
| `audio` | Périphériques, capture, tampon circulaire, filtre, niveau, VAD, enregistrement | Fait |
| `analysis` | YIN, suivi de hauteur, notes, diapason, tonalité, tempo, garde anti-réécoute | Fait |
| `conductor` | Horloge musicale, moteur harmonique, chef d'orchestre | Fait (base) |
| `instruments` | Styles, piano, batterie (contrat commun `Instrument`) | Fait |
| `midi` | Notes planifiées en temps musical, file thread-safe | Fait |
| `synthesis` | FluidSynth, synthé de secours, sortie audio et mixage | Fait |
| `app` | Session, ligne de commande, rendu d'un fichier | Fait |
| `interface` | Fenêtre Qt, vues, clavier animé, courbe de mélodie | 4 vues sur 6 |
| `recognition`, `learning`, `database` | Reconnaissance, mémoire, stockage | Phases 6-7 |

Ajouter un instrument (basse, guitare, cordes) : une classe avec `play_beat(ctx)` et `release_all(beat)`,
un canal MIDI, un programme General MIDI. Le chef d'orchestre l'appelle à chaque temps.

## Flux de données

```
Micro ─► [PortAudio] ─► AudioCaptureEngine ─► AnalysisEngine (thread « music-analysis »)
                         (thread « audio-processing »)   │ hauteur, notes, diapason, tonalité, tempo
                                                          ▼
                                            Conductor (thread « conductor », 100 Hz)
                                            │ accord, mode, intensité, entrées/sorties
                                            ▼
                     PianoEngine / DrumEngine ─► MidiScheduler (temps en beats)
                                                          ▼
Haut-parleur ◄─ [PortAudio] ◄─ AudioOutputEngine : MusicClock + FluidSynth + mixage
                                (callback temps réel)
```

- **Horloge unique** : `MusicClock` est cadencée par le compteur d'échantillons de la sortie.
  Piano et batterie lisent la même grille. Les messages MIDI sont appliqués à l'échantillon exact dans le bloc.
- **Planification anticipée** : le chef d'orchestre planifie chaque temps ~200 ms à l'avance.
- **Retour de la sortie vers l'analyse** : la sortie publie son niveau et ses notes en cours.
  L'analyse s'en sert pour ignorer la réécoute de l'orchestre par le micro.

## États du chef d'orchestre

`inactif → écoute → joue (libre ⇄ rythmé) → conclusion → écoute`, plus `pause` à tout moment.

## Événements

| Événement | Émetteur | Fréquence |
|---|---|---|
| `CaptureStateChanged`, `AudioLevelEvent`, `VoiceActivityChanged`, `CaptureStats` | capture | transitions, 30/s, 2/s |
| `PitchUpdate`, `NoteFinished`, `KeyUpdate`, `TempoUpdate` | analyse | 30/s, par note, au changement, 1/s |
| `ConductorUpdate` | chef d'orchestre | à chaque temps et transition |
| `OutputStateChanged` | sortie | transitions |

L'interface reçoit tout via `QtEventBridge` (connexions Qt « queued » vers le thread graphique).
