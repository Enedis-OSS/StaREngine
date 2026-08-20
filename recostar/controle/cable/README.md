# Contrôles de câble

Ce dossier regroupe les contrôles de cohérence appliqués aux câbles des jeux de
données GeoJSON Recostar. Chaque contrôle parcourt un ou plusieurs fichiers
GeoJSON, détecte les anomalies et produit un fichier d'écarts GeoJSON (préfixé
`ecarts_`) directement exploitable dans QGIS (le `crs` du fichier source est
propagé).

Les fichiers d'écarts (`ecarts_*`) sont automatiquement exclus des analyses.

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
| E500 | `controle_e500.py` | Jonction, CableElectrique | `DomaineTension` d'un câble électrique lié ≠ `DomaineTension` de la jonction | `bloquant` | `ecarts_e500_coherence_domaine_tension.geojson` |
| E501 | `controle_e501.py` | CableElectrique, CableTerre, CableTelecommunication | incohérence métier entre `FonctionCable_href`, `DomaineTension` et `HierarchieBT` | `mineur` | `ecarts_e501_coherence_fonction_cable.geojson` |
| E502 | `controle_e502.py` | CableElectrique (`Statut = UnderCommissionning`) | combinaison de caractéristiques absente du référentiel des désignations normalisées | `bloquant` | `ecarts_e502_designation_normalisee.geojson` |
| E503 | `controle_e503.py` | CableElectrique (`Statut = UnderCommissionning`), Fourreau, PleineTerre, ProtectionMecanique | cheminement associé dont `PrecisionXY` ou `PrecisionZ` ≠ `A` | `bloquant` | `ecarts_e503_precision_cheminement_cable.geojson` |
| E504 | `controle_e504.py` | CableElectrique (`Statut = UnderCommissionning`, hors aériens) | segment entre deux sommets consécutifs > 15 m | `bloquant` | `ecarts_e504_densite_sommets_cable.geojson` |
| E505 | `controle_e505.py` | CableElectrique (`Statut = UnderCommissionning`, hors aériens) | longueur > 250 m (BT) ou > 500 m (HTA) | `information` | `ecarts_e505_longueur_domaine_tension.geojson` |
| E506 | `controle_e506.py` | CableElectrique, CableTerre (`Statut = UnderCommissionning`) | câble électrique sans nœud à chaque extrémité ; câble de terre sans `RPD_Terre_Reco` | `bloquant` / `majeur` | `ecarts_e506_raccordement_cable.geojson` |
| E507 | `controle_e507.py` | CableElectrique (`Statut = UnderCommissionning`), Jonction | jonction liée à un câble mais non posée exactement (XY) sur l'une de ses extrémités | `bloquant` | `ecarts_e507_jonction_extremite_cable.geojson` |
| E508 | `controle_e508.py` | CableElectrique (`Statut = UnderCommissionning`, `DomaineTension = HTB`) | câble HTB situé **dans** l'emprise DR du numéro d'affaire | `information` | `ecarts_e508_cable_htb_emprise_dr.geojson` |
| E509 | `controle_e509.py` | CableElectrique (`Statut = UnderCommissionning`, hors aériens) | sommet dont les **deux** flèches à l'arc reconstruit (cercle 3 points) atteignent 10 cm, ou dont **une** atteint 40 cm sur un virage de rayon < 15 m | `bloquant` | `ecarts_e509_discretisation_courbe_cable.geojson` |

Les fonctions utilitaires communes (lecture/écriture GeoJSON, extraction
d'identifiant) sont centralisées dans `utils_geojson.py` (délégation vers
`utils_geojson_commun.py`). L'extraction des références `cables_href` et la
liste de référence des types de nœuds sont fournies par `utils_cable.py`. La
résolution de l'emprise DR (E508) est fournie par `utils_emprise_dr.py`
(délégation vers `utils_emprise_dr_commun.py`, partagé avec E303).
L'orchestration de l'ensemble est assurée par `pipeline_controle_cable.py`.

### Usage CLI

```bash
python controle_e500.py --repertoire <chemin> [--sortie <chemin>]
python controle_e501.py --repertoire <chemin> [--sortie <chemin>]
python controle_e502.py --repertoire <chemin> [--sortie <chemin>]
python controle_e503.py --repertoire <chemin> [--sortie <chemin>]
python controle_e504.py --repertoire <chemin> [--sortie <chemin>]
python controle_e505.py --repertoire <chemin> [--sortie <chemin>]
python controle_e506.py --repertoire <chemin> [--sortie <chemin>]
python controle_e507.py --repertoire <chemin> [--sortie <chemin>]
python controle_e508.py --repertoire <chemin> --numero_affaire <numero> [--sortie <chemin>]
python controle_e509.py --repertoire <chemin> [--sortie <chemin>]

# Enchaînement de tous les contrôles ci-dessus :
python pipeline_controle_cable.py --repertoire <chemin> [--sortie <chemin>]
                                  [--numero_affaire <numero>]
```

