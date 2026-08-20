# Contrôles de projection

Ce dossier regroupe les contrôles de conformité de projection appliqués aux fichiers GeoJSON.
Chaque contrôle parcourt les fichiers GeoJSON d'un jeu de données Recostar, détecte les
anomalies et produit un fichier d'écarts GeoJSON (préfixé `ecarts_`) directement
exploitable dans QGIS.

La projection de référence est lue depuis le fichier `_metadata.json` du jeu de données
(champ `Metadata.SRS`). Les fichiers d'écarts (`ecarts_*`) sont automatiquement exclus
des analyses.

### Nom des fichiers d'écarts

Chaque fichier d'écarts porte le **code du contrôle** qui l'a produit :

```
ecarts_<code>_<objet>.geojson        ex. ecarts_e600_materiel_jonction_non_reference.geojson
```

Le code est inséré **après** le préfixe `ecarts_`, et non devant : c'est ce
préfixe qui fait exclure le fichier des analyses par `lister_fichiers_geojson`.
Un nom commençant par le code (`e600_ecarts_…`) ferait réingérer les fichiers
d'écarts comme couches d'entrée par les contrôles qui balaient tout le
répertoire (E204, E209, E604, E609, E610).

Le fichier d'écarts n'est produit **que si au moins une anomalie est détectée**.
En l'absence d'anomalie, aucun fichier n'est écrit (le champ `sortie` du rapport
vaut `null`) et un éventuel fichier issu d'une exécution précédente est supprimé.

### Socle commun des propriétés d'écarts

Quel que soit le contrôle, chaque `feature` du fichier d'écarts porte en tête les
cinq mêmes propriétés, dans cet ordre :

| Propriété | Description |
|-----------|-------------|
| `code_controle` | Code du contrôle ayant produit l'écart (`E200`, `E401`…) |
| `priorite` | Niveau de priorité de l'anomalie (`bloquant`, `mineur`, `information`) |
| `id_entite` | Identifiant de l'entité portant la géométrie de la feature |
| `type_anomalie` | Code technique de l'anomalie, stable et exploitable en filtre |
| `description` | Phrase décrivant l'anomalie, lisible dans QGIS |

Les propriétés métier spécifiques à chaque contrôle sont conservées à la suite du
socle. La normalisation est assurée par `normaliser_geojson_ecarts()` à partir du
`ProfilEcarts` déclaré en tête de chaque script de contrôle.

## Vue d'ensemble

| Code | Script | Cible | Condition d'anomalie | Priorité | Fichier de sortie |
|------|--------|-------|----------------------|----------|-------------------|
| E300 | `controle_e300.py` | Tous les GeoJSON | projection ≠ `Metadata.SRS` | `bloquant` | `ecarts_e300_projection.geojson` |
| E301 | `controle_e301.py` | Tous les GeoJSON | groupe d'entités détaché du réseau (> 500 m) | `bloquant` | `ecarts_e301_coherence_spatiale.geojson` |
| E302 | `controle_e302.py` | `RPD_GeometrieSupplementaire_Reco.geojson` | superficie > 100 m² | `bloquant` | `ecarts_e302_geometrie_supplementaire.geojson` |
| E303 | `controle_e303.py` | Tous les GeoJSON | entité hors emprise DR | `bloquant` | `ecarts_e303_emprise_dr.geojson` |

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

**Sortie — `ecarts_e300_projection.geojson` :** un `Feature` par entité non conforme,
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

**Ce qui est contrôlé :** détecte les entités dont la position est **aberrante** —
détachées du réseau, signe d'une faute de saisie de coordonnée.

**Algorithme — rattachement au réseau :**

Chaque entité est représentée par son **centroïde**. Les entités sont regroupées par
**proximité** (composantes connexes) : deux entités distantes d'au plus
`SEUIL_RATTACHEMENT` appartiennent au même groupe, la relation étant **transitive**.
Un réseau continu forme donc un groupe unique, quelle que soit son étendue totale.
Le groupe le plus nombreux constitue le réseau ; **toute entité d'un autre groupe est
signalée**.

**Pourquoi pas un écart à un point central.** Un réseau de distribution est linéaire et
ramifié, jamais circulaire autour de son centre : sa périphérie est naturellement
éloignée de tout point de référence, sans être aberrante. Mesurer l'écart à un centre
revient à mesurer l'**excentricité**, pas l'**aberration** — le résultat dépend alors de
la forme du jeu de données et non de la présence d'un défaut.

> **Historique.** Le contrôle appliquait la méthode de Tukey (`Q3 + 1,5 × IQR`) à la
> distance au médian spatial. Sur les jeux de référence, il signalait 29, 11, 29, 29, 73,
> 0 et 0 entités — au gré de leur forme. Toutes étaient des extensions légitimes du
> réseau : sur `Echantillon1/V11`, les 11 entités signalées avaient leur plus proche
> voisin à **0,00–0,06 m**, donc plus densément entourées que la moyenne du jeu (0,58 m).
> Le rattachement, lui, produit **0 anomalie sur les 7 jeux**.

