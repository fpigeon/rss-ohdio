# Flux RSS OHdio pour Pocket Casts

Flux RSS personnalisés pour trois émissions de Radio-Canada OHdio, dont le flux officiel ne reprend qu'une sélection hebdomadaire. L'audio pointe directement vers les serveurs de Radio-Canada, rien n'est recopié.

| Émission | Flux à ajouter dans Pocket Casts |
| --- | --- |
| La journée (est encore jeune) | https://raw.githubusercontent.com/fpigeon/rss-ohdio/main/la-journee.xml |
| L'histoire (est encore jeune) | https://raw.githubusercontent.com/fpigeon/rss-ohdio/main/lhistoire.xml |
| Hors des ondes avec Patrice Roy | https://raw.githubusercontent.com/fpigeon/rss-ohdio/main/hors-des-ondes.xml |

Dans Pocket Casts : onglet **Podcasts → + → Ajouter par URL**, puis coller l'adresse du flux.

## Mise à jour automatique

Les flux sont régénérés chaque jour par GitHub Actions (`.github/workflows/update-feeds.yml`, 21 h UTC, soit 16 h heure de l'Est en hiver) à partir des scripts Python dans `scripts/`. Aucune intervention manuelle n'est requise : les nouveaux épisodes apparaissent automatiquement dans Pocket Casts. On peut aussi lancer une mise à jour manuellement depuis l'onglet **Actions** du dépôt.
