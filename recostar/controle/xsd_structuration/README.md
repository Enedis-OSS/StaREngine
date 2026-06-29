# Contrôles de structuration XSD (E110 – E114)

Ce dossier regroupe les contrôles qui valident un fichier **GML RecoStaR** par
rapport au schéma XSD `SchemaStarElecRecoStar.xsd` et au PDF de structuration
RecoStaR. Les **versions 1.0 et 1.1** du format sont prises en charge (voir
« Sélection de version » ci-dessous). Chaque contrôle couvre un angle différent
et complémentaire de la validation.

- **Entrée commune** : un fichier `.gml`.
- **Sortie commune** : un rapport JSON `<nom_gml>_controle_e1xx.json` écrit dans
  le répertoire du GML (ou dans `--output-dir`). Chaque rapport porte le champ
  `version_controlee` indiquant la version appliquée.
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

La connaissance propre à chaque version est centralisée dans le package
`versions/` (un `ProfilVersion` par version, registre `resoudre_profil`). Les
séquences de structure et l'énumération SRS de chaque version sont **dérivées
automatiquement de son XSD** par `generateur_sequences` ; seuls les deltas
métier (règles conditionnelles E111, valeurs E114) y sont curés à la main.

## Vue d'ensemble

| Code | Script | Ce qui est vérifié | Référence | Sévérités | `type_controle` |
|------|--------|--------------------|-----------|-----------|-----------------|
| E110 | `controle_e110.py` | Ordre des éléments des objets RPD | `sequenceur_xsd` (XSD v1.1) | ERREUR | `E110_ORDRE` |
| E111 | `controle_e111.py` | Règles métier conditionnelles | `regles_metier` (PDF V1.1) | ERREUR | `E111_METIER` |
| E112 | `controle_e112.py` | Validation XSD native complète | XSD officiel via `lxml` | ERREUR | `E112_XSD_NATIF` |
| E113 | `controle_e113.py` | En-tête, namespaces, métadonnées, unicité `gml:id` | `regles_entete` | ERREUR | `E113_ENTETE` |
| E114 | `controle_e114.py` | Valeurs des champs (énumérations, CodeLists, formats) | `regles_valeurs` (PDF §9/§10) | ERREUR + AVERTISSEMENT | `E114_VALEURS` |

Le script `pipeline_controle_xsd.py` orchestre l'exécution des cinq contrôles
sur un même fichier GML.

### Format de rapport commun

Chaque contrôle produit un JSON homogène :

```json
{
  "fichier": "...",
  "date_controle": "AAAA-MM-JJTHH:MM:SS",
  "niveau": "Forte",
  "type_controle": "E1xx_...",
  "conformite": "CONFORME | NON_CONFORME",
  "nb_erreurs": 0,
  "nb_par_severite": { "ERREUR": 0 },
  "erreurs": [ ... ]
}
```

La conformité découle du nombre d'entrées de sévérité `ERREUR` (les
`AVERTISSEMENT` d'E114 n'invalident pas le fichier).

### Usage CLI (contrôle isolé)

