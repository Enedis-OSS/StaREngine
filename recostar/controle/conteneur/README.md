# Contrôles de conteneur

Ce dossier regroupe les contrôles appliqués aux entités de conteneur et au
matériel qui leur est associé dans les fichiers GeoJSON Recostar. Chaque
contrôle parcourt un ou plusieurs fichiers GeoJSON, détecte les anomalies et
produit un fichier d'écarts GeoJSON (préfixé `ecarts_`) directement exploitable
dans QGIS (le `crs` du fichier source est propagé).

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
| `code_controle` | Code du contrôle ayant produit l'écart (`E600`…) |
| `priorite` | Niveau de priorité de l'anomalie (`bloquant`, `majeur`, `mineur`, `information`) |
| `id_entite` | Identifiant de l'entité portant la géométrie de la feature |
| `type_anomalie` | Code technique de l'anomalie, stable et exploitable en filtre |
| `description` | Phrase décrivant l'anomalie, lisible dans QGIS |

Les propriétés métier spécifiques à chaque contrôle sont conservées à la suite du
socle. La normalisation est assurée par `normaliser_geojson_ecarts()` à partir du
`ProfilEcarts` déclaré en tête de chaque script de contrôle.

## Vue d'ensemble

| Code | Script | Cible | Condition d'anomalie | Priorité | Fichier de sortie |
|------|--------|-------|----------------------|----------|-------------------|
| E600 | `controle_e600.py` | Jonction, Materiel | matériel absent du catalogue de référence | `majeur` | `ecarts_e600_materiel_jonction_non_reference.geojson` |
| E601 | `controle_e601.py` | Materiel, Jonction | matériel non rattaché à une jonction de type valide | `bloquant` | `ecarts_e601_materiel_jonction_non_rattache.geojson` |
| E602 | `controle_e602.py` | Materiel, Jonction | couple `NumeroLot` / `NumeroSerie` partagé par plusieurs jonctions | `majeur` | `ecarts_e602_materiel_identifiants_partages.geojson` |
| E603 | `controle_e603.py` | Support | `Classe` / `Effort` / `Hauteur` hors du catalogue poteau | `majeur` | `ecarts_e603_poteau_caracteristiques_non_referencees.geojson` |
| E604 | `controle_e604.py` | Coffret, toutes couches | nœud d'un type non autorisé rattaché à un coffret | `mineur` | `ecarts_e604_coffret_noeud_non_autorise.geojson` |
| E605 | `controle_e605.py` | 6 couches de nœuds, conteneurs, GeometrieSupplementaire | chaîne de localisation rompue | `bloquant` | `ecarts_e605_noeud_localisation_incomplete.geojson` |
| E606 | `controle_e606.py` | Jonction (remontée), Support, GeometrieSupplementaire | remontée aéro-souterraine sans localisation | `bloquant` | `ecarts_e606_remontee_localisation_absente.geojson` |
| E607 | `controle_e607.py` | PointDeComptage, OuvrageCollectifBranchement, conteneurs | ouvrage sans localisation | `bloquant` | `ecarts_e607_ouvrage_localisation_absente.geojson` |
| E608 | `controle_e608.py` | Jonction, 3 couches de câble | nombre de câbles raccordés incompatible avec le TypeJonction | `majeur` | `ecarts_e608_jonction_nombre_cables.geojson` |
| E609 | `controle_e609.py` | 9 couches de nœuds, toutes couches | `cables_href` ne résout pas un câble existant | `bloquant` | `ecarts_e609_noeud_rattachement_cable.geojson` |
| E610 | `controle_e610.py` | Coffret, toutes couches | composition du coffret non conforme à la nomenclature de son `TypeCoffret` | `majeur` | `ecarts_e610_coffret_nomenclature.geojson` |

