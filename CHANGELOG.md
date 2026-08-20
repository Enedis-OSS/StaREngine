# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/) ·
Versionnage : [SemVer](https://semver.org/lang/fr/).

> Ce journal est volontairement synthétique : une ligne par changement notable.
> Le détail des règles métier est dans les `README.md` de chaque famille de
> contrôles, et le raisonnement complet dans l'historique git.

## [1.0.2] - 2026-08-20

### Ajouté

- Famille de contrôles **Conteneur** : E600 à E610 — matériel de jonction au catalogue, rattachements, caractéristiques de poteau, nœuds autorisés dans un coffret, chaînes de localisation, cardinalité des raccordements, rattachement des nœuds à un câble, nomenclature de composition des coffrets.
- Contrôles de **structuration XSD en version 1.0** : E010 à E014.
- Contrôles **câble** E508 (HTB en Métropole) et E509 (discrétisation des courbes).
- **Pipeline complet** : traitement par lot (`--lot`) et option `--commentaire`.

### Modifié

- Les fichiers d'écarts portent le **code du contrôle** : `ecarts_<code>_<objet>.geojson`, sur les 40 contrôles à sortie GeoJSON. Le code est placé après le préfixe `ecarts_`, qui seul fait exclure ces fichiers des analyses.
- Ventilation des anomalies par type **mutualisée** dans `utils_geojson_commun` (11 copies identiques supprimées) ; géométrie, tolérance de superposition, correction des Z nuls et emprise DR déjà mutualisées de même.
- **Priorités réétalonnées** : E201 `bloquant` ; E202, E404 et E506 (règle câble de terre) `majeur` ; E204, E209, E501 et E604 `mineur`. Seul `bloquant` déclasse une famille.
- E509 : discrétisation mesurée à la flèche à l'arc, toutes anomalies `bloquant`.
- README des familles altimétrie et câble alignés sur les priorités réelles d'E202 et E506.

### Corrigé

- Faux positifs : E205, E208 et E209 (contours de polygones), E504 et E505 (altitudes manquantes), E509 (raccords terminaux).
- Fichiers V1.0 contrôlés en V1.1 par le pipeline global.
- Emprises DR `MultiPolygon` ignorées (E303).
- `mapper_galerie` : champ `Commentaire` perdu à l'aller-retour.
- Contrat de symétrie des shims `utils_geometrie.py`, désormais vérifié — garde étendue aux shims `utils_geojson.py`.

### Retiré

- Code mort : paramètres inutilisés de `classer_sommet` (E509) et `compter_liens_couche` (E604), `__init__.py` superflus des répertoires de tests.

## [1.0.1] - 2026-06-28

### Ajouté

- Contrôles **altimétrie** E204 (doublons spatiaux) et E205 (points de levé / géométries supplémentaires).
- Famille **Projection** : E300 à E303, et son pipeline.
- Famille **Cheminement** : E400 à E404.
- Pipeline de contrôle **XSD / structuration** et ses tests.
- Prise en charge de `RPD_Galerie_Reco` dans les convertisseurs V1.0 et V1.1.
- Gestion des dépendances par **Poetry**.
- `README.md` des paquets de contrôle ; priorité exposée dans les rapports JSON altimétriques.

### Modifié

- `pyproject.toml` : table `[project]` (PEP 517/518).
- Contrôles altimétriques renommés selon la codification E2xx.
- E200 (conformité 3D) passe en `bloquant`.

### Corrigé

- E202 : risque d'`IndexError` sur les sommets.