```bash
python controle_e110.py <fichier.gml> [--output-dir <repertoire>] \
    [--version {auto,1.0,1.1}]
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

---

## E110 — Ordre de structure des objets RPD (`controle_e110.py`)

**Ce qui est contrôlé :** pour chaque `featureMember` dont l'enfant est un type
RPD connu, vérifie que l'ordre des éléments enfants respecte la `xs:sequence`
du XSD (via `sequenceur_xsd`). Les objets `EP_` et les types non-RPD sont
ignorés.

**Détecte :** `ORDRE_INCORRECT`, `ELEMENT_REQUIS_MANQUANT`, `ELEMENT_INATTENDU`.

**Sortie — `<gml>_controle_e110.json`** (`type_controle: E110_ORDRE`).
Chaque erreur : `type_rpd`, `gml_id`, `severite`, `type_erreur`, `position`,
`element_trouve`, `element_attendu`, `message`.

---

## E111 — Règles métier conditionnelles (`controle_e111.py`)

**Ce qui est contrôlé :** les obligations que le XSD ne peut exprimer, selon le
contexte de l'objet :

- câble électrique au statut « En attente de mise en exploitation » → champs requis ;
- câble électrique de domaine de tension **BT** → champs requis ;
- support de type **Poteau** en attente → champs requis.

Les valeurs sont résolues depuis le texte de l'élément ou le fragment
`xlink:href`.

**Sortie — `<gml>_controle_e111.json`** (`type_controle: E111_METIER`).
Chaque erreur : `type_rpd`, `gml_id`, `severite`, `regle`, `champ_attendu`,
`contexte`, `message`.

---

## E112 — Validation XSD native (`controle_e112.py`)

**Ce qui est contrôlé :** délègue toute la vérification structurelle et typée à
`lxml.etree.XMLSchema` à partir du XSD officiel. Les erreurs natives `lxml`
(`SCHEMAV_*`) sont reclassées dans une **taxonomie française** stable
(`VALEUR_HORS_ENUMERATION`, `ELEMENT_REQUIS_MANQUANT`, `ATTRIBUT_INCONNU`,
`STRUCTURE_INVALIDE`, …). Un XML mal formé donne `XML_MALFORME` ; un XSD non
compilable donne `XSD_NON_COMPILABLE`.

**Options :** `--xsd`, `--cache-dir`, `--offline`. Les XSD externes (GML,
ISO 19139, XLink…) sont résolus depuis un cache local
(`conversion/conversion_V1_1/xsd/cache/`), ce qui permet une compilation
hors-ligne.

**Sortie — `<gml>_controle_e112.json`** (`type_controle: E112_XSD_NATIF`, +
champ `xsd`). Chaque erreur : `code`, `severite`, `ligne`, `colonne`, `xpath`,
`type_lxml`, `message`.

---

## E113 — En-tête, namespaces et métadonnées (`controle_e113.py`)

**Ce qui est contrôlé :** l'enveloppe GML elle-même :

- namespaces déclarés et URI correctes ;
- `xsi:schemaLocation` présent et pointant la bonne version (v1.1) ;
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

**Sortie — `<gml>_controle_e113.json`** (`type_controle: E113_ENTETE`).

---

## E114 — Valeurs des champs (`controle_e114.py`)

**Ce qui est contrôlé :** les valeurs littérales / `xlink:href` des enfants des
objets RPD contre :

- **énumérations fermées** (§10) → `VALEUR_HORS_ENUMERATION`, sévérité **ERREUR** ;
- **CodeLists ouvertes** (§10) → `VALEUR_HORS_CODELIST`, sévérité
  **AVERTISSEMENT** (n'invalide pas le fichier) ;
- **contraintes de format métier** (ex. `Theme=ELECTRD`, `NumeroPRM` à 14
  chiffres) → `FORMAT_INVALIDE`, sévérité **ERREUR**.

C'est le seul contrôle à **deux sévérités** : la `conformite` n'est
`NON_CONFORME` que s'il existe au moins une entrée `ERREUR`.

**Sortie — `<gml>_controle_e114.json`** (`type_controle: E114_VALEURS`,
`nb_par_severite` ventilé ERREUR / AVERTISSEMENT). Chaque entrée : `type_rpd`,
`gml_id`, `champ`, `valeur_trouvee`, `code`, `severite`, `regle`, `source`,
`message`.

---

## Pipeline (`pipeline_controle_xsd.py`)

Exécute séquentiellement les cinq contrôles (E110 → E111 → E112 → E113 → E114)
sur un même fichier GML. Chaque contrôle est isolé : un échec (par exemple un
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

- Les 5 rapports individuels `<gml>_controle_e1xx.json`.
- Le rapport global `<gml>_controle_xsd_global.json`, également imprimé sur la
  sortie standard :

```json
{
  "succes": true,
  "fichier": "...",
  "date_controle": "AAAA-MM-JJTHH:MM:SS",
  "controles": {
    "E110": { "succes": true, "type_controle": "E110_ORDRE", "conformite": "...",
              "nb_erreurs": 0, "nb_par_severite": {}, "rapport": "..." },
    "E111": { ... }, "E112": { ... }, "E113": { ... }, "E114": { ... }
  },
  "nb_erreurs_total": 0,
  "controles_en_echec": [],
  "conformite_globale": "CONFORME"
}
```

- `nb_erreurs_total` : somme des erreurs bloquantes des contrôles exécutés ;
- `controles_en_echec` : codes des contrôles qui n'ont pas pu s'exécuter ;
- `conformite_globale` : `CONFORME` seulement si aucune erreur bloquante **et**
  aucun contrôle en échec.

Un contrôle en échec est représenté par
`{ "succes": false, "type_controle": "...", "erreur": "<message>" }`.