Les fonctions utilitaires communes (lecture/écriture GeoJSON, extraction
d'identifiant) sont centralisées dans `utils_geojson.py`, qui délègue au module
partagé `../utils_geojson_commun.py`. La décomposition géométrique passe de même
par `utils_geometrie.py`, shim vers `../utils_geometrie_commun.py` — il réexporte
**exactement** le même jeu de noms que les shims des autres domaines, contrainte
vérifiée par `TestCoherenceDesShims`. L'orchestration de l'ensemble est assurée
par `pipeline_controle_conteneur.py`.

### Usage CLI

```bash
python controle_e600.py --repertoire <chemin> [--sortie <chemin>]
python controle_e601.py --repertoire <chemin> [--sortie <chemin>]
python controle_e602.py --repertoire <chemin> [--sortie <chemin>]
python controle_e603.py --repertoire <chemin> [--sortie <chemin>]
python controle_e604.py --repertoire <chemin> [--sortie <chemin>]
python controle_e605.py --repertoire <chemin> [--sortie <chemin>]
python controle_e606.py --repertoire <chemin> [--sortie <chemin>]
python controle_e607.py --repertoire <chemin> [--sortie <chemin>]
python controle_e608.py --repertoire <chemin> [--sortie <chemin>]
python controle_e609.py --repertoire <chemin> [--sortie <chemin>]
python controle_e610.py --repertoire <chemin> [--sortie <chemin>]

# Enchaînement de tous les contrôles ci-dessus :
python pipeline_controle_conteneur.py --repertoire <chemin> [--sortie <chemin>]
```

- `--repertoire` : répertoire contenant les fichiers GeoJSON.
- `--sortie` : répertoire de sortie (par défaut, le répertoire d'entrée).

Le résultat est imprimé en JSON sur la sortie standard.
Les fichiers absents du répertoire ne bloquent pas l'exécution.

---

## E600 — Conformité du matériel de jonction au catalogue (`controle_e600.py`)

**Ce qui est contrôlé :** le matériel déclaré pour une jonction électrique doit
correspondre à une entrée du catalogue de référence des boîtes de jonction et de
dérivation :

```
recostar/referentiels/boites/catalogue-materiel-jonction.json
```

**Fichiers analysés :**

- `RPD_Jonction_Reco.geojson` (porte le lien `materiel_href` et le `DomaineTension`)
- `RPD_Materiel_Reco.geojson` (porte le `Fabricant` et le `Modele`)

La présence de chacun de ces fichiers est optionnelle : leur absence est
signalée dans le rapport JSON (`fichier_jonction_absent`,
`fichier_materiel_absent`) sans retourner d'erreur. En revanche, un catalogue
**absent, illisible ou vide est une erreur bloquante** : sans référence, aucune
conclusion ne peut être tirée des valeurs du matériel.

### Chaîne de références

```
RPD_Jonction_Reco.materiel_href  ──►  RPD_Materiel_Reco.id
        │                                     │
        │ DomaineTension                      │ Fabricant, Modele
        └──────────────┬──────────────────────┘
                       ▼
        entrée du catalogue (domaineTension, fabricant, modele)
```

`RPD_Materiel_Reco` n'a **pas de géométrie propre**. La feature d'écart porte
donc le `Point` de la jonction : l'anomalie serait sinon invisible dans QGIS.

### Périmètre

Une entité `RPD_Jonction_Reco` n'est contrôlée que si elle remplit les **trois**
conditions cumulatives suivantes :

| Condition | Valeur attendue |
|-----------|-----------------|
| Lien vers un matériel | `materiel_href` renseigné |
| Statut | `UnderCommissionning` |
| Type de jonction | `Derivation` ou `Jonction` |

Toute autre jonction est ignorée. En particulier, une jonction **sans**
`materiel_href` est hors périmètre : les `ExtremiteReseau` n'ont légitimement
pas de matériel (cf. `champsFabricantModele` dans `jonction-mapping.json`), et
l'exigence de présence du lien relève du contrôle de structuration.

### Types d'anomalie

| `type_anomalie` | Condition |
|-----------------|-----------|
| `materiel_introuvable` | `materiel_href` ne résout aucune entité `RPD_Materiel_Reco` |
| `domaine_tension_hors_catalogue` | le `DomaineTension` de la jonction n'est couvert par aucune entrée du catalogue (`HTB`, valeur absente ou inconnue) |
| `fabricant_non_reference` | le `Fabricant` du matériel n'existe pas au catalogue pour ce domaine |
| `modele_non_reference` | le `Modele` du matériel n'existe pas au catalogue pour ce domaine |
| `couple_fabricant_modele_non_reference` | `Fabricant` et `Modele` existent séparément, mais leur association n'est pas répertoriée |

Les règles ne se recouvrent jamais :

- un **domaine hors catalogue court-circuite** les autres règles — sans domaine
  de référence, `Fabricant` et `Modele` ne sont pas évaluables ;
- l'**association n'est évaluée que si les deux valeurs sont individuellement
  reconnues** — signaler l'association d'une valeur déjà invalide n'apporterait
  aucune information ;
- `Fabricant` et `Modele` inconnus **cumulent** deux anomalies : ce sont deux
  défauts distincts, chacun à corriger.

Un `Fabricant` ou un `Modele` non renseigné ne peut correspondre à aucune
entrée : il est signalé par l'anomalie « non référencé » correspondante, la
valeur brute (`null`) étant reportée dans le fichier d'écarts.

### Normalisation des valeurs comparées

Le catalogue et l'export GeoJSON n'utilisent pas les mêmes conventions de
saisie. La comparaison s'effectue sur des chaînes normalisées :

- **casse ignorée** (`Cahors` ↔ `cahors`) ;
- **suites d'espaces blancs repliées** en un espace unique, bords supprimés —
  sémantique `collapse` de XSD (`xs:token`).

Le repliement des espaces **internes** n'est pas cosmétique. Les valeurs issues
du GML portent les sauts de ligne du document source : le jeu `Echantillon/`
déclare `"DDC 240-35 \nv2006"` là où le catalogue écrit `"DDC 240-35 v2006"`.
Un simple `strip()` laisserait diverger ces deux écritures du **même** modèle et
produirait des faux positifs (2 sur 4 matériels du jeu de test). Le repliement
n'introduit aucun faux négatif : les 30 modèles BT, les 23 modèles HTA et les
8 fabricants du catalogue restent tous distincts après normalisation.

Même principe que le contrôle E502, étendu ici aux espaces internes.

### Construction de l'index du catalogue

L'index est construit à partir de la **seule liste `entrees`**. Les blocs
`fabricants`, `modeles` et `correspondancesParDomaine` du catalogue en sont des
vues dérivées : les ignorer supprime tout risque de divergence si le catalogue
évolue.

C'est un choix de robustesse, pas une préférence de style. Les 424 entrées
actuelles forment exactement le produit cartésien de chaque domaine
(HTA : 8 × 23 = 184, BT : 8 × 30 = 240) : **aujourd'hui**, vérifier
l'association est donc équivalent à vérifier les deux valeurs séparément. Le
jour où un modèle ne sera plus proposé par tous les fabricants, le contrôle
restera correct sans une ligne de code à changer — et l'anomalie
`couple_fabricant_modele_non_reference` prendra effet d'elle-même.

L'index expose trois structures en `frozenset`, pour un test d'appartenance en
`O(1)` par jonction :

| Structure | Contenu |
|-----------|---------|
| `entrees` | triplets `(domaine, fabricant, modele)` |
| `fabricants_par_domaine` | fabricants valides pour chaque domaine |
| `modeles_par_domaine` | modèles valides pour chaque domaine |

Le catalogue est chargé **une seule fois** par exécution, hors de toute boucle.

### Propriétés du fichier d'écarts

Au-delà du socle commun :

| Propriété | Description |
|-----------|-------------|
| `fichier_source` | `RPD_Jonction_Reco.geojson` |
| `id_jonction` | identifiant de la jonction contrôlée |
| `id_materiel` | valeur de `materiel_href` |
| `type_jonction` | `Derivation` ou `Jonction` |
| `domaine_tension` | valeur brute portée par la jonction |
| `fabricant` | valeur brute du matériel (`null` si le matériel est introuvable) |
| `modele` | valeur brute du matériel (`null` si le matériel est introuvable) |

Les valeurs sont reportées **brutes**, non normalisées : l'opérateur doit voir
ce que la donnée contient réellement.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "majeur",
  "nombre_anomalies": 6,
  "anomalies_par_type": { "fabricant_non_reference": 4, "modele_non_reference": 2 },
  "nombre_jonctions_analysees": 12,
  "nombre_jonctions_controlees": 4,
  "nombre_materiels": 4,
  "nombre_entrees_catalogue": 424,
  "fichier_jonction_absent": false,
  "fichier_materiel_absent": false,
  "sortie": ".../ecarts_e600_materiel_jonction_non_reference.geojson"
}
```

### Priorité

`majeur` : l'écart est compté et détaillé dans le rapport PDF, mais **ne
déclasse pas** la famille en « Non conforme » — seule la priorité `bloquant` est
déclassante (cf. `PRIORITES_DECLASSANTES` dans `synthese_controles.py`).

### Versions

Jonction et matériel ont une structure identique en RecoStaR V1.0 et V1.1 : le
contrôle est **agnostique de version** et n'implémente aucune détection.

---

## E601 — Rattachement du matériel à une jonction (`controle_e601.py`)

**Ce qui est contrôlé :** chaque entité `RPD_Materiel_Reco` doit être portée par
une entité `RPD_Jonction_Reco`, et cette jonction doit être d'un type
susceptible de recevoir du matériel.

**Fichiers analysés :**

- `RPD_Materiel_Reco.geojson` (entités contrôlées)
- `RPD_Jonction_Reco.geojson` (porte la référence `materiel_href` et le `TypeJonction`)

L'absence de l'un ou l'autre est signalée au rapport sans bloquer. Un fichier
jonction absent rend simplement tous les matériels orphelins — c'est le constat
exact, pas un contournement.

### La même relation qu'E600, parcourue en sens inverse

```
E600 :  RPD_Jonction_Reco.materiel_href  ──►  RPD_Materiel_Reco.id
E601 :  RPD_Materiel_Reco.id             ◄──  RPD_Jonction_Reco.materiel_href
```

Ce n'est pas une redite. **E600 itère sur les jonctions** : un matériel
qu'aucune jonction ne référence lui échappe structurellement — il ne le
rencontre jamais. E601 retourne l'index (`{id_materiel: [jonctions]}`) et
devient le seul contrôle capable de voir cet orphelin. Le point est verrouillé
par un test (`TestCoherenceAvecE600.test_materiel_orphelin_invisible_pour_e600`).

Les deux contrôles partagent leurs constantes de relation — fichiers source,
noms de champs, ensemble des types de jonction — E601 les important d'E600,
comme E505 le fait d'E504 et E507 d'E506. Un test vérifie que les deux vues
restent alignées.

### Périmètre

**Toutes** les entités `RPD_Materiel_Reco`, sans condition. Deux différences
avec E600, délibérées :

| | E600 | E601 |
|---|---|---|
| Entité contrôlée | la jonction | le matériel |
| Filtre de statut | `Statut == UnderCommissionning` | **aucun** |
| `{Derivation, Jonction}` | un **périmètre** (les autres types sont ignorés) | une **règle** (les autres types sont une anomalie) |

`RPD_Materiel_Reco` ne porte pas de champ `Statut`, et la règle ne subordonne le
rattachement à aucun état de la jonction : un matériel porté par une jonction
`Decommissioned` reste conforme si le type de celle-ci est valide.

### Types d'anomalie

| `type_anomalie` | Condition |
|-----------------|-----------|
| `jonction_absente` | aucune `RPD_Jonction_Reco` ne référence ce matériel via `materiel_href` |
| `type_jonction_invalide` | une jonction le référence, mais son `TypeJonction` n'est ni `Derivation` ni `Jonction` |

Seuls ces deux types portent du matériel — c'est le drapeau
`champsFabricantModele` du référentiel
`referentiels/boites/jonction-mapping.json`. Une `ExtremiteReseau` ou une
`RemonteeAeroSouterraine` n'a ni `Fabricant` ni `Modele` à déclarer.

La comparaison du `TypeJonction` est **stricte, sans normalisation** :
c'est une énumération du schéma XSD et non une saisie libre, même convention
qu'E600. Une valeur absente, vide ou d'une autre casse est donc invalide — et
doit l'être, elle ne correspond à aucune valeur du schéma.

### Matériel référencé par plusieurs jonctions

Le cas ne se rencontre pas sur les jeux de référence, mais rien ne l'interdit
structurellement. Une anomalie est alors émise **par lien fautif**, convention
des contrôles de relation du projet (E500, E503, E507) : chaque jonction indûment
rattachée est un défaut à corriger pour elle-même. Un lien valide n'efface donc
pas un lien fautif portant sur le même matériel.

### Géométrie des écarts

`RPD_Materiel_Reco` n'a pas de géométrie propre : la feature d'écart porte le
`Point` de la jonction en cause.

Un matériel **orphelin** n'a en revanche aucune position connue — ni la sienne,
ni celle d'une jonction. Sa feature est écrite avec une **géométrie nulle**, ce
que le format GeoJSON admet. Le signaler sans position est préférable à lui en
inventer une : l'anomalie reste lisible dans la table attributaire de QGIS, et
aucun point n'apparaît à un endroit arbitraire de la carte.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "bloquant",
  "nombre_anomalies": 0,
  "anomalies_par_type": {},
  "nombre_materiels_analyses": 4,
  "nombre_materiels_non_conformes": 0,
  "nombre_jonctions_analysees": 12,
  "nombre_liens_controles": 4,
  "fichier_materiel_absent": false,
  "fichier_jonction_absent": false,
  "sortie": null
}
```

`nombre_materiels_non_conformes` dédoublonne les matériels : un matériel portant
deux liens fautifs compte pour deux anomalies mais un seul matériel.

### Priorité

`bloquant` : un matériel orphelin ou porté par une jonction inapte rompt
l'intégrité de la relation `Ouvrage_Materiel`, sans laquelle le récolement ne
décrit plus quel matériel est posé où. La famille Conteneur est **déclassée en
« Non conforme »** dès la première anomalie (cf. `PRIORITES_DECLASSANTES` dans
`synthese_controles.py`).

### Versions

Matériel et jonction ont une structure identique en RecoStaR V1.0 et V1.1 : le
contrôle est **agnostique de version**.

---

## E602 — Unicité des identifiants de matériel (`controle_e602.py`)

**Ce qui est contrôlé :** un couple d'identifiants `NumeroLot` / `NumeroSerie` ne
doit désigner qu'une seule `RPD_Jonction_Reco`. Un même matériel physique ne peut
pas être posé à deux endroits : si ses identifiants apparaissent sur plusieurs
jonctions, c'est qu'il a été saisi plusieurs fois, ou que deux matériels
distincts portent par erreur les mêmes références.

**Fichiers analysés :**

- `RPD_Materiel_Reco.geojson` (porte `NumeroLot` et `NumeroSerie`)
- `RPD_Jonction_Reco.geojson` (porte la référence `materiel_href`)

### Le couple, et non chaque champ pris isolément

C'est le point de conception central, et il n'est pas une préférence de style.

`NumeroLot` est un **numéro de fabrication** : toutes les boîtes issues d'un même
lot le partagent, et sont posées à des jonctions différentes. C'est le cas
normal, pas un défaut. Le jeu `Echantillon2` en donne l'exemple :

| Matériel | `NumeroLot` | `NumeroSerie` | Jonction |
|---|---|---|---|
| m2 | `123654654` | `r` | j2 |
| m6 | `123654654` | `FE3214321` | j6 |

Contrôler `NumeroLot` seul signalerait ces deux boîtes — à tort. Seul le
**couple** identifie une unité physique, et seul le couple est donc regroupé :

```python
def couple_identifiants(proprietes) -> tuple[str, str] | None:
    lot = normaliser_valeur(proprietes.get(CHAMP_NUMERO_LOT))
    serie = normaliser_valeur(proprietes.get(CHAMP_NUMERO_SERIE))
    if lot is None or serie is None:
        return None  # couple incomplet -> hors périmètre
    return lot, serie
```

### Périmètre

Les entités `RPD_Materiel_Reco` remplissant **les deux** conditions :

| Condition | Pourquoi |
|---|---|
| **Les deux** identifiants sont renseignés | Un couple incomplet n'identifie aucune unité. Si `NumeroSerie` manquait, tous les matériels d'un même lot partageraient le couple `(lot, vide)` et seraient signalés à tort. L'exigence de renseignement des champs relève de la structuration (E114). |
| Une jonction **identifiée** les référence | Un matériel orphelin n'est associé à aucune jonction : il ne peut donc pas l'être à plusieurs. Le défaut est celui d'E601. Les jonctions sans `id`, indiscernables entre elles, sont également écartées — elles gonfleraient le compte de jonctions distinctes et provoqueraient un conflit fictif. |

E602 **ne filtre ni sur `Statut` ni sur `TypeJonction`** : la règle d'unicité vaut
quel que soit le type de jonction porteuse. La validité du type est la règle
d'E601.

### Deux cas volontairement laissés conformes

- **Deux enregistrements partageant un couple sur la *même* jonction.** La règle
  porte sur la pluralité des *jonctions*, pas des enregistrements. Le doublon
  strict relève du contrôle de structuration.
- **Un couple incomplet**, quel que soit le nombre de jonctions concernées (voir
  périmètre ci-dessus).

### Un cas volontairement signalé

Un **matériel unique référencé par plusieurs jonctions** : son couple désigne à
lui seul plusieurs jonctions, la règle ne distinguant pas selon le nombre de
matériels en cause. Le rattachement multiple est par ailleurs signalé par E601 —
les deux constats sont exacts et répondent à des questions différentes.

### Comparaison des identifiants

`NumeroLot` et `NumeroSerie` sont des saisies libres, comparées **normalisées** :
casse ignorée, suites d'espaces blancs repliées en un espace unique — même
convention qu'E600, et pour la même raison (les valeurs issues du GML portent
les sauts de ligne du document source). Deux écritures différentes du même
identifiant restent le même matériel.

