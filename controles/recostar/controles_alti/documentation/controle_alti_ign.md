# controle_alti_ign.py — Contrôle altimétrique via l'API IGN

## Description

Compare les altitudes Z des sommets du fichier
`RPD_GeometrieSupplementaire_Reco.geojson` avec les altitudes de référence
fournies par l'API altimétrique de l'IGN. Les sommets dont l'écart dépasse
le seuil de **40 cm** sont signalés et exportés dans un fichier GeoJSON
d'écarts.

Les coordonnées du projet sont en Lambert 93 (EPSG:2154). La conversion
vers WGS84 est effectuée en interne avant chaque appel à l'API IGN.

**Règles** :

- Seul le fichier `RPD_GeometrieSupplementaire_Reco.geojson` est analysé.
- Pour chaque entité, tous les sommets 3D sont extraits et comparés.
- Si l'**écart absolu** entre l'altitude GeoJSON et l'altitude IGN est
  supérieur ou égal à `0.40 m`, le sommet est signalé.
- Les sommets 2D (sans composante Z) sont ignorés.
- Les géométries nulles sont ignorées.

## Fonctionnement

### 1. Chargement des données

Lecture de `RPD_GeometrieSupplementaire_Reco.geojson`. Si le fichier est
absent ou vide, le contrôle retourne une erreur.

### 2. Extraction des sommets

Tous les sommets 3D sont extraits avec leurs métadonnées (identifiant,
type de géométrie, indice). Les types supportés sont : `Point`,
`LineString`, `Polygon`, `MultiPoint`, `MultiLineString`, `MultiPolygon`.

### 3. Conversion Lambert 93 → WGS84

Les coordonnées sont converties vers WGS84 (lon, lat) pour interroger
l'API IGN. La conversion utilise une méthode itérative basée sur la
projection conique conforme, avec constantes pré-calculées au chargement.

### 4. Interrogation de l'API IGN

L'API est interrogée par lots de 5000 points maximum. Deux sources sont
essayées en cascade :

1. **LIDAR HD IGN** (`ign_lidar_hd_mnt_mono_wld`) — prioritaire
2. **RGE Alti IGN** (`ign_rge_alti_wld`) — fallback

Si la première source échoue, la seconde est automatiquement utilisée.

### 5. Comparaison des altitudes

Pour chaque sommet, l'écart absolu entre Z GeoJSON et Z IGN est calculé.
Si l'écart est ≥ 0.40 m, le sommet est marqué en anomalie.

## Paramètres

| Constante              | Valeur                             | Description                          |
| ---------------------- | ---------------------------------- | ------------------------------------ |
| `FICHIER_SOURCE`       | `RPD_GeometrieSupplementaire_Reco` | Fichier analysé                      |
| `FICHIER_SORTIE`       | `ecarts_z_ign.geojson`             | Fichier de sortie                    |
| `SEUIL_ECART`          | `0.40`                             | Seuil d'écart en mètres              |
| `PRIORITE_ANOMALIE`    | `information`                      | Priorité des anomalies               |
| `MAX_POINTS`           | `5000`                             | Points max par appel API             |

## Ligne de commande

```bash
python controle_alti_ign.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant le fichier source GeoJSON          |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `ecarts_z_ign.geojson` — FeatureCollection de points représentant les
  sommets en écart, avec les propriétés suivantes :

| Propriété            | Description                                       |
| -------------------- | ------------------------------------------------- |
| `id_entite`          | Identifiant métier de l'entité                    |
| `type_geometrie`     | Type de géométrie source                          |
| `indice_sommet`      | Indice du sommet dans la géométrie                |
| `altitude_geojson_m` | Altitude Z du GeoJSON (mètres)                    |
| `altitude_ign_m`     | Altitude Z IGN de référence (mètres)              |
| `ecart_m`            | Écart absolu entre les deux altitudes (mètres)    |
| `seuil_m`            | Seuil de déclenchement (`0.40`)                   |
| `source_ign`         | Source IGN utilisée                               |
| `type_anomalie`      | `ecart_altimetrique_ign`                          |
| `priorite`           | `information`                                     |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "nombre_sommets": 179,
  "nombre_anomalies": 12,
  "source_ign": "LIDAR HD IGN",
  "sortie": "…/ecarts_z_ign.geojson"
}
```

## Utilisation en tant que bibliothèque

```python
from controle_alti_ign import (
    extraire_sommets,
    convertir_sommets_wgs84,
    recuperer_altitudes_ign,
    comparer_altitudes,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Extraction des sommets
sommets = extraire_sommets(features)

# Conversion et interrogation IGN
points_wgs84 = convertir_sommets_wgs84(sommets)
altitudes_ign, source = recuperer_altitudes_ign(points_wgs84)

# Comparaison
anomalies = comparer_altitudes(sommets, altitudes_ign, source)

# Sérialisation GeoJSON
geojson = construire_geojson_ecarts(anomalies)

# Contrôle complet
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_alti_ign.py`. L'API
IGN est systématiquement mockée pour garantir des tests isolés et
reproductibles. Ils couvrent :

- Conversion Lambert 93 → WGS84 sur des points connus.
- Extraction des sommets pour chaque type de géométrie.
- Comparaison des altitudes avec et sans dépassement du seuil.
- Gestion du fallback entre sources IGN.
- Découpage en lots.
- Structure du GeoJSON de sortie.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_alti_ign.py -v
```
