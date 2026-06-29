# Contrôles de projection

Ce dossier regroupe les contrôles de conformité de projection appliqués aux fichiers GeoJSON.
Chaque contrôle parcourt les fichiers GeoJSON d'un jeu de données Recostar, détecte les
anomalies et produit un fichier d'écarts GeoJSON (préfixé `ecarts_`) directement
exploitable dans QGIS.

La projection de référence est lue depuis le fichier `_metadata.json` du jeu de données
(champ `Metadata.SRS`). Les fichiers d'écarts (`ecarts_*`) sont automatiquement exclus
des analyses.

## Vue d'ensemble

| Code | Script | Cible | Condition d'anomalie | Priorité | Fichier de sortie |
|------|--------|-------|----------------------|----------|-------------------|
| E300 | `controle_e300.py` | Tous les GeoJSON | projection ≠ `Metadata.SRS` | `bloquant` | `ecarts_projection.geojson` |
| E301 | `controle_e301.py` | Tous les GeoJSON | position aberrante (IQR Tukey) | `bloquant` | `ecarts_coherence_spatiale.geojson` |
| E302 | `controle_e302.py` | `RPD_GeometrieSupplementaire_Reco.geojson` | superficie > 100 m² | `bloquant` | `ecarts_geometrie_supplementaire.geojson` |
| E303 | `controle_e303.py` | Tous les GeoJSON | entité hors emprise DR | `bloquant` | `ecarts_emprise_dr.geojson` |