Les valeurs **brutes** sont en revanche reportées dans le fichier d'écarts :
l'opérateur doit voir ce que la donnée contient réellement.

### Une anomalie par occurrence

Le conflit se corrige sur le terrain, à chacune des positions qu'il met en
cause. Une anomalie est donc émise **par occurrence** du couple, et non une par
couple : chaque feature porte le `Point` de sa propre jonction et la liste
complète des jonctions concernées.

| Propriété | Description |
|-----------|-------------|
| `fichier_source` | `RPD_Materiel_Reco.geojson` |
| `id_materiel` | identifiant du matériel de cette occurrence |
| `id_jonction` | jonction portant cette occurrence (et la géométrie de la feature) |
| `numero_lot` / `numero_serie` | valeurs brutes, non normalisées |
| `nombre_jonctions` | nombre de jonctions distinctes partageant le couple |
| `jonctions_en_conflit` | identifiants de ces jonctions, séparés par des virgules (convention `*_href`), triés pour une sortie stable |

Depuis n'importe laquelle des features, `jonctions_en_conflit` permet donc de
retrouver toutes les autres positions du conflit.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "majeur",
  "nombre_anomalies": 4,
  "nombre_couples_en_conflit": 1,
  "nombre_materiels_analyses": 4,
  "nombre_materiels_controles": 4,
  "nombre_jonctions_analysees": 12,
  "fichier_materiel_absent": false,
  "fichier_jonction_absent": false,
  "sortie": ".../ecarts_e602_materiel_identifiants_partages.geojson"
}
```

`nombre_materiels_controles` ne compte que les matériels du périmètre — couple
complet **et** jonction identifiée.

### Priorité

`majeur` : l'écart est compté et détaillé dans le rapport PDF, mais **ne
déclasse pas** la famille (cf. `PRIORITES_DECLASSANTES` dans
`synthese_controles.py`).

### Versions

Matériel et jonction ont une structure identique en RecoStaR V1.0 et V1.1 : le
contrôle est **agnostique de version**.

---

## E603 — Caractéristiques de poteau conformes au catalogue (`controle_e603.py`)

**Ce qui est contrôlé :** les caractéristiques saisies sur une
`RPD_Support_Reco` doivent former une combinaison complète et valide du
catalogue de référence :

```
recostar/referentiels/supports/poteau-catalogue-mapping.json
```

C'est la transposition du principe d'E600 aux supports : mêmes mécanismes
(chargement unique du catalogue, index en `frozenset`, court-circuit sur le
discriminant, cumul des anomalies par axe), autre entité et autre référentiel.

**Fichier analysé :** `RPD_Support_Reco.geojson`. Son absence est signalée au
rapport sans bloquer ; un catalogue absent, illisible ou vide est en revanche
une **erreur bloquante** — sans référence, aucune conclusion n'est possible.

### Correspondance catalogue ↔ GeoJSON

Les noms diffèrent : le mapping est explicite dans le code.

| Axe du catalogue | Champ `RPD_Support_Reco` |
|---|---|
| `classes` | `Classe_href` |
| `efforts` | `Effort` + `Effort_uom` |
| `hauteurs` | `HauteurPoteau` + `HauteurPoteau_uom` |
| *discriminant* | `Matiere_href` |

### Filtrage par matière

Le catalogue **ne fournit aucune liste de combinaisons**. Il déclare, pour
chaque matière, les valeurs admises sur chacun des trois axes — c'est le
« filtrage dynamique par matière » qu'annonce sa propre note de version. Une
combinaison valide est donc un triplet dont les trois valeurs appartiennent aux
listes de la matière du poteau.

| Matière | Classes | Efforts | Hauteurs |
|---|---:|---:|---:|
| Bois | 13 | 82 | 16 |
| Béton | 24 | 32 | 14 |
| Métal | 2 | 20 | 12 |

Les listes de premier niveau (`classes`, `efforts`, `hauteurs`) sont l'**union**
des trois matières — 39 classes, soit exactement 13 + 24 + 2. Les utiliser
reviendrait à accepter une classe bois sur un poteau béton. Seul
`correspondancesParMatiere` est indexé, et un test le vérifie sur le catalogue
réel (la classe `M` existe en métal, pas en béton).

### Périmètre

Entités `RPD_Support_Reco` au `Statut` **`UnderCommissionning`**, comme E600 pour
les jonctions.

### Types d'anomalie

| `type_anomalie` | Condition |
|-----------------|-----------|
| `matiere_hors_catalogue` | la `Matiere` n'est couverte par aucune matière du catalogue (`Autre`, valeur absente ou inconnue) |
| `classe_non_referencee` | la `Classe` n'existe pas au catalogue pour cette matière |
| `effort_non_reference` | l'`Effort` n'existe pas au catalogue pour cette matière |
| `hauteur_non_referencee` | la `Hauteur` n'existe pas au catalogue pour cette matière |

Une **matière hors catalogue court-circuite** les trois autres règles : sans
listes de référence, les axes ne sont pas évaluables, et les signaler produirait
trois anomalies redondantes. Même parti qu'E600 pour un domaine de tension
inconnu.

Les trois axes sont ensuite évalués **indépendamment** et **cumulent** leurs
anomalies : ce sont trois valeurs à corriger distinctement.

Une valeur non renseignée ne peut correspondre à aucune entrée : elle est
signalée par l'anomalie « non référencé » correspondante, la valeur brute
(`null`) étant reportée. C'est ainsi qu'une **combinaison incomplète** est
signalée — même convention qu'E600 pour `Fabricant` et `Modele`.

### Unités : le point à ne pas manquer

`Effort` et `HauteurPoteau` sont des **`gml:MeasureType`** (confirmé au XSD) :
leur valeur n'a de sens qu'accompagnée de son unité, portée par `Effort_uom` et
`HauteurPoteau_uom`. Le catalogue exprime les efforts en **kN** et les hauteurs
en **mètres**. Les mesures sont donc converties dans l'unité du catalogue avant
comparaison :

| Effort | Hauteur |
|---|---|
| `kN` ×1, `daN` ×0,01, `N` ×0,001 | `m` ×1, `cm` ×0,01, `mm` ×0,001 |

- Une unité **absente** est interprétée comme celle du catalogue (valeur par
  défaut déclarée au format GeoJSON).
- Une unité **inconnue** rend la mesure ininterprétable : elle est donc non
  référencée.

La comparaison se fait sur des flottants arrondis à 3 décimales. Le catalogue
exprime les efforts à 2 décimales ; la 3ᵉ absorbe le bruit de la multiplication
par un facteur décimal sans jamais confondre deux valeurs du catalogue, dont le
plus petit écart est de 5 centièmes de kN.

> **⚠ Constat sur le jeu `Echantillon`.** Ses 18 supports déclarent
> `Effort_uom = "kN"` avec des valeurs de **400, 1250 et 1600**, alors que le
> catalogue plafonne à 160 kN. Ces trois valeurs sont **exactement 100 ×** des
> entrées `4.00`, `12.50` et `16.00` kN : la donnée est en **daN** et l'unité
> déclarée est fausse. E603 signale les 18 supports, l'unité déclarée faisant
> foi — c'est un défaut réel de la donnée, pas du contrôle. Si `Effort_uom`
> était corrigé en `daN`, le jeu deviendrait intégralement conforme.

### Normalisation textuelle

`Matiere` et `Classe` sont comparées normalisées — casse ignorée, suites
d'espaces repliées — même convention qu'E600.

### Propriétés du fichier d'écarts

Au-delà du socle commun : `id_support`, `matiere`, `classe`, `effort`,
`effort_uom`, `hauteur`, `hauteur_uom`. Les **unités figurent à côté des
mesures** : sans elles une valeur d'effort n'est pas interprétable, et c'est
souvent l'unité qui est en cause. Les valeurs sont reportées **brutes**.

La géométrie de chaque feature est le `Point` du support concerné.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "majeur",
  "nombre_anomalies": 18,
  "anomalies_par_type": { "effort_non_reference": 18 },
  "nombre_supports_analyses": 18,
  "nombre_supports_controles": 18,
  "nombre_supports_non_conformes": 18,
  "matieres_catalogue": ["beton", "bois", "metal"],
  "fichier_support_absent": false,
  "sortie": ".../ecarts_e603_poteau_caracteristiques_non_referencees.geojson"
}
```

