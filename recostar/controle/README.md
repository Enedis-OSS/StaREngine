# Contrôles RecoStaR

Ce répertoire regroupe l'ensemble des contrôles appliqués aux jeux de données
RecoStaR, organisés en **familles**, chacune dans son sous-dossier avec son
propre pipeline. La **pipeline globale** (`pipeline_globale.py`) les exécute
toutes depuis un point d'entrée unique et produit un rapport PDF de synthèse.

## Familles de contrôles

| Famille | Dossier | Contrôles | Entrée | Documentation |
|---------|---------|-----------|--------|---------------|
| Structuration | `xsd_structuration/` | E010 – E014 (V1.0)<br>E110 – E114 (V1.1) | fichier GML | [README](xsd_structuration/README.md) |
| Projection | `projection/` | E300 – E303 | répertoire GeoJSON | [README](projection/README.md) |
| Altimétrie | `altimetrie/` | E200 – E209 | répertoire GeoJSON | [README](altimetrie/README.md) |
| Cheminement | `cheminement/` | E400 – E404 | répertoire GeoJSON | [README](cheminement/README.md) |
| Câble | `cable/` | E500 – E509 | répertoire GeoJSON | [README](cable/README.md) |
| Conteneur | `conteneur/` | E600 – E610 | répertoire GeoJSON | [README](conteneur/README.md) |

Les utilitaires GeoJSON communs (lecture/écriture, extraction d'identifiant,
normalisation des propriétés d'écarts) sont centralisés dans
`utils_geojson_commun.py`, chaque famille y déléguant via son
propre `utils_geojson.py`. De même, la résolution du référentiel DR (numéro
d'affaire → code DR → emprise géographique) et le test d'appartenance
planimétrique sont centralisés dans `utils_emprise_dr_commun.py`, partagé par
E303 (entités hors emprise) et E508 (câbles HTB dans l'emprise) via le module
délégué `utils_emprise_dr.py` de chaque famille.

Tout fichier d'écarts n'est écrit **que si au moins une anomalie est détectée**,
et chaque `feature` porte en tête le même socle de propriétés :
`code_controle`, `priorite`, `id_entite`, `type_anomalie` (code technique) et
`description` (phrase décrivant l'anomalie). Les propriétés métier propres à
chaque contrôle suivent ce socle.

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
- `--numero_affaire` : requis par les contrôles d'emprise DR (E303 et E508).

Le rapport global est imprimé en JSON sur la sortie standard.

### Arborescence produite

```
controle/
├── rapport_controles.pdf     synthèse destinée au client
├── rapport_controles.json    pendant machine du PDF
├── altimetrie/               *.geojson
├── cable/                    *.geojson
├── cheminement/              *.geojson
├── conteneur/                *.geojson
├── projection/               *.geojson
└── structuration/            *.json
```

Chaque sous-dossier reçoit **exactement** les fichiers produits par le pipeline
de sa famille : les pipelines sont réutilisés tels quels, seul leur répertoire de
sortie change. Aucune logique métier n'est dupliquée ni modifiée.

### Sélection du fichier GML

Le pipeline de structuration contrôle un fichier GML, là où les cinq autres
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

Les anomalies de priorité **`information`** (E203, E505, E508) sont comptées
et détaillées mais **ne déclassent pas** : c'est la définition même de cette
priorité dans le projet. Il en va de même des priorités `majeur` et `mineur`.

Les anomalies de priorité **`majeur`** (E404, E600) sont, de la même manière,
comptées et détaillées sans déclasser la famille.

La priorité est portée par l'**anomalie**, pas par le contrôle : un même contrôle
peut en mêler plusieurs. C'est le cas d'E506 (câbles électriques bloquants,
câbles de terre majeurs) et, depuis l'introduction des priorités de
structuration, d'E113/E013 et E114/E014 — voir
`xsd_structuration/priorites_structuration.py`.

Le statut **`Incomplet`** distingue « je n'ai pas pu vérifier » de « c'est non
conforme ». Le cas est courant et légitime : E303 et E508 sans `--numero_affaire`, E300
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
  afficher des colonnes toujours vides nuirait à la lisibilité. Les cinq niveaux
  de l'échelle sont susceptibles d'apparaître, aucune colonne n'est figée.
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
scalaire, le pipeline XSD `nb_erreurs` et une ventilation
`anomalies_par_priorite` déjà calculée, et E506 un dictionnaire `priorites`
indexé par type d'anomalie. `synthese_controles.py` convertit ces formats en un
modèle unique, seul connu du rapport PDF. Les pipelines existants ne sont pas
modifiés : la normalisation est une adaptation **en lecture**, ce qui garantit
l'absence de régression.

La ventilation par priorité est **pilotée par les données**, sans cas particulier
codé en dur. Quatre conventions sont reconnues, de la plus explicite à la plus
implicite :

| Clés du rapport | Interprétation | Utilisée par |
|-----------------|----------------|--------------|
| `anomalies_par_priorite` | ventilation déjà établie à la source, reprise telle quelle | pipeline de structuration XSD |
| `priorites` + `anomalies_par_type` | priorité dérivée du type d'anomalie | E506 |
| `priorite` | priorité scalaire du contrôle entier | E200 à E509 (hors E506) |
| *(aucune)* | `priorite_par_defaut` de la famille | repli |

### Géométries multi-parties (`MultiLineString`)

Les parties d'un `MultiLineString` RecoStaR ne sont **ni ordonnées ni orientées** :
le premier sommet de la première partie peut coïncider avec le dernier de la
dernière. `utils_geometrie_commun.py` offre trois stratégies, à choisir selon ce
que le contrôle mesure :

| Fonction | Ce qu'elle rend | À employer quand | Utilisée par |
|---|---|---|---|
| `extraire_parties_lineaires` | les parties telles quelles | les parties n'ont pas à être reliées | E504, E505 |
| `extraire_extremites` | les extrémités **topologiques** (sommets de parité impaire) | le contrôle raisonne sur les bouts du câble | E208, E506, E507 |
| `recoller_parties_lineaires` | les polylignes **continues maximales** (`shapely.ops.linemerge`) | le contrôle parcourt des sommets **consécutifs** | E202, E509 |

Prendre le premier et le dernier sommet après mise à plat désignerait un raccord
interne et manquerait les vrais bouts : l'écart est mesuré à 22 câbles sur 30 en
E208, et 10 fausses anomalies en E507. Symétriquement, analyser les parties
séparément prive un contrôle à fenêtre glissante des **sommets de raccord**, qui
ne sont jamais des sommets intermédiaires.

Le recollement préserve le Z, réordonne et oriente les tronçons et dédoublonne
les nœuds partagés. Un appelant exigeant une entité d'un seul tenant (E202) teste
la longueur du résultat ; un appelant tolérant les tronçons disjoints (E509) itère
dessus.

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
