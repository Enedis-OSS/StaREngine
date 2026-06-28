# Journal des modifications

Toutes les modifications notables de ce projet sont consignées dans ce fichier.


## [Unreleased]

## [1.0.3] - 2026-06-28

### Ajouté

- **Contrôle E204 — Doublons spatiaux dans les points de levé**
  (`recostar/controle/altimetrie/controle_e204.py`) : détecte les entités
  `RPD_PointLeveOuvrageReseau_Reco` partageant exactement les mêmes coordonnées XY.
  Priorité : **information**. Sortie : `ecarts_doublons_spatiaux.geojson`.
  - Gestion multi-version (détection automatique depuis `TypeLeve`).
  - Option CLI `--version {auto,1.0,1.1}`.
- **Pipeline altimétrique — intégration E204**
  (`recostar/controle/altimetrie/pipeline_controle_alti.py`) : E204 ajouté en
  5ème position (E200 → … → E203 → E204).

- **Contrôle E205 — Cohérence points de levé / géométries supplémentaires de
  coffrets** (`recostar/controle/altimetrie/controle_e205.py`) : vérifie que
  chaque géométrie supplémentaire (`RPD_GeometrieSupplementaire_Reco`) liée à un
  coffret éligible possède au moins un point de levé
  (`RPD_PointLeveOuvrageReseau_Reco`) en superposition géographique planimetrique.
  Priorité : **bloquant**. Sortie : `ecarts_point_leve_geom_supp.geojson`.
  - **Gestion multi-version** : détection automatique depuis `TypeLeve` —
    v1.0 : tous les coffrets portant un `geometriesupplementaire_href` ;
    v1.1 : uniquement les coffrets dont `Statut` vaut `UnderCommissionning`.
  - Option CLI `--version {auto,1.0,1.1}`.
  - Détection spatiale planimetrique via `STRtree` Shapely
    (`predicate="intersects"`, Z ignoré).
  - 49 tests unitaires.
- **Pipeline altimétrique — intégration E205**
  (`recostar/controle/altimetrie/pipeline_controle_alti.py`) : E205 ajouté en
  6ème position (E200 → … → E204 → E205).
- **README altimétrique mis à jour** : documentation d'E204 et E205 (règles
  métier, comportement multi-version, format de sortie, rapport JSON).

- **Contrôle E300 — Conformité de projection**
  (`recostar/controle/projection/controle_e300.py`) : vérifie que l'ensemble
  des fichiers GeoJSON utilisent la projection déclarée dans `_metadata.json`
  (champ `Metadata.SRS`). Priorité : **bloquant**.
  Sortie : `ecarts_projection.geojson`.
- **Contrôle E301 — Cohérence spatiale des entités**
  (`recostar/controle/projection/controle_e301.py`) : identifie les entités
  anormalement éloignées du reste des données via la méthode de Tukey
  (Q3 + 1,5 × IQR). Seuil minimum : 4 entités. Priorité : **bloquant**.
  Sortie : `ecarts_coherence_spatiale.geojson`.
- **Contrôle E302 — Cohérence géométrique des géométries supplémentaires**
  (`recostar/controle/projection/controle_e302.py`) : vérifie que la superficie
  de chaque entité `RPD_GeometrieSupplementaire_Reco` ne dépasse pas 100 m².
  Priorité : **bloquant**. Sortie : `ecarts_geometrie_supplementaire.geojson`.
- **Contrôle E303 — Appartenance à l'emprise de la direction régionale**
  (`recostar/controle/projection/controle_e303.py`) : vérifie que les entités
  se situent dans l'emprise DR correspondant au numéro d'affaire fourni,
  à partir des référentiels `reference_dr.json` et `emprise_dr.geojson`.
  Priorité : **bloquant**. Sortie : `ecarts_emprise_dr.geojson`.
- **Pipeline de contrôle de projection**
  (`recostar/controle/projection/pipeline_controle_projection.py`) :
  orchestre les contrôles E300 à E303 de manière séquentielle avec isolation
  des erreurs.

- **Contrôle E400 — Superpositions géométriques entre cheminements**
  (`recostar/controle/cheminement/controle_e400.py`) : détecte les
  chevauchements spatiaux (totaux ou partiels) entre les entités linéaires des
  fichiers de cheminement. Priorité : **bloquant**.
  Sortie : `ecarts_superpositions_cheminements.geojson`.
- **Contrôle E401 — Intégrité des relations câbles / cheminements**
  (`recostar/controle/cheminement/controle_e401.py`) : vérifie la cohérence
  bidirectionnelle entre câbles et cheminements via `cables_href`.
  Priorité : **bloquant**.
  Sortie : `ecarts_integrite_cables_cheminements.geojson`.
- **Contrôle E402 — Cohérence câbles de terre / cheminements aériens**
  (`recostar/controle/cheminement/controle_e402.py`) : vérifie qu'aucune
  entité `RPD_CableTerre_Reco` n'est associée à un cheminement aérien ou de
  protection mécanique. Priorité : **bloquant**.
  Sortie : `ecarts_cable_terre_cheminement_incompatible.geojson`.
- **Contrôle E403 — Cohérence du mode d'implantation des câbles électriques**
  (`recostar/controle/cheminement/controle_e403.py`) : vérifie qu'un même
  câble électrique n'est pas simultanément associé à un cheminement aérien et
  à un cheminement souterrain. Priorité : **bloquant**.
  Sortie : `ecarts_cable_electrique_implantation_incoherente.geojson`.
