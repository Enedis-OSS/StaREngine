# controle_plor_doublons.py — Contrôle des doublons de points levés

## Description

Détecte les doublons géographiques parmi les entités du fichier
`RPD_PointLeveOuvrageReseau_Reco.geojson`. Un doublon est défini comme
deux ou plusieurs entités ponctuelles partageant exactement les mêmes
coordonnées (X, Y, Z).

Toutes les entités d'un groupe de doublons sont signalées et exportées
dans le fichier GeoJSON de sortie.

**Règles** :

- Seules les géométries `Point` en 3D sont analysées.
- Les points 2D (sans composante Z) et les géométries non ponctuelles sont ignorés.
- La comparaison est exacte sur les trois axes X, Y et Z.
- Toutes les entités d'un groupe de doublons sont exportées (pas seulement les
  copies supplémentaires).
- Le contrôle est **bloquant**, avec `priorite = "information"`.
- Le CRS du fichier source est propagé dans le fichier de sortie.

### Segmentation par TypeLeve

Lorsque le champ `TypeLeve` est détecté dans les propriétés d'au moins une
feature du fichier PLOR, le contrôle segmente automatiquement la détection
par type de levé :

- Seules les entités partageant le **même TypeLeve** (ex. `AltitudeGeneratrice`
  ou `ChargeGeneratrice`) sont comparées entre elles.
- Deux points superposés mais de types différents ne sont **pas** considérés
  comme doublons.
- Si le champ `TypeLeve` est absent de toutes les features, le comportement
  classique est conservé (comparaison globale sans distinction de type).

## Fonctionnement

### 1. Chargement des données

Le fichier `RPD_PointLeveOuvrageReseau_Reco.geojson` est chargé depuis le
répertoire d'entrée.

### 2. Indexation par coordonnées

Chaque feature `Point` 3D est regroupée par ses coordonnées (X, Y, Z) dans
un dictionnaire. La clé est un tuple `(X, Y, Z)`, la valeur est la liste
des features partageant ces coordonnées.

### 3. Détection des doublons

Un groupe est considéré comme doublon dès lors qu'il contient au moins deux
features. Toutes les features du groupe sont alors signalées.

### 4. Construction du GeoJSON de sortie

Les doublons sont exportés en tant que `Point` avec leurs métadonnées
(identifiant de l'entité, nombre de doublons à cette position, type
d'anomalie, priorité).

## Paramètres

| Constante           | Valeur                                      | Description                             |
| ------------------- | ------------------------------------------- | --------------------------------------- |
| `FICHIER_PLOR`      | `RPD_PointLeveOuvrageReseau_Reco.geojson`   | Fichier des points levés                |
| `FICHIER_SORTIE`    | `plor_doublons.geojson`                     | Nom du fichier de sortie                |
| `PRIORITE_ANOMALIE` | `information`                               | Niveau de priorité des anomalies        |
| `CHAMP_TYPE_LEVE`   | `TypeLeve`                                  | Champ de segmentation optionnel         |

## Ligne de commande

```bash
python controle_plor_doublons.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant le fichier GeoJSON à analyser      |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `plor_doublons.geojson` — FeatureCollection de points représentant les
  doublons détectés, avec les propriétés suivantes :

| Propriété        | Description                                            |
| ---------------- | ------------------------------------------------------ |
| `id_entite`      | Identifiant métier de l'entité PLOR                    |
| `nb_doublons`    | Nombre total d'entités superposées à cette position    |
| `type_anomalie`  | `doublon_geometrique`                                  |
| `priorite`       | Niveau de priorité de l'anomalie (`information`)       |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "nombre_points_plor": 437,
  "nombre_groupes_doublons": 3,
  "nombre_anomalies": 6,
  "sortie": "…/plor_doublons.geojson"
}
```

## Utilisation en tant que bibliothèque

```python
from controle_plor_doublons import (
    indexer_points_par_coordonnees,
    detecter_doublons,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Indexation des features par coordonnées
index = indexer_points_par_coordonnees(features)

# Détection des doublons
anomalies = detecter_doublons(index)

# Sérialisation GeoJSON
geojson = construire_geojson_ecarts(anomalies, crs)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_plor_doublons.py` (même
répertoire que le script). Ils couvrent :

- Indexation des features par coordonnées (regroupement, unicité).
- Détection des groupes de doublons et non-détection des points uniques.
- Vérification de la distinction par axe Z.
- Gestion des géométries absentes, 2D ou de type non supporté.
- Structure et contenu du GeoJSON de sortie.
- Propagation du CRS dans le fichier de sortie.
- Détection de la présence du champ `TypeLeve`.
- Segmentation par type de levé (doublons intra-type uniquement).
- Non-détection de doublons entre types différents au même emplacement.
- Exécution CLI bout en bout via `tmp_path` (avec et sans `TypeLeve`).

```bash
pytest test_controle_plor_doublons.py -v
```
