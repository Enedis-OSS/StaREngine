# Référence des GeoJSON RPD_* (V1.1)

Document de référence rapide : champs par fichier GeoJSON manipulé par les scripts de conversion V1.1.

**Légende** : ✓ = Obligatoire · — = Optionnel

> **Note** : Les champs `fid` et `id` (gml:id) sont générés automatiquement et ne nécessitent pas d'être fournis en entrée.
> Le champ `Commentaire` est disponible sur toutes les entités héritant d'ElementReseau (optionnel, non répété dans chaque table).
> Les champs `cables_href`, `EtatAvantRaccordement` et `materiel_href` sont des champs de relation décrits en [fin de document](#champs-de-relation).

---

## RPD_CableElectrique_Reco

Câble électrique du réseau. Géométrie héritée du cheminement (LineString/MultiLineString).

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique de l'entité |
| `DomaineTension` | ✓ | string | Domaine de tension |
| `FonctionCable_href` | ✓ | href | Référence fonction du câble |
| `Materiau` | ✓ | string | Matériau du câble |
| `Statut` | ✓ | string | Statut de l'ouvrage |
| `Etiquette` | — | string | Étiquette du câble |
| `HierarchieBT` | — | string | Hiérarchie basse tension |
| `Isolant` | — | string | Type d'isolant |
| `NombreConducteurs` | — | int | Nombre de conducteurs |
| `Section` | — | float | Section (uom: mm-2) |
| `Section_uom` | — | string | Unité de section (défaut: mm-2) |
| `SectionNeutre` | — | float | Section du neutre (uom: mm-2) |
| `SectionNeutre_uom` | — | string | Unité section neutre |

---

## RPD_CableTerre_Reco

Câble de mise à la terre. Géométrie héritée du cheminement (LineString/MultiLineString).

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `FonctionCable_href` | ✓ | href | Référence fonction du câble |
| `Materiau` | ✓ | string | Matériau du câble |
| `Section` | ✓ | float | Section (uom: mm-2) |
| `Statut` | ✓ | string | Statut |
| `Section_uom` | — | string | Unité de section (défaut: mm-2) |
| `noeudreseau_href` | — | href | Référence vers RPD_Terre_Reco |
| `NatureCableTerre_href` | — | href | Nature du câble de terre |
| `TypePose` | — | string | Type de pose |
| `PrecisionXY` | — | string | Classe de précision XY |
| `PrecisionZ` | — | string | Classe de précision Z |

---

## RPD_CableTelecommunication_Reco

Câble de télécommunication. Géométrie héritée du cheminement (LineString/MultiLineString).

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Statut` | ✓ | string | Statut |
| `Capacite` | — | int | Capacité du câble |
| `Fonction` | — | string | Fonction du câble |
| `Section` | — | float | Section (uom: mm-2) |
| `Section_uom` | — | string | Unité de section (défaut: mm-2) |
| `TechnoCable_href` | — | href | Technologie du câble |

---

## RPD_Coffret_Reco

Coffret / armoire de distribution. Géométrie : **Point**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `FonctionCoffret_href` | ✓ | href | Référence fonction du coffret |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `Statut` | ✓ | string | Statut |
| `geometriesupplementaire_href` | — | href | Référence géométrie supplémentaire |
| `ImplantationArmoire_href` | — | href | Type d'implantation |
| `TypeCoffret_href` | — | href | Type de coffret |

---

## RPD_Support_Reco

Support (poteau). Géométrie : **Point**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `NatureSupport_href` | ✓ | href | Nature du support |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `Statut` | ✓ | string | Statut |
| `Classe_href` | — | href | Classe du support |
| `Effort` | — | float | Effort (uom: kN) |
| `Effort_uom` | — | string | Unité d'effort (défaut: kN) |
| `HauteurPoteau` | — | float | Hauteur (uom: m) |
| `HauteurPoteau_uom` | — | string | Unité de hauteur (défaut: m) |
| `Matiere_href` | — | href | Matière du support |
| `geometriesupplementaire_href` | — | href | Référence géométrie supplémentaire |

---

## RPD_BatimentTechnique_Reco

Bâtiment technique (conteneur). Géométrie : **Point**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `Statut` | ✓ | string | Statut |
| `geometriesupplementaire_href` | — | href | Référence géométrie supplémentaire |

---

## RPD_EnceinteCloturee_Reco

Enceinte clôturée (conteneur). Géométrie : **Point**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `Statut` | ✓ | string | Statut |
| `geometriesupplementaire_href` | — | href | Référence géométrie supplémentaire |

---

## RPD_Fourreau_Reco

Cheminement de type fourreau. Géométrie : **LineString**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `DiametreDuFourreau` | ✓ | float | Diamètre (uom: mm) |
| `Materiau` | ✓ | string | Matériau du fourreau |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `DiametreDuFourreau_uom` | — | string | Unité diamètre (défaut: mm) |
| `CoupeType` | — | string | Coupe type |
| `EtatCoupeType` | — | string | État de la coupe type |
| `ProfondeurMinNonReg` | — | float | Profondeur min non réglementaire (uom: m) |
| `ProfondeurMinNonReg_uom` | — | string | Unité profondeur (défaut: m) |

---

## RPD_PleineTerre_Reco

Cheminement en pleine terre. Géométrie : **LineString**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `CoupeType` | — | string | Coupe type |
| `EtatCoupeType` | — | string | État de la coupe type |
| `ProfondeurMinNonReg` | — | float | Profondeur min non réglementaire (uom: m) |
| `ProfondeurMinNonReg_uom` | — | string | Unité profondeur (défaut: m) |

---

## RPD_Aerien_Reco

Cheminement aérien. Géométrie : **LineString**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `ModePose` | ✓ | string | Mode de pose |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |

---

## RPD_ProtectionMecanique_Reco

Protection mécanique (fourreau de protection). Géométrie : **LineString**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Materiau` | ✓ | string | Matériau |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `CoupeType` | — | string | Coupe type |
| `EtatCoupeType` | — | string | État de la coupe type |
| `ProfondeurMinNonReg` | — | float | Profondeur min non réglementaire (uom: m) |
| `ProfondeurMinNonReg_uom` | — | string | Unité profondeur (défaut: m) |

---

## RPD_GeometrieSupplementaire_Reco

Géométrie complémentaire associée à un conteneur. Géométrie : **Polygon/MultiPolygon** (Surface2.5D).

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `Ligne2.5D` | — | string | Géométrie linéaire WKT supplémentaire |

---

## RPD_Jonction_Reco

Jonction (nœud réseau). Géométrie : **Point** (seulement si pas de conteneur).

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `DomaineTension` | ✓ | string | Domaine de tension |
| `Statut` | ✓ | string | Statut |
| `TypeJonction` | ✓ | string | Type de jonction |
| `conteneur_href` | — | href | Référence conteneur (coffret/support) |
| `PrecisionXY` | — | string | Classe de précision XY |
| `PrecisionZ` | — | string | Classe de précision Z |
| `angle` | — | float | Angle de la jonction |
| `materiel_href` | — | href | Référence matériel associé |

---

## RPD_PosteElectrique_Reco

Poste électrique (nœud réseau). Géométrie héritée du conteneur.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Categorie_href` | ✓ | href | Catégorie du poste |
| `Code` | ✓ | string | Code du poste |
| `InformationSupplementaire` | ✓ | string | Information complémentaire |
| `Statut` | ✓ | string | Statut |
| `TypePoste_href` | ✓ | href | Type de poste |
| `conteneur_href` | — | href | Référence conteneur |

---

## RPD_PointDeComptage_Reco

Point de comptage (nœud réseau). Géométrie : **Point**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `PrecisionXY` | ✓ | string | Classe de précision XY |
| `PrecisionZ` | ✓ | string | Classe de précision Z |
| `Statut` | ✓ | string | Statut |
| `conteneur_href` | — | href | Référence conteneur |
| `NumeroPRM` | — | string | Numéro PRM |

---

## RPD_PointLeveOuvrageReseau_Reco

Point levé d'ouvrage réseau (modèle V1.10). Géométrie : **Point**.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `NumeroPoint` | ✓ | string | Numéro du point |
| `PrecisionXYnum` | ✓ | int | Précision XY numérique |
| `PrecisionZnum` | ✓ | int | Précision Z numérique |
| `Producteur` | ✓ | string | Producteur du levé |
| `ChargeGeneratrice` | — | float | Charge génératrice (uom: m) |
| `ChargeGeneratrice_uom` | — | string | Unité charge (défaut: m) |
| `Horodatage` | — | string | Date du levé (xs:date) |

---

## RPD_CoupeCircuitAFusibles_Reco

Coupe-circuit à fusibles (nœud réseau). Pas de géométrie propre.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Statut` | ✓ | string | Statut |
| `conteneur_href` | — | href | Référence conteneur |

---

## RPD_JeuBarres_Reco

Jeu de barres (nœud réseau). Pas de géométrie propre.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Statut` | ✓ | string | Statut |
| `conteneur_href` | — | href | Référence conteneur |

---

## RPD_SupportModules_Reco

Modules sur support (nœud réseau). Pas de géométrie propre.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Statut` | ✓ | string | Statut |
| `conteneur_href` | — | href | Référence conteneur |

---

## RPD_Terre_Reco

Prise de terre (nœud réseau). Pas de géométrie propre.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `NatureTerre_href` | ✓ | href | Nature de la terre |
| `Statut` | ✓ | string | Statut |
| `conteneur_href` | — | href | Référence conteneur |
| `Resistance` | — | float | Résistance (uom: Ohm) |
| `Resistance_uom` | — | string | Unité de résistance (défaut: Ohm) |

---

## RPD_OuvrageCollectifBranchement_Reco

Ouvrage collectif de branchement (nœud réseau). Géométrie : **Point** (seulement si pas de conteneur).

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Statut` | ✓ | string | Statut |
| `conteneur_href` | — | href | Référence conteneur |
| `PrecisionXY` | — | string | Classe de précision XY |
| `PrecisionZ` | — | string | Classe de précision Z |

---

## RPD_Materiel_Reco

Matériel associé à un ouvrage via relation Ouvrage_Materiel. Pas de géométrie.

| Champ | Req. | Type | Description |
| --- | :---: | --- | --- |
| `ogr_pkid` | ✓ | string | Identifiant unique |
| `Fabricant` | ✓ | string | Fabricant |
| `Modele` | ✓ | string | Modèle |
| `NumeroLot` | ✓ | string | Numéro de lot |
| `NumeroSerie` | ✓ | string | Numéro de série |

---

## Champs de relation

Ces champs sont générés automatiquement à partir des relations GML et utilisés pour le round-trip GeoJSON ↔ GML.

### `cables_href` / `EtatAvantRaccordement`

Présents sur les **cheminements** (Fourreau, PleineTerre, Aérien, ProtectionMécanique) et les **nœuds réseau** (Jonction, CoupeCircuitAFusibles, JeuBarres, SupportModules, Terre, OuvrageCollectifBranchement, PointDeComptage, PosteElectrique).

| Champ | Type | Description |
| --- | --- | --- |
| `cables_href` | string | IDs des câbles liés, séparés par virgules |
| `EtatAvantRaccordement` | string | État avant raccordement par câble, séparés par virgules |

### `materiel_href`

Présent uniquement sur **RPD_Jonction_Reco**.

| Champ | Type | Description |
| --- | --- | --- |
| `materiel_href` | href | Référence vers RPD_Materiel_Reco associé |

---

> **Nommage** : Tous les fichiers sont nommés `RPD_<Type>_Reco.geojson`.