- `--repertoire` : répertoire contenant les fichiers GeoJSON.
- `--sortie` : répertoire de sortie (par défaut, le répertoire d'entrée).
- `--numero_affaire` : requis par E508 uniquement (contrôle d'emprise DR).

Le résultat est imprimé en JSON sur la sortie standard.
Les fichiers absents du répertoire ne bloquent pas l'exécution.

---

## E500 — Cohérence du `DomaineTension` jonction / câbles électriques (`controle_e500.py`)

**Ce qui est contrôlé :** vérifie que chaque entité `RPD_Jonction_Reco` possède
exactement la même valeur de `DomaineTension` que chacun des câbles électriques
qu'elle référence via son champ `cables_href`.

**Règle de gestion :**

1. Parcourir les entités `RPD_Jonction_Reco`.
2. Pour chaque référence présente dans `cables_href`, récupérer le câble
   électrique correspondant.
3. Comparer le `DomaineTension` de la jonction à celui du câble.
4. Les deux valeurs doivent être **strictement identiques** ; toute différence
   (valeur distincte ou absence sur l'un des deux) génère une anomalie.

**Périmètre des câbles — uniquement `RPD_CableElectrique_Reco` :**

Dans le modèle RecoStaR (schéma XSD), seul `RPD_CableElectrique_Reco` porte
l'attribut `DomaineTension`. Les câbles de terre (`RPD_CableTerre_Reco`) et de
télécommunication (`RPD_CableTelecommunication_Reco`) n'ont pas de domaine de
tension. En conséquence :

- seules les références `cables_href` pointant vers un câble électrique sont
  comparées ;
- les références vers un câble de terre / télécommunication, ou vers un
  identifiant inexistant, sont **ignorées** — l'intégrité référentielle des
  `cables_href` relève du contrôle E401 (module `cheminement`).

**Versions :** `RPD_Jonction_Reco` et `RPD_CableElectrique_Reco` (attribut
`DomaineTension` inclus) ont une structure identique en RecoStaR **V1.0** et
**V1.1**. Le contrôle est donc **agnostique de version** : il s'applique tel quel
aux deux jeux de données, sans détection de version ni dépendance à
`RPD_PointLeveOuvrageReseau_Reco`. Les champs additionnels de la V1.1
(ex. `Commentaire`, `Etiquette`) sont sans effet sur le résultat.

**Cas d'anomalie :** un lien (jonction → câble électrique) dont les deux
`DomaineTension` diffèrent. Une jonction liée à plusieurs câbles électriques
incohérents produit **une anomalie par câble** fautif.

**Sortie — `ecarts_e500_coherence_domaine_tension.geojson` :** un `Feature` par lien
incohérent, portant la **géométrie de la jonction** (`Point`) pour la
localisation dans QGIS, avec les propriétés :

- `type_anomalie` = `domaine_tension_incoherent`
- `id_jonction` : identifiant de la jonction
- `id_cable` : identifiant du câble électrique lié
- `domaine_tension_jonction` : valeur portée par la jonction
- `domaine_tension_cable` : valeur portée par le câble
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_jonctions_analysees`, `nombre_cables_electriques`,
`nombre_liens_controles`, `fichier_jonction_absent`, `fichier_cable_absent`,
`sortie`.

**Comportement en l'absence de fichier :** si `RPD_Jonction_Reco.geojson` ou
`RPD_CableElectrique_Reco.geojson` est absent, le contrôle n'échoue pas : il
retourne `succes = true`, signale le fichier manquant via
`fichier_jonction_absent` / `fichier_cable_absent` et ne produit aucun fichier
d'écarts.

---

## E501 — Cohérence métier `FonctionCable_href` / `DomaineTension` / `HierarchieBT` (`controle_e501.py`)

**Ce qui est contrôlé :** vérifie, pour chaque type de câble, la cohérence entre
la fonction du câble (`FonctionCable_href`), son domaine de tension
(`DomaineTension`) et sa hiérarchie BT (`HierarchieBT`). Le champ
`FonctionCable_href` contient directement la valeur métier (et non un identifiant
à résoudre) dans les données Recostar sérialisées en GeoJSON.

**Règles par type de câble :**

*`RPD_CableElectrique_Reco` :*

- `FonctionCable_href` doit valoir `DistributionEnergie` ou `TransportEnergie`.
- Cohérence fonction / domaine :
  - `TransportEnergie` → `DomaineTension` doit être strictement `HTB` ;
  - `DistributionEnergie` → `DomaineTension` doit être `BT` ou `HTA`.
- Cohérence domaine / hiérarchie :
  - `DomaineTension = BT` → `HierarchieBT` peut être renseigné (autorisé) ;
  - `DomaineTension ≠ BT` (`HTA`, `HTB`…) → `HierarchieBT` ne doit contenir
    aucune valeur.

*`RPD_CableTerre_Reco` :* `FonctionCable_href` doit valoir `ProtectionCathodique`,
`MaltEquipot`, `Equipotentialite` ou `MiseTerre` ; toute autre valeur est une anomalie.

*`RPD_CableTelecommunication_Reco` :* `FonctionCable_href` doit valoir
`Communication` ; toute autre valeur est une anomalie.

**Cumul :** la règle sur `HierarchieBT` ne dépend que du `DomaineTension` ; elle
s'applique donc indépendamment de la validité de la fonction. Une même entité
peut ainsi produire **plusieurs anomalies** (une par règle violée).

**Versions :** les trois fichiers câble ont une structure identique en RecoStaR
**V1.0** et **V1.1** ; le contrôle est **agnostique de version**. Les champs
additionnels de la V1.1 (`Etiquette`, `Commentaire`…) sont sans effet.

**Sortie — `ecarts_e501_coherence_fonction_cable.geojson` :** un `Feature` par
non-conformité, **conservant la géométrie du câble** concerné, avec les
propriétés :

- `type_anomalie` ∈ {`fonction_cable_invalide`, `domaine_tension_fonction_incoherent`,
  `hierarchie_bt_interdite`}
- `fichier_source`, `id_cable`
- `fonction_cable`, `domaine_tension`, `hierarchie_bt` : valeurs en cause
- `priorite` = `mineur`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `anomalies_par_type`,
`nombre_cables_analyses`, `fichiers_absents`, `sortie`.

Les fichiers câble absents du répertoire ne bloquent pas l'exécution (listés
dans `fichiers_absents`).

---

## E502 — Désignation normalisée des câbles électriques (`controle_e502.py`)

**Ce qui est contrôlé :** vérifie que la combinaison des caractéristiques d'une
entité `RPD_CableElectrique_Reco` correspond à une entrée valide du référentiel
des désignations normalisées :

```
recostar/referentiels/cables/verificateur_designation_normal.json
```

**Périmètre :** uniquement les `RPD_CableElectrique_Reco` dont
`Statut = UnderCommissionning`. Compatible V1.0 et V1.1 (mêmes champs, référentiel
indépendant de la version).

**Champs comparés (dans cet ordre) :** `DomaineTension`, `HierarchieBT`,
`NombreConducteurs`, `Section`, `SectionNeutre`, `Isolant`, `Materiau`.

**Normalisation (indispensable) :** le référentiel et l'export GeoJSON n'utilisent
pas les mêmes conventions de sérialisation. La comparaison porte sur des valeurs
normalisées :

| Type | Règle | Exemple |
|------|-------|---------|
| chaîne | minuscules, sans espaces de bord (casse ignorée) | `"Reseau"` ↔ `"reseau"` |
| flottant entier | converti en entier | `70.0` ↔ `70` |
| valeur absente (`None`) | sentinelle du référentiel : `HierarchieBT` → `"0"`, `Section`/`SectionNeutre` → `0` | `None` ↔ `0` |

**Neutralisation de `HierarchieBT` en HTA :** le champ `HierarchieBT` ne qualifie
que les câbles **BT** — les 162 entrées HTA du référentiel portent toutes la
sentinelle `"0"`. Sa valeur est donc **ignorée quand `DomaineTension = HTA`**
(ramenée à `"0"` des deux côtés de la comparaison, la clé étant construite par la
même fonction pour le référentiel et pour la donnée). Sans cette neutralisation,
un câble HTA dont les 6 autres champs correspondent exactement à une désignation
du référentiel était signalé à tort. Un `HierarchieBT` renseigné sur un câble HTA
**reste détecté**, mais par **E501** seul (`hierarchie_bt_interdite`), dont c'est
précisément la règle. Les domaines **BT** et **HTB** conservent `HierarchieBT`
comme critère discriminant.

**Algorithme :** le référentiel est **chargé une seule fois** ; ses entrées sont
converties en clés normalisées et stockées dans un **`set`** (test d'appartenance
en `O(1)`, doublons de désignation dédupliqués). Chaque câble contrôlé est réduit
à sa clé normalisée : si elle est absente du `set`, une anomalie est générée.

**Cas d'anomalie :** aucune entrée du référentiel ne correspond à la combinaison
des 7 champs renseignés pour le câble.

**Sortie — `ecarts_e502_designation_normalisee.geojson` :** un `Feature` par câble non
conforme, **conservant sa géométrie d'origine**, avec les propriétés :

- `type_anomalie` = `designation_non_referencee`
- `fichier_source`, `id_cable`
- les 7 champs bruts (`DomaineTension`, `HierarchieBT`, `NombreConducteurs`,
  `Section`, `SectionNeutre`, `Isolant`, `Materiau`) sous leur nom d'origine
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_cables_controles`, `nombre_entrees_referentiel`, `fichier_cable_absent`,
`sortie`.

**Erreurs remontées :** référentiel introuvable ou illisible (erreur bloquante),
répertoire introuvable. L'absence du fichier `RPD_CableElectrique_Reco.geojson`
n'est pas bloquante (signalée via `fichier_cable_absent`).

---

## E503 — Précision des cheminements associés à un câble électrique (`controle_e503.py`)

**Ce qui est contrôlé :** vérifie que tous les cheminements qui référencent un
câble électrique en cours de mise en service possèdent `PrecisionXY = A` **et**
`PrecisionZ = A`.

**Périmètre :** câbles `RPD_CableElectrique_Reco` dont `Statut = UnderCommissionning`.
Cheminements analysés (porteurs du champ `cables_href`) : `RPD_Fourreau_Reco`,
`RPD_PleineTerre_Reco`, `RPD_ProtectionMecanique_Reco`. Compatible V1.0 et V1.1.

**Sens de la relation :** c'est le **cheminement** qui porte `cables_href`
pointant vers le câble (même mécanisme que le contrôle d'intégrité E401).

**Algorithme :**

1. Chargement des identifiants des câbles électriques à contrôler dans un `set`
   (filtre `Statut`, appartenance en `O(1)`).
2. Parcours **unique** des trois couches de cheminement : construction d'un index
   `dict[id_câble → liste de cheminements]`, ne conservant que les cheminements
   référençant un câble contrôlé (filtrage par le `set` d'identifiants).
   L'extraction des références réutilise `utils_cable.extraire_ids_cables_href`.
3. Pour chaque lien (câble, cheminement) indexé, contrôle de
   `PrecisionXY == "A"` et `PrecisionZ == "A"`.

**Cas d'anomalie :** un cheminement associé à un câble contrôlé dont `PrecisionXY`
**ou** `PrecisionZ` diffère de `A`. Une anomalie est générée **par lien
(câble, cheminement) non conforme**. Un câble sans cheminement associé est
conforme (aucune anomalie).

**Sortie — `ecarts_e503_precision_cheminement_cable.geojson` :** un `Feature` par
cheminement non conforme, **conservant la géométrie du cheminement** (localisation
de la valeur incorrecte), avec les propriétés :

- `type_anomalie` = `precision_cheminement_non_conforme`
- `id_cable` : identifiant du câble électrique contrôlé
- `fichier_cheminement`, `id_cheminement`
- `precision_xy`, `precision_z` : valeurs en cause
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_cables_controles`, `nombre_liens_controles`, `fichier_cable_absent`,
`fichiers_cheminement_absents`, `sortie`.

Les fichiers absents (câble ou cheminements) ne bloquent pas l'exécution.

---

## E504 — Densité de sommets des câbles électriques (`controle_e504.py`)

**Ce qui est contrôlé :** vérifie que chaque câble électrique en cours de mise en
service possède une densité de sommets suffisante — aucun segment entre deux
sommets consécutifs ne doit dépasser **15 mètres** (au moins un sommet tous les
15 m le long de la géométrie).

**Périmètre :** câbles `RPD_CableElectrique_Reco` dont `Statut = UnderCommissionning`.
Les câbles référencés par un cheminement aérien sont **exclus**. Compatible
V1.0 et V1.1.

**Exclusion aérienne :** identique aux contrôles E202 / E208 — l'ensemble des
identifiants de câbles présents dans `RPD_Aerien_Reco.cables_href` est chargé dans
un `set` (appartenance en `O(1)`) via `charger_ids_cables_aeriens`. Les câbles
aériens, dont les portées entre poteaux dépassent naturellement 15 m, ne sont
donc pas contrôlés. L'absence du fichier aérien n'est pas bloquante.

**Calcul de distance — 3D :** la distance entre deux sommets consécutifs est
calculée en 3D (`√(dx² + dy² + dz²)`), selon la convention du calcul de longueur
du projet (`recostar/traitement/calcul_longueurs`). Un sommet sans composante Z
est traité en 2D (`dz = 0`). Pour un `MultiLineString`, les segments sont évalués
**au sein de chaque partie** (aucun segment fictif entre parties disjointes).

**Cas d'anomalie :** au moins un segment strictement supérieur à 15 m
(exactement 15 m est conforme). Une anomalie est générée **par câble** non conforme.

**Sortie — `ecarts_e504_densite_sommets_cable.geojson` :** un `Feature` par câble non
conforme, **conservant sa géométrie d'origine**, avec les propriétés :

- `type_anomalie` = `densite_sommets_insuffisante`
- `fichier_source`, `id_cable`
- `distance_max_m` : longueur du plus long segment (arrondie à 2 décimales)
- `seuil_m` = `15.0`
- `nombre_segments_trop_longs` : nombre de segments dépassant le seuil
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_cables_controles`, `nombre_cables_aeriens_exclus`, `seuil_m`,
`fichier_cable_absent`, `sortie`.

---

## E505 — Cohérence longueur / `DomaineTension` des câbles électriques (`controle_e505.py`)

**Ce qui est contrôlé :** vérifie que la longueur d'un câble électrique en cours
de mise en service reste compatible avec son domaine de tension :

| `DomaineTension` | Seuil de longueur | Au-delà |
|------------------|-------------------|---------|
| `BT` | 250 m | anomalie |
| `HTA` | 500 m | anomalie |
| autres (`HTB`…) | — | aucune vérification |

**Périmètre :** câbles `RPD_CableElectrique_Reco` dont `Statut = UnderCommissionning`,
hors câbles aériens. Compatible V1.0 et V1.1.

**Réutilisation :** l'exclusion aérienne (`charger_ids_cables_aeriens`) et la
décomposition géométrique (`_extraire_parties`) sont **importées du contrôle
E504**. La longueur est calculée en 3D (somme des distances `√(dx²+dy²+dz²)` entre
sommets consécutifs, toutes parties confondues), selon la convention du calcul de
longueur du projet.

**Sélection par table de seuils :** `SEUILS_LONGUEUR = {"BT": 250, "HTA": 500}`.
Le seuil applicable est obtenu par un simple `dict.get(DomaineTension)` : les
domaines absents de la table (ex. `HTB`) renvoient `None` et sont ignorés sans
traitement supplémentaire.

**Cas d'anomalie :** longueur strictement supérieure au seuil du domaine
(exactement le seuil est conforme). Une anomalie est générée **par câble**.

**Priorité : `information`** (non bloquante).

**Sortie — `ecarts_e505_longueur_domaine_tension.geojson` :** un `Feature` par câble
non conforme, **conservant sa géométrie d'origine**, avec les propriétés :

- `type_anomalie` = `longueur_excessive`
- `fichier_source`, `id_cable`
- `domaine_tension`
- `longueur_m` : longueur 3D calculée (arrondie à 2 décimales)
- `seuil_m` : seuil appliqué (`250.0` ou `500.0`)
- `priorite` = `information`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_cables_controles`, `nombre_cables_aeriens_exclus`, `fichier_cable_absent`,
`sortie`.

---

## E506 — Raccordement des câbles aux nœuds du réseau (`controle_e506.py`)

**Ce qui est contrôlé :** vérifie que les câbles en cours de mise en service sont
effectivement raccordés au réseau. Deux règles indépendantes, de priorités
différentes, alimentent un fichier d'écarts unique.

### Identification des types de nœuds — source de vérité unique

La liste des types d'entités constituant les **nœuds du réseau** n'est pas
redéfinie dans ce contrôle. Elle est importée de la constante
`TYPES_NOEUDS_RESEAU` du module de conversion
(`recostar/conversion/conversion_V1_1/geojson_to_recostar.py`), qui l'utilise
déjà pour extraire les relations `CableElectrique_NoeudReseau`. L'accès se fait
via `utils_cable.charger_types_noeuds_reseau()`, mis en cache (`lru_cache`) pour
ne charger le module qu'une fois par processus.

Les neuf types concernés — seules entités porteuses du champ `cables_href` au
titre de la relation nœud ↔ câble :

`RPD_CoupeCircuitAFusibles_Reco`, `RPD_JeuBarres_Reco`, `RPD_Jonction_Reco`,
`RPD_ModuleRaccordement_Reco`, `RPD_OuvrageCollectifBranchement_Reco`,
`RPD_PointDeComptage_Reco`, `RPD_PosteElectrique_Reco`,
`RPD_SupportModules_Reco`, `RPD_Terre_Reco`.

> Les **cheminements** (`RPD_Fourreau_Reco`, `RPD_Aerien_Reco`…) portent eux
> aussi un champ `cables_href`, mais ne sont **pas** des nœuds : ils sont hors
> périmètre de ce contrôle (leur intégrité relève de E401).

La liste est **identique en V1.0 et V1.1** ; le contrôle est donc **agnostique de
version**, comme E500 à E505. Un test vérifie que les deux versions déclarent
bien les mêmes types.

### Règle 1 — Raccordement des câbles électriques (`bloquant`)

**Périmètre :** `RPD_CableElectrique_Reco` dont `Statut = UnderCommissionning`.

Chaque câble doit être raccordé à un nœud à **chacune de ses deux extrémités**.
Deux défauts distincts sont détectés, et ils sont **mutuellement exclusifs** —
un câble produit **au plus une anomalie** :

| Défaut | Condition | Type d'anomalie |
|--------|-----------|-----------------|
| Relationnel | aucun nœud ne référence le câble | `cable_sans_noeud` |
| Relationnel | un seul nœud référence le câble | `cable_noeud_unique` |
| Topologique | ≥ 2 nœuds, mais une extrémité n'est couverte par aucun d'eux | `extremite_non_raccordee` |

Le contrôle topologique ne s'applique qu'à partir de deux nœuds : en deçà, le
défaut est déjà qualifié par la règle relationnelle et couvrir deux extrémités
serait de toute façon impossible.

**Extrémités topologiques :** les parties d'un `MultiLineString` RecoStaR ne sont
**ni ordonnées ni orientées** — le premier sommet de la première partie peut
coïncider avec le dernier sommet de la dernière. Prendre le premier et le dernier
sommet après mise à plat donnerait donc des extrémités fausses (jusqu'à deux
points confondus). Les vraies extrémités sont les bouts de partie qui n'en
rejoignent aucun autre, c'est-à-dire les sommets apparaissant un **nombre impair
de fois** parmi les bouts de partie. Un `LineString` retombe naturellement sur ses
deux bouts.

**Affectation des nœuds — sans seuil de distance :** chaque nœud lié est rattaché
à l'extrémité dont il est le **plus proche** (comparaison relative en 2D). Aucune
tolérance n'est à paramétrer : un nœud reste correctement affecté même s'il est
distant de plusieurs mètres du bout de câble qu'il raccorde — cas courant d'un
poste électrique représenté par un point unique. Le Z est ignoré : l'affectation
n'en a pas besoin et y gagne en robustesse face au bruit altimétrique que les
contrôles E200 à E209 ont précisément pour rôle de détecter.

**Cas laissés conformes (aucune anomalie topologique) :**

- géométrie absente, fermée (boucle) ou ramifiée — la notion de « deux bouts »
  n'est pas définie ; seule la règle relationnelle s'applique ;
- moins de deux nœuds **localisés** (sans géométrie `Point`) — une extrémité
  paraîtrait libre alors que le défaut porterait sur la géométrie des nœuds, et
  non sur le raccordement, déjà validé par la règle relationnelle.

### Règle 2 — Raccordement des câbles de terre (`information`)

**Périmètre :** `RPD_CableTerre_Reco` dont `Statut = UnderCommissionning`.

Chaque câble de terre doit être relié à **au moins une** entité
`RPD_Terre_Reco`. Les **deux sens de liaison** présents dans le modèle RecoStaR
sont acceptés, un seul suffit :

1. `RPD_CableTerre_Reco.noeudreseau_href` → identifiant d'un `RPD_Terre_Reco`
   (sens produit par la conversion, cf. `mapper_cable_terre`) ;
2. `RPD_Terre_Reco.cables_href` → identifiant du câble de terre (sens entretenu
   par la propagation en conteneur, cf. `_nettoyer_cables_noeud_terre`).

La référence doit pointer vers une prise de terre **existante** : un
`noeudreseau_href` désignant une entité absente ou d'un autre type ne vaut pas
raccordement (type `cable_terre_non_raccorde`).

**Absence du fichier `RPD_Terre_Reco.geojson` :** contrairement à la convention
des autres contrôles, l'absence du fichier **ne neutralise pas** la règle. Sans
aucune prise de terre, aucun câble de terre ne peut être raccordé : l'absence
**est** le défaut. Tous les câbles de terre contrôlés sont alors signalés, et le
rapport porte `fichier_terre_absent = true` pour expliquer le volume. La priorité
`information` rend ce signalement non bloquant.

### Sortie — `ecarts_e506_raccordement_cable.geojson`

Un `Feature` par câble non conforme, **conservant la géométrie du câble** pour la
localisation dans QGIS. Les deux règles cohabitent dans le fichier ; la priorité
étant portée par chaque `Feature`, elle diffère selon la règle :

- `type_anomalie` ∈ {`cable_sans_noeud`, `cable_noeud_unique`,
  `extremite_non_raccordee`, `cable_terre_non_raccorde`}
- `id_cable` : identifiant du câble en cause
- `priorite` : `bloquant` (règle 1) ou `information` (règle 2)
- `nombre_noeuds`, `types_noeuds` : règle 1 — nœuds liés et types concernés
- `nombre_extremites_libres` : règle 1, défaut topologique uniquement
- `noeudreseau_href` : règle 2 — valeur en cause (éventuellement `null`)

Les champs propres à une règle sont **omis** des features de l'autre.

**Rapport JSON :** `succes`, `priorites` (priorité de chaque type d'anomalie),
`nombre_anomalies`, `anomalies_par_type`, `nombre_cables_electriques_controles`,
`nombre_cables_terre_controles`, `nombre_noeuds_indexes`, `nombre_terres`,
`fichier_cable_electrique_absent`, `fichier_cable_terre_absent`,
`fichier_terre_absent`, `fichiers_noeuds_absents`, `sortie`.

> Ce contrôle produisant des anomalies de **deux priorités**, il expose un
> dictionnaire `priorites` (par type d'anomalie) là où E500 à E505 exposent un
> champ `priorite` scalaire.

---

## E507 — Position des jonctions sur les extrémités des câbles (`controle_e507.py`)

**Ce qui est contrôlé :** vérifie que chaque `RPD_Jonction_Reco` liée à un câble
électrique en cours de mise en service est positionnée **exactement sur l'une des
extrémités** de la géométrie de ce câble.

**Périmètre :** câbles `RPD_CableElectrique_Reco` dont
`Statut = UnderCommissionning`. Compatible V1.0 et V1.1 (champs et géométries
identiques, contrôle agnostique de version).

**Sens de la relation :** c'est la **jonction** qui porte `cables_href` pointant
vers le câble (même mécanisme que E500 et E506).

**Règle de gestion :**

1. Parcourir les entités `RPD_Jonction_Reco` porteuses d'au moins une référence.
2. Ne retenir que les références pointant vers un câble électrique contrôlé.
3. Comparer le point de la jonction aux extrémités du câble.
4. Toute jonction ne coïncidant avec **aucune** extrémité génère une anomalie.

**Être sur le tracé ne suffit pas.** Une jonction posée sur un sommet
intermédiaire, ou sur un point quelconque d'un segment, est **non conforme** :
seule une coïncidence avec une extrémité l'est. C'est le cœur de la règle.

**Comparaison planimétrique (XY), sans tolérance :** la coïncidence est évaluée
sur X et Y par **égalité stricte**. Les données de référence le valident — les
**96 liens** jonction/câble des cinq échantillons sont exacts au bit près ;
aucune tolérance n'est donc à introduire ni à justifier.

Le **Z est écarté**, comme dans E506. Un cas réel (Echantillon3) présente une
jonction à `610.66 m` et une extrémité de câble à `610.67 m` pour un XY identique
au bit près : cet écart d'un centimètre traduit un arrondi altimétrique, pas un
défaut de raccordement. Le signaler en `bloquant` serait un faux positif ; la
cohérence altimétrique relève des contrôles **E200 à E209**, dont c'est le rôle.

**Extrémités topologiques — réutilisation d'E506 :** la décomposition
géométrique réutilise `extraire_extremites` (contrôle E506), qui retourne les
extrémités **topologiques** et non le premier/dernier sommet après mise à plat.
Les parties d'un `MultiLineString` RecoStaR n'étant ni ordonnées ni orientées,
l'interprétation littérale produirait **10 fausses anomalies** sur les
échantillons, contre **0** pour l'approche topologique. L'extraction du point de
la jonction réutilise `_extraire_point` (E506) — les deux fonctions renvoient
déjà des coordonnées 2D, le test de conformité se réduit donc à une appartenance
à un `frozenset` (`O(1)`, égalité exacte).

**Optimisation :** les extrémités d'un câble sont **mémorisées** au premier lien
rencontré (`_obtenir_extremites`). Un câble étant généralement référencé par deux
jonctions, sa géométrie n'est décomposée qu'une seule fois. Les jonctions
dépourvues de `cables_href` sont écartées dès le chargement.

**Cas laissés conformes :**

- référence vers un câble d'un autre statut, d'un autre type ou inexistant —
  hors périmètre (l'intégrité référentielle relève d'E401, la présence d'un nœud
  à chaque extrémité d'E506) ;
- jonction sans géométrie `Point` ;
- câble dont la géométrie est absente, non linéaire ou fermée : aucune extrémité
  n'est définie, la conformité ne peut être tranchée. Ces câbles sont comptés
  dans `nombre_cables_geometrie_non_exploitable` plutôt qu'ignorés silencieusement.

**Cas d'anomalie :** une anomalie est générée **par lien (jonction, câble)** non
conforme. Une jonction liée à trois câbles et mal positionnée en produit trois.

**Sortie — `ecarts_e507_jonction_extremite_cable.geojson` :** un `Feature` par lien non
conforme, portant la **géométrie de la jonction** (`Point`) — c'est l'entité à
repositionner, donc le point à localiser dans QGIS — avec les propriétés :

- `type_anomalie` = `jonction_hors_extremite`
- `id_jonction` : identifiant de la jonction mal positionnée
- `id_cable` : identifiant du câble électrique concerné
- `distance_extremite_m` : distance planimétrique à l'extrémité la plus proche
  (arrondie à 3 décimales). **Valeur de diagnostic uniquement** : elle indique
  l'ampleur du décalage (quelques centimètres ou plusieurs dizaines de mètres) et
  n'intervient pas dans la décision de conformité, qui reste une égalité stricte.
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_cables_controles`, `nombre_jonctions_analysees`, `nombre_liens_controles`,
`nombre_cables_geometrie_non_exploitable`, `fichier_cable_absent`,
`fichier_jonction_absent`, `sortie`.

Les fichiers absents (câble ou jonction) ne bloquent pas l'exécution.

---

## E508 — Câbles HTB situés en Métropole (`controle_e508.py`)

**Ce qui est contrôlé :** vérifie qu'aucun câble électrique **HTB** en cours de
mise en service ne se situe **dans** l'emprise géographique de la direction
régionale résolue depuis le numéro d'affaire.

**Périmètre :** entités `RPD_CableElectrique_Reco` cumulant
`Statut = UnderCommissionning` et `DomaineTension = HTB`. Le filtre est appliqué
dès le chargement : les autres câbles ne sont pas conservés en mémoire.
Compatible V1.0 et V1.1 (champs identiques, contrôle agnostique de version).

**Règle de gestion :**

1. Résoudre le numéro d'affaire vers un ou plusieurs codes DR, puis charger les
   emprises correspondantes.
2. Ne retenir que les câbles électriques HTB au statut `UnderCommissionning`.
3. Toute entité retenue dont le centroïde est **inclus** dans l'une des emprises
   autorisées génère une anomalie.

**Sens inverse d'E303.** E303 signale les entités **hors** emprise DR ; E508
signale les câbles HTB **dans** l'emprise. Le réseau HTB relevant du transport,
sa présence dans une emprise de distribution est remontée pour analyse — d'où la
priorité `information`, non déclassante.

**Référentiel et géométrie — réutilisation d'E303 :** la résolution du numéro
d'affaire (formats `RAC-CVL-25-007998` et `DA21/256553`), le chargement des
emprises depuis `projection/fichiers_dr/emprise_dr.geojson` (EPSG:2154) et le
test de containment par Ray Casting avec filtrage bbox proviennent du module
commun `utils_emprise_dr_commun.py`. Si le fichier câble est dans un autre CRS
projeté, ses coordonnées sont reprojetées vers EPSG:2154 via `pyproj` avant le
test ; le transformateur est créé **une seule fois** pour le fichier, hors boucle
d'entités.

**Exclusions métier — mêmes que E303 :** le contrôle est **entièrement ignoré**
(aucune vérification, aucune anomalie, aucun fichier d'écarts) lorsque le numéro
d'affaire vaut exactement `12345678` ou commence par `OSR` / `osr`. Ces numéros
ne sont pas résolvables dans le référentiel DR : sans cette règle, ils
produiraient une erreur « Format de numéro d'affaire non reconnu » et
déclasseraient la famille en « Incomplet ». La vérification précède tout
chargement ; le rapport porte alors `controle_ignore = true`,
`nombre_anomalies = 0` et un champ `motif`. Le prédicat
`affaire_exclue_du_controle` est mutualisé dans `utils_emprise_dr_commun.py`.

**Cas laissés conformes :**

- câble d'un autre statut ou d'un autre domaine de tension (hors périmètre) ;
- câble sans géométrie ou de géométrie vide : aucun point représentatif ne peut
  être calculé, l'entité n'est pas comptée dans `nombre_cables_analyses`.

**Sortie — `ecarts_e508_cable_htb_emprise_dr.geojson` :** un `Feature` par câble
concerné, **conservant sa géométrie d'origine** — c'est l'objet à localiser dans
QGIS — avec les propriétés :

- `type_anomalie` = `cable_htb_dans_emprise_dr`
- `id_cable` : identifiant du câble électrique concerné
- `type_geometrie` : type de la géométrie du câble
- `domaine_tension` = `HTB`
- `codes_dr` : codes DR de l'emprise contrôlée (ex. `8A` ou `1Z, 2Z` si plusieurs)
- `priorite` = `information`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `nombre_cables_htb`,
`nombre_cables_analyses`, `numero_affaire`, `codes_dr`, `fichier_cable_absent`,
`sortie`.

**Erreurs remontées :** paramètre `--numero_affaire` absent, format du numéro non
reconnu, trigramme ou référence dossier absente de `reference_dr.json`, DR sans
emprise (zones SEI), répertoire introuvable. L'absence du fichier câble n'est
**pas** bloquante : elle est reportée dans `fichier_cable_absent`.

---

## E509 — Discrétisation des courbes des câbles électriques (`controle_e509.py`)

**Ce qui est contrôlé :** vérifie qu'une courbe portée par un câble électrique en
cours de mise en service comporte assez de sommets pour rester fidèle à son tracé
réel. Une courbe rendue par trop peu de segments est remplacée par une ligne
brisée dont chaque corde s'écarte de l'arc véritable : c'est cet écart — la
**flèche** — qui est mesuré.

**Périmètre :** entités `RPD_CableElectrique_Reco` au `Statut = UnderCommissionning`.
Comme dans E202, E208, E504 et E505, les câbles référencés par un cheminement
aérien (`RPD_Aerien_Reco.cables_href`) sont **exclus** : la géométrie d'un câble
aérien suit une portée entre supports, dont la courbure ne relève pas de la
discrétisation d'un tracé au sol. Compatible V1.0 et V1.1 (géométries
identiques, contrôle agnostique de version).

**Règle de gestion, en deux temps :**

1. **Filtrage des sommets.** Après nettoyage du tracé, tout sommet dont le
   changement de direction est **inférieur à 3°** est ignoré : le tracé y est
   droit à la précision du levé, il n'y a pas d'arc à contrôler.
2. **Classement du sommet.** Sur les sommets restants, l'arc est reconstruit
   localement et **deux** flèches sont mesurées — une par corde adjacente.
   Le sommet est classé par deux déclencheurs indépendants (détail ci-dessous).

### Méthode : rayon, corde, flèche

Trois sommets consécutifs A, B, C définissent un **cercle unique** — le cercle
circonscrit au triangle ABC. Son rayon donne la courbure locale du câble :

```
R = (|AB| · |BC| · |AC|) / (2 · |AB ∧ BC|)
```

De ce rayon et de la longueur d'une corde tracée on tire la **flèche**, c'est-à-dire
l'écart maximal entre le segment dessiné et la courbe réelle :

```
f = R − √(R² − c²/4)          forme inverse :  R = (c² + 4f²) / (8f)
```

Chaque sommet est évalué sur ses **deux cordes adjacentes** (celle qui y arrive
et celle qui en repart) ; la plus grande des deux flèches est retenue.

Références : « Calcul Rayon-Flèche-corde d'un arc »
([metabricoleur.com/t13942](http://www.metabricoleur.com/t13942-calcul-rayon-fleche-corde-d-un-arc))
et « Cercle 3 pts »
([scribd.com/document/340858108](https://fr.scribd.com/document/340858108/Cercle-3pts)).

**Pourquoi passer par le rayon.** La distance d'un sommet à la corde de ses deux
voisins — la mesure directe — est **bornée par la longueur des segments** : sur
des cordes de 20 cm elle ne peut mathématiquement pas atteindre 40 cm, quel que
soit l'angle. Le rayon, lui, est une grandeur **intrinsèque à la courbe** : il ne
dépend pas de la finesse du découpage. La flèche qu'on en tire mesure donc
l'erreur réellement commise au sol, ce qui rend les seuils comparables à toutes
les échelles.

### Classement d'un sommet

Deux défauts distincts sont recherchés, par **deux déclencheurs indépendants** —
un seul suffit :

| Déclencheur | Condition | Défaut détecté |
|---|---|---|
| **A** — arc uniformément sous-décrit | les **deux** flèches ≥ **10 cm** | tout le virage manque de sommets |
| **B** — corde isolée trop longue | **une** flèche ≥ **40 cm** et rayon < **15 m** | un sommet manque à cet endroit précis |

Deux exceptions ramènent le sommet à **conforme** :

- les deux flèches restent sous 10 cm : le tracé suit l'arc de près ;
- un seul écart significatif, porté par une corde de **moins d'un mètre** : un
  virage serré décrit sur un segment très court est un détail de tracé.

**Priorité.** Toutes les anomalies du contrôle sont **bloquantes** : une courbe
insuffisamment discrétisée décrit le câble ailleurs qu'où il se trouve, le
récolement ne peut pas être exploité en l'état. E509 suit donc la convention
scalaire majoritaire (`priorite`), comme E500 à E508.

Deux **types** d'anomalie restent distingués — ils décrivent des défauts
différents, non des gravités différentes, et servent au diagnostic :

| Type | Signification |
|---|---|
| `courbe_non_discretisee` | les **deux** flèches atteignent 40 cm : la courbe n'est pas décrite du tout |
| `courbe_mal_discretisee` | tous les autres cas retenus |

Le rapport JSON conserve `anomalies_par_type` à titre informatif.

**Pourquoi le garde-fou de rayon ne vise que le déclencheur B.** Sur une courbe
très ample, une corde longue s'écarte arithmétiquement de l'arc sans que le câble
soit mal placé — seule la forme est lissée. Mesuré sur le jeu Echantillon2 : une
corde de 11,9 m sur un rayon de 34 m donne 53 cm de flèche, alors que le tracé
reste fidèle. Le déclencheur A, lui, n'a pas besoin de ce garde-fou : il faudrait
que **les deux** cordes soient longues, ce qui est déjà un arc grossier.

### Ordres de grandeur

Corde maximale admissible avant de dépasser 40 cm de flèche, par rayon de
courbure :

| Rayon de courbure | Corde maximale | Angle par sommet |
|---|---|---|
| 2 m | 2,40 m | 73,7° |
| 5 m | 3,92 m | 46,1° |
| 10 m | 5,60 m | 32,5° |
| 20 m | 7,96 m | 23,0° |
| 50 m | 12,62 m | 14,5° |
| 100 m | 17,87 m | 10,3° |
| 200 m | 25,29 m | 7,2° |
| 500 m | 39,99 m | 4,6° |

Flèche obtenue selon le découpage, pour un arc de 90° (× = non conforme) :

| Segments | R = 2 m | R = 10 m | R = 50 m | R = 200 m |
|---|---|---|---|---|
| 2 | 0,15 m | 0,76 m × | 3,81 m × | 15,22 m × |
| 3 | 0,07 m | 0,34 m | 1,70 m × | 6,81 m × |
| 4 | 0,04 m | 0,19 m | 0,96 m × | 3,84 m × |
| 6 | 0,02 m | 0,09 m | 0,43 m × | 1,71 m × |
| 8 | 0,01 m | 0,05 m | 0,24 m | 0,96 m × |
| 12 | 0,00 m | 0,02 m | 0,11 m | 0,43 m × |
| 20 | 0,00 m | 0,01 m | 0,04 m | 0,15 m |

Lecture : **plus la courbe est ample, plus elle exige de sommets** pour un même
écart au sol. Attention toutefois : sur une courbe très ample (rayon ≥ 15 m), un
écart porté par une **seule** corde n'est plus signalé — c'est le garde-fou du
déclencheur B.

**Cas laissés conformes :**

- tracé rectiligne, ou câble à deux sommets : aucun sommet intermédiaire ;
- tout sommet tournant de moins de 3°, quelle que soit la longueur des segments ;
- les deux flèches sous 10 cm ;
- écart significatif isolé dès que **l'une des deux cordes** encadrant le sommet
  mesure moins d'un mètre — voir « échantillonnage dissymétrique » ci-dessous ;
- écart isolé, même supérieur à 40 cm, sur une courbe de rayon ≥ 15 m ;
- sommets dupliqués ou parfaitement alignés : retirés au nettoyage ;
- câbles portés par un cheminement aérien.

**Échantillonnage dissymétrique.** Le déclencheur B exige que **les deux** cordes
encadrant le sommet atteignent 1 m. La raison est de fond : le défaut recherché
est un *manque* de sommets, or deux sommets distants de quelques centimètres
établissent exactement le contraire — le tracé y est localement sur-échantillonné.
Sur un tel triangle, le cercle reconstruit est dicté par l'orientation du
micro-segment, la mesure la plus bruitée du jeu : à 8 cm, une erreur de levé d'un
centimètre vaut 7° de gisement. La flèche prêtée à la longue corde n'est alors
plus une mesure mais une **extrapolation** — entre ses deux extrémités, aucun
sommet n'atteste d'une quelconque courbure.

Les câbles RecoStaR portent régulièrement de tels micro-segments : ce sont leurs
**raccords terminaux dans les boîtes**. Le câble `idb70c029c` du jeu Echantillon
en est l'illustration — un talon de 8 cm, 7,97 m de ligne droite, un talon de
11 cm :

| Sommet | Segment précédent |
|---|---|
| #1 | 0,46 m |
| #2 | **0,08 m** |
| #3 | 7,97 m |
| #4 | 0,11 m |

Le câble est rigoureusement droit sur 8 m ; E509 lui attribuait pourtant une
flèche de 1,73 m sur un rayon reconstruit de 5,46 m. Le déclencheur A n'a pas
besoin de cette réserve : il exige deux flèches significatives, ce qu'une
micro-corde ne peut pas produire — la courbure y est corroborée des deux côtés.

Effet mesuré : Echantillon **5 → 0** anomalies, Echantillon2 **13 → 7** (les 7
restantes relèvent toutes du déclencheur A, cordes de longueurs comparables), et
le nombre de sommets évalués est inchangé — le garde-fou classe le sommet, il ne
l'exclut pas de la mesure.

**Point de vigilance.** Un **coude volontaire** — angle droit au coin d'une rue —
est mesuré comme un arc et signalé dès lors qu'il déclenche A ou B : aucun câble
ne tourne à rayon nul, donc un virage franc rendu par un seul sommet est bien
sous-décrit. Un plafond d'angle serait à ajouter si ces coudes devaient rester
conformes.

**Géométries multi-parties.** Les tronçons d'un `MultiLineString` sont d'abord
**recollés** en polylignes continues, via `utils_geometrie.recoller_parties_lineaires`
(le même mécanisme que E202). Les parties d'un `MultiLineString` RecoStaR n'étant
ni ordonnées ni orientées, les analyser séparément laisserait échapper les
**sommets de raccord** : ils sont bouts de partie dans chaque tronçon, donc jamais
sommets intermédiaires, donc jamais évalués. Mesuré sur le jeu Echantillon2, le
recollement fait passer de 20 à 27 les sommets évalués sur les câbles
multi-parties. Les polylignes restantes — tronçons réellement disjoints — sont
ensuite traitées **indépendamment** : aucun arc fictif n'est reconstruit entre
elles.

**Sortie — `ecarts_e509_discretisation_courbe_cable.geojson` :** un `Feature` **par
portion de courbe fautive**, dont la géométrie est restreinte aux **seuls sommets
concernés** — et non au tracé complet du câble. Une portion regroupe les sommets
non conformes d'indices **consécutifs**, et s'étend du sommet qui les précède à
celui qui les suit : ces deux sommets ferment l'arc et rendent le tronçon
directement exploitable dans QGIS, sans avoir à retrouver l'arc dans une
polyligne de plusieurs centaines de mètres. Un câble portant deux arcs mal
discrétisés séparés par un tracé correct produit donc **deux** entités distinctes.

Propriétés de chaque `Feature` :

- `type_anomalie` = `courbe_non_discretisee` (bloquant) ou `courbe_mal_discretisee` (majeur)
- `fichier_source` = `RPD_CableElectrique_Reco.geojson`
- `id_cable` : identifiant du câble portant la portion
- `fleche_max_m` : plus grande flèche mesurée sur la portion (mètres, 3 décimales)
- `rayon_min_m` : plus petit rayon de courbure de la portion (mètres, 2 décimales),
  soit l'endroit où la courbe est la plus serrée
- `angle_max_deg` : plus grand changement de direction de la portion (degrés, 1 décimale)
- `seuil_fleche_forte_m` = `0.4`, `seuil_fleche_negligeable_m` = `0.1`,
  `seuil_rayon_arc_serre_m` = `15.0`, `seuil_angle_deg` = `3.0`
- `nombre_sommets_non_conformes` : sommets de la portion classés en anomalie
- `nombre_sommets_portion` : nombre total de sommets de la portion extraite
- `priorite` = `bloquant`

Une portion ne mélange **jamais** deux types : le type fait partie de la clé de
regroupement, chaque portion en porte donc un seul.

**Rapport JSON :** `succes`, `priorite`, `anomalies_par_type` (informatif),
`nombre_anomalies` (nombre de portions fautives), `nombre_cables_non_conformes`
(câbles distincts concernés), `nombre_cables_controles`,
`nombre_cables_aeriens_exclus`, `nombre_sommets_evalues` (sommets ayant franchi
le seuil d'angle et donc réellement mesurés), les quatre seuils,
`fichier_cable_absent`, `sortie`.

L'absence du fichier câble n'est **pas** bloquante : elle est reportée dans
`fichier_cable_absent`.

---

## Pipeline (`pipeline_controle_cable.py`)

Exécute séquentiellement les contrôles de câble dans l'ordre
E500 → E501 → E502 → E503 → E504 → E505 → E506 → E507 → E508 → E509. Un échec
d'un contrôle n'interrompt pas l'exécution des suivants.

`--numero_affaire` n'est utilisé que par E508 : sans lui, seul ce contrôle
retourne une erreur, les neuf autres s'exécutent normalement.

**Rapport JSON :**

- `succes`
- `controles` : dictionnaire des rapports individuels, indexé par `controle_e500`
  à `controle_e509` (chacun contenant son champ `priorite`, à l'exception d'E506
  qui expose `priorites` — voir ci-dessus) ;
- `nombre_anomalies_total` : somme des anomalies des contrôles réussis.
