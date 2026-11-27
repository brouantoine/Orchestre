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
| PyAV 19.0.2 (FFmpeg intégré) | BSD-3 / LGPL 2.1 | OK en liaison dynamique ; sert à lire m4a, webm, opus, aac pour l'étude de chants |

Les SoundFonts devront avoir une licence permettant la redistribution commerciale.
Ce point sera vérifié individuellement en phase 4.

## D8 — Avertissement connu
sounddevice 0.5.6 utilise une API NumPy dépréciée en 2.5 (`DeprecationWarning`).
Sans effet fonctionnel. L'avertissement est filtré dans les tests. À surveiller lors des mises à jour.

## D13 — Apprentissage : écoutes de louange et bibliothèque de chants (2026-11-08)
- Écoute muette (`--learn-listen`) : aucun son joué, pas de filtre passe-haut (la basse porte l'harmonie),
  WAV par parties de 5 min avec entête mis à jour toutes les 2 s, veille Windows bloquée.
- Étude hors ligne : HPSS, temps forts, chroma CQT et chroma de basse par temps ; accords par Viterbi
  (24 accords + aucun), seconde passe qui avantage les accords de la tonalité locale (+0,06) ; tonalité
  d'un morceau = rôle des accords + profil de Krumhansl. Bruit écarté par la platitude du chroma.
- Mémoire : accords relatifs à la tonalité (« IV », « bVII »), compteurs par source (séance ou chant),
  réétude = remplacement. Confiance pleine après 500 changements d'accord : à 200, une séance inédite
  était moins bien devinée que par les règles génériques (mesure sur 3 séances réelles).
- Bibliothèque de chants (`--learn-library`) : un chant par fichier, empreinte du contenu (reprise,
  doublons), plusieurs processus. Seuls tonalité, tempo et suite d'accords sont conservés, jamais le son.
  Les fichiers doivent provenir de sources dont l'utilisateur a le droit de se servir : les conditions de
  YouTube interdisent le téléchargement sans autorisation de l'ayant droit.
- Limite assumée : la mémoire apprend des habitudes (quel accord suit souvent), pas la grille exacte d'un
  chant. Jouer la grille exacte demandera de reconnaître le chant chanté (phase 6).

## D14 — Corpus de grilles d'accords plutôt que téléchargement YouTube (2026-11-24)
- Objectif : apprendre sur des centaines de milliers de chants. Télécharger YouTube en masse est exclu
  (conditions d'utilisation, droits d'auteur, modèle invendable) et inutile : la mémoire ne garde que
  tonalité, tempo et accords, et l'étude audio coûte ≈ 30 s par chant (≈ 1 an de calcul pour un million).
- Source retenue : Chordonomicon (Kantarelis et al., 2024, arXiv 2410.22046), licence MIT sur Hugging Face,
  ≈ 680 000 grilles avec sections et genres Spotify, dont ≈ 35 000 de louange (worship, christian, ccm, gospel).
  Les auteurs considèrent les suites d'accords comme non protégeables ; c'est leur position, pas un avis juridique.
- Accords : 's' = dièse, 'b' = bémol, basse ignorée, 'Csus4' = Do ; no3d, dim et aug coupent la grille
  (comme « pas d'accord » dans l'étude audio). Une tonalité par chant, par le rôle des accords (même table que D13).
- Stockage séparé (`corpus.sqlite`) : versé dans `memoire.sqlite`, le corpus noierait les habitudes de l'équipe.
  Il sert d'a priori : P(suivant | accord) = (n_équipe + 30 · P_corpus) / (total_équipe + 30), donc
  l'équipe l'emporte après une trentaine d'enchaînements entendus depuis un accord donné.
- Mesure (50 000 premiers chants, un sur 20 tenu à part), accord suivant 1er choix / parmi 3 :
  louange 35 % / 81 % (règles génériques) → 41 % / 83 % (corpus) ; pop 31 % / 73 % → 35 % / 78 %.
  Le moteur atteint déjà le plafond d'une mémoire à un accord (40 %) ; avec les deux derniers accords : 47 %.
- Lakh MIDI (CC-BY 4.0) contient des œuvres protégées : réservé à un usage interne si on l'ajoute.

## D15 — Deux derniers accords et mémoire du chant en cours (2026-11-26)
- Contexte à deux accords (table `contexts`) : P(suivant | avant-dernier, actuel), lissée vers l'enchaînement
  simple. Avec le corpus, seule la part du corpus est remplacée par sa version en contexte : les comptes de
  l'équipe ne sont jamais réduits (une première formule multiplicative effaçait une habitude d'équipe que le
  corpus jugeait rare dans ce contexte ; un test le vérifie).
- Mémoire du chant en cours (`HarmonyEngine.remember`), indépendante de la tonalité, oubliée à `reset()` :
  interpolation à deux niveaux (accord actuel, deux derniers accords), poids n / (n + 1) après n observations.
- Mesure, accord suivant 1er choix sur chants tenus à part : louange 36 % (règles) → 41 % (corpus) → 46 %
  (deux accords) → 72 % (chant en cours, mesure séparée sur 60 000 chants) ; parmi 3 : 95 %.
- Limite : en direct, la mémoire du chant retient les choix de l'orchestre, pas la vérité ; une erreur peut
  s'entretenir. Les notes chantées gardent le dernier mot (le bonus reste ≤ 0,25 face à l'adéquation au chant).
  À juger à l'oreille.
- Évaluation : les « règles génériques » n'ont aucune mémoire ; « appris + chant en cours » = ce que joue l'application.

## D16 — Main droite mélodique et verrouillage de grille (2026-11-27)
- Demande de l'utilisateur après un essai : « je n'entends que les accords » et « une fois la progression trouvée,
  il doit maintenir la cadence et ne s'adapter que si le chant change ». L'essai était en jeu libre (tempo non
  détecté) : le piano n'y tient que des accords arpégés.
- Main droite (`instruments/melody.py`, canal MIDI 2, curseur de volume) : registre Do5–Sol6 au-dessus de la voix,
  un motif par phrase de 4 mesures (pas de gamme autour d'une note de l'accord, temps forts sur l'accord), varié
  d'une phrase à l'autre ; discrète pendant le chant (réponse en fin de mesure, une mesure sur deux), motif entier
  et relance descendante pendant les respirations ; cellules rythmiques par style. Jeu libre : ornement au changement.
- Grille (`conductor/lock.py`, jeu rythmé seulement) : verrouillée quand une suite de 2 à 8 accords revient avec les
  mêmes durées (dès le dernier accord du 2e tour) ; vérifiée à chaque point de décision chanté sur l'adéquation au
  chant seule (sans bonus de contexte, qui favoriseraient l'accord prévu), en comparant à l'accord prévu au temps
  précédent (les notes entendues l'accompagnaient) ; lâchée après 2 contradictions (écart > 0,3) ; reprise après
  2 accords reconnus si elle revient ; oubliée si lâchée avant 4 vérifications réussies (erreur d'écoute).
- Recalage : un changement chanté est entendu au point de décision suivant (2 temps plus tard, mesuré sur la démo) ;
  la grille verrouillée est avancée de 2 temps quand les changements repérés sont réguliers.
- Essai rejeté : écouter seulement les 2 derniers temps (au lieu de 2,5 lissés) ajoutait des accords à mi-mesure.
- Démo synthétique (refrain ×3, pont ×2, refrain ×3) : grille verrouillée au 3e tour, lâchée au début du pont.
  La reconnaissance lit cette mélodie en La mineur et la grille retenue en hérite : à juger sur de vrais chants.
