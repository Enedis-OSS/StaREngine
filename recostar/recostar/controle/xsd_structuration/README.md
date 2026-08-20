# Contrôles de structuration XSD (E010 – E014 / E110 – E114)

Ce dossier regroupe les contrôles qui valident un fichier **GML RecoStaR** par
rapport au schéma XSD `SchemaStarElecRecoStar.xsd` et au PDF de structuration
RecoStaR. Les **versions 1.0 et 1.1** du format sont prises en charge (voir
« Sélection de version » ci-dessous). Chaque contrôle couvre un angle différent
et complémentaire de la validation.

**Le code du contrôle dépend de la version contrôlée** : les cinq contrôles
portent les codes **E010 à E014 en V1.0** et **E110 à E114 en V1.1**. Les deux
séries partagent le même moteur d'analyse : seuls la version du profil appliqué,
le code, le `type_controle` et le nom du rapport diffèrent. Il n'y a donc aucune
logique de contrôle dupliquée entre les versions.

- **Entrée commune** : un fichier `.gml`.
- **Sortie commune** : un rapport JSON `<nom_gml>_controle_e0xx.json` (V1.0) ou
  `<nom_gml>_controle_e1xx.json` (V1.1) écrit dans le répertoire du GML (ou dans
  `--output-dir`). Chaque rapport porte le champ `version_controlee` indiquant la
  version appliquée. Les noms étant distincts, contrôler un même fichier dans les
  deux versions n'écrase aucun rapport.
- **Sécurité** : le parsing XML est durci (`defusedxml`, ou parser `lxml` en
  `no_network` / `resolve_entities=False`) pour neutraliser les attaques XXE.

## Sélection de version (1.0 / 1.1)

Tous les contrôles et le pipeline acceptent l'option `--version {auto,1.0,1.1}` :

- `auto` (défaut) : la version est déduite du fragment `RecoStar-vX.Y` présent
  dans le `xsi:schemaLocation` du fichier (`detection_version`). Si la détection
  échoue (en-tête absent ou non reconnu), repli sur la version par défaut (1.1)
  avec un message sur `stderr`, afin que les contrôles s'exécutent malgré tout.
- `1.0` / `1.1` : impose explicitement la version, sans détection.

```bash
python controle_e110.py <fichier.gml>                 # version auto-détectée
python controle_e110.py <fichier.gml> --version 1.0   # version imposée
```

Les scripts `controle_e010.py` à `controle_e014.py` sont des **points d'entrée
V1.0** : ils délèguent au moteur correspondant en figeant la version 1.0. Ils
n'exposent donc pas l'option `--version`, et produisent toujours un rapport
`E01x`. Ils sont utiles lorsque la version voulue est connue d'avance ou que
l'en-tête du fichier est absent / incorrect.

```bash
python controle_e010.py <fichier.gml>                 # V1.0, sans détection
```

La connaissance propre à chaque version est centralisée dans le package
`versions/` (un `ProfilVersion` par version, registre `resoudre_profil`). Les
séquences de structure et l'énumération SRS de chaque version sont **dérivées
automatiquement de son XSD** par `generateur_sequences` ; seuls les deltas
métier (règles conditionnelles E111, valeurs E114) y sont curés à la main.

## Vue d'ensemble

| V1.0 | V1.1 | Point d'entrée V1.0 / moteur | Ce qui est vérifié | Référence | Sévérités | Priorités |
|------|------|------------------------------|--------------------|-----------|-----------|-----------|
| E010 | E110 | `controle_e010.py` / `controle_e110.py` | Ordre des éléments des objets RPD | `sequenceur_xsd` (XSD de la version) | ERREUR | bloquant |
| E011 | E111 | `controle_e011.py` / `controle_e111.py` | Règles métier conditionnelles | `regles_metier` (PDF de structuration) | ERREUR | bloquant |
| E012 | E112 | `controle_e012.py` / `controle_e112.py` | Validation XSD native complète | XSD officiel via `lxml` | ERREUR | bloquant |
| E013 | E113 | `controle_e013.py` / `controle_e113.py` | En-tête, namespaces, métadonnées, unicité `gml:id` | `regles_entete` | ERREUR | bloquant, **sauf `schemaLocation` sur la branche `main` → majeur** |
| E014 | E114 | `controle_e014.py` / `controle_e114.py` | Valeurs des champs (énumérations, CodeLists, formats) | `regles_valeurs` (PDF §9/§10) | ERREUR | bloquant, **sauf `ReseauUtilite/Theme` → mineur** |

