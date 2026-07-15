# Contrôles RecoStaR

Ce répertoire regroupe l'ensemble des contrôles appliqués aux jeux de données
RecoStaR, organisés en **familles**, chacune dans son sous-dossier avec son
propre pipeline. La **pipeline globale** (`pipeline_globale.py`) les exécute
toutes depuis un point d'entrée unique et produit un rapport PDF de synthèse.

## Familles de contrôles

| Famille | Dossier | Contrôles | Entrée | Documentation |
|---------|---------|-----------|--------|---------------|
| Structuration | `xsd_structuration/` | E110 – E114 | fichier GML | [README](xsd_structuration/README.md) |
| Projection | `projection/` | E300 – E303 | répertoire GeoJSON | [README](projection/README.md) |
| Altimétrie | `altimetrie/` | E200 – E209 | répertoire GeoJSON | [README](altimetrie/README.md) |
| Cheminement | `cheminement/` | E400 – E404 | répertoire GeoJSON | [README](cheminement/README.md) |
| Câble | `cable/` | E500 – E507 | répertoire GeoJSON | [README](cable/README.md) |

Les utilitaires GeoJSON communs (lecture/écriture, extraction d'identifiant) sont
centralisés dans `utils_geojson_commun.py`, chaque famille y déléguant via son
propre `utils_geojson.py`.

---

## Pipeline globale (`pipeline_globale.py`)

### Usage

```bash
python pipeline_globale.py --repertoire <chemin> [--sortie <chemin>]
                           [--gml <fichier.gml>] [--numero_affaire <numero>]
```

- `--repertoire` : répertoire contenant les données à contrôler ;
- `--sortie` : répertoire dans lequel créer le dossier `controle/`
  (défaut : le répertoire d'entrée) ;
- `--gml` : fichier GML des contrôles de structuration (voir ci-dessous) ;
- `--numero_affaire` : requis par le contrôle d'emprise DR (E303).

Le rapport global est imprimé en JSON sur la sortie standard.

### Arborescence produite

```
controle/
├── rapport_controles.pdf     synthèse destinée au client
├── rapport_controles.json    pendant machine du PDF
├── altimetrie/               *.geojson
├── cable/                    *.geojson
├── cheminement/              *.geojson
├── projection/               *.geojson
└── structuration/            *.json
```

Chaque sous-dossier reçoit **exactement** les fichiers produits par le pipeline
de sa famille : les pipelines sont réutilisés tels quels, seul leur répertoire de
sortie change. Aucune logique métier n'est dupliquée ni modifiée.

### Sélection du fichier GML

Le pipeline de structuration contrôle un fichier GML, là où les quatre autres
reçoivent un répertoire. Le fichier est résolu ainsi :

1. `--gml` s'il est fourni ;
2. sinon, détection automatique **si et seulement si** le répertoire contient un
   seul GML ;
3. plusieurs GML ou aucun : la famille est **ignorée**, avec son motif dans le
   rapport. Aucun fichier n'est choisi arbitrairement.

### Statuts

| Statut | Condition |
|--------|-----------|
| **Non conforme** | au moins une anomalie de priorité déclassante (`bloquant`) |
| **Incomplet** | aucune anomalie déclassante, mais au moins un contrôle n'a pas pu s'exécuter |
| **Conforme** | tous les contrôles ont abouti, sans anomalie déclassante |
| **Non exécuté** | famille ignorée (donnée d'entrée absente) |

Un **défaut avéré prime sur une vérification incomplète** : une famille présentant
une anomalie bloquante est « Non conforme », même si l'un de ses contrôles a
échoué.

Les anomalies de priorité **`information`** (E505, règle 2 d'E506) sont comptées
et détaillées mais **ne déclassent pas** : c'est la définition même de cette
priorité dans le projet.

Le statut **`Incomplet`** distingue « je n'ai pas pu vérifier » de « c'est non
conforme ». Le cas est courant et légitime : E303 sans `--numero_affaire`, E300
sans `_metadata.json`, ou une couche source absente. L'assimiler à « Non
conforme » signalerait un défaut inexistant sur un document client ; à
« Conforme », cela affirmerait une vérification non faite. Le motif de chaque
échec est restitué dans le PDF.

### Rapport PDF (`rapport_pdf.py`)

Généré avec **ReportLab** (déclaré dans `pyproject.toml`), police Helvetica —
aucune police externe n'est embarquée.

- **Page de synthèse** : statut global, encadré du jeu de données, tableau par
  famille (statut, nombre de contrôles, anomalies, ventilation par priorité).
  Seules les colonnes de priorité **effectivement alimentées** sont affichées :
  le projet n'utilise à ce jour que `bloquant` et `information`, afficher des
  colonnes « Majeure » et « Mineure » toujours vides nuirait à la lisibilité.
- **Détail par famille** : statut rappelé par une pastille colorée, puis un
  tableau `Code · Contrôle · Anomalies · Priorité`. Les motifs d'échec y sont
  restitués.

---

## Architecture

```
pipeline_globale.py     orchestration + CLI
familles_controle.py    registre déclaratif des familles + libellés
synthese_controles.py   modèle normalisé (module pur, sans E/S)
rapport_pdf.py          rendu ReportLab
```

**Couche de normalisation.** Les pipelines n'exposent pas le même format de
rapport : les pipelines GeoJSON produisent `nombre_anomalies` et une `priorite`
scalaire, le pipeline XSD `nb_erreurs` et une `conformite`, et E506 un
dictionnaire `priorites` indexé par type d'anomalie. `synthese_controles.py`
convertit ces formats en un modèle unique, seul connu du rapport PDF. Les
pipelines existants ne sont pas modifiés : la normalisation est une adaptation
**en lecture**, ce qui garantit l'absence de régression.

La ventilation par priorité est **pilotée par les données**, sans cas particulier
codé en dur : un contrôle déclarant `priorites` + `anomalies_par_type` est
ventilé par type ; à défaut, sa `priorite` scalaire s'applique ; à défaut encore,
la `priorite_par_defaut` de sa famille.

**Isolation des défaillances.** L'échec d'une famille (pipeline introuvable,
exception, donnée absente) n'interrompt pas les autres : elle est reportée comme
non exécutée avec son motif — même principe que chaque pipeline vis-à-vis de ses
propres contrôles.

**Chargement des pipelines.** Les modules de contrôle s'importent à plat
(`from controle_e200 import ...`) et ne constituent pas des paquets installables :
le sous-dossier de chaque famille est ajouté à `sys.path` et son pipeline chargé
via `importlib` sous un nom préfixé (les cinq exposent tous un
`executer_pipeline`). Le chargement est mis en cache (`@cache`).

### Ajouter une famille

Une seule modification suffit — ni l'orchestrateur ni le rapport PDF ne sont à
toucher :

1. déclarer une entrée dans `familles_controle.FAMILLES` (clé, libellé, dossier,
   module de pipeline, sous-dossier de sortie, mode) ;
2. déclarer les libellés de ses contrôles dans `LIBELLES_CONTROLES`.

Deux tests garantissent cette intégrité : `test_tous_les_controles_ont_un_libelle`
échoue si un contrôle apparaîtrait sans libellé dans le PDF, et
`test_aucun_libelle_orphelin` si un libellé désigne un contrôle inexistant.

> Les libellés ne sont pas extraits des docstrings des modules de contrôle : leur
> format n'est pas homogène (19 des 32 contrôles seulement suivent la convention
> `Controle EXXX : ...`), une extraction automatique serait partielle et fragile.
> Le registre est la source de vérité du rapport.

Le mode d'une famille (`MODE_REPERTOIRE` ou `MODE_GML`) détermine la façon dont
son pipeline est appelé ; un mode supplémentaire s'ajouterait dans
`pipeline_globale._executer_pipeline_*`.

---

## Tests

```bash
cd recostar/controle && python -m pytest tests/          # pipeline globale
cd recostar/controle/<famille> && python -m pytest tests/  # une famille
```
