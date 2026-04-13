# Référence des GeoJSON RPD_*

Document de référence rapide : champs par fichier GeoJSON manipulé par les scripts de conversion.

---

## RPD_CableElectrique_Reco

Câble électrique du réseau. Pas de géométrie propre (héritée du cheminement).

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique de l'entité |
| `DomaineTension` | string | Domaine de tension |
| `FonctionCable_href` | href | Référence fonction du câble |
| `HierarchieBT` | string | Hiérarchie basse tension |
| `Isolant` | string | Type d'isolant |
| `Materiau` | string | Matériau du câble |
| `NombreConducteurs` | int | Nombre de conducteurs |
| `Section` | float | Section (uom: mm-2) |
| `Statut` | string | Statut de l'ouvrage |
| `Section_uom` | string | Unité de section (défaut: mm-2) |
| `SectionNeutre` | float | Section du neutre (uom: mm-2) |
| `SectionNeutre_uom` | string | Unité section neutre |

---

## RPD_CableTerre_Reco

Câble de mise à la terre.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `FonctionCable_href` | href | Référence fonction du câble |
| `Materiau` | string | Matériau du câble |
| `Section` | float | Section (uom: mm-2) |
| `Statut` | string | Statut |
| `noeudreseau_href` | href | Référence vers RPD_Terre_Reco |
| `Commentaire` | string | Commentaire libre |
| `NatureCableTerre_href` | href | Nature du câble de terre |
| `Section_uom` | string | Unité de section |

---

## RPD_Coffret_Reco

Coffret / armoire de distribution. Géométrie : **Point**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `FonctionCoffret_href` | href | Référence fonction du coffret |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `geometriesupplementaire_href` | href | Référence géométrie supplémentaire |
| `ImplantationArmoire_href` | href | Type d'implantation |
| `TypeCoffret_href` | href | Type de coffret |

---

## RPD_Support_Reco

Support (poteau). Géométrie : **Point**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `NatureSupport_href` | href | Nature du support |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `Classe_href` | href | Classe du support |
| `Effort` | float | Effort (uom: kN) |
| `Effort_uom` | string | Unité d'effort |
| `HauteurPoteau` | float | Hauteur (uom: m) |
| `HauteurPoteau_uom` | string | Unité de hauteur |
| `Matiere_href` | href | Matière du support |

---

## RPD_Fourreau_Reco

Cheminement de type fourreau. Géométrie : **LineString**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `DiametreDuFourreau` | float | Diamètre (uom: mm) |
| `Materiau` | string | Matériau du fourreau |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `DiametreDuFourreau_uom` | string | Unité diamètre (défaut: mm) |
| `CoupeType` | string | Coupe type |
| `EtatCoupeType` | string | État de la coupe type |
| `ProfondeurMinNonReg` | float | Profondeur min non réglementaire (uom: m) |
| `ProfondeurMinNonReg_uom` | string | Unité profondeur |

---

## RPD_PleineTerre_Reco

Cheminement en pleine terre. Géométrie : **LineString**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `CoupeType` | string | Coupe type |
| `EtatCoupeType` | string | État de la coupe type |
| `ProfondeurMinNonReg` | float | Profondeur min non réglementaire (uom: m) |
| `ProfondeurMinNonReg_uom` | string | Unité profondeur |

---

## RPD_Aerien_Reco

Cheminement aérien. Géométrie : **LineString**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `ModePose` | string | Mode de pose |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |

---

## RPD_ProtectionMecanique_Reco

Protection mécanique (fourreau de protection). Géométrie : **LineString**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `Materiau` | string | Matériau |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `CoupeType` | string | Coupe type |
| `EtatCoupeType` | string | État de la coupe type |
| `ProfondeurMinNonReg` | float | Profondeur min non réglementaire (uom: m) |
| `ProfondeurMinNonReg_uom` | string | Unité profondeur |

---

## RPD_GeometrieSupplementaire_Reco