Le `type_controle` du rapport suit le code : `E010_ORDRE` en V1.0,
`E110_ORDRE` en V1.1, et ainsi de suite. La correspondance version → code est
centralisée dans `codes_controle.py` (`identite_controle()`), unique source de
vérité pour les moteurs et le pipeline.

Le script `pipeline_controle_xsd.py` orchestre l'exécution des cinq contrôles
sur un même fichier GML, sous les codes de la version détectée.

### Format de rapport commun

Chaque contrôle produit un JSON homogène :

```json
{
  "fichier": "...",
  "date_controle": "AAAA-MM-JJTHH:MM:SS",
  "niveau": "Forte",
  "type_controle": "E01x_... | E11x_...",
  "conformite": "CONFORME | NON_CONFORME",
  "nb_erreurs": 0,
  "nb_par_severite": { "ERREUR": 0 },
  "nb_par_priorite": { "bloquant": 0 },
  "erreurs": [ ... ]
}
```

Les cinq contrôles sont **mono-sévérité** dans les deux versions : toute entrée
est une `ERREUR`. Ils sont en revanche **multi-priorités** — chaque entrée porte
un champ `priorite` — et **seules les entrées `bloquant` invalident la
`conformite`**. Voir la section Priorités ci-dessous.

### Priorités des anomalies

La **sévérité** dit ce qui a été violé ; la **priorité** dit ce que la violation
coûte. Les deux dimensions sont indépendantes : ici toutes les entrées sont de
sévérité `ERREUR`, mais deux règles seulement dérogent au niveau bloquant.

| Priorité | Déclasse ? | Règles concernées |
|----------|-----------|-------------------|
| `bloquant` | **oui** | toutes, sauf les deux ci-dessous |
| `majeur` | non | E113/E013 — `xsi:schemaLocation` pointant la branche `main` du XSD |
| `mineur` | non | E114/E014 — règle `E_THEME_RPD` (`ReseauUtilite/Theme` hors énumération) |

L'échelle et les fonctions de ventilation vivent dans
**`priorites_structuration.py`**. Les dérogations, elles, sont déclarées **au
plus près de la règle concernée**, jamais dans ce module :

- `regles_entete.PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN` pour E113/E013 ;
- le champ `priorite` de la règle `E_THEME_RPD` dans
  `regles_valeurs.REGLES_VALEURS` pour E114/E014.

Le champ `priorite` de `RegleValeur` a pour défaut `bloquant` : **oublier de la
déclarer ne relâche jamais un contrôle**, seule une dérogation explicite le fait.
Ajouter une dérogation revient donc à poser une priorité sur une règle, sans
toucher au moteur de détection ni au message d'erreur.

Deux conséquences à connaître :

- un fichier dont les seules anomalies sont majeures ou mineures est
  `CONFORME` au sens des rapports de structuration, tout en listant ces
  anomalies avec leur décompte (`nb_par_priorite`) ;
- ces priorités sont reprises telles quelles par `synthese_controles.py` via la
  clé `anomalies_par_priorite` du rapport de pipeline : la famille
  « Structuration » du rapport PDF global n'est déclassée que par des anomalies
  bloquantes, cohérence garantie entre les deux niveaux de rapport.

### Usage CLI (contrôle isolé)

```bash
# Moteur multi-version (V1.1 par défaut, détection automatique)
python controle_e110.py <fichier.gml> [--output-dir <repertoire>] \
    [--version {auto,1.0,1.1}]

# Point d'entrée V1.0 (version figée, pas d'option --version)
python controle_e010.py <fichier.gml> [--output-dir <repertoire>]
```

---

## Modules de support (non exécutables seuls)

- **`sequenceur_xsd.py`** : table `SEQUENCES_RPD` modélisant la `xs:sequence`
  attendue de chaque type RPD (héritage XSD reconstitué par composition :
  `ElementReseau` → `Ouvrage` → `NoeudReseau`). Moteur `valider_sequence()`
  détectant `ORDRE_INCORRECT`, `ELEMENT_REQUIS_MANQUANT`, `ELEMENT_INATTENDU`.
  Utilisé par E110 et E113.
- **`regles_metier.py`** : catalogue des règles conditionnelles (R001–R003) et
  moteur `evaluer_regles()`. Utilisé par E111.
- **`regles_valeurs.py`** : catalogue des énumérations, CodeLists et contraintes
  de format, et moteur `evaluer_valeur()`. Utilisé par E114.
