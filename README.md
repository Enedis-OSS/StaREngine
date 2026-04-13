# Star Engine

Moteur de traitements pour les données de réseaux électriques au format GML (RecoStaR).

## Structure du projet

```text
star_engine/
├── conversion/       Conversion de fichiers GML ↔ GeoJSON
│   └── recostar/
│       ├── conversion_V1/    Convertisseur RecoStaR v1
│       └── conversion_V1_1/  Convertisseur RecoStaR v1.1
├── controles/        Contrôles qualité des données GeoJSON
│   └── recostar/
│       ├── controles_alti/          Contrôles altimétriques (Z null, 3D, IGN)
│       ├── controles_noeuds/        Contrôles des nœuds (géométrie, extrémités, tension, terre)
│       ├── controles_plor/          Contrôles PLOR (doublons, câbles, cheminements)
│       └── controles_projections/   Contrôles de projection (coordonnées, ensembles)
├── traitements/      Traitements métier sur les données
│   └── recostar/
│       └── calcul_longueurs/  Calcul des longueurs électriques de câbles
├── pipelines/        Orchestration complète des chaînes de traitement
│   └── recostar/
│       ├── pipeline_recostar_complet_v1.py    Pipeline complet (conversion V1)
│       └── pipeline_recostar_complet_v1_1.py  Pipeline complet (conversion V1.1)
└── contraintes_python.md   Conventions et règles de développement
```

## Librairies Python utilisées

### Dépendances principales

| Librairie   | Version | Licence    | Usage                                        |
| ----------- | ------- | ---------- | -------------------------------------------- |
| defusedxml  | 0.7.1   | PSFL       | Parsing XML sécurisé (protection XXE)        |
| pyproj      | 3.7.2   | MIT        | Transformations de coordonnées géographiques |
| reportlab   | 4.4.10  | BSD        | Génération des rapports PDF                  |
| requests    | 2.32.5  | Apache-2.0 | Requêtes HTTP (API IGN altimétrie)           |

### Dépendances de développement

| Librairie | Version | Licence | Usage                        |
| --------- | ------- | ------- | ---------------------------- |
| pytest    | 9.0.2   | MIT     | Exécution de tests unitaires |

### Bibliothèque standard Python

`argparse`, `collections`, `datetime`, `functools`, `itertools`, `json`,
`logging`, `math`, `os`, `pathlib`, `re`, `subprocess`, `sys`, `typing`,
`unittest`, `uuid`, `xml`
