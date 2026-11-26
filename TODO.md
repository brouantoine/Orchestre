# TODO — ORCHESTRE IA

## À faire par l'utilisateur maintenant
- [ ] Écouter les deux fichiers accompagnés dans le dossier des enregistrements et dire ce qui sonne faux.
- [ ] Tester en direct : Studio > « Écouter et accompagner », chanter 30 s.
- [ ] Tester avec un casque si possible (case « J'utilise un casque »).
- [ ] Tester la batterie : Orchestre > Taper le tempo, puis chanter en rythme.

## Améliorations de l'accompagnement (suite phase 5)
- [ ] Harmonie : anticiper l'accord (aujourd'hui décidé sur ce qui vient d'être chanté).
- [ ] Détecter couplets/refrains et répétitions de phrases pour réutiliser les mêmes accords.
- [ ] Annulation d'écho adaptative (filtre NLMS sur le signal de sortie) pour le jeu sur haut-parleurs.
- [ ] Faire évoluer les rythmes pendant le morceau (variations, montée en intensité au refrain).
- [ ] Introductions et transitions plus riches entre sections.
- [ ] Faire valider chaque style par un musicien (zouglou, afro, gospel, reggae…).
- [ ] Suivre le tempo du chanteur en continu (aujourd'hui fixé à l'entrée).
- [ ] Ajustement lent du diapason pendant le morceau.

## Phase 6 — Reconnaissance musicale
- [ ] Empreintes d'intervalles (indépendantes de la tonalité), DTW, trois réponses.
- [ ] Bibliothèque de référence autorisée (chansons du domaine public, compositions de l'utilisateur).

## Phase 7 — Apprentissage
- [x] Écoute muette d'une séance (louange) : `--learn-listen`, `ecouter_louange.bat` (2026-11-08).
- [x] Étude hors ligne : tonalité, tempo et accords par morceau ; mémoire SQLite des enchaînements et accords favoris.
- [x] Le chef d'orchestre utilise la mémoire (confiance croissante avec le nombre d'enchaînements entendus).
- [x] Mesure : accord suivant deviné, règles génériques contre habitudes apprises (morceaux tenus à part).
- [x] Bibliothèque de chants : `--learn-library`, `etudier_chants.bat`, mp3/m4a/webm via PyAV, parallèle, reprise.
- [x] Corpus de grilles Chordonomicon (≈ 680 000 chants, MIT) : `--learn-corpus`, a priori de la mémoire (2026-11-24).
- [ ] Mémoire sur les 2 derniers accords (trigrammes) : 47 % d'accords suivants devinés en louange
      contre 40 % avec le seul accord en cours (mesure du 2026-11-24 sur 50 000 chants).
- [ ] Tonalité par section dans le corpus (modulations de fin de chant, aujourd'hui une tonalité par chant).
- [ ] Mesurer corpus + habitudes de l'équipe sur les vraies séances de louange (`--learn-study --force`).
- [ ] Lakh MIDI (CC-BY 4.0, usage interne) : rythmes de batterie, voicings de piano, mélodie → accords.
- [ ] Déposer des centaines de chants (sources autorisées) dans Musique\Orchestre chants et lancer l'étude.
- [ ] Phase 6 avec cette bibliothèque : garder la grille de chaque chant et la mélodie chantée, reconnaître
      le chant en direct, puis jouer sa grille en avance au lieu de deviner accord par accord.
- [ ] Écouter d'autres séances de louange : la mémoire en mineur n'a que 18 % de confiance (2026-11-08).
- [ ] Brancher l'ordinateur sur la table de mixage (sortie ligne) : le micro intégré capte surtout la salle.
- [ ] Vérifier le tempo : 120-136 BPM détectés, peut-être le double du tempo ressenti (60-68).
- [ ] Apprendre aussi le style rythmique (batterie, basse) et les tempos préférés pour régler l'orchestre.
- [ ] Mémoire individuelle : styles préférés, corrections d'accords faites par l'utilisateur.
- [ ] Vue Apprentissage de l'interface : séances, morceaux, habitudes, bouton « Étudier ».
- [ ] Bibliothèque collective avec consentement explicite ; jamais d'envoi automatique des voix.

## Phases 8 à 10
- [ ] Vues Bibliothèque et Apprentissage.
- [ ] Test de stabilité de 30 minutes, mesure de la latence aller-retour réelle.
- [ ] PyInstaller (dossier, DLL FluidSynth, SoundFont, licences), installateur, guide utilisateur.

## Outillage
- [x] Git installé, projet versionné et publié sur https://github.com/brouantoine/Orchestre (2026-11-02).
