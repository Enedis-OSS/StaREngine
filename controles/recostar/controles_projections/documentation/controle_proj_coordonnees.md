# controle_proj_coordonnees.py — Contrôle de cohérence des coordonnées

## Description

Vérifie que les coordonnées de chaque entité GeoJSON sont cohérentes avec
le système de référence de coordonnées (CRS) déclaré dans le fichier.
Détecte les anomalies telles que :

- **Coordonnées hors emprise** : les valeurs X/Y du sommet se situent en
  dehors de la zone d'utilisation officielle du CRS.
- **Coordonnées invalides** : valeurs non finies (NaN, infini), non
  numériques ou nombre de composantes insuffisant.
- **CRS indéterminé** : le CRS du fichier est absent ou non interprétable,
  empêchant toute vérification des coordonnées.

**Cas typiques détectés** :

- Coordonnées géographiques (longitude/latitude) dans un CRS projeté
  (ex : `[3.5, 43.2]` dans un fichier déclaré en EPSG:2154).
- Coordonnées projetées dans un mauvais système (ex : Lambert 93 dans un
  fichier déclaré en CC46).
- Valeurs aberrantes résultant d'erreurs de conversion ou de format.

## Principe de fonctionnement

Le script utilise **pyproj** pour déterminer l'emprise projetée de chaque CRS :

1. La zone d'utilisation géographique officielle (`area_of_use`) est
   récupérée depuis la base de données EPSG via `pyproj.CRS`.
2. Les bords de cette zone sont échantillonnés (points régulièrement
   espacés) et transformés en coordonnées projetées via `pyproj.Transformer`.
3. L'enveloppe projetée résultante définit les bornes de validité.
4. Chaque sommet de chaque entité est vérifié par rapport à cette emprise.

Le calcul d'emprise est mis en cache (`lru_cache`) : une seule transformation
par code EPSG unique, quel que soit le nombre de fichiers.

## Fonctionnement détaillé

### 1. Listing des fichiers

Le répertoire d'entrée est parcouru. Seuls les fichiers `.geojson` sont
retenus. Les fichiers dont le nom commence par `ecarts_` sont exclus pour
éviter l'analyse des sorties de contrôles précédents.

### 2. Extraction du CRS

Pour chaque fichier GeoJSON, le code EPSG est extrait depuis le champ
`crs.properties.name` (formats URN OGC et court supportés). Cette fonction
est réutilisée depuis `controle_proj.py`.

### 3. Calcul de l'emprise projetée

Pour chaque code EPSG rencontré, l'emprise projetée est calculée via pyproj :

- Récupération des bornes géographiques (`area_of_use.bounds`).
- Échantillonnage de 9 points par bord (36 points au total).
- Transformation en coordonnées projetées.
- Calcul du min/max en coordonnées projetées pour l'enveloppe de validité.

### 4. Vérification des coordonnées

Pour chaque entité, tous les sommets sont extraits (tous types de géométrie
GeoJSON supportés : Point, LineString, Polygon, Multi*). Chaque sommet est
vérifié :

- Les composantes X et Y doivent être des nombres finis.
- Les composantes X et Y doivent se trouver dans l'emprise projetée.
- La composante Z (altitude) n'est pas vérifiée par ce contrôle.

### 5. Construction du GeoJSON d'écarts

Les anomalies détectées sont exportées sous forme de Points dans le fichier
d'écarts, avec les métadonnées de contrôle.

## Anomalies détectées

| Type d'anomalie       | Description                                        |
| --------------------- | -------------------------------------------------- |
| `hors_emprise`        | Coordonnées X/Y en dehors de l'emprise du CRS      |
| `coordonnee_invalide` | Valeur non finie, non numérique ou composantes < 2 |
| `crs_indetermine`     | CRS absent ou non interprétable par pyproj         |

## Paramètres

| Constante              | Valeur                            | Description                            |
| ---------------------- | --------------------------------- | -------------------------------------- |
| `FICHIER_SORTIE`       | `ecarts_proj_coordonnees.geojson` | Nom du fichier de sortie               |
| `PRIORITE_ANOMALIE`    | `bloquant`                        | Niveau de priorité des anomalies       |
| `_NB_ECHANTILLONS_BORD`| `8`                               | Points par bord pour l'échantillonnage |

## Réutilisation de code

Le script importe les fonctions suivantes de `controle_proj.py` :

| Fonction                  | Rôle                                  |
| ------------------------- | ------------------------------------- |
| `lire_geojson`            | Chargement d'un fichier GeoJSON       |
| `lister_fichiers_geojson` | Listing et filtrage des fichiers      |
| `extraire_code_epsg`      | Extraction du code EPSG depuis le CRS |
| `_obtenir_id_feature`     | Extraction de l'identifiant métier    |

## Ligne de commande

```bash
python controle_proj_coordonnees.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant les fichiers GeoJSON à analyser    |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `ecarts_proj_coordonnees.geojson` — FeatureCollection contenant un Point
  par sommet anomal, avec les propriétés suivantes :

| Propriété        | Description                                     |
| ---------------- | ----------------------------------------------- |
| `fichier_source` | Nom du fichier GeoJSON d'origine                |
| `id_entite`      | Identifiant métier de l'entité                  |
| `type_geometrie` | Type de géométrie de l'entité d'origine         |
| `indice_sommet`  | Position du sommet dans la géométrie            |
| `type_anomalie`  | Type d'anomalie détectée                        |
| `priorite`       | Niveau de priorité (`bloquant`)                 |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "fichiers_analyses": 17,
  "fichiers_conformes": 17,
  "fichiers_non_conformes": 0,
  "nombre_anomalies": 0,
  "sortie": "…/ecarts_proj_coordonnees.geojson",
  "detail": [
    {
      "fichier": "RPD_Aerien_Reco.geojson",
      "code_epsg": 2154,
      "nb_sommets": 14,
      "nb_anomalies": 0,
      "statut": "conforme"
    }
  ]
}
```

## Dépendances

- **pyproj** : calcul de l'emprise projetée à partir de la zone d'utilisation
  officielle du CRS. Installé dans l'environnement conda `lazio_source`.

## Utilisation en tant que bibliothèque

```python
from controle_proj_coordonnees import (
    obtenir_emprise_projetee,
    verifier_point,
    detecter_anomalies_feature,
    detecter_anomalies_collection,
    controler_fichier,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Calcul de l'emprise pour un CRS (résultat mis en cache)
emprise = obtenir_emprise_projetee(2154)

# Vérification d'un point
anomalie = verifier_point([850000.0, 6800000.0], emprise)

# Contrôle d'un fichier
anomalies, detail = controler_fichier(collection, "source.geojson")

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_proj_coordonnees.py`
(même répertoire que le script). Ils couvrent :

- Calcul d'emprise pour tous les CRS autorisés (Lambert 93, CC42-CC50,
  CC V2b, UTM outre-mer).
- Validation de valeurs finies / non finies / non numériques.
- Vérification de points dans/hors emprise, aux limites, en 2D et 3D.
- Extraction indexée des sommets pour tous les types de géométrie.
- Détection d'anomalies par feature et par collection.
- Gestion du CRS absent ou indéterminé.
- Construction du GeoJSON d'écarts (structure, priorité, géométrie).
- Exécution CLI bout en bout (répertoire de sortie, exclusion des fichiers
  d'écarts, fichiers multiples, détection inter-CRS).
- Tests sur données réelles (EPSG:2154, Lambert 93).

```bash
conda run -n lazio_source pytest test_controle_proj_coordonnees.py -v
```
