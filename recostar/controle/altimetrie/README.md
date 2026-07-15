# Contrôles altimétriques

Ce dossier regroupe les contrôles altimétriques appliqués aux fichiers GeoJSON.
Chaque contrôle parcourt un ou plusieurs fichiers GeoJSON, détecte les anomalies
et produit un fichier d'écarts GeoJSON (préfixé `ecarts_`) directement
exploitable dans QGIS (le `crs` du fichier source est propagé).

Les fichiers d'écarts (`ecarts_*`) sont automatiquement exclus des analyses.

## Vue d'ensemble

| Code | Script | Cible | Seuil | Priorité | Fichier de sortie |
|------|--------|-------|-------|----------|-------------------|
| E200 | `controle_e200.py` | Tous les GeoJSON | présence de Z | `bloquant` | `ecarts_3d.geojson` |
| E201 | `controle_e201.py` | v1.0 : câbles élec. — v1.1 : tous les GeoJSON (statut `UnderCommissionning`) | Z = 0.0 | `bloquant` | `ecarts_z_null.geojson` |
| E202 | `controle_e202.py` | Câbles (élec./terre/télécom) | écart résiduel > 0,40 m | `bloquant` | `ecarts_controle_alti_sommets.geojson` |
| E203 | `controle_e203.py` | Géométries supplémentaires | écart / MNT IGN ≥ 0,40 m | `information` | `ecarts_z_ign.geojson` |
| E204 | `controle_e204.py` | Points levés ouvrage réseau | coordonnées identiques | `information` | `ecarts_doublons_spatiaux.geojson` |
| E205 | `controle_e205.py` | Géométries suppl. de coffrets | point de levé absent | `bloquant` | `ecarts_point_leve_geom_supp.geojson` |
| E206 | `controle_e206.py` | Géométries suppl. de bâtiments techniques (rattachés à un poste) | point de levé absent **sur les sommets** | `bloquant` | `ecarts_point_leve_sommets_geom_supp.geojson` |
| E207 | `controle_e207.py` | Géométries suppl. de supports (**v1.1 uniquement**) | point de levé absent (toute la géométrie) | `bloquant` | `ecarts_point_leve_geom_supp_support.geojson` |
| E208 | `controle_e208.py` | Sommets des câbles (élec./terre/télécom) | sommet non superposé à un point de levé, ou X/Y/Z ≠ | `bloquant` | `ecarts_point_leve_sommets_cables.geojson` |
| E209 | `controle_e209.py` | Points levés (`RPD_PointLeveOuvrageReseau_Reco`) | point levé orphelin (aucune superposition avec un autre GeoJSON) | `bloquant` | `ecarts_points_leve_orphelins.geojson` |

