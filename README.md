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

FluidSynth (DLL) est dans `vendor\fluidsynth\` et la banque de sons dans `orchestre_ia\resources\soundfonts\`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest                       # tous les tests, matériel compris
.\.venv\Scripts\python.exe -m pytest -m "not hardware"     # sans le vrai micro
```

## Données utilisateur

`%APPDATA%\OrchestreIA\` contient `config.json`, `logs\orchestre_ia.log` et
`enregistrements\` (fichiers WAV créés seulement si la case « Enregistrer ma voix » est cochée).
La variable `ORCHESTRE_IA_HOME` permet de déplacer ce dossier.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) : modules, threads, flux de données.
- [docs/DECISIONS.md](docs/DECISIONS.md) : choix techniques et licences.
