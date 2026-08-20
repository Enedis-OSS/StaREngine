# Contrôles de cheminement

Ce dossier regroupe les contrôles géométriques appliqués aux fichiers GeoJSON
de cheminement Recostar. Chaque contrôle parcourt un ou plusieurs fichiers GeoJSON,
détecte les anomalies et produit un fichier d'écarts GeoJSON (préfixé `ecarts_`)
directement exploitable dans QGIS (le `crs` du fichier source est propagé).

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
| `code_controle` | Code du contrôle ayant produit l'écart (`E200`, `E401`…) |
| `priorite` | Niveau de priorité de l'anomalie (`bloquant`, `mineur`, `information`) |
| `id_entite` | Identifiant de l'entité portant la géométrie de la feature |
| `type_anomalie` | Code technique de l'anomalie, stable et exploitable en filtre |
| `description` | Phrase décrivant l'anomalie, lisible dans QGIS |

Les propriétés métier spécifiques à chaque contrôle sont conservées à la suite du
socle. La normalisation est assurée par `normaliser_geojson_ecarts()` à partir du
`ProfilEcarts` déclaré en tête de chaque script de contrôle.

## Vue d'ensemble

| Code | Script | Cible | Condition d'anomalie | Priorité | Fichier de sortie |
|------|--------|-------|----------------------|----------|-------------------|
| E400 | `controle_e400.py` | Fourreau, PleineTerre, Aerien, ProtectionMecanique | chevauchement géométrique linéaire | `bloquant` | `ecarts_e400_superpositions_cheminements.geojson` |
| E401 | `controle_e401.py` | CableElectrique, CableTerre, CableTelecommunication, Fourreau, PleineTerre, Aerien, ProtectionMecanique | intégrité des relations `cables_href` | `bloquant` | `ecarts_e401_integrite_cables_cheminements.geojson` |
| E402 | `controle_e402.py` | CableTerre, Aerien, ProtectionMecanique | câble de terre associé à un cheminement incompatible | `bloquant` | `ecarts_e402_cable_terre_cheminement_incompatible.geojson` |
| E403 | `controle_e403.py` | CableElectrique, Aerien, Fourreau, PleineTerre, ProtectionMecanique | câble électrique simultanément aérien et souterrain | `bloquant` | `ecarts_e403_cable_electrique_implantation_incoherente.geojson` |
| E404 | `controle_e404.py` | PointLeveOuvrageReseau, Fourreau, PleineTerre, ProtectionMecanique | cheminement souterrain sans profondeur à une charge génératrice | `majeur` | `ecarts_e404_charge_generatrice_profondeur_absente.geojson` |

