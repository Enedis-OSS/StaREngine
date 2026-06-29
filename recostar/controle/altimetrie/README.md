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
| E201 | `controle_e201.py` | Tous les GeoJSON | Z = 0.0 | `information` | `ecarts_z_null.geojson` |
| E202 | `controle_e202.py` | Câbles (élec./terre/télécom) | écart résiduel > 0,25 m | `bloquant` | `ecarts_controle_alti_sommets.geojson` |
| E203 | `controle_e203.py` | Géométries supplémentaires | écart / MNT IGN ≥ 0,40 m | `information` | `ecarts_z_ign.geojson` |
| E204 | `controle_e204.py` | Points levés ouvrage réseau | coordonnées identiques | `information` | `ecarts_doublons_spatiaux.geojson` |
| E205 | `controle_e205.py` | Géométries suppl. de coffrets | point de levé absent | `bloquant` | `ecarts_point_leve_geom_supp.geojson` |

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

**E202, E203, E204 et E205** — option supplémentaire `--version` :

```bash
python controle_e202.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e203.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e204.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
python controle_e205.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]
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

**Sortie — `ecarts_z_null.geojson` :** un point `Point` par sommet fautif, avec
les propriétés :

- `fichier_source`, `id_entite`, `type_geometrie`, `indice_sommet`
- `z_detecte` = `0.0`
- `type_anomalie` = `z_null`
- `priorite` = `information`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`fichiers_analyses`, `sortie`.

---

## E202 — Cohérence altimétrique des sommets de câbles (`controle_e202.py`)

**Ce qui est contrôlé :** analyse les couches de câbles selon la version
RecoStaR. À l'aide d'une **fenêtre glissante de 4 sommets consécutifs**, l'écart
altimétrique entre les 2 sommets centraux est comparé à la tendance (pente)
définie par les sommets extrêmes. Si l'**écart résiduel dépasse 0,25 m**, les 2
sommets centraux sont signalés. L'écart résiduel **maximal** observé est conservé
par sommet.

Les géométries **`LineString`** et **`MultiLineString`** sont prises en charge.
Pour un `MultiLineString`, chaque partie est analysée **indépendamment** (une
fenêtre ne franchit jamais la discontinuité entre deux parties) ; l'`indice_sommet`
reporté reste séquentiel sur l'ensemble des sommets du câble.

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
- les parties trop courtes (moins de 4 sommets) ou dépourvues de composante Z,
  sans pour autant disqualifier les autres parties d'un même `MultiLineString`.

**Sortie — `ecarts_controle_alti_sommets.geojson` :** un point `Point` par
sommet en anomalie, avec les propriétés :

- `id_cable`, `couche`, `indice_sommet`
- `ecart_residuel_m`, `seuil_m` = `0.25`
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

## Pipeline (`pipeline_controle_alti.py`)

Exécute séquentiellement les 6 contrôles dans l'ordre E200 → E201 → E202 → E203 → E204 → E205.
Un échec d'un contrôle n'interrompt pas l'exécution des suivants.

**Rapport JSON :**

- `succes`
- `controles` : dictionnaire des rapports individuels, indexés par
  `controle_e200`, `controle_e201`, `controle_e202`, `controle_e203`,
  `controle_e204`, `controle_e205` (chacun contenant son champ `priorite`) ;
- `nombre_anomalies_total` : somme des anomalies des contrôles réussis.