### Priorité

`majeur` : l'écart est compté et détaillé dans le rapport PDF, mais **ne
déclasse pas** la famille.

### Versions

Les champs de `RPD_Support_Reco` sont identiques en RecoStaR V1.0 et V1.1, et le
catalogue est indépendant de la version : le contrôle est **agnostique de
version**.

---

## E604 — Types de nœuds rattachés aux coffrets (`controle_e604.py`)

**Ce qui est contrôlé :** une `RPD_Coffret_Reco` ne doit être référencée que par
des nœuds dont le type figure parmi les **sept couches autorisées** :

| Couches autorisées |
|---|
| `RPD_CoupeCircuitAFusibles_Reco` |
| `RPD_JeuBarres_Reco` |
| `RPD_ModuleRaccordement_Reco` |
| `RPD_OuvrageCollectifBranchement_Reco` |
| `RPD_PointDeComptage_Reco` |
| `RPD_SupportModules_Reco` |
| `RPD_Terre_Reco` |

### Sens de la relation

C'est le **nœud** qui porte la référence, via son champ `conteneur_href`, et le
coffret qui la subit :

```
RPD_Coffret_Reco.id  ◄──  <couche du nœud>.conteneur_href
```

Le contrôle parcourt donc les nœuds pour qualifier les coffrets, comme E601
parcourt les jonctions pour qualifier les matériels.

### Pourquoi toutes les couches du répertoire sont parcourues

C'est le point de conception central. Un type de nœud **non autorisé** est, par
définition, un type qui **ne figure pas** dans la liste. Restreindre l'analyse
aux sept couches autorisées rendrait donc le contrôle structurellement incapable
de détecter quoi que ce soit.

Toutes les couches GeoJSON du répertoire sont parcourues — les fichiers d'écarts
en étant exclus par `lister_fichiers_geojson`, ce qui rend le contrôle idempotent
d'une exécution à l'autre. Même parti que le contrôle **E209**, qui confronte les
points de levé à toutes les autres couches.

Le **nom du fichier fait foi** pour le type du nœud : c'est la convention de
nommage RecoStaR `RPD_<Type>_Reco`, et la seule information de type disponible —
les features ne portent pas leur classe.

Les couches sont chargées **une à la fois** (`parcourir_couches` est un
générateur) : le volume du jeu de données est sans rapport avec le nombre
d'anomalies recherchées.

### Ce qui évite l'avalanche de faux positifs

Seules les références **visant un coffret du périmètre** sont examinées. Les
autres `conteneur_href` désignent un support ou un bâtiment technique et ne
relèvent pas de cette règle.

C'est indispensable : dans les jeux de référence, `RPD_Jonction_Reco` et
`RPD_PosteElectrique_Reco` portent aussi `conteneur_href` sans figurer parmi les
sept couches autorisées. Elles ne sont signalées **que si** elles pointent
effectivement vers un coffret. Deux tests verrouillent ce comportement.

L'index des coffrets sert ainsi simultanément de filtre de périmètre, de test
d'appartenance en `O(1)` et d'accès à la géométrie de repli — même parti que
l'index d'E507.

### Périmètre

Entités `RPD_Coffret_Reco` dont le `Statut` vaut **`UnderCommissionning`** ou
**`Functional`**. Les coffrets d'un autre statut sont ignorés, et les références
qui les visent avec eux.

### Portée de la règle

La contrainte porte sur le **type** du nœud rattaché, **non sur l'existence** du
rattachement. Un coffret que ne référence aucun nœud n'est donc pas signalé — à
la différence d'E601, dont la règle exigeait explicitement la présence du lien.

### Génération des anomalies

Une anomalie est émise **par lien fautif** (coffret, nœud), convention des
contrôles de relation du projet (E500, E503, E507). Un coffret rattaché à deux
nœuds interdits porte deux anomalies : chaque rattachement est à corriger pour
lui-même.

| `type_anomalie` | Condition |
|-----------------|-----------|
| `noeud_non_autorise` | un nœud d'une couche hors liste référence un coffret du périmètre |

Propriétés au-delà du socle : `id_coffret`, `id_noeud`, `couche_noeud` — cette
dernière nomme le type fautif, information sans laquelle l'écart ne serait pas
diagnosticable.

### Géométrie des écarts

Le `Point` du **nœud** fautif : c'est lui qui porte la référence, donc le défaut.

Certains nœuds n'ont pas de géométrie propre — leur position est déduite de leur
conteneur, c'est le cas de `RPD_ModuleRaccordement_Reco` selon le XSD. La
géométrie du **coffret** prend alors le relais, afin que l'écart reste
localisable dans QGIS.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "mineur",
  "nombre_anomalies": 0,
  "nombre_coffrets_controles": 14,
  "nombre_coffrets_non_conformes": 0,
  "nombre_couches_analysees": 17,
  "nombre_liens_controles": 17,
  "fichier_coffret_absent": false,
  "sortie": null
}
```

`nombre_liens_controles` compte **toutes** les références vers un coffret du
périmètre, conformes comprises : c'est la couverture réelle du contrôle.

### Priorité

`mineur` : l'écart est compté et détaillé dans le rapport PDF, mais **ne
déclasse pas** la famille.

### Versions

Coffret et nœuds ont une structure identique en RecoStaR V1.0 et V1.1 : le
contrôle est **agnostique de version**.

---

## E605 — Chaîne de localisation des nœuds sans géométrie (`controle_e605.py`)

**Ce qui est contrôlé :** certains nœuds du réseau ne portent pas de géométrie —
leur position est celle du conteneur qui les héberge, dont l'emprise est décrite
par une géométrie supplémentaire. E605 vérifie que cette chaîne est complète et
résolue de bout en bout :

```
nœud (sans géométrie propre)
  ──► conteneur_href                ──► conteneur
  ──► geometriesupplementaire_href  ──► RPD_GeometrieSupplementaire_Reco
  ──► géométrie valide
```

### Entités contrôlées

| Couche |
|---|
| `RPD_CoupeCircuitAFusibles_Reco` |
| `RPD_JeuBarres_Reco` |
| `RPD_ModuleRaccordement_Reco` |
| `RPD_SupportModules_Reco` |
| `RPD_Terre_Reco` |
| `RPD_PosteElectrique_Reco` |

Les six couches y entrent **sans condition** : toutes leurs entités tiennent
leur position d'un conteneur. Aucune autre entité n'est contrôlée —
`RPD_Jonction_Reco` en particulier est hors périmètre, quel que soit son
`TypeJonction`.

**Conteneurs reconnus** : `RPD_Coffret_Reco`, `RPD_Support_Reco`,
`RPD_BatimentTechnique_Reco`, `RPD_EnceinteCloturee_Reco` — les quatre couches
qui alimentent le cache de géométries du convertisseur, donc les seules dont un
nœud puisse hériter sa position.

### ⚠ Détecter une géométrie *directe* : le point à ne pas manquer

Le champ `geometry` du GeoJSON **ne peut pas être testé tel quel**. Les sept
extracteurs de `recostar_to_geojson.py` appliquent tous la même règle :

```python
elif conteneur and conteneur in self.conteneur_geometries:
    # Hériter de la géométrie du conteneur si pas de géométrie propre
    geometry = self.conteneur_geometries[conteneur]
