# controle_proj.py — Contrôle des projections

## Description

Vérifie que le système de référence de coordonnées (CRS) déclaré dans chaque
fichier GeoJSON d'un répertoire appartient à la liste des projections
autorisées. Les entités issues de fichiers dont la projection est absente ou
non conforme sont exportées dans un fichier GeoJSON d'écarts.

**Règles** :

- Tous les fichiers `.geojson` du répertoire sont analysés (sauf ceux
  préfixés par `ecarts_`).
- Pour chaque fichier, le champ `crs.properties.name` est lu et interprété.
- Le code EPSG est extrait depuis le format URN OGC
  (`urn:ogc:def:crs:EPSG::<code>`) ou le format court (`EPSG:<code>`).
- Si le code EPSG n'appartient pas à la liste des projections autorisées,
  **toutes les entités** du fichier sont signalées comme non conformes.
- Si le CRS est absent, mal formé ou non interprétable, le fichier est
  également signalé comme non conforme.
- Les anomalies de projection sont de priorité **bloquante**.

## Projections autorisées

| Code EPSG   | Alias            |
| ----------- | ---------------- |
| EPSG:3942   | CC42             |
| EPSG:3943   | CC43             |
| EPSG:3944   | CC44             |
| EPSG:3945   | CC45             |
| EPSG:3946   | CC46             |
| EPSG:3947   | CC47             |
| EPSG:3948   | CC48             |
| EPSG:3949   | CC49             |
| EPSG:3950   | CC50             |
| EPSG:9842   | CC42 V2b         |
| EPSG:9843   | CC43 V2b         |
| EPSG:9844   | CC44 V2b         |
| EPSG:9845   | CC45 V2b         |
| EPSG:9846   | CC46 V2b         |
| EPSG:9847   | CC47 V2b         |
| EPSG:9848   | CC48 V2b         |
| EPSG:9849   | CC49 V2b         |
| EPSG:9850   | CC50 V2b         |
| EPSG:2154   | RGF93LAMB93      |
| EPSG:9794   | RGF93LAMB93 V2b  |
| EPSG:5490   | RGAF09UTM20      |
| EPSG:2972   | RGFG95UTM22      |
| EPSG:2975   | RGR92UTM40S      |
| EPSG:4471   | RGM04UTM38S      |
| EPSG:4467   | RGSPM06U21       |

## Fonctionnement

### 1. Listing des fichiers

Le répertoire d'entrée est parcouru. Seuls les fichiers `.geojson` sont
retenus. Les fichiers dont le nom commence par `ecarts_` sont exclus pour
éviter l'analyse des sorties de contrôles précédents.

### 2. Extraction et vérification du CRS

Pour chaque fichier GeoJSON :

1. Le champ `crs.properties.name` est lu.
2. Le code EPSG est extrait via une expression régulière (formats URN OGC
   et court supportés).
3. Le code est vérifié par lookup en O(1) dans l'ensemble des projections
   autorisées.

### 3. Construction du GeoJSON d'écarts

Si un fichier est non conforme, toutes ses entités sont collectées et
exportées dans le fichier d'écarts avec les métadonnées de contrôle
(fichier source, CRS détecté, type d'anomalie, priorité).

## Paramètres

| Constante                | Valeur                    | Description                               |
| ------------------------ | ------------------------- | ----------------------------------------- |
| `FICHIER_SORTIE`         | `ecarts_proj.geojson`     | Nom du fichier de sortie                  |
| `PRIORITE_ANOMALIE`      | `bloquant`                | Niveau de priorité des anomalies          |
| `PREFIXES_ECARTS`        | `ecarts_`, `ecart_`       | Préfixes des fichiers exclus de l'analyse |
| `PROJECTIONS_AUTORISEES` | dictionnaire (26 entrées) | Codes EPSG autorisés et alias             |

## Ligne de commande

```bash
python controle_proj.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant les fichiers GeoJSON à analyser    |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `ecarts_proj.geojson` — FeatureCollection contenant les entités issues de
  fichiers dont la projection n'est pas conforme, avec les propriétés
  suivantes :

| Propriété        | Description                                              |
| ---------------- | -------------------------------------------------------- |
| `fichier_source` | Nom du fichier GeoJSON d'origine                         |
| `id_entite`      | Identifiant métier de l'entité                           |
| `crs_detecte`    | Valeur brute du CRS trouvé (ou `absent`)                 |
| `type_anomalie`  | `projection_non_conforme`                                |
| `priorite`       | Niveau de priorité de l'anomalie (`bloquant`)            |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "fichiers_analyses": 17,
  "fichiers_conformes": 17,
  "fichiers_non_conformes": 0,
  "nombre_anomalies": 0,
  "sortie": "…/ecarts_proj.geojson",
  "detail": [
    {
      "fichier": "RPD_Aerien_Reco.geojson",
      "conforme": true,
      "code_epsg": 2154,
      "alias": "RGF93LAMB93",
      "message": "Projection conforme : EPSG:2154 (RGF93LAMB93)"
    }
  ]
}
```

## Utilisation en tant que bibliothèque

```python
from controle_proj import (
    extraire_code_epsg,
    est_projection_autorisee,
    controler_projection_fichier,
    construire_geojson_ecarts,
    executer_controle_cli,
    lister_fichiers_geojson,
)

# Extraction du code EPSG d'une collection
code = extraire_code_epsg(collection)

# Vérification d'un code EPSG
conforme = est_projection_autorisee(2154)

# Contrôle d'un fichier individuel
resultat = controler_projection_fichier(collection, "source.geojson")

# Sérialisation GeoJSON des écarts
geojson = construire_geojson_ecarts(anomalies)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_proj.py` (même répertoire
que le script). Ils couvrent :

- Extraction du code EPSG depuis les formats URN OGC et court.
- Gestion du CRS absent, mal formé ou non interprétable.
- Vérification d'appartenance pour les 26 codes EPSG autorisés.
- Contrôle de projection par fichier (conforme et non conforme).
- Extraction de l'identifiant métier.
- Listing et filtrage des fichiers GeoJSON.
- Structure du GeoJSON d'écarts.
- Priorité `bloquant` dans les écarts.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_proj.py -v
```
