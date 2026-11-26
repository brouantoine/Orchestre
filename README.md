# ORCHESTRE IA

Musicien artificiel : il écoute une personne chanter au micro, comprend sa mélodie
et l'accompagne avec un orchestre virtuel (piano, batterie, puis d'autres instruments).

**Version actuelle : 0.2.0 — le piano et la batterie accompagnent le chant (phases 1 à 4, base de la phase 5).**
Voir [PROJECT_STATUS.md](PROJECT_STATUS.md) pour l'état exact et [TODO.md](TODO.md) pour la suite.

## Ce qui fonctionne aujourd'hui

- **Écoute** : choix du micro, capture temps réel, VU-mètre, détection de voix, enregistrement WAV local.
- **Analyse** : note chantée (YIN), notes et mélodie, diapason personnel, tonalité avec inertie, tempo et régularité.
- **Chef d'orchestre** : choisit les accords d'après le chant et la tonalité, fait entrer le piano après ~2,5 s de chant,
  la batterie quand la pulsation est stable, allège pendant les silences, conclut sur l'accord de tonique.
- **Piano** : renversements avec conduite des voix, neuf jeux (ballade, pop, gospel, jazz, R&B, classique, afro, reggae, soul, zouglou).
- **Batterie** : dix styles, relances en fin de phrase, cymbale d'entrée, trois niveaux d'intensité.
- **Son** : FluidSynth et la banque FluidR3Mono (MIT), synthé intégré de secours, placement des notes à l'échantillon près.
- **Haut-parleurs** : garde anti-réécoute ; l'orchestre s'accorde sur le diapason du chanteur.
- **Interface** : Studio, Analyse, Orchestre et Paramètres opérationnels. Bibliothèque et Apprentissage indiquent leur phase, sans rien simuler.
- **Apprentissage (base de la phase 7)** : écoute muette d'une séance entière (louange, répétition), étude hors ligne
  (tonalités, tempos, accords par morceau), mémoire SQLite des habitudes d'accords. Le chef d'orchestre s'en sert
  au lancement suivant : enchaînements préférés de l'équipe, accords d'emprunt (bVII…) devenus familiers.

## Installation (développement)

Terminal : **PowerShell** dans VS Code. Dossier : `C:\Users\DELL\ORCHESTRE_IA`.

```powershell
cd C:\Users\DELL\ORCHESTRE_IA
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv   # une seule fois
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Utilisation

```powershell
.\.venv\Scripts\python.exe -m orchestre_ia                  # interface graphique
.\.venv\Scripts\python.exe -m orchestre_ia --list-devices   # liste des micros
.\.venv\Scripts\python.exe -m orchestre_ia --test-mic 10    # diagnostic micro de 10 s
.\.venv\Scripts\python.exe -m orchestre_ia --test-mic 10 --device 9
# accompagner un enregistrement et écrire le mixage voix + orchestre à côté du fichier
.\.venv\Scripts\python.exe -m orchestre_ia --accompany-file chant.wav --style gospel --tempo 76
```

### Apprendre en écoutant la louange

Double-cliquer sur `ecouter_louange.bat`, ou :

```powershell
# écoute muette (aucun son joué), parties de 5 min, veille bloquée ; Ctrl+C pour arrêter
.\.venv\Scripts\python.exe -m orchestre_ia --learn-listen --label louange
# étudier toutes les nouvelles séances et mettre à jour la mémoire (≈ 6 s de calcul par minute écoutée)
.\.venv\Scripts\python.exe -m orchestre_ia --learn-study
# réétudier une séance précise
.\.venv\Scripts\python.exe -m orchestre_ia --learn-study "$env:APPDATA\OrchestreIA\apprentissage\ecoutes\<séance>" --force
```

L'étude affiche chaque morceau trouvé (tonalité, tempo, progression typique), puis la part d'accords suivants
devinés avec les règles génériques et avec les habitudes apprises, mesurée sur des morceaux tenus à part.

### Apprendre sur une bibliothèque de chants

Déposer les fichiers dans `Musique\Orchestre chants` (un chant par fichier : mp3, m4a, webm, opus, aac, mp4,
wav, flac, ogg), puis double-cliquer sur `etudier_chants.bat`, ou glisser un autre dossier sur ce fichier.

```powershell
.\.venv\Scripts\python.exe -m orchestre_ia --learn-library                       # Musique\Orchestre chants
.\.venv\Scripts\python.exe -m orchestre_ia --learn-library "D:\chants" --workers 4
```

Plusieurs chants sont étudiés en parallèle (environ 30 s de calcul par chant de 5 min et par processus).
Ctrl+C interrompt sans rien perdre : la reprise saute les chants déjà étudiés, même renommés. Seuls la
tonalité, le tempo et la suite d'accords sont gardés. N'utiliser que des fichiers dont on a le droit de se
servir : les conditions de YouTube interdisent le téléchargement sans l'accord de l'ayant droit.

### Apprendre sur un corpus de grilles d'accords

```powershell
# télécharge Chordonomicon (≈ 264 Mo, licence MIT, ≈ 680 000 chants) puis l'importe (≈ 2 min)
.\.venv\Scripts\python.exe -m orchestre_ia --learn-corpus
.\.venv\Scripts\python.exe -m orchestre_ia --learn-corpus chordonomicon_v2.csv   # fichier déjà téléchargé
.\.venv\Scripts\python.exe -m orchestre_ia --learn-corpus --limit 50000          # essai rapide
```

Aucun son : seules les suites d'accords sont lues, ramenées à la tonalité et rangées par groupe
(louange, afro, pop, rock…) dans `apprentissage\corpus.sqlite`. Le corpus remplace les règles
génériques ; les habitudes de l'équipe (`--learn-listen`, `--learn-study`) l'emportent dès qu'elles
sont assez nombreuses. L'import affiche la part d'accords suivants devinés sur des chants tenus à part.

FluidSynth (DLL) est dans `vendor\fluidsynth\` et la banque de sons dans `orchestre_ia\resources\soundfonts\`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest                       # tous les tests, matériel compris
.\.venv\Scripts\python.exe -m pytest -m "not hardware"     # sans le vrai micro
```

## Données utilisateur

`%APPDATA%\OrchestreIA\` contient `config.json`, `logs\orchestre_ia.log` et
`enregistrements\` (fichiers WAV créés seulement si la case « Enregistrer ma voix » est cochée).
`apprentissage\ecoutes\<date>_<nom>\` contient les séances écoutées (`partie_NNN.wav`, `seance.json`) et
`apprentissage\memoire.sqlite` la mémoire musicale. Rien n'est transmis.
La variable `ORCHESTRE_IA_HOME` permet de déplacer ce dossier.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) : modules, threads, flux de données.
- [docs/DECISIONS.md](docs/DECISIONS.md) : choix techniques et licences.