- **`regles_entete.py`** : constantes d'en-tête (namespaces attendus, SRS
  autorisés, séquences d'en-tête, codes d'erreur) et type `ErreurEntete`.
  Utilisé par E113.
- **`priorites_structuration.py`** : échelle de priorité des anomalies
  (`bloquant` / `majeur` / `mineur`), ventilation (`ventiler_par_priorite`) et
  conformité qui en découle (`statut_conformite`). Utilisé par les cinq
  contrôles et par le pipeline.
- **`codes_controle.py`** : correspondance version → code de contrôle
  (`identite_controle(version, rang)` retourne le code, le `type_controle` et le
  suffixe de rapport). Unique source de vérité des codes E01x / E11x.
- **`cli_controle.py`** : enveloppe CLI mutualisée des cinq contrôles (parseur
  commun, validation des arguments, résolution du profil, exécution et compte
  rendu). Permet aux points d'entrée V1.0 de rester purement déclaratifs.
- **`versions/`** : un `ProfilVersion` par version (`v1_0.py`, `v1_1.py`) et le
  registre `resoudre_profil`. Chaque profil porte notamment son `prefixe_code`
  (`E01` / `E11`) et le chemin de son XSD.
- **`detection_version.py`** : extraction de la version depuis le fragment
  `RecoStar-vX.Y` du `xsi:schemaLocation`.
- **`generateur_sequences.py`** : dérivation automatique des séquences et de
  l'énumération SRS depuis un XSD, utilisée pour construire les profils.

## Différences V1.0 → V1.1 prises en compte

Les profils de version encodent les écarts suivants, mesurés par comparaison
programmatique des deux XSD officiels :

| Domaine | V1.0 | V1.1 |
|---------|------|------|
| Types RPD | — | ajout de `RPD_CableTelecommunication_Reco` |
| Champ `Commentaire` | absent | ajouté (0..1) sur la quasi-totalité des types RPD |
| Champ `Statut` | absent | ajouté (1..1) sur `RPD_BatimentTechnique_Reco`, `RPD_Coffret_Reco`, `RPD_EnceinteCloturee_Reco`, `RPD_Support_Reco` |
| `RPD_CableElectrique_Reco` | `Isolant`, `Materiau`, `NombreConducteurs`, `Section` **requis** | ces champs deviennent **optionnels** ; ajout d'`Etiquette` |
| `RPD_GeometrieSupplementaire_Reco` | `Ligne2.5D`, `Surface2.5D` | renommés `Ligne3D`, `Surface3D` |
| `RPD_PointLeveOuvrageReseau_Reco` | `Leve`, `TypeLeve` | remplacés par `ChargeGeneratrice`, `Horodatage` |
| `RPD_SupportModules_Reco` | `NombrePlages` | champ supprimé |
| `RPD_ModuleRaccordement_Reco` | position de `noeudParent` différente | — |
| Systèmes de référence (SRS) | énumération de base | ajout de 10 codes (`EPSG:9794`, `EPSG:9842` à `EPSG:9850`) |

Ces écarts sont **dérivés du XSD** pour tout ce qui est structurel (E010/E110,
E013/E113) et **curés à la main** pour les deltas métier et de valeurs
(E011/E111, E014/E114). En particulier, le contrôle de valeur du type de levé
s'applique au champ `TypeLeve` en V1.0 ; il est sans objet en V1.1, où le champ
a disparu.

---

## E110 / E010 — Ordre de structure des objets RPD (`controle_e110.py`)

**Ce qui est contrôlé :** pour chaque `featureMember` dont l'enfant est un type
RPD connu, vérifie que l'ordre des éléments enfants respecte la `xs:sequence`
du XSD (via `sequenceur_xsd`). Les objets `EP_` et les types non-RPD sont
ignorés.

**Détecte :** `ORDRE_INCORRECT`, `ELEMENT_REQUIS_MANQUANT`, `ELEMENT_INATTENDU`.

**Sortie — `<gml>_controle_e110.json`** (`type_controle: E110_ORDRE`), ou
`<gml>_controle_e010.json` (`E010_ORDRE`) en V1.0.
Chaque erreur : `type_rpd`, `gml_id`, `severite`, `type_erreur`, `position`,
`element_trouve`, `element_attendu`, `message`.

---

## E111 / E011 — Règles métier conditionnelles (`controle_e111.py`)

**Ce qui est contrôlé :** les obligations que le XSD ne peut exprimer, selon le
contexte de l'objet :