L'orchestration de l'ensemble est assurée par `pipeline_controle_alti.py`.
Les fonctions utilitaires communes (lecture/écriture/listage GeoJSON, extraction
d'identifiant) sont centralisées dans `utils_geojson.py`.

### Usage CLI

Chaque contrôle (et le pipeline) s'exécute de la même manière :

```bash
python <script>.py --repertoire <chemin> [--sortie <chemin>]
```

- `--repertoire` : répertoire contenant les fichiers GeoJSON à analyser.
- `--sortie` : répertoire de sortie (par défaut, le répertoire d'entrée).

Le résultat est imprimé en JSON sur la sortie standard. Tous les rapports de
contrôle incluent le champ `priorite`.

**E201, E202, E203, E204, E205 et E206** — option supplémentaire `--version` :

```bash
python controle_e201.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e202.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e203.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e204.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e205.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e206.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e207.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e208.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
```

- `--version` : version RecoStaR à appliquer. `auto` (par défaut) la déduit des
  propriétés GeoJSON (présence du champ `TypeLeve` dans `RPD_PointLeveOuvrageReseau_Reco`
  → v1.0 ; absence → v1.1).

---

## E200 — Conformité 3D (`controle_e200.py`)

**Ce qui est contrôlé :** vérifie que toutes les entités possèdent une
composante Z. Une entité comportant **au moins un point sans Z** (coordonnées de
longueur < 3) est signalée. Tous les types de géométrie sont gérés (`Point`,
`LineString`, `Polygon`, `MultiPoint`, `MultiLineString`, `MultiPolygon`).

**Sortie — `ecarts_3d.geojson` :** un `Feature` par entité non conforme,
**conservant sa géométrie d'origine**, avec les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`
- `type_anomalie` = `absence_coordonnee_z`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`fichiers_analyses`, `sortie`.

---

## E201 — Coordonnées Z nulles (`controle_e201.py`)

**Ce qui est contrôlé :** détecte les sommets **3D** dont l'altitude est
exactement `0.0`. Les sommets 2D sont ignorés (ils relèvent du contrôle E200).

**Périmètre selon la version RecoStaR** (détection identique à E202/E204 —
présence du champ `TypeLeve` dans `RPD_PointLeveOuvrageReseau_Reco` → v1.0,
absence → v1.1, imposable via `--version`) :

- **v1.0** : seul `RPD_CableElectrique_Reco.geojson` est contrôlé.
- **v1.1** : l'ensemble des GeoJSON du répertoire est contrôlé.

Dans les deux versions, seules les entités dont le champ `Statut` vaut
`UnderCommissionning` sont soumises au contrôle.

**Sortie — `ecarts_z_null.geojson` :** un point `Point` par sommet fautif, avec
les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`, `indice_sommet`
- `z_detecte` = `0.0`
- `type_anomalie` = `z_null`
- `priorite` = `bloquant`
- `version` = version RecoStaR appliquée

**Rapport JSON :** `succes`, `priorite`, `version_detectee`,
`nombre_anomalies`, `fichiers_analyses`, `sortie`.

---

## E202 — Cohérence altimétrique des sommets de câbles (`controle_e202.py`)

**Ce qui est contrôlé :** analyse les couches de câbles selon la version
RecoStaR. À l'aide d'une **fenêtre glissante de 4 sommets consécutifs**, l'écart
altimétrique entre les 2 sommets centraux est comparé à la tendance (pente)
définie par les sommets extrêmes. Si l'**écart résiduel dépasse 0,40 m**, les 2
sommets centraux sont signalés. L'écart résiduel **maximal** observé est conservé
par sommet.

Chaque câble est traité comme **une entité unique**, la fenêtre glissante
parcourant l'intégralité de ses sommets :

- **`LineString`** : analyse directe de ses sommets ;
- **`MultiLineString`** : les tronçons sont **recollés** en une polyligne
  continue via `shapely.ops.linemerge` (réordonnancement, orientation et
  déduplication des nœuds partagés, `Z` préservé), puis analysés comme un seul
  câble. Un `MultiLineString` dont les tronçons sont **réellement disjoints**
  (linemerge ne produit pas un `LineString` unique) est **écarté** : il ne forme
  pas un ensemble continu.

**Couches contrôlées selon la version** (détection identique à E204, via
`RPD_PointLeveOuvrageReseau_Reco`) :

| Version | Couches contrôlées |
|---|---|
| **v1.0** | `RPD_CableElectrique_Reco`, `RPD_CableTerre_Reco` |
| **v1.1** | v1.0 + `RPD_CableTelecommunication_Reco` |

Dans **toutes les versions**, seules les entités dont le champ `Statut` vaut
`UnderCommissionning` sont contrôlées. Les couches absentes du répertoire sont
ignorées sans erreur (cas nominal de la télécommunication).

**Exclusions :**

- les 3 premiers et 3 derniers sommets de chaque câble ;
- les câbles dont l'identifiant est référencé dans un cheminement aérien
  (`RPD_Aerien_Reco.geojson`, champ `cables_href`), quelle que soit la couche ;
- les câbles `MultiLineString` aux tronçons disjoints (non recollables) ;
- les câbles trop courts (moins de 4 sommets) ou dépourvus de composante Z.

**Sortie — `ecarts_controle_alti_sommets.geojson` :** un point `Point` par
sommet en anomalie, avec les propriétés :

- `id_cable`, `couche`, `indice_sommet`
- `ecart_residuel_m`, `seuil_m` = `0.40`
- `type_anomalie` = `ecart_altimetrique_sommet`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `version_detectee`,
`couches_controlees`, `nombre_anomalies`, `cables_exclus`, `sortie`.

---

## E203 — Confrontation au MNT IGN (`controle_e203.py`)

**Ce qui est contrôlé :** analyse `RPD_GeometrieSupplementaire_Reco.geojson`.
Chaque sommet est converti de **Lambert 93 (EPSG:2154) vers WGS84** (projection
conique conforme implémentée en interne), puis l'**API altimétrie IGN** est
interrogée pour obtenir l'altitude de référence. Si l'écart entre le Z du sommet
et l'altitude IGN est **supérieur ou égal à 0,40 m**, le sommet est signalé.

**Sélection des entités selon la version RecoStaR :**

| Version | Entités contrôlées |
|---------|--------------------|
| **v1.0** | Toutes les entités (comportement historique) |
| **v1.1** | Uniquement celles dont le champ `Statut` vaut `UnderCommissionning` |

La version est détectée comme pour E204 (présence du champ `TypeLeve` dans
`RPD_PointLeveOuvrageReseau_Reco` → v1.0 ; absence → v1.1) et peut être imposée
via l'option `--version`. En v1.1, l'absence d'entité `UnderCommissionning` est
un cas nominal (aucune anomalie, contrôle en succès).

**Détails techniques :**

- Sources IGN avec repli (fallback) : LIDAR HD, puis RGE Alti.
- Requêtes par lots de 5 000 points, timeout de 30 s.
- La valeur sentinelle `-99999.0` (altitude inconnue) est ignorée.

**Sortie — `ecarts_z_ign.geojson` :** un point `Point` par sommet en écart, avec
les propriétés :

- `id_entite`, `type_geometrie`, `indice_sommet`
- `altitude_geojson_m`, `altitude_ign_m`, `ecart_m`, `seuil_m` = `0.40`
- `source_ign`
- `type_anomalie` = `ecart_altimetrique_ign`
- `priorite` = `information`

**Rapport JSON :** `succes`, `priorite`, `version_detectee`, `nombre_sommets`,
`nombre_anomalies`, `source_ign`, `sortie`.

---

## E204 — Doublons spatiaux (`controle_e204.py`)

**Ce qui est contrôlé :** analyse `RPD_PointLeveOuvrageReseau_Reco.geojson`.
Détecte les entités ponctuelles partageant **exactement les mêmes coordonnées**.
La règle de détection varie selon la version du modèle RecoStaR :

| Version | Condition de doublon |
|---------|----------------------|
| **v1.1** | Mêmes coordonnées (X, Y, Z), quelle que soit la valeur de tout autre champ |
| **v1.0** | Mêmes coordonnées **ET** même valeur du champ `TypeLeve` |

La version est détectée automatiquement depuis les propriétés du fichier GeoJSON
(présence du champ `TypeLeve` → v1.0 ; absence → v1.1). Elle peut être imposée
via l'option `--version`.

**Sortie — `ecarts_doublons_spatiaux.geojson` :** un point `Point` par **groupe**
de doublons, positionné aux coordonnées communes, avec les propriétés :

- `ids_entites` : identifiants des entités en doublon, séparés par des virgules
- `nb_points` : nombre d'entités dans le groupe
- `TypeLeve` *(v1.0 uniquement)* : valeur commune du champ discriminant
- `version` : version RecoStaR appliquée
- `type_anomalie` = `doublons_spatiaux`
- `priorite` = `information`

**Rapport JSON :** `succes`, `priorite`, `version_detectee`, `nombre_anomalies`
(nombre de groupes en doublon), `nombre_points_en_doublon`, `sortie`.

---

## E205 — Point de levé des géométries supplémentaires de coffrets (`controle_e205.py`)

**Ce qui est contrôlé :** vérifie que chaque **géométrie supplémentaire** liée à
un coffret éligible (`RPD_GeometrieSupplementaire_Reco.geojson`) possède au moins
un **point de levé** (`RPD_PointLeveOuvrageReseau_Reco.geojson`) en superposition
géographique planimetrique (2D) avec son polygone.

La sélection des coffrets éligibles dépend de la version RecoStaR :

| Version | Coffrets éligibles |
|---------|--------------------|
| **v1.0** | Tous les coffrets portant un `geometriesupplementaire_href` |
| **v1.1** | Uniquement les coffrets dont le champ `Statut` vaut `UnderCommissionning` |

La version est détectée automatiquement depuis les features de
`RPD_PointLeveOuvrageReseau_Reco` (présence du champ `TypeLeve` → v1.0 ;
absence → v1.1), identiquement au contrôle E204.

**Détails techniques :**

- La détection spatiale est **planimetrique** (`force_2d`) : les Z sont ignorés.
- Un point positionné sur le **bord** du polygone est accepté (`intersects`).
- Un `STRtree` Shapely est utilisé pour l'interrogation spatiale en O(log n).

**Sortie — `ecarts_point_leve_geom_supp.geojson` :** un `Feature` par géométrie
supplémentaire en anomalie, **conservant son polygone d'origine**, avec les
propriétés :

- `id_entite` : identifiant de la géométrie supplémentaire
- `version` : version RecoStaR appliquée
- `type_anomalie` = `point_leve_absent`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `version_detectee`, `nombre_anomalies`,
`nombre_geomsupp_controlees`, `sortie`.

---

## E206 — Point de levé sur les sommets des géométries supplémentaires de bâtiments techniques (`controle_e206.py`)

**Ce qui est contrôlé :** vérifie que chaque **géométrie supplémentaire** liée à
un **bâtiment technique** lui-même rattaché à un **poste électrique** possède au
moins un **point de levé** (`RPD_PointLeveOuvrageReseau_Reco.geojson`) en
superposition planimétrique (2D) avec l'un de ses **sommets**.

**Différence avec E205 :**

| Contrôle | Point d'entrée | Superposition analysée |
|----------|----------------|------------------------|
| **E205** | Coffret | **toute** la géométrie supplémentaire (segments et surface) — `STRtree` + `intersects` |
| **E206** | Poste → Bâtiment technique | **uniquement les sommets** de la géométrie supplémentaire — test d'appartenance à un `set` de coordonnées |

**Chaîne de références remontée :**

```
Poste (Statut == UnderCommissionning)
  --conteneur_href-->              RPD_BatimentTechnique_Reco.id
RPD_BatimentTechnique_Reco
  --geometriesupplementaire_href--> RPD_GeometrieSupplementaire_Reco.id
```

**Entités contrôlées :** seuls les postes électriques dont le champ `Statut`
vaut `UnderCommissionning` sont pris en compte, **pour les versions 1.0 et 1.1**
(règle identique dans les deux versions, contrairement à E205). La version est
détectée automatiquement depuis les features de `RPD_PointLeveOuvrageReseau_Reco`
(présence du champ `TypeLeve` → v1.0 ; absence → v1.1), identiquement à E204/E205.

**Détails techniques :**

- La détection est **planimétrique** : sommets et points de levé sont comparés
  en 2D (la composante Z est ignorée).
- Le test de superposition est une **appartenance à un `set`** de coordonnées
  de points de levé, snappées au centimètre (`PRECISION_COORD = 2`). Aucun
  `STRtree` ni chargement de géométrie Shapely n'est nécessaire (O(1) par sommet).
- Le sommet de fermeture des anneaux (premier == dernier) est naturellement
  dédupliqué par le `set`.

**Sortie — `ecarts_point_leve_sommets_geom_supp.geojson` :** un `Feature` par
géométrie supplémentaire en anomalie, **conservant son polygone d'origine**, avec
les propriétés :

- `id_entite` : identifiant de la géométrie supplémentaire
- `version` : version RecoStaR appliquée
- `type_anomalie` = `point_leve_sommet_absent`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `version_detectee`, `nombre_anomalies`,
`nombre_geomsupp_controlees`, `sortie`.

---

## E207 — Point de levé des géométries supplémentaires de supports (`controle_e207.py`)

**Ce qui est contrôlé :** vérifie que chaque **géométrie supplémentaire** liée à
un **support** éligible (`RPD_Support_Reco`) possède au moins un **point de levé**
(`RPD_PointLeveOuvrageReseau_Reco.geojson`) en superposition planimétrique (2D)
avec **l'ensemble de sa géométrie** (ligne, surface, bord et intérieur) —
**comportement strictement identique à E205** (et non limité aux sommets, ce qui
le distingue d'E206).

**Périmètre :**

- **Version 1.1 uniquement.** En version 1.0, le contrôle est **désactivé** :
  il ne produit aucune anomalie et le rapport indique `applicable: false`.
- Sont contrôlés les supports dont le champ `Statut` vaut `UnderCommissionning`.
- Le lien support → géométrie supplémentaire est porté par
  `geometriesupplementaire_href` (même champ que les coffrets d'E205).

La version est détectée automatiquement depuis les features de
`RPD_PointLeveOuvrageReseau_Reco` (présence du champ `TypeLeve` → v1.0 ;
absence → v1.1), identiquement à E204/E205.

**Réutilisation d'E205 :** E207 réutilise directement le moteur de détection
spatiale d'E205 (`_charger_points_leve`, `detecter_geomsupp_sans_point_leve`,
`construire_geojson_ecarts`) ainsi que la logique de filtrage v1.1
(`extraire_hrefs_geomsupp_liees_coffrets`). Seuls le fichier source
(`RPD_Support_Reco`), le garde de version et l'orchestration CLI lui sont propres.

**Sortie — `ecarts_point_leve_geom_supp_support.geojson` :** un `Feature` par
géométrie supplémentaire en anomalie, **conservant sa géométrie d'origine**, avec
les propriétés :

- `id_entite` : identifiant de la géométrie supplémentaire
- `version` : version RecoStaR appliquée
- `type_anomalie` = `point_leve_absent`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `version_detectee`, `applicable`,
`nombre_anomalies`, `nombre_geomsupp_controlees`, `sortie`.

---

## E208 — Rattachement des sommets de câbles aux points de levé (`controle_e208.py`)

**Ce qui est contrôlé :** vérifie que **chaque sommet** des câbles contrôlés est
en **superposition exacte** avec un point de levé
(`RPD_PointLeveOuvrageReseau_Reco`) **et** que ses coordonnées **X, Y et Z** sont
**strictement égales** à celles de ce point.

**Périmètre par version (identique à E202) :**

| Version | Couches contrôlées |
|---------|--------------------|
| **v1.0** | `RPD_CableElectrique_Reco`, `RPD_CableTerre_Reco` |
| **v1.1** | v1.0 + `RPD_CableTelecommunication_Reco` |

Dans les deux versions, seules les entités dont `Statut` vaut
`UnderCommissionning` sont contrôlées. La version est détectée depuis les
features de `RPD_PointLeveOuvrageReseau_Reco` (`TypeLeve` → v1.0 ; absence →
v1.1). Les couches absentes du répertoire sont ignorées silencieusement.

**Deux causes d'anomalie (une anomalie par sommet fautif) :**

- `point_leve_absent` : aucun point de levé n'a exactement les mêmes X, Y que le
  sommet (pas de superposition planimétrique) ;
- `coordonnees_differentes` : un point de levé superposé existe (mêmes X, Y) mais
  aucun ne partage exactement le même Z.

**Détails techniques :**

- Comparaison **stricte** (aucune tolérance) et **sans Shapely** : un index
  `dict[(x, y) → set(z)]` des points de levé permet un test d'appartenance O(1)
  par sommet.
- Les `MultiLineString` sont analysés **sommet par sommet** (aplatis, sans
  recollage `linemerge`) : aucun câble connexe n'est écarté.
- Les câbles référencés par un cheminement aérien
  (`RPD_Aerien_Reco.cables_href`) sont **exclus**, comme dans E202.
- Le périmètre (`resoudre_fichiers_cables`), le filtrage par statut
  (`filtrer_cables_a_controler`) et l'exclusion aérienne
  (`charger_ids_cables_aeriens`) sont **réutilisés d'E202**.

**Exception — extrémité en contact avec une géométrie supplémentaire :**

Un sommet d'**extrémité** du câble dont la position est **en contact** avec une
entité `RPD_GeometrieSupplementaire_Reco` est **exempté** de l'obligation de point
de levé : l'ouvrage y est déjà levé par sa géométrie supplémentaire.

Trois conditions **cumulatives** :

| Condition | Détail |
|-----------|--------|
| Cause `point_leve_absent` | un sommet superposé à un point de levé de **Z divergent** reste signalé (`coordonnees_differentes`) : l'ouvrage est levé, mais mal |
| Sommet d'**extrémité** | les sommets **intermédiaires** restent soumis à la règle, sans exception |
| **Contact** géométrique | prédicat `intersects` planimétrique — intérieur **ou** bord |

**Définition d'une extrémité — topologique, pas positionnelle.** Les extrémités
sont obtenues via `extraire_extremites` (module commun `utils_geometrie`, partagé
avec E506 / E507) : ce sont les sommets terminaux n'en rejoignant aucun autre, et
**non** le premier et le dernier sommet de la liste concaténée. Les parties d'un
`MultiLineString` RecoStaR n'étant ni ordonnées ni orientées, la lecture littérale
désignerait un **raccord interne** et manquerait les vrais bouts : sur les jeux de
référence, les deux lectures divergent sur **22 des 30 câbles multi-parties**.

**Mécanisme de contact.** Index spatial `STRtree` sur les géométries
supplémentaires forcées en 2D (`force_2d`) — **même mécanisme géométrique que
E205 et E209**. L'absence de `RPD_GeometrieSupplementaire_Reco.geojson` n'est pas
bloquante : aucune exemption n'est alors appliquée, et le comportement historique
du contrôle est conservé à l'identique.

**Sortie — `ecarts_point_leve_sommets_cables.geojson` :** un `Feature` **Point**
par sommet en anomalie (positionné sur le sommet), avec les propriétés
`id_cable`, `couche`, `indice_sommet`, `type_anomalie`, `priorite`, `version`.

**Rapport JSON :** `succes`, `priorite`, `version_detectee`, `couches_controlees`,
`cables_exclus`, `nombre_anomalies`, `nombre_sommets_sans_point_leve`,
`nombre_sommets_coordonnees_differentes`, `sortie`.

---

## E209 — Points levés orphelins (`controle_e209.py`)

**Ce qui est contrôlé :** vérifie que chaque **point levé**
(`RPD_PointLeveOuvrageReseau_Reco`) est en **superposition planimétrique (2D)**
avec au moins une entité provenant d'un **autre** fichier GeoJSON du jeu de
données. Un point levé qui n'est superposé à **aucun** objet métier d'un autre
fichier est **orphelin** et signalé en anomalie bloquante.

**Détails techniques :**

- Les entités du fichier `RPD_PointLeveOuvrageReseau_Reco` lui-même **ne sont pas
  prises en compte** dans la recherche (les points levés ne se valident pas entre
  eux) ; les fichiers d'écarts (`ecarts_*`) sont également exclus
  (`lister_fichiers_geojson`).
- Toutes les géométries des autres fichiers (tous types) sont chargées en 2D
  (`force_2d`) et indexées dans un **unique `STRtree`** ; chaque point levé est
  interrogé avec le prédicat `intersects`. C'est le **même moteur de
  superposition que E205**, appliqué en sens inverse (l'arbre contient les objets
  métier, les points sont les requêtes).
- Contrôle **sans version** : il s'applique à tous les GeoJSON indistinctement.

**Sortie — `ecarts_points_leve_orphelins.geojson` :** un `Feature` **Point** par
point levé orphelin (géométrie conservée), avec les propriétés `id_entite`,
`type_anomalie` = `point_leve_orphelin`, `priorite` = `bloquant`.

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_points_controles`, `fichiers_analyses`, `sortie`.

---

## Pipeline (`pipeline_controle_alti.py`)

Exécute séquentiellement les 10 contrôles dans l'ordre E200 → E201 → E202 → E203 → E204 → E205 → E206 → E207 → E208 → E209.
Un échec d'un contrôle n'interrompt pas l'exécution des suivants.

**Rapport JSON :**

- `succes`
- `controles` : dictionnaire des rapports individuels, indexés par
  `controle_e200`, `controle_e201`, `controle_e202`, `controle_e203`,
  `controle_e204`, `controle_e205`, `controle_e206`, `controle_e207`,
  `controle_e208`, `controle_e209` (chacun contenant son champ `priorite`) ;
- `nombre_anomalies_total` : somme des anomalies des contrôles réussis.
