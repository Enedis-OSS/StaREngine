# controle_coherence_terre.py — Contrôle de cohérence terre

## Description

Vérifie la cohérence entre les éléments de terre (câbles et nœuds).
Ce contrôle est **bloquant** : aucun export ne doit être possible si une anomalie est
détectée.

**Règles** :

- Chaque **câble terre** doit posséder un **identifiant** (champ `id`).
- Chaque **câble terre** doit avoir un `noeudreseau_href` référençant un `id`
  existant dans `RPD_Terre_Reco.geojson`.

## Fonctionnement

1. Chargement des câbles terre (`RPD_CableTerre_Reco.geojson`) et des nœuds terre
   (`RPD_Terre_Reco.geojson`) depuis le répertoire d'entrée.
2. Extraction de l'ensemble des identifiants des nœuds terre.
3. Pour chaque câble terre : vérification que `noeudreseau_href` pointe vers un
   identifiant existant parmi les nœuds terre.
4. Les câbles sans identifiant sont également signalés.

## Constantes

| Constante              | Valeur                        | Description                    |
| ---------------------- | ----------------------------- | ------------------------------ |
| `FICHIER_CABLES_TERRE` | `RPD_CableTerre_Reco.geojson` | Fichier source des câbles terre |
| `FICHIER_NOEUDS_TERRE` | `RPD_Terre_Reco.geojson`      | Fichier source des nœuds terre  |

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
- `ecarts_coherence_terre.geojson` — GeoJSON FeatureCollection des anomalies

Le champ `bloquant` du rapport vaut `true` dès qu'au moins une anomalie est présente.

### Utilisation en tant que bibliothèque

```python
from controle_coherence_terre import controler_coherence_terre, executer_controle_cli

# Logique métier seule
anomalies = controler_coherence_terre(features_cables, ids_noeuds)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```