L'orchestration est assurée par `pipeline_controle_projection.py`.
Les fonctions utilitaires communes (lecture/écriture/listage GeoJSON, extraction
d'identifiant) sont centralisées dans `utils_geojson.py`.

### Usage CLI

La plupart des contrôles s'exécutent de la même manière :

```bash
python <script>.py --repertoire <chemin> [--sortie <chemin>]
```

E303 requiert en plus le numéro d'affaire :

```bash
python controle_e303.py --repertoire <chemin> --numero_affaire <numero> [--sortie <chemin>]
```

Le pipeline accepte également ce paramètre optionnel :

```bash
python pipeline_controle_projection.py --repertoire <chemin> [--numero_affaire <numero>] [--sortie <chemin>]
```

- `--repertoire` : répertoire contenant les fichiers GeoJSON.
- `--numero_affaire` : numéro d'affaire au format `RAC-XXX-YY-NNNNNN` ou `XXNN/NNNNNN` (requis pour E303).
- `--sortie` : répertoire de sortie (par défaut, le répertoire d'entrée).

Le résultat est imprimé en JSON sur la sortie standard. Tous les rapports de
contrôle incluent le champ `priorite`.

---

## E300 — Conformité de projection (`controle_e300.py`)

**Ce qui est contrôlé :** vérifie que l'ensemble des fichiers GeoJSON d'un jeu de données
Recostar utilisent la projection déclarée dans `_metadata.json` (champ `Metadata.SRS`).
Tout fichier dont le champ `crs` ne correspond pas à la projection attendue, ou ne
possède pas de champ `crs`, voit l'intégralité de ses entités signalée comme anomalie.
Les entités sans géométrie sont ignorées.

**Formats de projection acceptés :**

- URN OGC : `urn:ogc:def:crs:EPSG::3947` ou `urn:ogc:def:crs:EPSG:6.18.3:3947`
- Format direct : `EPSG:3947` (insensible à la casse)

Les deux formats sont normalisés vers `EPSG:NNNN` avant comparaison.

**Cas d'anomalie :**

- La projection du fichier GeoJSON diffère de celle déclarée dans `_metadata.json`.
- Le fichier GeoJSON ne possède pas de champ `crs` (projection inconnue).

**Sortie — `ecarts_projection.geojson` :** un `Feature` par entité non conforme,
**conservant sa géométrie d'origine**, avec les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`
- `projection_attendue` : code EPSG lu depuis `_metadata.json`
- `projection_detectee` : code EPSG lu dans le fichier, ou `inconnue` si absent
- `type_anomalie` = `projection_incorrecte`
- `priorite` = `bloquant`

Le champ `crs` du fichier de sortie est construit depuis la projection attendue,
ce qui permet à QGIS d'afficher les entités dans le bon référentiel.

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `fichiers_analyses`,
`projection_attendue`, `sortie`.

**Erreurs remontées :**

- `_metadata.json` absent du répertoire.
- Champ `Metadata.SRS` absent ou non reconnu.
- Aucun fichier GeoJSON dans le répertoire.

---

## E301 — Cohérence spatiale (`controle_e301.py`)

**Ce qui est contrôlé :** vérifie que la position de chaque entité GeoJSON est cohérente
avec l'ensemble du jeu de données. Les entités dont la position est anormalement éloignée
du reste des données sont signalées comme anomalies.

**Algorithme — méthode Tukey IQR :**

Le contrôle représente chaque entité par son **centroïde** (moyenne de toutes ses
coordonnées). La distance de chaque centroïde au **médian spatial** (médiane
indépendante de X et de Y) est calculée. Le seuil est : `Q3 + 1,5 × IQR`. Toute entité
dépassant ce seuil est signalée.

Le médian spatial (et non la moyenne) est utilisé comme référence car il est insensible
aux valeurs aberrantes — la moyenne serait elle-même attirée par les positions anormales.

**Prérequis :** si le champ `crs` est présent dans les fichiers GeoJSON, le CRS doit
être **projeté** (coordonnées en mètres). Les CRS géographiques (en degrés) ne
permettent pas d'appliquer des distances euclidiennes significatives.
La vérification est effectuée via `pyproj`.

**Cas d'anomalie :** entité dont la distance au médian spatial dépasse le seuil IQR
de Tukey, calculé sur l'ensemble des entités du jeu de données.

**Conditions de rejet :** moins de 4 entités au total (insuffisant pour la statistique),
CRS géographique détecté, répertoire introuvable, aucun GeoJSON dans le répertoire.

**Sortie — `ecarts_coherence_spatiale.geojson` :** un `Feature` par entité aberrante,
**conservant sa géométrie d'origine**, avec les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`
- `distance_au_median_m` : distance euclidienne au médian spatial (en mètres)
- `seuil_m` : seuil IQR appliqué (en mètres)
- `type_anomalie` = `position_aberrante`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `entites_analysees`,
`fichiers_analyses`, `seuil_m`, `sortie`.

---

## E302 — Superficie des géométries supplémentaires (`controle_e302.py`)

**Ce qui est contrôlé :** vérifie que la superficie de chaque entité surfacique présente
dans `RPD_GeometrieSupplementaire_Reco.geojson` ne dépasse pas **100 m²**. Au-delà,
l'entité est signalée comme anomalie bloquante.

**Cible :** uniquement le fichier `RPD_GeometrieSupplementaire_Reco.geojson` du répertoire.
Si ce fichier est absent, le contrôle retourne une erreur sans bloquer le pipeline.

**Calcul de superficie — formule de Shoelace :**

L'aire est calculée par l'algorithme de Gauss (Shoelace), applicable aux coordonnées
projetées en mètres : `A = 0,5 × |Σ(xᵢ × yᵢ₊₁ − xᵢ₊₁ × yᵢ)|`.
Pour un `Polygon`, l'aire des trous (anneaux intérieurs) est soustraite.
Pour un `MultiPolygon`, les aires de chaque polygone sont sommées.
Les géométries non surfaciques (`Point`, `LineString`, etc.) sont ignorées.

**Condition d'anomalie :** superficie calculée **strictement supérieure à 100 m²** (une
entité à exactement 100 m² est conforme).

**Sortie — `ecarts_geometrie_supplementaire.geojson` :** un `Feature` par entité
non conforme, **conservant sa géométrie d'origine**, avec les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`
- `aire_m2` : superficie calculée (arrondie à 2 décimales)
- `seuil_m2` = `100.0`
- `type_anomalie` = `aire_excessive`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `entites_analysees`,
`seuil_aire_m2`, `sortie`.

**Erreurs remontées :**

- Répertoire introuvable.
- Fichier `RPD_GeometrieSupplementaire_Reco.geojson` absent du répertoire.
- Fichier illisible ou JSON invalide.

---

## E303 — Appartenance à l'emprise DR (`controle_e303.py`)

**Ce qui est contrôlé :** vérifie que chaque entité GeoJSON se trouve à l'intérieur de
l'emprise géographique de la direction régionale (DR) correspondant au numéro d'affaire
fourni. Toute entité située hors de l'emprise autorisée est signalée comme anomalie.

**Résolution du numéro d'affaire :**

Le contrôle accepte deux formats :

| Format | Exemple | Extraction | Champ de recherche |
|--------|---------|------------|-------------------|
| RAC | `RAC-CVL-25-007998` | `CVL` (2ᵉ segment) | `trigramme_racing` |
| DA | `DA21/256553` | `DA21` (avant `/`) | `ref_dossier` |

La correspondance est effectuée dans `fichiers_dr/reference_dr.json` pour obtenir le
code `repertoire` de la DR (ex. `8A`). Un trigramme peut résoudre vers plusieurs codes
`repertoire` — dans ce cas, toutes les emprises associées sont considérées autorisées
(gestion des affaires à cheval sur plusieurs DR).

**Référentiel spatial :** l'emprise est chargée depuis `fichiers_dr/emprise_dr.geojson`
(CRS EPSG:2154, Lambert 93), filtré sur le champ `code_dr_oa`. Si les GeoJSON analysés
utilisent un autre CRS projeté, les coordonnées sont automatiquement reprojetées vers
EPSG:2154 via `pyproj` avant le test de containment.

**Algorithme de containment — Ray Casting :**

Chaque entité est représentée par son centroïde. Le test d'appartenance utilise
l'algorithme du Ray Casting (Crossing Number) : un rayon horizontal est lancé depuis
le point et le nombre de croisements avec les arêtes du polygone est compté.
Une bounding box pré-calculée permet d'éviter le test complet pour les entités
manifestement hors zone.

**Cas d'anomalie :** entité dont le centroïde n'est inclus dans aucune des emprises DR
autorisées pour le numéro d'affaire donné.

**Sortie — `ecarts_emprise_dr.geojson` :** un `Feature` par entité hors emprise,
**conservant sa géométrie d'origine**, avec les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`
- `codes_dr_autorises` : codes DR attendus (ex. `8A` ou `1Z, 2Z` si plusieurs)
- `type_anomalie` = `hors_emprise_dr`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `entites_analysees`,
`fichiers_analyses`, `numero_affaire`, `codes_dr`, `sortie`.

**Erreurs remontées :**

- Paramètre `--numero_affaire` absent.
- Format du numéro d'affaire non reconnu.
- Trigramme ou référence dossier absente de `reference_dr.json`.
- DR sans emprise dans `emprise_dr.geojson` (zones SEI : COR, GUA, MAR, REU, GUY).
- Répertoire introuvable, aucun GeoJSON dans le répertoire.

**Note sur les zones SEI (A Terminer):** les DR d'outre-mer (Corse, Guadeloupe, Martinique,
La Réunion, Guyane) sont référencées dans `reference_dr.json` mais ne disposent pas
d'emprise dans `emprise_dr.geojson`. Le contrôle retourne une erreur explicite pour
ces zones.

---

## Pipeline (`pipeline_controle_projection.py`)

Exécute séquentiellement les contrôles de projection dans l'ordre E300 → E301 → E302 → E303.
Un échec d'un contrôle n'interrompt pas l'exécution des suivants.

Le paramètre `--numero_affaire` est optionnel au niveau du pipeline. Sans lui, E303
retourne une erreur qui n'impacte pas le `nombre_anomalies_total`.

**Rapport JSON :**

- `succes`
- `controles` : dictionnaire des rapports individuels, indexé par `controle_e300`,
  `controle_e301`, `controle_e302` et `controle_e303` (chacun contenant son champ `priorite`) ;
- `nombre_anomalies_total` : somme des anomalies des contrôles réussis.
