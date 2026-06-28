# StaR-Engine

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

| Paquet | Version | Rôle |
|--------|---------|------|
| defusedxml | 0.7.1 | Lecture XML sécurisée |
| lxml | 5.3.0 | Validation XSD et manipulation XML |
| pyproj | 3.7.2 | Transformations de projections cartographiques |
| reportlab | 4.4.10 | Génération de rapports PDF |
| requests | 2.32.5 | Téléchargement des schémas XSD distants |
| shapely | 2.1.2 | Opérations géométriques |
