# controle_3d.py — Contrôle de conformité 3D

## Description

Vérifie que toutes les entités géométriques des fichiers GeoJSON d'un
répertoire possèdent des coordonnées 3D (X, Y, Z). Les entités ne disposant
pas de composante Z sont exportées dans un fichier GeoJSON d'écarts.

**Règles** :

- Tous les fichiers `.geojson` du répertoire sont analysés (sauf ceux
  préfixés par `ecarts_`).
- Pour chaque entité, tous les points de la géométrie sont inspectés.
- Si **au moins un point** ne possède pas de composante Z, l'entité est
  signalée comme non conforme.
- Les géométries nulles (`null`) sont ignorées (rien à signaler).
- Les types de géométrie supportés : `Point`, `LineString`, `Polygon`,
  `MultiPoint`, `MultiLineString`, `MultiPolygon`.

## Fonctionnement

### 1. Listing des fichiers

Le répertoire d'entrée est parcouru. Seuls les fichiers `.geojson` sont
retenus. Les fichiers dont le nom commence par `ecarts_` sont exclus pour
éviter l'analyse des sorties de contrôles précédents.

### 2. Analyse de chaque entité

Pour chaque feature GeoJSON :

1. La géométrie est extraite.
2. Tous les points sont récupérés (aplatissement des structures multi).
3. Si un point possède moins de 3 composantes, l'entité est marquée non
   conforme.

### 3. Construction du GeoJSON d'écarts

Les entités non conformes sont exportées avec leur géométrie originale et
des propriétés descriptives permettant le diagnostic.

## Paramètres

| Constante            | Valeur               | Description                              |
| -------------------- | -------------------- | ---------------------------------------- |
| `FICHIER_SORTIE`     | `ecarts_3d.geojson`  | Nom du fichier de sortie                 |
| `PRIORITE_ANOMALIE`  | `information`        | Niveau de priorité des anomalies         |
| `PREFIXE_ECARTS`     | `ecarts_`            | Préfixe des fichiers exclus de l'analyse |

## Ligne de commande

```bash
python controle_3d.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant les fichiers GeoJSON à analyser    |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `ecarts_3d.geojson` — FeatureCollection contenant les entités non conformes,
  avec les propriétés suivantes :

| Propriété        | Description                                          |
| ---------------- | ---------------------------------------------------- |
| `fichier_source` | Nom du fichier GeoJSON d'origine                     |
| `id_entite`      | Identifiant métier de l'entité                       |
| `type_geometrie` | Type de géométrie (`Point`, `LineString`, etc.)      |
| `type_anomalie`  | `absence_coordonnee_z`                               |
| `priorite`       | Niveau de priorité de l'anomalie (`information`)     |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "nombre_anomalies": 3,
  "fichiers_analyses": 17,
  "sortie": "…/ecarts_3d.geojson"
}
```

## Utilisation en tant que bibliothèque

```python
from controle_3d import (
    detecter_entites_2d,
    construire_geojson_ecarts,
    executer_controle_cli,
    lister_fichiers_geojson,
)

# Détection sur une collection de features
anomalies = detecter_entites_2d(features, "source.geojson")

# Sérialisation GeoJSON
geojson = construire_geojson_ecarts(anomalies)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_3d.py` (même répertoire
que le script). Ils couvrent :

- Extraction des points pour chaque type de géométrie.
- Détection correcte des entités 2D et 3D.
- Gestion des géométries nulles ou vides.
- Exclusion des fichiers d'écarts.
- Structure du GeoJSON de sortie.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_3d.py -v
```
