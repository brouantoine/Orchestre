# Décisions techniques

## D1 — Python 3.12 installé par winget (2026-11-01)
La machine n'avait pas Python. Python 3.12.10 a été installé pour l'utilisateur courant
(`%LOCALAPPDATA%\Programs\Python\Python312`) sans droits administrateur.
L'environnement du projet est isolé dans `.venv`.

## D2 — Un seul paquet `orchestre_ia/`
Les dossiers demandés (audio, analysis, conductor…) sont des sous-paquets d'un paquet
unique. Cela évite les conflits de noms avec d'autres bibliothèques (`audio`, `midi`…)
et simplifie PyInstaller.

## D3 — Capture via sounddevice / PortAudio, WASAPI en priorité
WASAPI offre la latence la plus faible en mode partagé sous Windows. La conversion
automatique de format est activée. En cas de refus, le moteur essaie mono puis stéréo,
puis l'autre fréquence (44,1 ↔ 48 kHz). Latence mesurée sur le micro Realtek : environ 33 ms.

## D4 — Les périphériques sont mémorisés par nom + pilote
Les index PortAudio changent quand on branche un appareil.

## D5 — Détection de voix maison plutôt que WebRTC VAD
Critères : niveau au-dessus du bruit de fond adaptatif, niveau minimum, énergie
concentrée dans 80 Hz – 3 kHz. Hystérésis d'attaque 30 ms et maintien 300 ms.
Aucune dépendance native supplémentaire. Le VAD WebRTC est optimisé pour la parole
téléphonique à 8-16 kHz. Le seuil sera recalibré avec de vrais enregistrements de chant.

## D6 — Réécoute de l'accompagnement par le micro (à traiter en phase 4)
Rien n'est joué pour l'instant, donc pas encore d'écho. Approche prévue, par ordre de priorité :
1. Recommander le casque (le plus fiable).
2. Le moteur connaît exactement ce qu'il joue : la détection de hauteur ignorera les notes
   correspondant aux notes MIDI en cours.
3. Annulation d'écho adaptative (filtre NLMS sur le signal de sortie de référence),
   avec compensation de la latence aller-retour mesurée.

## D6 bis — Réécoute : ce qui est fait (2026-11-02)
- Garde par niveau (`analysis/echo.py`) : le couplage haut-parleur → micro est estimé en continu
  (statistique de minimum sur 8 s). Une trame n'est comptée comme voix que si elle dépasse la fuite attendue de 6 dB.
- Garde par hauteur : une note identique à une note que joue l'orchestre est ignorée.
- Test acoustique réel : sans ces gardes, le piano ne s'arrêtait jamais (il s'entendait lui-même).
  Avec elles, il conclut environ 9 s après la fin du chant.
- Reste à faire : annulation d'écho adaptative. Le casque reste recommandé dans l'interface.

## D9 — Hauteur : YIN maison plutôt que librosa.pyin en temps réel
pYIN (librosa) est excellent mais traite des fichiers entiers et coûte ~1 s pour 60 s de son.
Le YIN vectorisé (`analysis/pitch.py`) coûte 0,08 ms par trame, moins de 5 cents d'erreur sur les signaux de test,
sans erreur d'octave avec une 2e harmonique forte. Le lissage médian et la correction d'octave
compensent l'absence du modèle de Markov de pYIN. librosa reste disponible pour les analyses hors ligne.

## D10 — Diapason personnel et accord de l'orchestre
L'enregistrement réel de l'utilisateur est à +39 cents du La 440. Sans correction, les notes tombent entre
deux demi-tons et la tonalité hésite. Le diapason est estimé (moyenne circulaire) et retranché avant l'arrondi.
À l'entrée de l'accompagnement, piano et basse sont décalés du même écart (pitch bend MIDI, ±2 demi-tons),
comme le ferait un accompagnateur humain. Mesure : décalage demandé = décalage obtenu, à la précision de l'échantillon près.

## D11 — Harmonie sans dépendre de la reconnaissance
L'accord est choisi parmi les 24 accords majeurs/mineurs selon les notes chantées (2,5 s, récent pondéré),
avec un bonus pour les accords de la tonalité, les enchaînements usuels (V→I…) et la continuité.
Une chanson inconnue est donc toujours harmonisée. Les changements ne sont permis qu'aux temps 1 et 3
(jeu rythmé), après au moins 2 temps sur le même accord.

## D12 — Banque de sons FluidR3Mono_GM.sf3
Licence MIT (Frank Wen, Michael Cowgill, S. Christian Collins). Le fichier de licence est fourni à côté.
Point de vigilance : le fichier indique que la licence de la collection MuseScore « pourrait évoluer ».
La version téléchargée le 2026-11-02 est sous MIT. Il faut conserver ce fichier et ses mentions.
Avant commercialisation, faire valider ce point ou passer à FluidR3_GM original (MIT, plus volumineux).

## D7 — Licences des dépendances (vérifiées pour usage commercial)

| Bibliothèque | Licence | Remarque |
|---|---|---|
| NumPy, SciPy | BSD-3 | OK |
| sounddevice | MIT | OK |
| PortAudio | MIT | OK |
| PySide6 / Qt 6 | LGPL v3 | OK en liaison dynamique (cas de PyInstaller en mode dossier). Fournir le texte de licence et permettre le remplacement des DLL Qt. |
| librosa | ISC | OK |
| numba | BSD-2 | OK (dépendance de librosa) |
| soundfile / libsndfile | BSD-3 / LGPL 2.1 | OK en liaison dynamique |
| mido | MIT | OK |
| FluidSynth 2.6.2 | LGPL 2.1 | OK en liaison dynamique (DLL séparée dans `vendor/`) |
| pyfluidsynth 1.4.0 | MIT | OK |
| SDL3, libsndfile (livrées avec FluidSynth) | zlib, LGPL 2.1 | OK en liaison dynamique |
| PyTorch (si utilisé) | BSD-3 | OK, mais lourd : n'ajouter que si un modèle l'exige |
| FAISS (si utilisé) | MIT | Probablement inutile : une bibliothèque de quelques milliers de chansons se compare en NumPy |

Les SoundFonts devront avoir une licence permettant la redistribution commerciale.
Ce point sera vérifié individuellement en phase 4.

## D8 — Avertissement connu
sounddevice 0.5.6 utilise une API NumPy dépréciée en 2.5 (`DeprecationWarning`).
Sans effet fonctionnel. L'avertissement est filtré dans les tests. À surveiller lors des mises à jour.