```

L'export **renseigne donc `geometry` même lorsque le GML n'en porte aucune**.
Tester la simple présence d'une géométrie signalerait la totalité des entités
(115 sur les jeux de référence) et mesurerait le convertisseur, non la donnée.

Le discriminant est l'**égalité avec la géométrie du conteneur** :

| Géométrie du nœud | Interprétation |
|---|---|
| absente | pas de géométrie directe ✅ |
| **égale** à celle du conteneur | héritée par l'export, donc absente à la source ✅ |
| **différente** de celle du conteneur | propre au nœud, donc directe ❌ |

Vérifié empiriquement : **toutes** les entités du périmètre portent, sur les
jeux de référence, une géométrie strictement identique à celle de leur
conteneur.

### Types d'anomalie

Les six situations sont distinguées, conformément au besoin de diagnostic :

| `type_anomalie` | Condition |
|-----------------|-----------|
| `conteneur_absent` | `conteneur_href` n'est pas renseigné |
| `conteneur_introuvable` | il ne résout aucun conteneur connu |
| `geometrie_directe_presente` | la géométrie du nœud diffère de celle de son conteneur |
| `geometrie_supplementaire_absente` | le conteneur ne porte pas de `geometriesupplementaire_href` |
| `geometrie_supplementaire_introuvable` | cette référence ne résout aucune `RPD_GeometrieSupplementaire_Reco` |
| `geometrie_supplementaire_invalide` | l'entité existe mais sa géométrie est absente ou vide |

### Cascade et cumul

**L'absence de conteneur interrompt la cascade.** Sans conteneur, ni la
comparaison de géométrie ni la suite de la chaîne ne sont évaluables : les
signaler produirait des anomalies redondantes issues d'une même cause. Même
parti qu'E600 pour un domaine de tension inconnu.

**La géométrie directe n'interrompt pas** la vérification de la chaîne : c'est
un défaut propre au nœud, qui peut coexister avec une chaîne de conteneur
rompue. Les deux anomalies cumulent alors.

**Une seule rupture de chaîne est signalée** par nœud : la cascade s'arrête à la
première.

### Une géométrie valide

Une géométrie supplémentaire est valide si elle porte un `type` **et** un
contenu : des `coordinates` non vides, ou des `geometries` non vides pour une
`GeometryCollection`. Une référence qui aboutit à une géométrie vide ne localise
rien — la nuance avec `geometrie_supplementaire_introuvable` est conservée, car
le correctif n'est pas le même.

### Un conteneur fautif multiplie les anomalies

La règle qualifie l'**entité**, pas le conteneur : un conteneur sans géométrie
supplémentaire rend non conformes **tous** les nœuds qu'il héberge, chacun étant
effectivement privé de localisation. C'est la lecture littérale de « l'entité est
conforme uniquement si l'ensemble de ces conditions est respecté ».

### Propriétés du fichier d'écarts

Au-delà du socle : `couche_noeud`, `id_noeud`, `id_conteneur`,
`id_geometrie_supplementaire`. Les six couches partagent un même fichier
d'écarts : `couche_noeud` — repris aussi dans `fichier_source` — est
indispensable pour retrouver l'entité.

La géométrie de la feature est celle du nœud si elle existe, à défaut celle de
son conteneur : un nœud sans position ne serait sinon pas localisable dans QGIS.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "bloquant",
  "nombre_anomalies": 0,
  "anomalies_par_type": {},
  "nombre_noeuds_controles": 99,
  "nombre_noeuds_non_conformes": 0,
  "nombre_conteneurs": 111,
  "nombre_geometries_supplementaires": 111,
  "couches_absentes": ["RPD_Terre_Reco"],
  "couches_conteneur_absentes": ["RPD_EnceinteCloturee_Reco"],
  "sortie": null
}
```

Les couches absentes sont remontées sans bloquer : un jeu ne contient pas
nécessairement tous les types de nœuds.

### Priorité

`bloquant` : une chaîne de localisation rompue prive le nœud de toute position
exploitable — le récolement ne peut pas être utilisé en l'état. La famille
Conteneur est **déclassée en « Non conforme »** dès la première anomalie.

### Versions

Les champs de relation sont identiques en RecoStaR V1.0 et V1.1 : le contrôle est
**agnostique de version**.

---

## E606 — Localisation des remontées aéro-souterraines (`controle_e606.py`)

**Ce qui est contrôlé :** une `RPD_Jonction_Reco` décrivant une remontée
aéro-souterraine doit être localisable. **Deux voies sont admises, l'une des deux
suffit** :

| | Condition |
|---|---|
| **Cas 1** — géométrie propre | la jonction porte elle-même une géométrie valide |
| **Cas 2** — géométrie par le support | la jonction est rattachée à un `RPD_Support_Reco` existant, qui référence une `RPD_GeometrieSupplementaire_Reco` résolue et pourvue d'une géométrie valide |

Une jonction ne satisfaisant **aucune** des deux voies n'a aucune position
exploitable : une anomalie est émise.

### Périmètre

Entités `RPD_Jonction_Reco` remplissant les **deux** conditions cumulatives :

| Condition | Valeur attendue |
|---|---|
| `TypeJonction` | `RemonteeAeroSouterraine` |
| `Statut` | `UnderCommissionning` **ou** `Functional` |

Toutes les autres jonctions sont ignorées. E606 prend ainsi en charge les
entités qu'E605 ne couvre pas.

### ⚠ Ce qu'est une géométrie « propre »

Le champ `geometry` du GeoJSON **ne peut pas être testé tel quel**. L'extracteur
de jonction de `recostar_to_geojson.py` applique la même règle que les autres
nœuds — « hériter de la géométrie du conteneur si pas de géométrie propre » — et
renseigne donc `geometry` même lorsque le GML n'en porte aucune.

Lire le cas 1 comme « le champ `geometry` est renseigné » le rendrait vrai pour
**toute** jonction rattachée à un conteneur, et **le cas 2 deviendrait
inatteignable** : la disjonction perdrait tout contenu.

Le discriminant est donc le même qu'en E605 :

| Géométrie de la jonction | Cas 1 |
|---|---|
| absente ou vide | ✗ |
| **égale** à celle du conteneur | ✗ — héritée par l'export |
| **différente** de celle du conteneur | ✓ — propre à la jonction |
| présente, sans conteneur résolu | ✓ — elle ne peut venir d'ailleurs |

Vérifié sur les jeux de référence : les deux voies sont effectivement
empruntées — **2 jonctions par le cas 1** (une sans conteneur, une dont la
géométrie diffère de celle de son support) et **7 par le cas 2**.

### Le cas 2 exige un support, pas un conteneur quelconque

Une remontée aéro-souterraine est portée par un **support**. Un rattachement à
un coffret ou à un bâtiment technique ne satisfait donc pas le cas 2, même si
la chaîne de géométrie supplémentaire y aboutit — c'est le motif
`conteneur_non_support`.

Les quatre couches de conteneur sont malgré tout indexées, mais pour un autre
usage : reconnaître une géométrie héritée, quelle que soit la nature du
conteneur. Les deux index sont construits **en une passe**.

### Anomalie et motifs

**Un seul type d'anomalie** : `localisation_absente`. La règle est une
disjonction, son échec est unique — il n'y a pas six façons de ne pas être
localisable.

La propriété **`motif`** porte le diagnostic, en indiquant où la voie du support
s'est interrompue :

| `motif` | Signification |
|---|---|
| `support_absent` | `conteneur_href` n'est pas renseigné |
| `support_introuvable` | la référence ne résout aucun conteneur |
| `conteneur_non_support` | elle résout un conteneur qui n'est pas un `RPD_Support_Reco` |
| `geometrie_supplementaire_absente` | le support ne porte pas de `geometriesupplementaire_href` |
| `geometrie_supplementaire_introuvable` | cette référence ne résout aucune entité |
| `geometrie_supplementaire_invalide` | l'entité existe mais sa géométrie est absente ou vide |

Le cas 1 étant évalué **en premier**, le motif décrit toujours l'échec du cas 2 —
seul restant à examiner une fois la géométrie propre écartée.

### Propriétés du fichier d'écarts

