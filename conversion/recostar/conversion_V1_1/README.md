# Scripts de conversion GML ↔ GeoJSON — RecoStaR V1.1

Documentation technique des scripts de conversion bidirectionnelle entre GML (StaR-Elec RecoStaR) et GeoJSON.

Pour les éléments relatifs au standard, veuillez vous référer aux informations disponibles ici :  : [StaRElec](https://gitlab.com/StaR-Elec/StaR-Elec/-/tree/RecoStar-v1.10?ref_type=tags)

---

## Vue d'ensemble

| Script | Direction | Entrée | Sortie |
| --- | --- | --- | --- |
| `recostar_to_geojson.py` | GML → GeoJSON | 1 fichier `.gml` | N fichiers `RPD_*.geojson` + `_metadata.json` |
| `geojson_to_recostar.py` | GeoJSON → GML | N fichiers `RPD_*.geojson` | 1 fichier `.gml` conforme XSD |

Schéma de référence : `xsd/SchemaStarElecRecoStar_V1_1.xsd` (namespace `http://StaR-Elec.com`, GML 3.2).

---

## 1. recostar_to_geojson.py

### Rôle — GML vers GeoJSON

Convertit un fichier GML RecoStaR en un ensemble de fichiers GeoJSON (un par type d'entité RPD_*), avec préservation des métadonnées et des relations.

### Utilisation CLI — GML vers GeoJSON

```bash
python recostar_to_geojson.py <fichier_gml> <dossier_sortie>
```

| Paramètre | Type | Description |
| --- | --- | --- |
| `input_gml` | Path | Fichier GML RecoStaR en entrée |
| `output_dir` | Path | Dossier de sortie pour les GeoJSON |

### Classes principales — GML vers GeoJSON

| Classe | Rôle |
| --- | --- |
| **GMLNamespaceHelper** | Résolution des namespaces GML/RecoStaR (avec `@lru_cache`) |
| **GeometryParser** | Parse les géométries GML (Point, Curve, Surface) → GeoJSON |
| **EntityExtractor** | Extraction des propriétés de chaque type d'entité RPD_* |
| **GMLConverter** | Orchestrateur du pipeline de conversion en 4 passes |

### Pipeline de traitement — GML vers GeoJSON

```text
Fichier GML
  │
  ├─ Passe 1 : Conteneurs (Coffret, Support, BatimentTechnique, EnceinteCloturee)
  │             → Cache des géométries pour héritage
  │
  ├─ Passe 2 : Cheminements (Aerien, Fourreau, PleineTerre, ProtectionMecanique)
  │             → Cache des géométries pour câbles
  │
  ├─ Passe 3 : Entités restantes (Noeuds, Câbles, Équipements)
  │             → Héritage des géométries depuis le cache
  │
  └─ Passe 4 : Post-traitement
               → Propagation des propriétés câbles
               → Injection des matériels dans les jonctions
               → Génération GeometrieSupplementaire (V1.0)
               → Écriture des fichiers GeoJSON + _metadata.json
```

### Sortie

- **`RPD_*.geojson`** : Un fichier par type d'entité (jusqu'à 24 types)
- **`_metadata.json`** : Métadonnées du réseau (Datecreation, Logiciel, Producteur, SRS, VersionSpecification, ReseauUtilite)

### Gestion des versions

- **V1.0** : Normalisation automatique (ex. ChargeGeneratrice PLOR, génération GeometrieSupplementaire pour supports)
- **V1.1** : Extraction directe avec les champs additionnels (Etiquette, EtatAvantRaccordement, Commentaire, Statut)

---

## 2. geojson_to_recostar.py

### Rôle — GeoJSON vers GML

Recompose un fichier GML RecoStaR conforme au XSD V1.1 à partir d'un ensemble de fichiers GeoJSON.

### Utilisation CLI — GeoJSON vers GML

```bash
python geojson_to_recostar.py <dossier_geojson> <fichier_gml_sortie> [options]
```

| Paramètre | Type | Défaut | Description |
| --- | --- | --- | --- |
| `input_dir` | Path | — | Dossier contenant les `RPD_*.geojson` |
| `output_file` | Path | — | Chemin du fichier GML de sortie |
| `--logiciel` | str | `"LAZio"` | Logiciel utilisé |
| `--producteur` | str | `"TEST"` | Producteur des données |
| `--responsable` | str | `"TEST"` | Responsable |
| `--nom` | str | `"TEST"` | Nom du réseau |
| `--srs` | str | auto-détecté | CRS (ex. `EPSG:2154`) |

### Classes principales — GeoJSON vers GML

| Classe | Rôle |
| --- | --- |
| **ElementGML** | Conteneur léger avec `__slots__` (économie mémoire ~20-30%) |
| **ConvertisseurGeometrie** | Conversion GeoJSON → GML (Point, LineString, Polygon) |
| **MappeurEntites** | Mapping des propriétés GeoJSON → éléments XML par type |
| **GenerateurGML** | Orchestrateur : chargement, construction de l'arbre XML, écriture |

### Pipeline de traitement — GeoJSON vers GML

```text
Dossier GeoJSON (RPD_*.geojson)
  │
  ├─ Chargement des fichiers + détection CRS
  ├─ Extraction et déduplications des matériels (depuis jonctions)
  ├─ Construction du cache conteneurs (géométries)
  ├─ Enrichissement des géométries par héritage
  ├─ Reconstruction des relations :
  │     • CableElectrique_NoeudReseau (+ EtatAvantRaccordement)
  │     • Cheminement_Cables
  │     • Ouvrage_Materiel
  ├─ Ajout des métadonnées et informations réseau
  └─ Écriture du fichier GML conforme XSD
```

### Fichiers GeoJSON attendus en entrée

18 fichiers RPD_* minimum requis :

| Catégorie | Types |
| --- | --- |
| **Câbles** | CableElectrique, CableTelecommunication, CableTerre |
| **Cheminements** | Aerien, Fourreau, PleineTerre, ProtectionMecanique |
| **Noeuds** | Jonction, JeuBarres, PointDeComptage, CoupeCircuitAFusibles, SupportModules, Terre, OuvrageCollectifBranchement |
| **Conteneurs** | Coffret, EnceinteCloturee, BatimentTechnique, PosteElectrique |
| **Autres** | GeometrieSupplementaire, PointLeveOuvrageReseau |
| **Optionnels** | Support, Materiel |

---

## 3. Schéma XSD

| Propriété | Valeur |
| --- | --- |
| Fichier | `xsd/SchemaStarElecRecoStar_V1_1.xsd` |
| Version | 1.01 (V1.1) |
| Namespace | `http://StaR-Elec.com` |
| GML | 3.2 |
| Types d'entités | 24+ types RPD_* |

### SRS supportés

- **France métropolitaine** : EPSG:2154 (Lambert-93), EPSG:3942–3950 (CC zones)
- **Outre-mer** : EPSG:2972, 2975, 4471, 4467

---

## 4. Dépendances

| Bibliothèque | Usage | Script |
| --- | --- | --- |
| `defusedxml` | Parsing XML sécurisé (protection XXE) | `recostar_to_geojson.py` |
| `json` | Lecture/écriture GeoJSON | Les deux |
| `xml.etree.ElementTree` | Construction XML | `geojson_to_recostar.py` |
| `argparse` | Interface CLI | Les deux |
| `uuid` | Génération d'identifiants GML | `geojson_to_recostar.py` |
| `functools.lru_cache` | Cache de performance | Les deux |

> **Note** : Aucune dépendance externe lourde (pas de GDAL, PDAL, etc.). Seul `defusedxml` nécessite une installation pip.

```bash
pip install defusedxml
```

---

## 5. Optimisations

| Technique | Impact | Localisation |
| --- | --- | --- |
| `frozenset` pour lookups de types | O(1) vs O(n) | Les deux scripts |
| `@lru_cache` namespaces | Cache 64 entrées | `recostar_to_geojson.py` |
| `@lru_cache` formatage coordonnées | Cache 128 entrées | `geojson_to_recostar.py` |
| `__slots__` sur ElementGML | ~20-30% économie mémoire | `geojson_to_recostar.py` |
| Déduplications par `set` | O(1) vérification matériels | `geojson_to_recostar.py` |

---

## 6. Flux de conversion complet

> **Fichier GML RecoStaR (V1.0 ou V1.1)**
>
> ⬇ `recostar_to_geojson.py`
>
> **RPD_\*.geojson (×24) + \_metadata.json**
> *(normalisé V1.1, même si l'entrée est en V1.0 — édition possible)*
>
> ⬇ `geojson_to_recostar.py`
>
> **Fichier GML RecoStaR (V1.1, conforme XSD)**

La chaîne garantit un aller-retour fidèle (round-trip) avec conservation des métadonnées, relations et géométries.
