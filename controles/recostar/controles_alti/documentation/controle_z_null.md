# controle_z_null.py — Contrôle des coordonnées Z nulles

## Description

Détecte les sommets dont l'altitude est exactement égale à `0.0` dans
l'ensemble des fichiers GeoJSON d'un répertoire. Chaque sommet concerné est
exporté sous forme de point dans un fichier GeoJSON d'écarts.

Les entités sans géométrie ou en 2D (sans composante Z) sont ignorées :
seuls les sommets 3D portant une valeur `Z = 0.0` sont signalés.

**Règles** :

- Tous les fichiers `.geojson` du répertoire sont analysés (sauf ceux
  préfixés par `ecarts_`).
- Pour chaque entité, tous les sommets 3D de la géométrie sont inspectés.
- Si un sommet possède une composante Z exactement égale à `0.0`, il est
  signalé comme anomalie.
- Les sommets 2D (sans composante Z) sont ignorés (relevant du contrôle 3D).
- Les géométries nulles (`null`) sont ignorées.
- Types de géométrie supportés : `Point`, `LineString`, `Polygon`,
  `MultiPoint`, `MultiLineString`, `MultiPolygon`.

## Fonctionnement

### 1. Listing des fichiers

Le répertoire d'entrée est parcouru. Seuls les fichiers `.geojson` sont
retenus. Les fichiers dont le nom commence par `ecarts_` sont exclus pour
éviter l'analyse des sorties de contrôles précédents.

### 2. Analyse de chaque entité

Pour chaque feature GeoJSON :

1. La géométrie est extraite.
2. Tous les sommets sont récupérés avec leur indice séquentiel.
3. Si un sommet possède 3 composantes et que `Z == 0.0`, il est marqué
   comme anomalie.

### 3. Construction du GeoJSON d'écarts

Les sommets en anomalie sont exportés en tant que `Point` avec les
métadonnées de localisation (fichier source, identifiant de l'entité,
indice du sommet dans la géométrie).

## Paramètres

| Constante            | Valeur                  | Description                              |
| -------------------- | ----------------------- | ---------------------------------------- |
| `FICHIER_SORTIE`     | `ecarts_z_null.geojson` | Nom du fichier de sortie                 |
| `PRIORITE_ANOMALIE`  | `information`           | Niveau de priorité des anomalies         |
| `PREFIXE_ECARTS`     | `ecarts_`               | Préfixe des fichiers exclus de l'analyse |
| `Z_NULL`             | `0.0`                   | Valeur Z considérée comme nulle          |

## Ligne de commande

```bash
python controle_z_null.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant les fichiers GeoJSON à analyser    |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `ecarts_z_null.geojson` — FeatureCollection de points représentant les
  sommets en anomalie, avec les propriétés suivantes :

| Propriété        | Description                                            |
| ---------------- | ------------------------------------------------------ |
| `fichier_source` | Nom du fichier GeoJSON d'origine                       |
| `id_entite`      | Identifiant métier de l'entité                         |
| `type_geometrie` | Type de géométrie (`Point`, `LineString`, etc.)        |
| `indice_sommet`  | Indice du sommet dans la géométrie                     |
| `z_detecte`      | Valeur Z détectée (`0.0`)                              |
| `type_anomalie`  | `z_null`                                               |
| `priorite`       | Niveau de priorité de l'anomalie (`information`)       |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "nombre_anomalies": 38,
  "fichiers_analyses": 17,
  "sortie": "…/ecarts_z_null.geojson"
}
```

## Utilisation en tant que bibliothèque

```python
from controle_z_null import (
    detecter_z_null_feature,
    detecter_z_null_collection,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Détection sur une feature individuelle
anomalies = detecter_z_null_feature(feature, "source.geojson")

# Détection sur une collection
anomalies = detecter_z_null_collection(features, "source.geojson")

# Sérialisation GeoJSON
geojson = construire_geojson_ecarts(anomalies)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_z_null.py` (même
répertoire que le script). Ils couvrent :

- Extraction indexée des points pour chaque type de géométrie.
- Détection des sommets Z nul et non-détection des sommets conformes.
- Non-détection des sommets 2D (sans composante Z).
- Gestion des géométries nulles ou vides.
- Exclusion des fichiers d'écarts.
- Structure du GeoJSON de sortie.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_z_null.py -v
```
