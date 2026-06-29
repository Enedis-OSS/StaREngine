# StaR-Engine

[![REUSE Compliance](https://img.shields.io/badge/reuse-compliant-green.svg)](https://reuse.software/)

Moteur de traitement des données RecoStaR — conversion GeoJSON ↔ GML, contrôles qualité et calcul des longueurs de câbles pour les réseaux électriques de distribution publique (format StaR-Elec).

---

## Structure

```
recostar/
├── conversion/        # GeoJSON ↔ GML (schémas RecoStaR v1.0 et v1.1)
├── controle/          # Contrôles qualité altimétrie, projection, structuration, cheminement
└── traitement/        # Calcul des longueurs de câbles et génération de rapport PDF
```

Chaque sous-module est autonome et possède son propre README.

---

## Conversion

Conversion bidirectionnelle entre fichiers GeoJSON terrain (`RPD_*.geojson`) et fichier GML d'archivage conforme au schéma XSD StaR-Elec.

Deux versions du schéma sont supportées :

- **V1.0** — `conversion/conversion_V1/`
- **V1.1** — `conversion/conversion_V1_1/` (ajout `RPD_CableTelecommunication_Reco`, géométries 3D, `ChargeGeneratrice`)

La version est détectée automatiquement depuis le `schemaLocation` du fichier GML.

---

## Contrôle

Quatre familles de contrôles, chacune disposant d'un pipeline orchestrant l'exécution séquentielle des vérifications. Un échec de contrôle n'interrompt pas les suivants.

| Famille | Répertoire | Codes | Périmètre |
|---------|-----------|-------|-----------|
| Altimétrie | `controle/altimetrie/` | E200–E205 | Qualité de la composante Z (3D, doublons, référentiel IGN) |
| Projection | `controle/projection/` | E300–E303 | Cohérence CRS, géométrie spatiale, emprise DR |
| Structuration XSD | `controle/xsd_structuration/` | E110–E114 | Conformité GML au schéma XSD, règles métier, valeurs |
| Cheminement | `controle/cheminement/` | E400–E404 | Topologie câble/cheminement, connexité, profondeur |

Chaque contrôle produit un rapport GeoJSON ou JSON listant les anomalies avec leur niveau de priorité (`bloquant`, `majeur`, `mineur`).

---

## Traitement

Le module `traitement/calcul_longueurs/` calcule les longueurs géographiques (distance euclidienne 3D) et électriques (avec corrections forfaitaires RAS, poste, coffret, taux aérien) des câbles, et génère un rapport PDF récapitulatif via ReportLab.

---

## Environnement Poetry

**Prérequis :** Python 3.13

```bash
poetry install          # Crée le virtualenv dans .venv/ et installe les dépendances
poetry run pytest       # Lance les tests
poetry run ruff check recostar/   # Lint
poetry run ruff format recostar/  # Formatage
```

### Dépendances principales

| Librairie   | Version | Licence      | Usage                                        |
| ----------- | ------- | ------------ | -------------------------------------------- |
| defusedxml  | 0.7.1   | PSF-2.0      | Parsing XML sécurisé (protection XXE)        |
| pillow      | 12.2.0  | MIT-CMU      | Manipulation d'images pour les rapports PDF  |
| pyproj      | 3.7.2   | MIT          | Transformations de coordonnées géographiques |
| reportlab   | 4.4.10  | BSD-3-Clause | Génération des rapports PDF                  |
| requests    | 2.32.5  | Apache-2.0   | Requêtes HTTP (API IGN altimétrie)           |
| shapely     | 2.1.2   | BSD-3-Clause | Opérations géométriques                      |
| lxml        | 5.3.0   | BSD          | Validation XSD et manipulation XML           |


### Dépendances transitives

| Librairie          | Version  | Licence      | Dépendance de |
| ------------------ | -------- | ------------ | ------------- |
| certifi            | 2026.2.25| MPL-2.0      | requests      |
| charset-normalizer | 3.4.7    | MIT          | requests      |
| idna               | 3.11     | BSD-3-Clause | requests      |
| packaging          | 26.1     | Apache-2.0   | pytest        |
| urllib3            | 2.6.3    | MIT          | requests      |

### Dépendances de développement

| Librairie | Version | Licence      | Usage                        |
| --------- | ------- | ------------ | ---------------------------- |
| iniconfig | 2.3.0   | MIT          | Configuration pytest         |
| pluggy    | 1.6.0   | MIT          | Système de plugins pytest    |
| pygments  | 2.20.0  | BSD-2-Clause | Coloration syntaxique        |
| pytest    | 9.0.2   | MIT          | Exécution de tests unitaires |