- **Contrôle E404 — Profondeur manquante aux points de charge génératrice**
  (`recostar/controle/cheminement/controle_e404.py`) : vérifie que les
  cheminements souterrains superposés à un point de charge génératrice
  renseignent le champ `ProfondeurMinNonReg`. Priorité : **bloquant**.
  Sortie : `ecarts_charge_generatrice_profondeur_absente.geojson`.

- **Prise en charge de `RPD_Galerie_Reco` dans les convertisseurs V1.0 et V1.1**
  (`recostar/conversion/conversion_V1/geojson_to_recostar.py`,
  `recostar/conversion/conversion_V1/recostar_to_geojson.py`,
  `recostar/conversion/conversion_V1_1/geojson_to_recostar.py`,
  `recostar/conversion/conversion_V1_1/recostar_to_geojson.py`) :
  - **GeoJSON → GML** : nouveau mappeur `mapper_galerie()` respectant l'ordre strict
    XSD (`Geometrie → Hauteur → Largeur → PrecisionXY → PrecisionZ →
    ProfondeurMinNonReg`). `Hauteur` et `Largeur` sont des `gml:MeasureType` avec
    `uom="m"`. `ProfondeurMinNonReg` est optionnel (0..1).
  - **GML → GeoJSON** : nouveau extracteur `extract_galerie()` stockant la géométrie
    dans `cheminement_geometries` pour l'héritage de géométrie par les câbles associés
    via la relation `Cheminement_Cables`. La galerie est traitée en passe 2
    (cheminements), avant les câbles.
  - `RPD_Galerie_Reco` ajouté dans `REQUIRED_RPD_FILES`, `RPD_ENTITY_TYPES`,
    `chemin_types`, `cheminement_types` et les tables de dispatch (`type_mappers`,
    `extractors`). Conforme à la règle métier : une galerie peut être vide (sans
    câble associé).
  - **Tests** : 12 tests unitaires par version (6 par convertisseur), couvrant les
    cas nominaux (Hauteur/Largeur avec uom, géométrie LineString, stockage dans le
    cache cheminements) et les cas limites (galerie vide, profondeur absente/présente).
  - **Documentation** : section `RPD_Galerie_Reco` ajoutée dans les deux
    `GEOJSON_REFERENCE.md` (V1.0 et V1.1).

- **Gestion des dépendances avec Poetry** : migration vers Poetry pour la gestion
  de l'environnement virtuel et des dépendances (`pyproject.toml`, `poetry.lock`,
  `poetry.toml`). Mode non-package (`package-mode = false`) : l'architecture en
  sous-paquets indépendants reste inchangée. Les dépendances principales
  (`defusedxml`, `lxml`, `pyproj`, `reportlab`, `requests`) et de développement
  (`pytest`, `pytest-cov`, `coverage`, `pyinstaller`) sont désormais épinglées.
- **Pipeline de contrôle XSD/structuration**
  (`recostar/controle/xsd_structuration/pipeline_controle_xsd.py`) : orchestrateur
  exécutant l'ensemble des contrôles E110 à E114 sur un fichier GML, avec
  isolation des erreurs (l'échec d'un contrôle ne bloque pas les suivants) et
  production d'un rapport global `*_controle_xsd_global.json`.
- **Tests du pipeline XSD**
  (`recostar/controle/xsd_structuration/tests/test_pipeline_controle_xsd.py`) :
  couverture des cas nominaux (orchestration mockée) et bout en bout (contrôles
  réels), ainsi que des cas limites (fichier inexistant, échec partiel).
- **Documentation des paquets de contrôle** : ajout des `README.md` pour
  `recostar/controle/altimetrie` (E200-E203) et
  `recostar/controle/xsd_structuration` (E110-E114), décrivant ce que contrôle
  chaque script et le format des rapports de sortie.
- **Priorité dans les rapports JSON** des contrôles altimétriques : chaque
  rapport de contrôle expose désormais le champ `priorite`.

### Modifié

- **`pyproject.toml` — ajout de la table `[project]` (PEP 517/518)** : le fichier
  expose désormais les métadonnées standard (`name`, `version`, `requires-python`)
  en plus de la table `[tool.poetry]`. La version du projet est portée à `1.0.3`.
  Poetry reste le gestionnaire de dépendances et d'environnement virtuel
  (mode non-package, `package-mode = false`) ; l'architecture en sous-paquets
  indépendants avec imports à plat reste inchangée.
- **Renommage des contrôles altimétriques** selon la codification E2xx :
  - `controle_3d.py` → `controle_e200.py` (conformité 3D) ;
  - `controle_z_null.py` → `controle_e201.py` (altitude nulle) ;
  - `controle_alti_sommets.py` → `controle_e202.py` (altimétrie des sommets) ;
  - `controle_alti_ign.py` → `controle_e203.py` (altimétrie IGN).
  Imports, clés de rapport, docstrings et tests associés ont été mis à jour en
  conséquence (`pipeline_controle_alti.py` inclus).
- **Priorité du contrôle E200** (conformité 3D) passée à `bloquant`.

### Corrigé

- **E202 (altimétrie des sommets)** : correction d'un risque d'`IndexError`
  (SonarLint S6466) lors de la vérification de la dimension des coordonnées,
  désormais validée sur l'ensemble des points
  (`any(len(point) < 3 for point in coordonnees)`).