- câble électrique au statut « En attente de mise en exploitation » → champs requis ;
- câble électrique de domaine de tension **BT** → champs requis ;
- support de type **Poteau** en attente → champs requis.

Les valeurs sont résolues depuis le texte de l'élément ou le fragment
`xlink:href`.

**Sortie — `<gml>_controle_e111.json`** (`type_controle: E111_METIER`), ou
`<gml>_controle_e011.json` (`E011_METIER`) en V1.0.
Chaque erreur : `type_rpd`, `gml_id`, `severite`, `regle`, `champ_attendu`,
`contexte`, `message`.

---

## E112 / E012 — Validation XSD native (`controle_e112.py`)

**Ce qui est contrôlé :** délègue toute la vérification structurelle et typée à
`lxml.etree.XMLSchema` à partir du XSD officiel. Les erreurs natives `lxml`
(`SCHEMAV_*`) sont reclassées dans une **taxonomie française** stable
(`VALEUR_HORS_ENUMERATION`, `ELEMENT_REQUIS_MANQUANT`, `ATTRIBUT_INCONNU`,
`STRUCTURE_INVALIDE`, …). Un XML mal formé donne `XML_MALFORME` ; un XSD non
compilable donne `XSD_NON_COMPILABLE`.

**Options :** `--xsd`, `--cache-dir`, `--offline`. Les XSD externes (GML,
ISO 19139, XLink…) sont résolus depuis un cache local
(`conversion/conversion_V1_1/xsd/cache/`), ce qui permet une compilation
hors-ligne. Sans `--xsd`, le XSD utilisé est celui de la version active
(`conversion/conversion_V1/xsd/` en V1.0, `conversion/conversion_V1_1/xsd/` en
V1.1).

**Sortie — `<gml>_controle_e112.json`** (`type_controle: E112_XSD_NATIF`, +
champ `xsd`), ou `<gml>_controle_e012.json` (`E012_XSD_NATIF`) en V1.0. Chaque erreur : `code`, `severite`, `ligne`, `colonne`, `xpath`,
`type_lxml`, `message`.

---

## E113 / E013 — En-tête, namespaces et métadonnées (`controle_e113.py`)

**Ce qui est contrôlé :** l'enveloppe GML elle-même :

- namespaces déclarés et URI correctes ;
- `xsi:schemaLocation` présent et pointant la version contrôlée (v1.0 ou v1.1) ;
- présence et cardinalité du `Metadata` et d'au moins un `ReseauUtilite`, ainsi
  que l'ordre de leurs champs (via `valider_sequence` sur des catalogues
  d'en-tête) ;
- SRS autorisé ;
- **unicité des `gml:id`** sur l'ensemble du fichier.

**Détecte :** `NAMESPACE_MANQUANT` / `NAMESPACE_URI_INCORRECTE`,
`SCHEMA_LOCATION_MANQUANT` / `SCHEMA_LOCATION_VERSION_INCORRECTE`,
`OBJET_ENTETE_MANQUANT` / `OBJET_ENTETE_TROP_NOMBREUX`,
`CHAMP_OBLIGATOIRE_MANQUANT` / `CHAMP_HORS_ORDRE` / `CHAMP_INATTENDU`,
`SRS_INVALIDE`, `GML_ID_DUPLIQUE`.

**Priorités :** toutes les anomalies sont bloquantes, à une exception près —
un `xsi:schemaLocation` pointant la **branche `main`** du XSD est de priorité
**`majeur`** (`regles_entete.PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN`) : le
fichier reste exploitable mais n'est plus ancré sur un tag de version figé.
La dérogation vise ce seul cas : les autres écarts de `schemaLocation` —
attribut absent, ou URL référençant une **autre version** — restent bloquants,
bien que ce dernier partage le code `SCHEMA_LOCATION_VERSION_INCORRECTE` avec
la branche `main`.

**Sortie — `<gml>_controle_e113.json`** (`type_controle: E113_ENTETE`), ou
`<gml>_controle_e013.json` (`E013_ENTETE`) en V1.0. Chaque entrée porte son
champ `priorite`.

---

## E114 / E014 — Valeurs des champs (`controle_e114.py`)

**Ce qui est contrôlé :** les valeurs littérales / `xlink:href` des enfants des
objets RPD contre trois familles de contraintes, **toutes de sévérité ERREUR** :