Au-delà du socle : `id_jonction`, `id_support`, `motif`. La géométrie de la
feature est celle de la jonction si elle existe, à défaut celle de son
conteneur : une jonction sans position ne serait sinon pas localisable dans QGIS.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "bloquant",
  "nombre_anomalies": 0,
  "anomalies_par_motif": {},
  "nombre_jonctions_analysees": 12,
  "nombre_jonctions_controlees": 4,
  "nombre_supports": 18,
  "nombre_geometries_supplementaires": 33,
  "fichier_jonction_absent": false,
  "couches_conteneur_absentes": ["RPD_EnceinteCloturee_Reco"],
  "sortie": null
}
```

### Priorité

`bloquant` : une remontée sans position exploitable ne peut pas être reportée
sur le terrain — le récolement n'est pas utilisable en l'état.

### Réutilisation

E606 partage avec E605 la définition de `geometrie_valide`, l'index des
géométries supplémentaires, la structure `Conteneur` et les champs de relation.
Un test vérifie que les deux contrôles s'appuient bien sur **la même** fonction
de validité, et qu'ils portent sur des entités disjointes.

### Versions

Les champs de relation sont identiques en RecoStaR V1.0 et V1.1 : le contrôle est
**agnostique de version**.

---

## E607 — Localisation des points de comptage et ouvrages collectifs (`controle_e607.py`)

**Ce qui est contrôlé :** les entités `RPD_PointDeComptage_Reco` et
`RPD_OuvrageCollectifBranchement_Reco` doivent être localisables. **Deux voies
sont admises, l'une des deux suffit** :

| | Condition |
|---|---|
| **Cas 1** — géométrie propre | l'entité porte elle-même une géométrie valide |
| **Cas 2** — géométrie par le conteneur | l'entité est rattachée à un `RPD_Coffret_Reco` ou à un `RPD_BatimentTechnique_Reco` existant, qui référence une `RPD_GeometrieSupplementaire_Reco` résolue et pourvue d'une géométrie valide |

C'est le jumeau structurel d'E606, sur d'autres entités et d'autres conteneurs
autorisés.

### Périmètre

Les entités des deux couches dont le `Statut` vaut **`UnderCommissionning`** ou
**`Functional`** — même périmètre de statut qu'E604 et E606, vérifié par un test.

Les ouvrages d'un autre statut sont ignorés : un ouvrage à l'état de projet n'a
pas à être localisable sur le terrain. Le cas est réel — `Echantillon` contient
4 points de comptage `Projected` sur 7.

### Conteneurs autorisés par le cas 2

| Autorisé | Non autorisé |
|---|---|
| `RPD_Coffret_Reco` | `RPD_Support_Reco` |
| `RPD_BatimentTechnique_Reco` | `RPD_EnceinteCloturee_Reco` |

Un rattachement à un support ne satisfait donc pas le cas 2, **même si la chaîne
de géométrie supplémentaire y aboutit** — c'est le motif
`conteneur_non_autorise`. Ce cas se rencontre réellement : `Echantillon2`
contient un point de comptage rattaché à un `RPD_Support_Reco`.

Les quatre couches de conteneur restent indexées, mais pour un autre usage :
reconnaître une géométrie héritée, quelle que soit la nature du conteneur.

### Géométrie « propre »

Même discriminant qu'E605 et E606, et pour la même raison — l'export hérite la
géométrie du conteneur quand l'entité n'en porte pas. Une géométrie **égale** à
celle du conteneur est héritée donc absente à la source ; une géométrie
**différente**, ou portée sans conteneur résolu, est propre à l'entité.

Vérifié sur les jeux de référence : les deux voies sont effectivement
empruntées — **32 entités par le cas 1** et **3 par le cas 2**.

### Anomalie et motifs

**Un seul type d'anomalie** : `localisation_absente`. La règle est une
disjonction, son échec est unique.

La propriété **`motif`** porte le diagnostic :

| `motif` | Signification |
|---|---|
| `conteneur_absent` | `conteneur_href` n'est pas renseigné |
| `conteneur_introuvable` | la référence ne résout aucun conteneur |
| `conteneur_non_autorise` | elle résout un conteneur d'un type non admis |
| `geometrie_supplementaire_absente` | le conteneur ne porte pas de `geometriesupplementaire_href` |
| `geometrie_supplementaire_introuvable` | cette référence ne résout aucune entité |
| `geometrie_supplementaire_invalide` | l'entité existe mais sa géométrie est absente ou vide |

Le cas 1 étant évalué **en premier**, le motif décrit toujours l'échec du cas 2.

### Réutilisation

E607 ne réimplémente ni le discriminant de géométrie propre, ni la chaîne de
géométrie supplémentaire, ni l'indexation des conteneurs :

| Emprunté | À |
|---|---|
| `possede_geometrie_propre` | E606 |
| `indexer_conteneurs_autorises` | E606 |
| `_classifier_chaine_conteneur`, `geometrie_valide`, `geometrie_ecart`, `Conteneur` | E605 |

L'indexation des conteneurs a été **généralisée dans E606** — les couches
autorisées deviennent un paramètre — et `indexer_conteneurs_et_supports` y
délègue désormais en une ligne. L'API d'E606 est inchangée. Cinq tests vérifient
que les contrôles partagent bien **les mêmes objets fonction**, et que leurs
couches cibles sont disjointes de celles d'E605.

La règle de repli de la géométrie d'écart — l'entité, à défaut son conteneur —
est elle aussi mutualisée dans `geometrie_ecart` (E605), à la place du
conditionnel imbriqué que les trois contrôles portaient chacun.

### Propriétés du fichier d'écarts

Au-delà du socle : `couche_ouvrage`, `id_ouvrage`, `id_conteneur`, `motif`. Les
deux couches partagent un même fichier d'écarts : `couche_ouvrage` — repris
aussi dans `fichier_source` — est indispensable pour retrouver l'entité.

La géométrie de la feature est celle de l'ouvrage si elle existe, à défaut celle
de son conteneur.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "bloquant",
  "nombre_anomalies": 2,
  "anomalies_par_motif": { "conteneur_absent": 1, "conteneur_non_autorise": 1 },
  "nombre_ouvrages_controles": 30,
  "nombre_conteneurs_autorises": 98,
  "nombre_geometries_supplementaires": 111,
  "couches_absentes": [],
  "couches_conteneur_absentes": ["RPD_EnceinteCloturee_Reco"],
  "sortie": ".../ecarts_e607_ouvrage_localisation_absente.geojson"
}
```

### Priorité

`bloquant` : un ouvrage sans position exploitable ne peut pas être retrouvé sur
le terrain — le récolement n'est pas utilisable en l'état.

### Versions

Les champs de relation sont identiques en RecoStaR V1.0 et V1.1 : le contrôle est
**agnostique de version**.

---

## E608 — Nombre de câbles raccordés selon le type de jonction (`controle_e608.py`)

**Ce qui est contrôlé :** une `RPD_Jonction_Reco` doit être raccordée au nombre
de câbles qu'impose son type.

| `TypeJonction` | Câbles attendus |
|---|---|
| `Derivation` | **au moins 3** |
| `Jonction` | **au moins 2** |
| `ExtremiteReseau` | **exactement 1** |
| `Telecom` | aucun compte imposé, mais **au moins un câble de télécommunication** |

**Périmètre :** jonctions au `Statut` `UnderCommissionning` dont le
`TypeJonction` figure dans ce tableau. Les autres types — la
`RemonteeAeroSouterraine` notamment — sont ignorés. Le dictionnaire des règles
tient lieu de filtre : un type absent n'est pas contrôlé.

### Règle propre au type `Telecom`

Une jonction `Telecom` doit déclarer, dans son champ `cables_href`, **au moins
une référence résolvant une entité `RPD_CableTelecommunication_Reco`**. La
contrainte porte sur la **nature** d'au moins un câble rattaché, non sur leur
nombre : aucun minimum ni maximum ne lui est imposé par ailleurs.

L'exigence est **attributaire**, comme l'énonce la règle (« lié via
`cables_href` »). Sa confirmation géométrique n'est pas exigée ici : si la
référence n'a pas de réalité géométrique, c'est le constat de cohérence
(`raccordement_incoherent`) qui le signale, indépendamment.

**Source de l'énumération.** Les valeurs admises de `TypeJonction` sont
déclarées par `xsd_structuration/regles_valeurs.py` (`_ENUM_TYPE_JONCTION`,
règle `E_TYPE_JONCTION`, source **PDF §10.4.1**), qui fait foi pour le projet.
`Telecom` y figure, aux côtés de `Derivation`, `ExtremiteReseau`, `Jonction`,
`RemonteeAeroSouterraine` et `EpanouissementHTA`.

Le XSD **V1.1** l'énumère également. Celui de la **V1.0** ne le fait pas : un
`TypeJonction` `Telecom` sur un jeu V1.0 est alors signalé par le contrôle de
structuration, non par E608 — qui reste agnostique de version et applique sa
règle dès que la valeur est présente.

> La valeur n'apparaît dans aucun des trois jeux de référence : la règle n'y
> produit donc aucune anomalie, sans que cela présume de sa fréquence sur des
> données de production.

### Un raccordement confirmé sur les deux plans

C'est le cœur du contrôle. Un câble n'est compté comme raccordé que si le
raccordement est établi **des deux côtés** :

| Plan | Condition |
|---|---|
| **attributaire** | l'identifiant du câble figure dans `cables_href` et résout un câble existant |
| **géographique** | le point de la jonction coïncide avec une extrémité topologique du câble |

Le nombre retenu est celui de l'**intersection**. Compter les seules références
de `cables_href` reviendrait à faire confiance à une déclaration sans la
vérifier ; compter les seules coïncidences géométriques reviendrait à inventer
un lien que la donnée ne déclare pas.

Les deux ensembles sont par ailleurs **comparés**, et leur divergence signalée
pour elle-même (`raccordement_incoherent`) — indépendamment du compte. Une
jonction peut donc être au bon nombre de raccordements tout en déclarant une
référence sans réalité géométrique.

### Ce que l'analyse des échantillons a établi

| Constat | Conséquence sur la conception |
|---|---|
| `cables_href` liste les identifiants **séparés par des virgules** (1 à 4 références observées) | l'extraction accepte virgule et espace, comme `utils_cable.extraire_ids_cables_href` |
| les câbles sont des `LineString` **et** des `MultiLineString` (18 sur 143 dans `Echantillon2`) | la décomposition doit être **topologique**, pas positionnelle |
| les liens réels coïncident **au bit près** (38 liens mesurables, tous à 0 m) | comparaison planimétrique, tolérance d'1 mm à titre préventif |
| `Echantillon2` contient 13 câbles dont les extrémités sont indéterminables | voir ci-dessous |

**Extrémités topologiques.** La décomposition réutilise `extraire_extremites`
(module commun), qui retient les bouts de partie apparaissant un nombre impair
de fois. Les parties d'un `MultiLineString` RecoStaR n'étant ni ordonnées ni
orientées, prendre le premier et le dernier sommet après mise à plat donnerait
des extrémités fausses. Même mécanisme qu'E506 et E507.

**Tolérance de coïncidence : 1 mm.** La comparaison est planimétrique — le Z est
écarté, l'écart altimétrique relevant des contrôles E200 à E209 — et admet un
écart d'un millimètre : `TOLERANCE_SUPERPOSITION` du module commun, **la même
valeur que celle déjà appliquée par E205, E208 et E209**, et non une constante
propre à E608.

La raison est la même que pour ces trois contrôles : le contact d'un nœud et
d'une extrémité est de **mesure nulle**, et les coordonnées RecoStaR sont
arrondies au millimètre dès le GML source — une égalité exacte s'y heurte. La
valeur reste très en deçà de toute précision de levé : un câble réellement
écarté, même au centimètre, demeure détecté.

Le seuil est **inclusif** : un écart d'exactement 1 mm compte comme un contact,
comme le `dwithin` de shapely employé par E205 et E209.

> **Effet mesuré : nul sur les jeux actuels.** Les 38 liens mesurables de
> `Echantillon` et `Echantillon2` coïncident **exactement** (0 m) — ce que la
> docstring d'E507 constatait déjà de son côté. La tolérance est donc un
> correctif **préventif**, aligné sur celui d'E205/E208 : elle protège des jeux
> futurs où l'arrondi produirait un décalage submillimétrique, sans rien changer
> aux verdicts d'aujourd'hui.

### ⚠ Câbles sans extrémité exploitable

Une géométrie fermée, ou dont les parties se neutralisent deux à deux, ne livre
**aucune** extrémité. `Echantillon2` en contient 13 : des `MultiLineString` dont
les deux parties sont **identiques**, si bien que chaque bout apparaît deux fois
et passe pour un raccord interne.

