# Conversion GeoJSON ↔ GML RecoStaR

Outils de conversion bidirectionnelle entre fichiers **GeoJSON** (RPD_\*) et **GML RecoStaR** conformes au schéma XSD StaR-Elec v1.0.

Pour les éléments relatifs au standard, veuillez vous référer aux informations disponibles ici :  : [StaRElec](https://gitlab.com/StaR-Elec/StaR-Elec/-/tree/RecoStar-v1.0?ref_type=tags)

---

## Scripts

| Script | Rôle |
| --- | --- |
| `geojson_to_recostar.py` | Convertit un dossier de GeoJSON RPD_\* → un fichier GML unique |
| `recostar_to_geojson.py` | Convertit un fichier GML RecoStaR → un dossier de GeoJSON (un par type) |

---

## Usage CLI

### GeoJSON → GML

```bash
python geojson_to_recostar.py <dossier_geojson> <sortie.gml> [options]
```

| Option | Défaut | Description |
| --- | --- | --- |
| `--logiciel` | `LAZio` | Logiciel de génération |
| `--producteur` | `TEST` | Producteur du récolement |
| `--responsable` | `TEST` | Responsable du récolement |
| `--nom` | `TEST` | Nom du réseau |
| `--srs` | auto-détecté | Forcer le CRS (ex: `EPSG:2154`) |

### GML → GeoJSON

```bash
python recostar_to_geojson.py <fichier.gml> <dossier_sortie>
```

Aucune option supplémentaire. Le CRS est lu depuis les métadonnées du GML.

---

## Entrées / Sorties

### `geojson_to_recostar.py`

- **Entrée** : Dossier contenant des fichiers `RPD_*.geojson` (CableElectrique, Coffret, Fourreau, Jonction, etc.)
- **Sortie** : Fichier GML unique avec métadonnées, réseau, entités et relations

### `recostar_to_geojson.py`

- **Entrée** : Fichier GML RecoStaR unique
- **Sortie** : Dossier contenant un fichier `RPD_*.geojson` par type d'entité

---

## Étapes de traitement

### GeoJSON → GML (`geojson_to_recostar.py`)

1. Chargement des fichiers GeoJSON RPD_\* et détection du CRS
2. Mapping des propriétés GeoJSON → éléments XML conformes au XSD
3. Conversion des géométries (Point, LineString, Polygon) en GML
4. Génération des relations (câble↔nœud, cheminement↔câble, ouvrage↔matériel)
5. Écriture du fichier GML avec métadonnées et namespaces

### GML → GeoJSON (`recostar_to_geojson.py`)

1. Parsing XML sécurisé du GML (via `defusedxml`)
2. **Passe 1** : Extraction des relations entre entités
3. **Passe 2** : Extraction des conteneurs (Coffret, Support, BâtimentTechnique) → cache de géométries
4. **Passe 3** : Extraction des cheminements (Fourreau, PleineTerre, Aérien, ProtectionMécanique) → cache de géométries
5. **Passe 4** : Extraction des autres entités avec héritage de géométries depuis les caches
6. Propagation des câbles dans les conteneurs et injection matériel→jonctions
7. Écriture d'un fichier GeoJSON par type d'entité

---

## Types d'entités supportés

`RPD_CableElectrique_Reco`, `RPD_CableTerre_Reco`, `RPD_Coffret_Reco`, `RPD_Fourreau_Reco`, `RPD_GeometrieSupplementaire_Reco`, `RPD_JeuBarres_Reco`, `RPD_Jonction_Reco`, `RPD_OuvrageCollectifBranchement_Reco`, `RPD_PointDeComptage_Reco`, `RPD_PointLeveOuvrageReseau_Reco`, `RPD_BatimentTechnique_Reco`, `RPD_PosteElectrique_Reco`, `RPD_ProtectionMecanique_Reco`, `RPD_SupportModules_Reco`, `RPD_Terre_Reco`, `RPD_Aerien_Reco`, `RPD_Materiel_Reco`, `RPD_PleineTerre_Reco`, `RPD_Support_Reco`

---

## Tests

```bash
pytest tests/
```

Les tests couvrent : constantes, conversion géométrique, mapping d'entités, relations, génération XML, détection CRS et héritage de géométries.

---

## Dépendances

- Python 3.x
- `defusedxml` (parsing XML sécurisé, utilisé par `recostar_to_geojson.py`)
- Bibliothèques standard : `json`, `xml.etree.ElementTree`, `argparse`, `uuid`, `pathlib`
- Schéma XSD de référence : `xsd/SchemaStarElecRecoStar.xsd`
