# controle_plor_cable.py — Contrôle de superposition PLOR / câbles

## Description

Vérifie que chaque entité du fichier `RPD_PointLeveOuvrageReseau_Reco.geojson`
se superpose exactement (X, Y, Z) à au moins un sommet des entités présentes
dans `RPD_CableElectrique_Reco.geojson`.

Les points non conformes sont exportés dans un fichier GeoJSON d'écarts.

**Règles** :

- Les coordonnées sont comparées sur les trois axes X, Y et Z.
- La superposition doit être exacte (aucune tolérance).
- Seuls les points 3D (possédant une composante Z) sont analysés.
- Les points 2D ou sans géométrie sont ignorés.
- Seules les géométries `Point` (PLOR) et `LineString` (câbles) sont traitées.
- Le contrôle est **bloquant** (`priorite = "bloquant"`).

## Fonctionnement

### 1. Chargement des données

Les deux fichiers GeoJSON sont chargés depuis le répertoire d'entrée :

- `RPD_PointLeveOuvrageReseau_Reco.geojson` — points levés d'ouvrage réseau
- `RPD_CableElectrique_Reco.geojson` — câbles électriques

### 2. Indexation des sommets de câbles

Tous les sommets 3D (X, Y, Z) des géométries `LineString` des câbles sont
extraits et stockés dans un `set` de tuples pour garantir un test
d'appartenance en O(1).

### 3. Détection des écarts

Pour chaque point PLOR :

1. La géométrie `Point` est extraite.
2. Les coordonnées (X, Y, Z) sont comparées à l'ensemble des sommets de câbles.
3. Si le point ne correspond à aucun sommet, il est marqué comme anomalie.

### 4. Construction du GeoJSON d'écarts

Les points en anomalie sont exportés en tant que `Point` avec leurs
métadonnées (identifiant de l'entité, type d'anomalie, priorité).

## Paramètres

| Constante           | Valeur                                      | Description                             |
| ------------------- | ------------------------------------------- | --------------------------------------- |
| `FICHIER_PLOR`      | `RPD_PointLeveOuvrageReseau_Reco.geojson`   | Fichier des points levés                |
| `FICHIER_CABLES`    | `RPD_CableElectrique_Reco.geojson`          | Fichier des câbles électriques          |
| `FICHIER_SORTIE`    | `ecarts_plor_cable.geojson`                 | Nom du fichier de sortie                |
| `PRIORITE_ANOMALIE` | `bloquant`                                  | Niveau de priorité des anomalies        |

## Ligne de commande

```bash
python controle_plor_cable.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant les fichiers GeoJSON à analyser    |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `ecarts_plor_cable.geojson` — FeatureCollection de points représentant les
  points PLOR en écart, avec les propriétés suivantes :

| Propriété        | Description                                            |
| ---------------- | ------------------------------------------------------ |
| `id_entite`      | Identifiant métier de l'entité PLOR                    |
| `type_anomalie`  | `point_hors_cable`                                     |
| `priorite`       | Niveau de priorité de l'anomalie (`bloquant`)          |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "nombre_points_plor": 437,
  "nombre_sommets_cables": 1024,
  "nombre_anomalies": 12,
  "sortie": "…/ecarts_plor_cable.geojson"
}
```

## Utilisation en tant que bibliothèque

```python
from controle_plor_cable import (
    extraire_sommets_cables,
    detecter_points_hors_cables,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Indexation des sommets de câbles
sommets = extraire_sommets_cables(features_cables)

# Détection des points hors câbles
anomalies = detecter_points_hors_cables(features_plor, sommets)

# Sérialisation GeoJSON
geojson = construire_geojson_ecarts(anomalies)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_plor_cable.py` (même
répertoire que le script). Ils couvrent :

- Extraction des sommets 3D pour un ou plusieurs câbles.
- Détection des points hors câbles et non-détection des points conformes.
- Vérification de l'écart sur chaque axe (X, Y, Z) individuellement.
- Gestion des géométries absentes, 2D ou de type non supporté.
- Structure et contenu du GeoJSON de sortie.
- Priorité bloquante dans les propriétés de sortie.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_plor_cable.py -v
```