Un tel câble ne peut pas être confirmé géographiquement : il n'est donc pas
compté comme raccordé. Leur nombre est reporté à l'anomalie
(`nombre_cables_sans_extremite`) et au rapport, afin que la cause réelle — la
géométrie du câble, non le compte de la jonction — reste lisible. E507 isole ces
mêmes câbles sous `nombre_cables_geometrie_non_exploitable`.

Sur `Echantillon2`, ces 13 câbles expliquent 5 des 7 anomalies de compte.

### Types d'anomalie

| `type_anomalie` | Condition |
|-----------------|-----------|
| `nombre_cables_insuffisant` | moins de câbles raccordés que le minimum du type |
| `nombre_cables_excessif` | plus que le maximum (`ExtremiteReseau` uniquement) |
| `cable_telecommunication_absent` | une jonction `Telecom` ne référence aucun câble de télécommunication |
| `raccordement_incoherent` | les ensembles attributaire et géographique divergent |

Le compte, la nature des câbles et la cohérence sont trois constats
**indépendants** : leurs anomalies **cumulent**.

### Couches de câble analysées

`RPD_CableElectrique_Reco`, `RPD_CableTerre_Reco` et
`RPD_CableTelecommunication_Reco`. Une référence ne résolvant aucune de ces
couches n'est pas un raccordement attributaire valide ; son intégrité relevant
du contrôle **E401**, elle n'est ici que comptée
(`nombre_references_non_resolues`).

### Coût du parcours

Les extrémités sont décomposées **une seule fois par câble**, puis interrogées
par toutes les jonctions en `O(1)`. Le test géographique est restreint aux
câbles **déclarés** par la jonction : balayer l'index complet pour chacune
serait quadratique. Le balayage complet n'est fait que par
`detecter_coincidences_non_declarees`, pour le seul diagnostic d'incohérence.

### Propriétés du fichier d'écarts

Au-delà du socle : `type_jonction`, `nombre_minimum`, `nombre_maximum`,
`nombre_cables_raccordes`, `nombre_references`, `nombre_geographiques`,
`nombre_references_sans_coincidence`, `nombre_coincidences_non_declarees`,
`nombre_references_non_resolues`, `nombre_cables_sans_extremite`,
`nombre_cables_telecommunication`.

Les comptes des deux sources sont exposés **côte à côte** : c'est leur
confrontation qui explique l'écart.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "majeur",
  "nombre_anomalies": 0,
  "anomalies_par_type": {},
  "nombre_jonctions_analysees": 12,
  "nombre_jonctions_controlees": 8,
  "nombre_jonctions_non_conformes": 0,
  "nombre_cables_indexes": 31,
  "nombre_cables_sans_extremite": 0,
  "nombre_cables_telecommunication": 0,
  "tolerance_coincidence_m": 0.001,
  "fichier_jonction_absent": false,
  "couches_cable_absentes": ["RPD_CableTelecommunication_Reco"],
  "sortie": null
}
```

### Priorité

`majeur` : l'écart est compté et détaillé dans le rapport PDF, mais **ne
déclasse pas** la famille.

### Versions

Jonction et câbles ont une structure identique en RecoStaR V1.0 et V1.1 : le
contrôle est **agnostique de version**.

---

## E609 — Rattachement des nœuds du réseau à un câble existant (`controle_e609.py`)

**Ce qui est contrôlé :** un nœud du réseau en service doit déclarer, dans son
champ `cables_href`, une ou plusieurs références résolvant **toutes** une entité
câble existante du jeu de données.

**Entités contrôlées** — neuf couches :

| | |
|---|---|
| `RPD_CoupeCircuitAFusibles_Reco` | `RPD_SupportModules_Reco` |
| `RPD_ModuleRaccordement_Reco` | `RPD_Terre_Reco` |
| `RPD_OuvrageCollectifBranchement_Reco` | `RPD_PosteElectrique_Reco` |
| `RPD_PointDeComptage_Reco` | `RPD_JeuBarres_Reco` |
| `RPD_Jonction_Reco` | |

**Périmètre :** entités au `Statut` `UnderCommissionning` **ou** `Functional`.
Un nœud d'un autre statut n'est pas encore — ou n'est plus — en service :
l'exigence de rattachement ne lui est pas opposable. Même parti qu'E604.

### Toutes les références doivent être valides

Le rattachement n'est **pas** réputé correct dès lors qu'une référence aboutit :
la règle porte sur **chaque** identifiant déclaré. Une référence sans réalité
désigne soit un câble supprimé, soit une entité d'une autre nature ; dans les
deux cas la donnée affirme un lien qui n'existe pas, que d'autres références
valides ne réparent pas. Même parti qu'**E401** pour ses références orphelines.

Une anomalie est donc émise **par référence fautive**, convention des contrôles
de relation du projet (E500, E503, E507, E604) : un nœud déclarant deux
références invalides porte deux anomalies, chacune étant à corriger pour
elle-même. Les doublons sont repliés — une même référence déclarée deux fois
désigne un seul rattachement.

### Distinguer l'identifiant inexistant de l'entité qui n'est pas un câble

Les deux cas appellent des corrections différentes — rétablir une entité
disparue, ou corriger un lien qui vise la mauvaise entité — et un index des
seules couches de câble ne permet pas de les séparer : il rendrait
« introuvable » toute référence visant, par exemple, un coffret bien présent.

L'index est donc construit sur **toutes** les couches du répertoire (les
fichiers d'écarts en sont exclus par `lister_fichiers_geojson`) et associe à
chaque identifiant le **nom de sa couche**. Le nom du fichier fait foi pour le
type de l'entité : c'est la convention de nommage RecoStaR `RPD_<Type>_Reco`, et
la seule information de type disponible, les features ne portant pas leur
classe. Même parti qu'E604 et E209.

La couche résolue est reportée au fichier d'écarts (`couche_reference`), afin
que la nature réelle de l'entité visée soit lisible dans QGIS.

**Couches de câble reconnues :** `RPD_CableElectrique_Reco`,
`RPD_CableTerre_Reco` et `RPD_CableTelecommunication_Reco` — les trois mêmes
qu'E401 et E608.

### Références mal formées

Une référence est mal formée lorsqu'elle ne peut pas être confrontée **telle
quelle** aux identifiants du jeu :

| Forme | Exemple |
|---|---|
| fragment XLink non résolu | `#id0a1b2c…` |
| URN | `urn:ogc:def:id0a1b2c…` |
| URL absolue | `https://exemple.fr/id0a1b2c…` |
| valeur non textuelle | un objet, un booléen |

Le GML source admet les formes XLink (cf. `geojson_to_recostar`, qui réécrit les
`#id` lors du renommage des identifiants) et l'export GeoJSON restitue
l'attribut **brut** : la forme se retrouve donc telle quelle dans `cables_href`.

> Le contrôle ne valide **pas la forme interne** de l'identifiant. Aucun motif
> d'identifiant n'est normatif dans le projet, et rejeter un jeton sur ce
> critère signalerait des références parfaitement résolubles. Un jeton bien
> formé mais sans correspondance relève de `cable_introuvable`.

Le découpage accepte la **virgule** et l'**espace**, comme
`utils_cable.extraire_ids_cables_href` : les identifiants RecoStaR ne
contiennent ni l'une ni l'autre, le découpage est donc sans ambiguïté.

### Types d'anomalie

| `type_anomalie` | Condition |
|-----------------|-----------|
| `cables_href_absent` | le champ n'est pas renseigné |
| `cables_href_vide` | le champ est renseigné mais ne porte aucune référence exploitable |
| `reference_malformee` | la référence ne peut pas être confrontée telle quelle à un identifiant |
| `cable_introuvable` | la référence ne résout aucune entité du jeu |
| `reference_hors_couche_cable` | la référence résout une entité existante, mais qui n'est pas un câble |

Les **deux premiers** qualifient le nœud et sont **exclusifs** : sans référence,
il n'y a rien à résoudre, et signaler en outre une référence introuvable
produirait une anomalie redondante issue d'une même cause. Même parti qu'E605
pour un conteneur absent.

Les **trois suivants** qualifient une référence et **cumulent**.

### Géométrie des écarts

Celle du nœud fautif, qui porte la référence et donc le défaut. Les nœuds sans
géométrie propre héritent de celle de leur conteneur **dès l'export** (cf.
E605) : l'écart reste localisable dans QGIS sans repli supplémentaire.

### Coût du parcours

Deux passes. La première indexe les identifiants de toutes les couches — seuls
les identifiants sont conservés, dont le volume est sans rapport avec celui des
géométries, et le générateur `parcourir_couches` ne détient qu'une couche à la
fois. La seconde relit les **neuf** couches cibles et résout chaque référence en
`O(1)`. Le `crs` est capté au passage, sans relecture supplémentaire.

### Propriétés du fichier d'écarts

Au-delà du socle : `couche_noeud`, `id_noeud`, `statut`, `cables_href`,
`reference`, `couche_reference`.

