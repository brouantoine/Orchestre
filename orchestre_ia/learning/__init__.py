"""Apprentissage (phase 7) : l'orchestre apprend en écoutant de vrais musiciens.

- `listening` : écoute muette d'une séance entière (louange, répétition), par parties WAV ;
- `study` : étude hors ligne (tonalité, tempo, accords par morceau) ;
- `memory` : mémoire SQLite des habitudes d'accords, lue par le moteur harmonique ;
- `evaluation` : part d'accords suivants devinés, règles génériques contre habitudes apprises ;
- `corpus` : grilles d'accords de centaines de milliers de chants (Chordonomicon, MIT),
  a priori que les habitudes de l'équipe corrigent.

Bibliothèque collective avec consentement explicite : pas encore implémentée.
"""
