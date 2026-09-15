# StaR-Engine

[![REUSE Compliance](https://img.shields.io/badge/reuse-compliant-green.svg)](https://reuse.software/)

Moteur de traitement des données RecoStaR — conversion GeoJSON ↔ GML, contrôles qualité et calcul des longueurs de câbles pour les réseaux électriques de distribution publique (format StaR-Elec).

---

## Structure

```
recostar/
├── pipeline_complet.py  # Orchestrateur : enchaîne les quatre étapes ci-dessous
├── conversion/          # GeoJSON ↔ GML (schémas RecoStaR v1.0 et v1.1)
├── controle/            # Contrôles qualité (structuration, projection, altimétrie,
│                        #   cheminement, câble)
└── traitement/          # Calcul des longueurs de câbles et génération de rapport PDF
```

Chaque sous-module est autonome et possède son propre README.

---

## Pipeline complet

`recostar/pipeline_complet.py` est le point d'entrée unique du traitement d'un récolement. Il enchaîne les quatre étapes, chacune consommant la sortie de la précédente :

| # | Étape | Script |
|---|-------|--------|
| 1 | Conversion GML → GeoJSON | `conversion/conversion_V1_1/recostar_to_geojson.py` |
| 2 | Contrôles qualité | `controle/pipeline_globale.py` |
| 3 | Calcul des longueurs | `traitement/calcul_longueurs/pipeline.py` |
| 4 | Conversion GeoJSON → GML | `conversion/conversion_V1_1/geojson_to_recostar.py` |

```bash
# Traitement d'un récolement
poetry run python recostar/pipeline_complet.py --gml recolement.gml [--sortie <chemin>]

# Traitement par lot : tous les GML d'un dossier
poetry run python recostar/pipeline_complet.py --lot dossier_livraison/ [--sortie <chemin>]
```

| Option | Rôle |
|--------|------|
| `--gml` | Fichier GML à traiter (**exclusif de `--lot`**) |
| `--lot` | Dossier contenant plusieurs GML, traités successivement (**exclusif de `--gml`**) |
| `--sortie` | Répertoire de travail (défaut : dossier `pipeline_recostar/` à côté du GML ou du dossier de lot) |
| `--gml-sortie` | GML régénéré (défaut : `<nom>_regenere.gml` dans le répertoire de sortie) — incompatible avec `--lot` |
| `--numero_affaire` | Numéro d'affaire, requis par les contrôles d'emprise DR (E303, E508) |
| `--srs` | Force le CRS du GML régénéré ; à défaut, détecté depuis les GeoJSON |
| `--commentaire` | Ajoute une balise `Commentaire` vide aux entités du GML régénéré qui n'en possèdent pas (évolution V1.1). Transmis à la conversion sortante ; les commentaires déjà renseignés sont conservés |

Arborescence produite :

```
<sortie>/
├── geojson/                  # étape 1 : fichiers RPD_*.geojson
├── controle/                 # étape 2 : rapports + rapport_controles.pdf
├── rapport/                  # étape 3 : resultats_longueurs.json + PDF
├── <nom>_regenere.gml        # étape 4 : GML reconstruit
└── rapport_pipeline.json     # synthèse des quatre étapes
```

### Traitement par lot

`--lot` désigne un dossier de livraison : chaque GML qu'il contient est traité indépendamment, dans son propre sous-dossier nommé d'après le fichier. Le parcours n'est pas récursif et l'extension est reconnue quelle que soit sa casse (`.gml` ou `.GML`).

```
<sortie>/
├── <nom_gml_1>/              # arborescence complète du premier récolement
├── <nom_gml_2>/              # arborescence complète du second
└── rapport_lot.json          # synthèse du lot
```

**L'échec d'un GML n'interrompt pas le lot** : les récolements sont indépendants les uns des autres, et s'arrêter priverait l'utilisateur des résultats déjà acquis. Les fichiers fautifs sont recensés dans `gml_en_echec`, et chaque rapport individuel reste consultable dans `traitements` comme dans le sous-dossier concerné. Le rapport de lot expose `nombre_gml`, `nombre_reussis` et `nombre_echoues`.

Deux fichiers partageant leur radical (`Reseau.gml` et `Reseau.GML`) reçoivent des dossiers distincts, le second étant suffixé d'un indice : sans quoi le premier serait écrasé.

Le rapport de synthèse est également écrit sur la sortie standard. Le script sort avec le **code 1** dès qu'une étape échoue — ou, en mode lot, dès qu'un GML échoue — ce qui le rend directement utilisable en CI.

**Arrêt à la première étape en échec** : chaque étape consommant la sortie de la précédente, poursuivre produirait des résultats calculés sur des données absentes. La politique est isolée dans `_interrompre_apres` pour pouvoir être assouplie sans toucher à l'orchestration. Les étapes non atteintes sont listées dans `etapes_ignorees`.

Les étapes sont exécutées dans des sous-processus dédiés : les quatre scripts s'importent à plat et exposent des modules homonymes, qui se masqueraient mutuellement dans un processus unique. Ajouter une étape consiste à déclarer une entrée dans le registre `ETAPES` et son constructeur d'arguments dans `CONSTRUCTEURS_ARGUMENTS`.

---

## Conversion

Conversion bidirectionnelle entre fichiers GeoJSON terrain (`RPD_*.geojson`) et fichier GML d'archivage conforme au schéma XSD StaR-Elec.

Deux versions du schéma sont supportées :

- **V1.0** — `conversion/conversion_V1/`
- **V1.1** — `conversion/conversion_V1_1/` (ajout `RPD_CableTelecommunication_Reco`, géométries 3D, `ChargeGeneratrice`)

La version est détectée automatiquement depuis le `schemaLocation` du fichier GML.

---

## Contrôle

Six familles de contrôles, chacune disposant d'un pipeline orchestrant l'exécution séquentielle des vérifications. Un échec de contrôle n'interrompt pas les suivants.

| Famille | Répertoire | Codes | Périmètre |
|---------|-----------|-------|-----------|
| Structuration XSD | `controle/xsd_structuration/` | E010–E014 (V1.0)<br>E110–E114 (V1.1) | Conformité GML au schéma XSD, règles métier, valeurs |
| Projection | `controle/projection/` | E300–E303 | Cohérence CRS, géométrie spatiale, emprise DR |
| Altimétrie | `controle/altimetrie/` | E200–E209 | Qualité de la composante Z (3D, doublons, référentiel IGN, points de levé) |
| Cheminement | `controle/cheminement/` | E400–E404 | Topologie câble/cheminement, connexité, profondeur |
| Câble | `controle/cable/` | E500–E509 | Cohérence métier, désignation, raccordement aux nœuds, emprise DR des câbles HTB, discrétisation des courbes |
| Conteneur | `controle/conteneur/` | E600–E610 | Conformité du matériel de jonction au catalogue de référence, rattachement du matériel à une jonction, unicité de ses identifiants, caractéristiques de poteau, types de nœuds rattachés aux coffrets, chaîne de localisation des nœuds sans géométrie, localisation des remontées aéro-souterraines et des points de comptage, cardinalité des raccordements de jonction, rattachement des nœuds du réseau à un câble existant, nomenclature de composition des coffrets |

L'ordre du tableau est celui d'exécution, déclaré dans `controle/familles_controle.py` — point d'extension unique : ni l'orchestrateur `pipeline_globale.py` ni le rapport PDF n'ont à être modifiés pour ajouter une famille.

Chaque contrôle produit un rapport GeoJSON ou JSON listant les anomalies avec leur niveau de priorité. `controle/pipeline_globale.py` exécute les six familles, centralise leurs sorties dans un dossier `controle/` et produit un PDF de synthèse.

### Priorités d'anomalie

L'échelle est déclarée dans `controle/synthese_controles.py`, du plus grave au moins grave :

| Priorité | Libellé | Couleur au rapport | Déclasse la famille ? | Contrôles concernés |
|----------|---------|--------------------|-----------------------|---------------------|
| `bloquant` | Bloquante | rouge (gras) | **Oui** | tous sauf ci-dessous |
| `majeur` | Majeure | **orange** | Non | E202, E404, E506 (règle câble de terre), E600, E602, E603, E608, E610, E113/E013 (règle `schemaLocation` sur la branche `main`) |
| `mineur` | Mineure | jaune | Non | E204, E209, E501, E604, E114/E014 (règle `E_THEME_RPD`) |
| `information` | Information | bleu | Non | E203, E505, E508 |
| `non_precisee` | Non précisée | gris | Non | repli si un rapport n'annonce pas de priorité |

**Seule la priorité `bloquant` déclasse** une famille en « Non conforme » (`PRIORITES_DECLASSANTES`). Les autres niveaux sont comptés et affichés dans le rapport : ils signalent un écart à corriger sans bloquer la livraison du récolement. La graisse du rapport PDF traduit cette distinction — seul ce qui invalide la conformité est en gras.

Ajouter ou recolorer une priorité se fait en deux endroits déclaratifs : `ORDRE_PRIORITES` / `LIBELLES_PRIORITES` / `PRIORITES_DECLASSANTES` dans `synthese_controles.py`, et `COULEURS_PRIORITE` dans `rapport_pdf.py`. Aucune fonction de style n'a à connaître l'échelle.

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