`cables_href` conserve la **valeur brute** du champ, afin que la référence
fautive reste lisible dans son contexte de déclaration ; `reference` isole le
jeton en cause, `couche_reference` nomme la couche de l'entité effectivement
visée (renseignée pour le seul `reference_hors_couche_cable`).

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "bloquant",
  "nombre_anomalies": 5,
  "anomalies_par_type": {
    "cables_href_absent": 1,
    "cables_href_vide": 1,
    "reference_malformee": 1,
    "cable_introuvable": 1,
    "reference_hors_couche_cable": 1
  },
  "nombre_noeuds_analyses": 7,
  "nombre_noeuds_controles": 6,
  "nombre_noeuds_non_conformes": 5,
  "nombre_entites_indexees": 9,
  "nombre_cables_indexes": 1,
  "couches_absentes": ["RPD_JeuBarres_Reco"],
  "couches_cable_absentes": ["RPD_CableTerre_Reco"],
  "sortie": "/chemin/ecarts_e609_noeud_rattachement_cable.geojson"
}
```

### Priorité

`bloquant` : un nœud qui ne résout aucun câble est détaché de la topologie du
réseau, le recolement ne peut pas être exploité en l'état — l'anomalie
**déclasse** la famille (cf. `PRIORITES_DECLASSANTES` dans
`synthese_controles`). Même priorité qu'**E601**, qui porte sur une exigence de
rattachement de même nature.

### Versions

Les champs `Statut` et `cables_href` sont identiques en RecoStaR V1.0 et V1.1 :
le contrôle est **agnostique de version**.

---

## E610 — Nomenclature de composition des coffrets (`controle_e610.py`)

**Ce qui est contrôlé :** les nœuds rattachés à une `RPD_Coffret_Reco` doivent
respecter la nomenclature de son `TypeCoffret` — types autorisés, nombres
minimal et maximal, obligations de présence.

| `TypeCoffret` | Composition admise |
|---|---|
| `RMBT300` | **1** `ModuleRaccordement` ; `PointDeComptage` et `SupportModules` sans plafond ; au plus **1** `Terre` |
| `RMBT450` | **1** `ModuleRaccordement` ; `PointDeComptage`, `OuvrageCollectifBranchement` et `SupportModules` sans plafond ; au plus **1** `Terre` |
| `RMBT600` | identique à `RMBT450` |
| `CIBE` | **1** `CoupeCircuitAFusibles` ; au plus **1** `JeuBarres` ; `PointDeComptage` sans plafond ; au plus **1** `Terre` |
| `CGV` | au plus **1** `CoupeCircuitAFusibles` ; au plus **1** `ModuleRaccordement` ; au plus **1** `Terre` ; `PointDeComptage` sans plafond |
| `ECP2D` | **1** `CoupeCircuitAFusibles` ; au plus **1** `JeuBarres` ; au plus **1** `Terre` ; `PointDeComptage` et `OuvrageCollectifBranchement` sans plafond |
| `ECP3D` | au plus **2** `CoupeCircuitAFusibles` ; au plus **1** `JeuBarres` ; au plus **1** `Terre` ; `PointDeComptage` et `OuvrageCollectifBranchement` sans plafond |
| `ArmoireComptage` | au plus **1** `CoupeCircuitAFusibles` ; au plus **1** `Terre` ; `PointDeComptage` sans plafond |

Tout type de nœud **absent** de la nomenclature d'un `TypeCoffret` est interdit
dans un coffret de ce type : un type interdit n'a pas besoin d'y figurer avec un
maximum nul.

**Obligations de présence :** seuls les « exactement 1 » en sont — le
`ModuleRaccordement` des `RMBT`, le `CoupeCircuitAFusibles` des `CIBE` et
`ECP2D`. Les autres types sont admis **sans minimum** : la nomenclature énonce
ce qu'un coffret *peut* contenir, non ce qu'il doit contenir.

**Périmètre :** coffrets au `Statut` `UnderCommissionning` ou `Functional` dont
le `TypeCoffret` porte une nomenclature. Le dictionnaire `NOMENCLATURES` tient
lieu de filtre — même parti que `REGLES_PAR_TYPE` dans E608 : sont hors
périmètre les types `Telecom` et `Autre` de la code-list, ainsi qu'un
`TypeCoffret` absent.

> La **validité de la valeur** elle-même n'est pas l'affaire d'E610 : la règle
> `C_TYPE_COFFRET` de `xsd_structuration/regles_valeurs.py` (`_CL_TYPE_COFFRET`,
> source **PDF §10.3.2**) la contrôle déjà et fait foi. E610 s'en tient à la
> nomenclature, comme E608 renvoie l'énumération `TypeJonction` à ce même
> contrôle de structuration.

### ⚠ Résolution du `TypeCoffret`

**Le GeoJSON ne porte pas de champ `TypeCoffret`.** Le convertisseur écrit
`TypeCoffret_href` (`recostar_to_geojson.py`), une référence vers une code-list
dont il restitue l'attribut **brut**. La valeur s'y présente donc sous deux
formes :

| Forme | Exemple |
|---|---|
| code seul | `RMBT300` |
| référence fragmentée | `…/codelists/TypeCoffret.xml#RMBT300` |

Le code retenu est le **fragment situé après le dernier `#`** — la règle
qu'applique déjà `controle_e111._extraire_valeur` côté GML, dont E610 reprend la
résolution plutôt que d'en définir une seconde.

Les codes de la table sont ceux de `_CL_TYPE_COFFRET` : **`ArmoireComptage`
s'écrit sans espace**.

### Pourquoi toutes les couches du répertoire sont parcourues

Un type de nœud non autorisé est, par définition, un type **absent** de la
nomenclature. Restreindre l'analyse aux types qu'elle énumère rendrait donc le
contrôle structurellement incapable de détecter un nœud interdit. Toutes les
couches GeoJSON sont parcourues (les fichiers d'écarts en sont exclus par
`lister_fichiers_geojson`), et le nom du fichier fait foi pour le type du nœud —
convention `RPD_<Type>_Reco`, seule information de type disponible. Même parti
qu'E604 et E209.

Le sens de la relation est celui d'E604 : c'est le **nœud** qui porte la
référence, via `conteneur_href`, et le coffret qui la subit. E610 réutilise
d'ailleurs le parcours des couches et la lecture de la référence d'E604. Seules
les références **visant un coffret du périmètre** sont retenues — les autres
`conteneur_href` désignent un support ou un bâtiment technique.

### Une anomalie par couple (coffret, type de nœud)

L'anomalie porte sur le **couple**, et non sur chaque nœud : c'est le *compte*
qui est fautif, non un lien en particulier — désigner un nœud parmi cinq
lorsque quatre sont admis serait arbitraire. Chaque anomalie expose donc le
nombre attendu et le nombre trouvé, seuls termes qui expliquent l'écart.

Un coffret enfreignant deux règles porte deux anomalies : le compte et
l'interdiction sont des constats indépendants, et **cumulent**.

| `type_anomalie` | Condition |
|-----------------|-----------|
| `nombre_noeuds_insuffisant` | moins de nœuds de ce type que le minimum |
| `nombre_noeuds_excessif` | plus que le maximum |
| `noeud_type_non_autorise` | le type n'est pas prévu par la nomenclature |

### Recouvrement assumé avec E604

Les deux règles sont **distinctes**, leurs priorités également :

| | E604 (`mineur`) | E610 (`majeur`) |
|---|---|---|
| Question posée | le type de nœud est-il globalement admis dans un coffret ? | la composition respecte-t-elle la nomenclature de **ce** `TypeCoffret` ? |
| `RPD_Jonction_Reco` rattachée à un coffret | signalé | signalé |
| `RPD_JeuBarres_Reco` dans un `RMBT300` | **non** signalé (type globalement admis) | signalé |
| Cardinalités | non vérifiées | vérifiées |

### Le champ `detail`

Le socle commun impose une `description` **par type d'anomalie**, identique pour
toutes les features qui le portent : elle ne peut donc nommer ni le coffret ni
ses comptes. La propriété métier `detail` restitue le constat rédigé :

```
Coffret cofC de type CIBE : RPD_Terre_Reco attendu au maximum 1, trouvé 2.
Coffret cofE de type ArmoireComptage : RPD_SupportModules_Reco n'est pas
autorisé par la nomenclature (attendu 0, trouvé 1).
```

La formulation suit la règle — « exactement 1 », « au maximum 2 » — plutôt que
d'exposer un intervalle, afin que le message se lise comme la nomenclature dont
il constate l'infraction. `detail` ne se substitue pas aux champs structurés
(`type_coffret`, `couche_noeud`, `nombre_trouve`, `nombre_minimum`,
`nombre_maximum`), qui restent la source exploitable en filtre.

### Géométrie des écarts

Le `Point` du **coffret**, entité contrôlée et porteuse de la composition
fautive. E604 retenait celle du nœud, qui portait la référence et donc le
défaut ; ici le défaut est celui du coffret.

### Coût du parcours

Un seul balayage du répertoire suffit à compter les nœuds de tous les coffrets :
les comptes sont accumulés dans un `Counter` par coffret, puis confrontés à leur
nomenclature. Les coffrets sont ensuite parcourus dans l'ordre de l'index — et
non dans celui des comptes — afin qu'un coffret **sans aucun nœud rattaché**
soit évalué lui aussi : ses obligations de présence ne sont alors satisfaites
par rien.

### Rapport JSON

```json
{
  "succes": true,
  "priorite": "majeur",
  "nombre_anomalies": 4,
  "anomalies_par_type": {
    "nombre_noeuds_insuffisant": 1,
    "nombre_noeuds_excessif": 2,
    "noeud_type_non_autorise": 1
  },
  "nombre_coffrets_controles": 5,
  "nombre_coffrets_non_conformes": 4,
  "coffrets_par_type": { "RMBT300": 2, "CIBE": 1, "ECP3D": 1, "ArmoireComptage": 1 },
  "nombre_couches_analysees": 6,
  "nombre_noeuds_rattaches": 12,
  "fichier_coffret_absent": false,
  "sortie": "/chemin/ecarts_e610_coffret_nomenclature.geojson"
}
```

### Priorité

`majeur` : l'écart est compté et détaillé dans le rapport PDF, mais **ne
déclasse pas** la famille.

### Versions

Coffret et nœuds ont une structure identique en RecoStaR V1.0 et V1.1 : le
contrôle est **agnostique de version**.
