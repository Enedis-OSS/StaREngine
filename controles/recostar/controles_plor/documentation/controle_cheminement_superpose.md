# controle_cheminement_superpose.py — Contrôle des superpositions de cheminements

## Description

Détecte les superpositions totales ou partielles entre les entités
linéaires des fichiers de cheminement :

- `RPD_Fourreau_Reco.geojson`
- `RPD_PleineTerre_Reco.geojson`
- `RPD_ProtectionMecanique_Reco.geojson`

Deux entités sont considérées comme superposées si elles partagent au
moins un **segment géométrique commun** — c'est-à-dire deux sommets
consécutifs identiques en X, Y, Z.

**Règles** :

- Les géométries `LineString` et `MultiLineString` sont analysées.
- Les segments sont normalisés pour que (A→B) et (B→A) soient considérés
  identiques.
- Les segments dégénérés (même point de départ et d'arrivée) sont ignorés.
- La comparaison porte sur les trois axes (X, Y, Z).
- La détection s'applique entre fichiers différents et au sein d'un même fichier.
- Les fichiers absents parmi les trois attendus sont simplement ignorés.
- Le contrôle est **bloquant**, avec `priorite = "bloquant"`.
- Le CRS du premier fichier chargé est propagé dans le fichier de sortie.

## Fonctionnement

### 1. Chargement des données

Les trois fichiers GeoJSON de cheminement sont chargés depuis le répertoire
d'entrée. Les fichiers absents sont ignorés ; le contrôle s'exécute dès
qu'au moins un fichier est trouvé.

### 2. Extraction des segments

Pour chaque feature, les segments géométriques (arêtes entre deux sommets
consécutifs) sont extraits et normalisés. La normalisation garantit que
deux segments de sens opposés (A→B et B→A) sont considérés comme identiques.

### 3. Indexation

Un index associe chaque segment unique à la liste des features qui le
contiennent. Cette structure permet une détection en O(1) par segment.

### 4. Détection des superpositions

Un segment référencé par au moins deux features signale une superposition.
Toutes les features impliquées dans au moins un segment partagé sont
collectées comme anomalies.

### 5. Construction du GeoJSON de sortie

Les anomalies sont exportées avec la géométrie originale de chaque feature
(LineString ou MultiLineString), accompagnée de métadonnées (identifiant,
fichier source, entités superposées, priorité).

## Paramètres

| Constante               | Valeur                                         | Description                              |
| ----------------------- | ---------------------------------------------- | ---------------------------------------- |
| `FICHIERS_CHEMINEMENTS` | (3 noms de fichiers RPD)                       | Fichiers de cheminement à analyser       |
| `FICHIER_SORTIE`        | `cheminement_superpose.geojson`                | Nom du fichier de sortie                 |
| `PRIORITE_ANOMALIE`     | `bloquant`                                     | Niveau de priorité des anomalies         |

## Ligne de commande

```bash
python controle_cheminement_superpose.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant les fichiers GeoJSON à analyser    |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sortie

- `cheminement_superpose.geojson` — FeatureCollection de lignes représentant les
  entités superposées, avec les propriétés suivantes :

| Propriété            | Description                                                   |
| -------------------- | ------------------------------------------------------------- |
| `id_entite`          | Identifiant métier de l'entité                                |
| `fichier_source`     | Nom du fichier GeoJSON d'origine                              |
| `ids_superposes`     | Identifiants des entités avec lesquelles elle se superpose    |
| `nb_superpositions`  | Nombre d'entités superposées                                  |
| `type_anomalie`      | `superposition_cheminement`                                   |
| `priorite`           | Niveau de priorité de l'anomalie (`bloquant`)                 |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "nombre_entites": 33,
  "nombre_fichiers": 2,
  "nombre_anomalies": 0,
  "sortie": "…/cheminement_superpose.geojson"
}
```

## Utilisation en tant que bibliothèque

```python
from controle_cheminement_superpose import (
    charger_cheminements,
    indexer_segments,
    construire_carte_superpositions,
    construire_anomalies,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Chargement des features
entrees, crs, nb_fichiers = charger_cheminements(repertoire)

# Indexation et détection
index = indexer_segments(entrees)
carte = construire_carte_superpositions(index)
anomalies = construire_anomalies(carte, entrees)

# Sérialisation GeoJSON
geojson = construire_geojson_ecarts(anomalies, crs)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_cheminement_superpose.py`
(même répertoire que le script). Ils couvrent :

- Extraction de segments depuis LineString et MultiLineString.
- Normalisation des segments (symétrie A→B / B→A).
- Gestion des segments dégénérés (sommets consécutifs identiques).
- Indexation des segments par feature.
- Construction de la carte de superpositions.
- Gestion des géométries absentes ou de type non supporté.
- Structure et contenu du GeoJSON de sortie.
- Propagation du CRS dans le fichier de sortie.
- Superpositions inter-fichiers et intra-fichier.
- Superpositions totales et partielles.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_cheminement_superpose.py -v
```
