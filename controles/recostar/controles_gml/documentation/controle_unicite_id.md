# controle_unicite_id.py — Contrôle d'unicité des identifiants

## Description

Vérifie que tous les objets présents dans les fichiers GeoJSON préfixés par
`RPD_` possèdent un identifiant unique. Si un même identifiant (`properties.id`)
apparaît plusieurs fois — que ce soit dans un même fichier ou entre fichiers
différents — chaque occurrence est signalée en anomalie bloquante.

**Règle** :

- Chaque identifiant (`properties.id`) doit être **unique** sur l'ensemble des
  fichiers `RPD_*.geojson` du répertoire.
- Les features sans identifiant (`id` absent ou `null`) sont ignorées par le
  contrôle.

## Fonctionnement

### 1. Listage des fichiers

Le script parcourt le répertoire d'entrée et sélectionne tous les fichiers dont
le nom commence par `RPD_` et se termine par `.geojson`, triés par ordre
alphabétique.

### 2. Collecte des identifiants

Pour chaque fichier, les features sont parcourues et le champ `properties.id`
est extrait. Les identifiants sont stockés dans un dictionnaire associant chaque
identifiant à la liste de ses occurrences (fichier source + feature complète).

### 3. Détection des doublons

Seuls les identifiants possédant plus d'une occurrence sont retenus comme
doublons.

### 4. Génération des sorties

- **Rapport JSON** (`rapport_controle_unicite_id.json`) : synthèse du contrôle
  incluant le nombre de fichiers analysés, le nombre total de features, le nombre
  d'identifiants dupliqués et le détail des anomalies.
- **GeoJSON des écarts** (`ecarts_unicite_id.geojson`) : FeatureCollection
  contenant chaque occurrence d'un doublon avec sa géométrie d'origine, permettant
  la visualisation directe dans QGIS.

## Ligne de commande

```bash
python controle_unicite_id.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                                  |
| -------------- | ----------- | ------------------------------------------------------------ |
| `--repertoire` | Oui         | Répertoire contenant les fichiers `RPD_*.geojson`            |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`)      |

### Sortie

- `rapport_controle_unicite_id.json` — rapport synthétique au format JSON :

```json
{
  "controle": "unicite_id",
  "bloquant": true,
  "nombre_fichiers_analyses": 17,
  "nombre_features_total": 607,
  "nombre_ids_dupliques": 1,
  "nombre_occurrences_doublons": 3,
  "nombre_anomalies": 1,
  "anomalies": [
    {
      "id_duplique": "id12345...",
      "nombre_occurrences": 3,
      "fichiers": ["RPD_A.geojson", "RPD_B.geojson"],
      "message": "L'identifiant id12345... est present 3 fois dans : RPD_A.geojson, RPD_B.geojson"
    }
  ]
}
```

- `ecarts_unicite_id.geojson` — FeatureCollection des anomalies :

| Propriété        | Description                                  |
| ---------------- | -------------------------------------------- |
| `id_duplique`    | Identifiant dupliqué                         |
| `fichier_source` | Nom du fichier contenant cette occurrence    |
| `type_anomalie`  | `id_duplique`                                |
| `message`        | Description détaillée de l'anomalie          |
| `priorite`       | Niveau de priorité (`bloquant`)              |

## Utilisation en tant que bibliothèque

```python
from controle_unicite_id import (
    lister_fichiers_rpd,
    collecter_ids_et_doublons,
    construire_anomalies,
    construire_rapport_json,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Lister les fichiers
fichiers = lister_fichiers_rpd(repertoire)

# Collecter les doublons
doublons, total, crs = collecter_ids_et_doublons(repertoire, fichiers)

# Construire les anomalies
anomalies = construire_anomalies(doublons)

# Generer le rapport
rapport = construire_rapport_json(anomalies, len(fichiers), total)

# Generer le GeoJSON des ecarts
geojson = construire_geojson_ecarts(anomalies, crs)

# Controle complet avec ecriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_unicite_id.py` (même
répertoire que le script). Ils couvrent :

- Listage et filtrage des fichiers (`RPD_*.geojson` uniquement).
- Lecture de fichiers GeoJSON valides et absents.
- Détection de doublons intra-fichier et inter-fichiers.
- Ignorance des features sans identifiant.
- Propagation du CRS dans le GeoJSON de sortie.
- Structure du rapport JSON (bloquant / non bloquant).
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_unicite_id.py -v
```