Les fonctions utilitaires communes (lecture/écriture GeoJSON, extraction
d'identifiant) sont centralisées dans `utils_geojson.py`. L'orchestration de
l'ensemble est assurée par `pipeline_controle_cheminement.py`.

### Usage CLI

```bash
python controle_e400.py --repertoire <chemin> [--sortie <chemin>]
python controle_e401.py --repertoire <chemin> [--sortie <chemin>]
python controle_e402.py --repertoire <chemin> [--sortie <chemin>]
python controle_e403.py --repertoire <chemin> [--sortie <chemin>]
python controle_e404.py --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]

# Enchaînement de tous les contrôles ci-dessus :
python pipeline_controle_cheminement.py --repertoire <chemin> [--sortie <chemin>]
```

- `--repertoire` : répertoire contenant les fichiers GeoJSON.
- `--sortie` : répertoire de sortie (par défaut, le répertoire d'entrée).
- `--version` (E404 uniquement) : version Recostar à appliquer. `auto` (défaut) la déduit du contenu GeoJSON.

Le résultat est imprimé en JSON sur la sortie standard.
Les fichiers absents du répertoire ne bloquent pas l'exécution.

---

## E400 — Superpositions géométriques entre cheminements (`controle_e400.py`)

**Ce qui est contrôlé :** détecte les chevauchements spatiaux (totaux ou partiels)
entre les entités linéaires des quatre fichiers de cheminement Recostar. Deux niveaux
de contrôle sont appliqués simultanément :

| Niveau | Description |
|--------|-------------|
| **Intra-couche** | Superpositions entre entités d'un même fichier (ex. deux fourreaux occupant le même tracé) |
| **Inter-couches** | Superpositions entre entités de fichiers différents (ex. un fourreau et une pleine terre coaxiaux) |

**Fichiers analysés :**

- `RPD_Fourreau_Reco.geojson`
- `RPD_PleineTerre_Reco.geojson`
- `RPD_Aerien_Reco.geojson`
- `RPD_ProtectionMecanique_Reco.geojson`

La présence de chacun de ces fichiers est optionnelle : le contrôle s'exécute
sur les fichiers disponibles et liste les fichiers absents dans le rapport JSON
sans retourner d'erreur.

**Algorithme de détection :**

La détection est **planimetrique (2D)** — les valeurs Z sont ignorées. Deux
cheminements coaxiaux en XY mais à des cotes Z différentes (ex. fourreau à
−0,5 m et pleine terre à 0 m) sont bien signalés comme superposés, laissant
le contrôle altimétrique à d'autres modules.

1. Les géométries de type `LineString` et `MultiLineString` sont chargées et
   converties en 2D.
2. Un **STRtree** (Sort-Tile-Recursive tree, index spatial de Shapely) est
   construit sur l'ensemble des entités toutes couches confondues.
3. Pour chaque entité, les candidats à l'intersection sont interrogés via le
   prédicat `intersects` — les simples croisements (intersection = point) sont
   éliminés à cette étape.
4. Pour chaque paire candidate, l'**intersection exacte** est calculée par
   Shapely/GEOS. Si sa longueur est supérieure au seuil minimal de **0,01 m**,
   une anomalie est produite.
5. Chaque paire `(i, j)` est traitée une seule fois (`i < j`), ce qui garantit
   l'absence de doublons sans surcoût mémoire.

**Classification de la superposition :**

| Type | Condition |
|------|-----------|
| `totale` | La longueur du chevauchement couvre ≥ 99 % de la longueur de la plus courte des deux entités |
| `partielle` | La longueur du chevauchement couvre < 99 % de la plus courte des deux entités |

**Géométries ignorées :**

- Entités sans géométrie ou de type non linéaire (`Point`, `Polygon`, etc.).
- Entités dont la longueur est inférieure à 0,01 m (dégénérées).
- Géométries invalides au sens GEOS.

**Sortie — `ecarts_e400_superpositions_cheminements.geojson` :** un `Feature` par paire
de cheminements en superposition. La **géométrie de la feature est la portion de
chevauchement calculée**, ce qui permet une localisation précise dans QGIS. Propriétés :

- `niveau` : `intra_couche` ou `inter_couches`
- `couche_a` : nom du fichier GeoJSON de la première entité
- `id_entite_a` : identifiant de la première entité (champ `id` des propriétés), ou `null` si absent
- `couche_b` : nom du fichier GeoJSON de la deuxième entité
- `id_entite_b` : identifiant de la deuxième entité, ou `null` si absent
- `type_superposition` : `totale` ou `partielle`
- `longueur_chevauchement_m` : longueur de la portion de chevauchement (en mètres, arrondie à 3 décimales)
- `type_anomalie` = `superposition_cheminements`
- `priorite` = `bloquant`

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `nombre_entites_analysees`,
`fichiers_absents`, `sortie`.

**Erreurs remontées :**

- Répertoire introuvable.

---

## E401 — Intégrité des relations câbles/cheminements (`controle_e401.py`)

**Ce qui est contrôlé :** vérifie la cohérence bidirectionnelle entre les entités câble et les entités cheminement via le champ `cables_href`. Quatre règles sont appliquées :

| Règle | Description | Type d'anomalie |
|-------|-------------|-----------------|
| **1 / 3** | Tout câble doit être référencé par au moins un cheminement | `cable_non_reference` |
| **2** | Toute valeur de `cables_href` doit correspondre à l'identifiant d'un câble existant | `reference_orpheline` |
| **4a** | Un cheminement sans `cables_href` (null ou absent) | `cheminement_sans_cable` |
| **4b** | Un cheminement référençant plusieurs câbles | `cheminement_multi_cables` |

**Fichiers câbles analysés :**

- `RPD_CableElectrique_Reco.geojson`
- `RPD_CableTerre_Reco.geojson`
- `RPD_CableTelecommunication_Reco.geojson` *(V1.1 uniquement)*

**Fichiers cheminement analysés :**

- `RPD_Fourreau_Reco.geojson`
- `RPD_PleineTerre_Reco.geojson`
- `RPD_Aerien_Reco.geojson`
- `RPD_ProtectionMecanique_Reco.geojson`

La présence de chacun de ces fichiers est optionnelle : le contrôle s'exécute sur les fichiers disponibles et liste les fichiers absents dans le rapport JSON sans retourner d'erreur.

**Format du champ `cables_href` :**

Le champ `cables_href` est une chaîne de caractères contenant un ou plusieurs identifiants câble séparés par des virgules (ex. `"idabc123"` ou `"idabc123,iddef456"`). Il correspond au champ `id` des entités câble (format `"id"` + UUID v4). La valeur `null` ou l'absence du champ signifient que le cheminement n'est associé à aucun câble.

**Sortie — `ecarts_e401_integrite_cables_cheminements.geojson` :** un `Feature` par anomalie détectée. La **géométrie de la feature est celle de l'entité concernée** (câble pour `cable_non_reference`, cheminement pour les autres types), ce qui permet la localisation dans QGIS. Propriétés communes :

- `type_anomalie` : `cable_non_reference`, `reference_orpheline`, `cheminement_sans_cable` ou `cheminement_multi_cables`
- `priorite` = `bloquant`

Propriétés spécifiques selon le type :

| Type d'anomalie | Propriétés additionnelles |
|-----------------|--------------------------|
| `cable_non_reference` | `fichier_cable`, `id_cable` |
| `reference_orpheline` | `fichier_cheminement`, `id_cheminement`, `cables_href_invalide` |
| `cheminement_sans_cable` | `fichier_cheminement`, `id_cheminement` |
| `cheminement_multi_cables` | `fichier_cheminement`, `id_cheminement`, `nb_cables`, `cables_href` |

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`, `anomalies_par_type` (compteurs par type), `nombre_cables_analyses`, `nombre_cheminements_analyses`, `fichiers_cables_absents`, `fichiers_cheminement_absents`, `sortie`.

**Erreurs remontées :**

- Répertoire introuvable.

---

## E402 — Cohérence métier câble de terre / cheminement (`controle_e402.py`)

**Ce qui est contrôlé :** un câble de terre ne peut donc jamais être acheminé via un cheminement aérien ou sous protection
mécanique. Le contrôle détecte toute référence croisée entre ces types incompatibles.

**Règle métier :** toute valeur du champ `cables_href` présente dans
`RPD_Aerien_Reco.geojson` ou `RPD_ProtectionMecanique_Reco.geojson` qui correspond
à l'identifiant d'une entité de `RPD_CableTerre_Reco.geojson` est signalée comme
anomalie.

**Fichier câble analysé :**

- `RPD_CableTerre_Reco.geojson`

**Fichiers cheminement incompatibles analysés :**

- `RPD_Aerien_Reco.geojson`
- `RPD_ProtectionMecanique_Reco.geojson`

La présence de chacun de ces fichiers est optionnelle : le contrôle s'exécute
sur les fichiers disponibles et liste les fichiers absents dans le rapport JSON
sans retourner d'erreur.

**Algorithme :**

1. Les identifiants (`id`) de toutes les entités de `RPD_CableTerre_Reco.geojson`
   sont chargés dans un **`set`** — la structure garantit un test d'appartenance en O(1).
2. Les entités des deux fichiers de cheminement incompatibles sont chargées.
3. Pour chaque cheminement, chaque valeur de `cables_href` est testée contre le set.
   Si l'ID est celui d'un câble de terre, une anomalie est produite.

Une anomalie est produite par **couple (cheminement, câble de terre)** : un
cheminement référençant deux câbles de terre génère deux anomalies distinctes.

**Sortie — `ecarts_e402_cable_terre_cheminement_incompatible.geojson` :** un `Feature` par
anomalie. La **géométrie de la feature est celle du cheminement incompatible**, ce
qui permet la localisation dans QGIS. Propriétés :

- `type_anomalie` = `cable_terre_cheminement_incompatible`
- `priorite` = `bloquant`
- `fichier_cheminement` : `RPD_Aerien_Reco.geojson` ou `RPD_ProtectionMecanique_Reco.geojson`
- `id_cheminement` : identifiant du cheminement concerné, ou `null` si absent
- `id_cable_terre` : identifiant du câble de terre incorrectement référencé

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_cables_terre_analyses`, `nombre_cheminements_analyses`,
`cable_terre_absent` (booléen), `fichiers_cheminement_absents`, `sortie`.

**Erreurs remontées :**

- Répertoire introuvable.

---

## E403 — Cohérence du mode d'implantation des câbles électriques (`controle_e403.py`)

**Ce qui est contrôlé :** un câble électrique doit être cohérent avec son mode
d'implantation. Un câble ne peut pas être à la fois aérien et physiquement enfoui
dans le sol. Le contrôle détecte les câbles électriques simultanément référencés
par un cheminement aérien et par un cheminement souterrain.

**Règle métier :** tout câble présent dans `RPD_CableElectrique_Reco.geojson` dont
l'identifiant apparaît à la fois dans les `cables_href` d'un cheminement aérien
**ET** dans les `cables_href` d'un cheminement souterrain est signalé comme anomalie.

**Catégories de cheminements :**

| Catégorie | Fichiers |
|-----------|----------|
| **Aérien** | `RPD_Aerien_Reco.geojson` |
| **Souterrain** | `RPD_Fourreau_Reco.geojson`, `RPD_PleineTerre_Reco.geojson`, `RPD_ProtectionMecanique_Reco.geojson` |

La présence de chacun de ces fichiers est optionnelle : le contrôle s'exécute
sur les fichiers disponibles et liste les fichiers absents dans le rapport JSON
sans retourner d'erreur.

**Algorithme :**

1. Les entités de `RPD_CableElectrique_Reco.geojson` sont chargées dans un
   dictionnaire `{id → EntiteCable}` — la géométrie est conservée pour la sortie.
2. Les quatre fichiers de cheminement (aérien + souterrains) sont chargés ensemble.
3. Deux **index inversés** (`defaultdict`) sont construits en un seul parcours :
   - `refs_aerien[id_cable]` → liste des cheminements aériens référençant ce câble
   - `refs_souterrain[id_cable]` → liste des cheminements souterrains référençant ce câble
4. Pour chaque câble électrique, si les deux index sont non vides → anomalie.

La catégorisation aérien/souterrain se fait par comparaison du nom de fichier en O(1),
sans produit cartésien ni double boucle sur les paires de cheminements.

**Sortie — `ecarts_e403_cable_electrique_implantation_incoherente.geojson` :** un `Feature`
par câble électrique en situation incohérente. La **géométrie de la feature est celle
du câble électrique**, ce qui permet la localisation dans QGIS. Propriétés :

- `type_anomalie` = `cable_electrique_implantation_incoherente`
- `priorite` = `bloquant`
- `id_cable_electrique` : identifiant du câble électrique signalé
- `nb_cheminements_aeriens` : nombre de cheminements aériens référençant le câble
- `ids_cheminements_aeriens` : identifiants des cheminements aériens (CSV)
- `fichiers_cheminements_aeriens` : noms de fichiers correspondants (CSV)
- `nb_cheminements_souterrains` : nombre de cheminements souterrains référençant le câble
- `ids_cheminements_souterrains` : identifiants des cheminements souterrains (CSV)
- `fichiers_cheminements_souterrains` : noms de fichiers correspondants (CSV)

**Rapport JSON :** `succes`, `priorite`, `nombre_anomalies`,
`nombre_cables_electriques_analyses`, `nombre_cheminements_analyses`,
`cable_electrique_absent` (booléen), `fichiers_cheminement_absents`, `sortie`.

**Erreurs remontées :**

- Répertoire introuvable.

---

## E404 — Profondeur manquante aux charges génératrices (`controle_e404.py`)

**Ce qui est contrôlé :** un point de charge génératrice correspond à un emplacement
où une contrainte de profondeur minimale est requise. Ce contrôle vérifie que les
cheminements souterrains présents à cet emplacement ont renseigné le champ
`ProfondeurMinNonReg`.

**Règle métier :** tout cheminement souterrain (Fourreau, PleineTerre ou
ProtectionMecanique) se superposant géographiquement à un point de charge
génératrice doit posséder une valeur dans le champ `ProfondeurMinNonReg`.

**Règle de conformité aux limites :** si un point de charge génératrice se situe
à la limite entre deux cheminements adjacents, le point est conforme dès lors
qu'**au moins un** des deux cheminements a `ProfondeurMinNonReg` renseigné.

**Détection des charges génératrices par version :**

| Version | Condition d'identification |
|---------|---------------------------|
| **V1.0** | `TypeLeve == "ChargeGeneratrice"` dans `RPD_PointLeveOuvrageReseau_Reco.geojson` |
| **V1.1** | Champ `ChargeGeneratrice` présent et non null dans `RPD_PointLeveOuvrageReseau_Reco.geojson` |

La version est détectée automatiquement par la présence du champ `TypeLeve` dans
les features (V1.0) ou son absence (V1.1). Le paramètre `--version` permet de
forcer la version sans détection automatique.

**Fichier source analysé :**

- `RPD_PointLeveOuvrageReseau_Reco.geojson` (points de levé — obligatoire)

**Fichiers de cheminement souterrain analysés :**

- `RPD_Fourreau_Reco.geojson`
- `RPD_PleineTerre_Reco.geojson`
- `RPD_ProtectionMecanique_Reco.geojson`

La présence de chacun de ces fichiers est optionnelle : le contrôle s'exécute
sur les fichiers disponibles et liste les fichiers absents dans le rapport JSON.
Le fichier source `RPD_PointLeveOuvrageReseau_Reco.geojson` est obligatoire :
son absence retourne une erreur.

**Algorithme de détection :**

La détection est **planimétrique (2D)** — les coordonnées Z sont ignorées. Un
point et un cheminement sont considérés comme superposés si leur distance
planaire est inférieure à **0,01 m** (seuil couvrant les écarts de précision
flottante entre les géométries).

1. Les points de levé correspondant à des charges génératrices sont filtrés
   selon la version détectée.
2. Un **STRtree** (index spatial Shapely) est construit sur l'ensemble des
   cheminements souterrains.
3. Pour chaque point de charge génératrice, les cheminements dans un rayon de
   0,01 m sont identifiés via le prédicat `dwithin`.
4. Si aucun cheminement n'est trouvé → le point est hors périmètre (ignoré).
5. Si au moins un cheminement trouvé possède `ProfondeurMinNonReg` → conforme.
6. Si aucun cheminement trouvé ne possède `ProfondeurMinNonReg` → anomalie.

**Sortie — `ecarts_e404_charge_generatrice_profondeur_absente.geojson` :** un `Feature`
par point de charge génératrice en situation d'anomalie. La **géométrie de la
feature est celle du point de charge génératrice**, ce qui permet la localisation
directe dans QGIS. Propriétés :

- `type_anomalie` = `cheminement_sans_profondeur_charge_generatrice`
- `priorite` = `majeur`
- `version` : version Recostar appliquée (`1.0` ou `1.1`)
- `id_point` : identifiant du point de charge génératrice, ou `null` si absent
- `nb_cheminements_touches` : nombre de cheminements superposés au point
- `ids_cheminements_touches` : identifiants des cheminements concernés (CSV)
- `fichiers_cheminements_touches` : noms de fichiers correspondants (CSV)

**Rapport JSON :** `succes`, `priorite`, `version_detectee`, `nombre_anomalies`,
`nombre_points_charge_analyses`, `nombre_cheminements_analyses`,
`fichiers_cheminement_absents`, `sortie`.

**Erreurs remontées :**

- Répertoire introuvable.
- Fichier `RPD_PointLeveOuvrageReseau_Reco.geojson` introuvable.

---

## Pipeline (`pipeline_controle_cheminement.py`)

Exécute séquentiellement les 5 contrôles dans l'ordre E400 → E401 → E402 → E403 → E404.
Un échec d'un contrôle (par exemple un fichier source absent) n'interrompt pas
l'exécution des suivants. E404 déduit seul la version RecoStaR (mode `auto`),
comme en exécution unitaire.

**Rapport JSON :**

- `succes` ;
- `controles` : dictionnaire des rapports individuels, indexés par
  `controle_e400`, `controle_e401`, `controle_e402`, `controle_e403`,
  `controle_e404` (chacun contenant son champ `priorite`) ;
- `nombre_anomalies_total` : somme des anomalies des contrôles réussis.
