# controle_proj_ensemble.py — Contrôle de cohérence des projections

## Description

Vérifie que tous les fichiers GeoJSON d'un répertoire partagent le même
système de référence de coordonnées (CRS). Le CRS de référence est déterminé
par **vote majoritaire** parmi les fichiers analysés. Les entités issues de
fichiers dont le CRS diffère du CRS de référence sont exportées dans un
fichier GeoJSON d'écarts.

**Règles** :

- Tous les fichiers `.geojson` du répertoire sont analysés (sauf ceux
  préfixés par `ecarts_`).
- Le code EPSG de chaque fichier est extrait depuis le champ
  `crs.properties.name` (formats URN OGC et court supportés).
- Le CRS de référence est le code EPSG le plus fréquent parmi les fichiers
  (les fichiers sans CRS ne participent pas au vote).
- Si **tous** les fichiers ont un CRS absent, ils sont considérés comme
  cohérents entre eux (référence = `absent`).
- Tout fichier dont le CRS diffère du CRS de référence est signalé :
  **toutes ses entités** sont exportées dans le fichier d'écarts.
- Les anomalies de cohérence sont de priorité **bloquante**.

## Fonctionnement

### 1. Listing des fichiers

Le répertoire d'entrée est parcouru. Seuls les fichiers `.geojson` sont
retenus. Les fichiers dont le nom commence par `ecarts_` sont exclus pour
éviter l'analyse des sorties de contrôles précédents.

### 2. Extraction des CRS

Pour chaque fichier GeoJSON, le code EPSG est extrait. Les fonctions
d'extraction sont réutilisées depuis `controle_proj.py` (pas de
duplication).

### 3. Détermination du CRS de référence

Le CRS de référence est déterminé par vote majoritaire via
`collections.Counter`. Seuls les codes EPSG valides participent au vote.

### 4. Identification des fichiers en écart

Chaque fichier dont le code EPSG diffère du CRS de référence est signalé.
Toutes ses entités sont collectées et exportées dans le fichier d'écarts
avec les métadonnées de contrôle.

## Paramètres

| Constante           | Valeur                          | Description                              |
| ------------------- | ------------------------------- | ---------------------------------------- |
| `FICHIER_SORTIE`    | `ecart_proj_ensemble.geojson`   | Nom du fichier de sortie                 |
| `PRIORITE_ANOMALIE` | `bloquant`                      | Niveau de priorité des anomalies         |

## Ligne de commande

```bash
python controle_proj_ensemble.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant les fichiers GeoJSON à analyser    |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `ecart_proj_ensemble.geojson` — FeatureCollection contenant les entités
  issues de fichiers dont le CRS diffère du CRS de référence, avec les
  propriétés suivantes :

| Propriété        | Description                                              |
| ---------------- | -------------------------------------------------------- |
| `fichier_source` | Nom du fichier GeoJSON d'origine                         |
| `id_entite`      | Identifiant métier de l'entité                           |
| `crs_detecte`    | Valeur brute du CRS trouvé dans le fichier (ou `absent`) |
| `crs_reference`  | CRS de référence déterminé par vote majoritaire          |
| `type_anomalie`  | `projection_incoherente`                                 |
| `priorite`       | Niveau de priorité de l'anomalie (`bloquant`)            |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "fichiers_analyses": 17,
  "fichiers_conformes": 17,
  "fichiers_non_conformes": 0,
  "nombre_anomalies": 0,
  "crs_reference": "EPSG:2154",
  "sortie": "…/ecart_proj_ensemble.geojson",
  "detail": [
    {
      "fichier": "RPD_Aerien_Reco.geojson",
      "conforme": true,
      "code_epsg": 2154,
      "crs_brut": "urn:ogc:def:crs:EPSG::2154"
    }
  ]
}
```

## Réutilisation de code

Ce script importe les fonctions suivantes depuis `controle_proj.py` pour
éviter la duplication :

| Fonction                  | Rôle                                            |
| ------------------------- | ----------------------------------------------- |
| `lire_geojson`            | Chargement d'un fichier GeoJSON                 |
| `lister_fichiers_geojson` | Listing et filtrage des fichiers `.geojson`     |
| `extraire_code_epsg`      | Extraction du code EPSG depuis le CRS           |
| `_extraire_nom_crs_brut`  | Récupération de la valeur brute du CRS          |
| `_obtenir_id_feature`     | Extraction de l'identifiant métier              |

## Utilisation en tant que bibliothèque

```python
from controle_proj_ensemble import (
    determiner_crs_reference,
    formater_crs_reference,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Détermination du CRS majoritaire
codes = {"a.geojson": 2154, "b.geojson": 2154, "c.geojson": 3946}
reference = determiner_crs_reference(codes)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_proj_ensemble.py` (même
répertoire que le script). Ils couvrent :

- Vote majoritaire : tous identiques, majorité simple, fichier unique.
- Exclusion des codes `None` du vote.
- Détection des fichiers dont le CRS diffère de la référence.
- Gestion du CRS absent dans un ou plusieurs fichiers.
- Cas où tous les CRS sont absents (cohérence par défaut).
- Formatage du CRS de référence.
- Structure et propriétés du GeoJSON d'écarts.
- Priorité `bloquant` dans les écarts.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_proj_ensemble.py -v
```