Géométrie complémentaire associée à un conteneur. Géométrie : **Polygon/MultiPolygon** (Surface2.5D).

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `Ligne2.5D` | string | Géométrie linéaire WKT supplémentaire |

---

## RPD_Jonction_Reco

Jonction (nœud réseau). Géométrie : **Point** (seulement si pas de conteneur).

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `DomaineTension` | string | Domaine de tension |
| `Statut` | string | Statut |
| `TypeJonction` | string | Type de jonction |
| `conteneur_href` | href | Référence conteneur (coffret/support) |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `angle` | float | Angle de la jonction |

---

## RPD_PosteElectrique_Reco

Poste électrique (nœud réseau). Géométrie héritée du conteneur.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `Categorie_href` | href | Catégorie du poste |
| `Code` | string | Code du poste |
| `InformationSupplementaire` | string | Information complémentaire |
| `Statut` | string | Statut |
| `TypePoste_href` | href | Type de poste |
| `conteneur_href` | href | Référence conteneur |

---

## RPD_PointDeComptage_Reco

Point de comptage. Géométrie : **Point**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `Statut` | string | Statut |
| `conteneur_href` | href | Référence conteneur |
| `NumeroPRM` | string | Numéro PRM |

---

## RPD_PointLeveOuvrageReseau_Reco

Point levé d'ouvrage réseau. Géométrie : **Point**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `NumeroPoint` | string | Numéro du point |
| `PrecisionXYnum` | string | Précision XY numérique |
| `PrecisionZnum` | string | Précision Z numérique |
| `Producteur` | string | Producteur du levé |
| `TypeLeve` | string | Type de levé |
| `Leve` | float | Valeur levé (uom: m) |
| `Leve_uom` | string | Unité du levé |

---

## RPD_JeuBarres_Reco

Jeu de barres (nœud réseau). Pas de géométrie propre.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `Statut` | string | Statut |
| `conteneur_href` | href | Référence conteneur |

---

## RPD_SupportModules_Reco

Modules sur support (nœud réseau). Pas de géométrie propre.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `NombrePlages` | int | Nombre de plages |
| `Statut` | string | Statut |
| `conteneur_href` | href | Référence conteneur |

---

## RPD_Terre_Reco

Prise de terre (nœud réseau). Pas de géométrie propre.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `NatureTerre_href` | href | Nature de la terre |
| `Statut` | string | Statut |
| `conteneur_href` | href | Référence conteneur |
| `Resistance` | float | Résistance (uom: Ohm) |
| `Resistance_uom` | string | Unité de résistance |

---

## RPD_OuvrageCollectifBranchement_Reco

Ouvrage collectif de branchement (nœud réseau). Géométrie : **Point** (seulement si pas de conteneur).

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `Statut` | string | Statut |
| `conteneur_href` | href | Référence conteneur |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |

---

## RPD_Materiel_Reco

Matériel associé à un ouvrage via relation Ouvrage_Materiel. Pas de géométrie.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `Fabricant` | string | Fabricant |
| `Modele` | string | Modèle |
| `NumeroLot` | string | Numéro de lot |
| `NumeroSerie` | string | Numéro de série |

---

## RPD_CoupeCircuitAFusibles_Reco

Coupe-circuit à fusibles (nœud réseau). Pas de géométrie propre.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `Statut` | string | Statut |
| `conteneur_href` | href | Référence conteneur |

---

## RPD_BatimentTechnique_Reco

Bâtiment technique (conteneur). Géométrie : **Point**.

| Champ | Type | Description |
| --- | --- | --- |
| `ogr_pkid` | string | Identifiant unique |
| `PrecisionXY` | string | Classe de précision XY |
| `PrecisionZ` | string | Classe de précision Z |
| `geometriesupplementaire_href` | href | Référence géométrie supplémentaire |

---

> **Note** : Tous les fichiers sont nommés `RPD_<Type>_Reco.geojson`. Le champ `fid` (auto-incrémenté) et `id` (gml:id) sont générés automatiquement par les scripts et ne nécessitent pas d'être fournis en entrée.