**Pourquoi un regroupement et non un simple isolement.** Un critère par entité (« aucun
voisin à moins de X m ») manquerait un **lot d'entités décalées ensemble** : chacune
conserve alors des voisins immédiats. Le regroupement les détecte, leur groupe étant
détaché du réseau.

**Seuil de rattachement — `SEUIL_RATTACHEMENT = 500 m` :** calibré sur les jeux de
référence, où l'écart le plus large à l'intérieur d'un réseau réel atteint **245 m**
(portion desservie par une antenne) — soit une marge de 2×. À l'inverse, une faute de
saisie en Lambert 93 (chiffre erroné) déplace l'entité d'au moins un kilomètre.

**Performance :** le regroupement passe par une **grille spatiale au pas du seuil**. Deux
points distants de moins du seuil tombant nécessairement dans des cellules adjacentes,
seul le voisinage 3×3 de chaque cellule est examiné : le coût passe de `O(n²)` à
`O(n × k)`. Le rattachement utilise une union-find avec compression de chemin.

**Prérequis :** si le champ `crs` est présent dans les fichiers GeoJSON, le CRS doit
être **projeté** (coordonnées en mètres). Les CRS géographiques (en degrés) ne
permettent pas d'appliquer des distances euclidiennes significatives.
La vérification est effectuée via `pyproj`.

**Cas d'anomalie :** entité appartenant à un groupe autre que le groupe majoritaire.
Une anomalie est générée **par entité**, portant la taille de son groupe et la distance
de celui-ci au réseau.

**Conditions de rejet :** moins de 2 entités (aucun groupe majoritaire déterminable),
CRS géographique détecté, répertoire introuvable, aucun GeoJSON dans le répertoire.

**Sortie — `ecarts_e301_coherence_spatiale.geojson` :** un `Feature` par entité détachée,
**conservant sa géométrie d'origine**, avec les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`
- `distance_au_reseau_m` : distance séparant le groupe du réseau (en mètres)
- `taille_groupe` : nombre d'entités du groupe détaché — distingue la faute isolée
  (1 entité) du lot décalé en bloc
- `seuil_m` = `500.0`
- `type_anomalie` = `groupe_detache_du_reseau`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `entites_analysees`,
`fichiers_analyses`, `nombre_groupes`, `seuil_rattachement_m`, `sortie`.

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

**Sortie — `ecarts_e302_geometrie_supplementaire.geojson` :** un `Feature` par entité
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

**Exception métier — numéros d'affaire exclus :**

Avant toute exécution, le numéro d'affaire est confronté à une liste d'exclusions.
Si l'un des cas suivants est vérifié, E303 est **entièrement ignoré** (aucune
vérification effectuée, aucune anomalie générée, aucun fichier d'écarts produit) :

- numéro d'affaire exactement égal à `12345678` ;
- numéro d'affaire commençant par `OSR` ;
- numéro d'affaire commençant par `osr`.

La vérification (`affaire_exclue_du_controle`) intervient avant même le contrôle
de validité du répertoire. Le rapport renvoie alors `succes = true`,
`controle_ignore = true`, `nombre_anomalies = 0` et un champ `motif`. Dans tous
les autres cas, le comportement décrit ci-dessous s'applique sans changement.

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
(CRS EPSG:2154, Lambert 93), filtré sur le champ `code_dr_oa`. Les emprises
`Polygon` comme `MultiPolygon` sont prises en charge (DR discontinues), chaque
partie donnant une emprise autorisée. Si les GeoJSON analysés utilisent un autre
CRS projeté, les coordonnées sont automatiquement reprojetées vers EPSG:2154 via
`pyproj` avant le test de containment.

**Mutualisation :** la résolution du numéro d'affaire, le chargement des emprises,
le test de containment et la règle d'exclusion métier (`12345678`, préfixe `OSR`)
sont portés par `utils_emprise_dr_commun.py` (module commun `controle/`),
accessible via le module délégué `utils_emprise_dr.py`. Le contrôle E508 (câbles
HTB dans l'emprise DR) s'appuie sur les mêmes briques, exclusions comprises.

**Algorithme de containment — Ray Casting :**

Chaque entité est représentée par son centroïde. Le test d'appartenance utilise
l'algorithme du Ray Casting (Crossing Number) : un rayon horizontal est lancé depuis
le point et le nombre de croisements avec les arêtes du polygone est compté.
Une bounding box pré-calculée permet d'éviter le test complet pour les entités
manifestement hors zone.

**Cas d'anomalie :** entité dont le centroïde n'est inclus dans aucune des emprises DR
autorisées pour le numéro d'affaire donné.

**Sortie — `ecarts_e303_emprise_dr.geojson` :** un `Feature` par entité hors emprise,
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