- **énumérations fermées** (§10) → `VALEUR_HORS_ENUMERATION` ;
- **CodeLists documentées** (§10) → `VALEUR_HORS_CODELIST` (politique RPD
  stricte : seules les valeurs documentées sont admises, aucune extension
  locale n'est tolérée) ;
- **contraintes de format métier** (ex. `Theme=ELECTRD`, `NumeroPRM` à 14
  chiffres) → `FORMAT_INVALIDE`.

Le code d'erreur distingue l'origine de la violation (énumération, CodeList ou
format) ; la sévérité, elle, est unique.

**Priorités :** une seule règle du catalogue déroge au niveau bloquant —
`E_THEME_RPD` (`ReseauUtilite/Theme` hors de l'énumération `{ELECTRD}`, §9) est
de priorité **`mineur`** : l'étiquette de réseau est corrigeable sans reprise du
levé et sans conséquence sur l'exploitation des ouvrages. La détection et le
message restent inchangés. Toutes les autres règles conservent la priorité
bloquante, y compris `F_NUMERO_PRM` qui partage pourtant le code
`FORMAT_INVALIDE`. La V1.0 dérivant son catalogue de la V1.1, la dérogation
s'applique identiquement à E014.

**Sortie — `<gml>_controle_e114.json`** (`type_controle: E114_VALEURS`,
`nb_par_severite` ne comportant que la clé `ERREUR`), ou
`<gml>_controle_e014.json` (`E014_VALEURS`) en V1.0. Chaque entrée : `type_rpd`,
`gml_id`, `champ`, `valeur_trouvee`, `code`, `severite`, `priorite`, `regle`,
`source`, `message`.

---

## Pipeline (`pipeline_controle_xsd.py`)

Exécute séquentiellement les cinq contrôles (ordre → métier → XSD natif →
en-tête → valeurs) sur un même fichier GML, sous les codes de la version
résolue : `E010 → E014` en V1.0, `E110 → E114` en V1.1. Chaque contrôle est isolé : un échec (par exemple un
XSD indisponible pour E112) **n'interrompt pas** les contrôles suivants. Chaque
contrôle écrit son rapport individuel, et le pipeline produit en plus un rapport
global agrégé.

### Usage

```bash
python pipeline_controle_xsd.py <fichier.gml> [--output-dir <repertoire>] \
    [--xsd <chemin.xsd>] [--cache-dir <repertoire>] [--offline] \
    [--version {auto,1.0,1.1}]
```

La version est résolue une seule fois en amont puis propagée aux cinq contrôles
(version homogène garantie). Sans `--xsd`, E112 utilise le XSD officiel de la
version active.

### Sorties

- Les 5 rapports individuels `<gml>_controle_e0xx.json` (V1.0) ou
  `<gml>_controle_e1xx.json` (V1.1).
- Le rapport global `<gml>_controle_xsd_global.json`, également imprimé sur la
  sortie standard :

```json
{
  "succes": true,
  "fichier": "...",
  "date_controle": "AAAA-MM-JJTHH:MM:SS",
  "version_controlee": "1.1",
  "controles": {
    "E110": { "succes": true, "type_controle": "E110_ORDRE", "conformite": "...",
              "nb_erreurs": 0, "nb_erreurs_bloquantes": 0, "nb_par_severite": {},
              "anomalies_par_priorite": {}, "rapport": "..." },
    "E111": { ... }, "E112": { ... }, "E113": { ... }, "E114": { ... }
  },
  "nb_erreurs_total": 0,
  "nb_erreurs_bloquantes": 0,
  "controles_en_echec": [],
  "conformite_globale": "CONFORME"
}
```

- `nb_erreurs_total` : somme de **toutes** les erreurs des contrôles exécutés,
  quelle que soit leur priorité ;
- `nb_erreurs_bloquantes` : sous-total des seules erreurs `bloquant` ;
- `anomalies_par_priorite` : ventilation par priorité, lue telle quelle par
  `synthese_controles.py` pour alimenter le rapport PDF global ;
- `controles_en_echec` : codes des contrôles qui n'ont pas pu s'exécuter ;
- `conformite_globale` : `CONFORME` seulement si aucune erreur **bloquante**
  **et** aucun contrôle en échec. Un fichier ne portant que des anomalies
  majeures ou mineures est donc `CONFORME`, ces anomalies restant comptées dans
  `nb_erreurs_total` et détaillées dans les rapports individuels ;
- les clés de `controles` sont `E010`…`E014` lorsque le fichier est contrôlé en
  V1.0.

Un contrôle en échec est représenté par
`{ "succes": false, "type_controle": "...", "erreur": "<message>" }`.
