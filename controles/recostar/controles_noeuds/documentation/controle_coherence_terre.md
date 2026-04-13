# controle_coherence_terre.py — Contrôle de cohérence terre

## Description

Vérifie la cohérence entre les éléments de terre (nœuds et câbles).
Ce contrôle est **bloquant** : aucun export ne doit être possible si une anomalie est
détectée.

**Règles** :

- Chaque **nœud terre** doit être lié à au moins un **câble terre** (via `cables_href`
  et proximité géométrique).
- Chaque **câble terre** doit être référencé par au moins un **nœud terre** proche
  d'une de ses extrémités.

## Fonctionnement

1. Chargement des câbles terre (`RPD_CableTerre_Reco.geojson`) et des nœuds terre
   (`RPD_Terre_Reco.geojson`) depuis le répertoire d'entrée.
2. Pour chaque nœud terre : vérification qu'au moins un câble terre référencé dans
   `cables_href` possède une extrémité à proximité (≤ seuil de distance).
3. Pour chaque câble terre : vérification qu'au moins un nœud terre le référence
   dans son `cables_href` et se situe à proximité d'une de ses extrémités.
4. Si aucun élément terre n'existe (0 câble et 0 nœud), le contrôle passe sans anomalie.

## Constantes

| Constante              | Valeur                          | Description                                      |
| ---------------------- | ------------------------------- | ------------------------------------------------ |
| `SEUIL_DISTANCE`       | 0.5 m (défini dans utilitaires) | Distance max pour considérer un lien géométrique |
| `FICHIER_CABLES_TERRE` | `RPD_CableTerre_Reco.geojson`   | Fichier source des câbles terre                  |
| `FICHIER_NOEUDS_TERRE` | `RPD_Terre_Reco.geojson`        | Fichier source des nœuds terre                   |

## Ligne de commande

```bash
python controle_coherence_terre.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                                                    |
| -------------- | ----------- | ------------------------------------------------------------------------------ |
| `--repertoire` | Oui         | Répertoire contenant `RPD_CableTerre_Reco.geojson` et `RPD_Terre_Reco.geojson` |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`)                        |

### Sorties

- `rapport_controle_coherence_terre.json` — rapport JSON synthétique du contrôle
- `ecarts_coherence_terre.geojson` — GeoJSON FeatureCollection des entités en anomalie

Le champ `bloquant` du rapport vaut `true` dès qu'au moins une anomalie est présente.

### Utilisation en tant que bibliothèque

```python
from controle_coherence_terre import controler_coherence_terre, executer_controle_cli

# Logique métier seule
anomalies = controler_coherence_terre(features_cables, features_noeuds)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```
