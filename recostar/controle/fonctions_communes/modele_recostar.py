"""
Vocabulaire du modele de donnees RecoStaR : noms de couches et de proprietes.

Ce module ne decrit aucun controle : il enonce des faits sur le **format**, que
les controles se contentent de lire. C'est a ce titre qu'il est commun — un nom
de couche ou de champ ne varie pas selon le controle qui l'interroge, et le
redeclarer dans chaque module revenait a maintenir la meme chaine a onze
endroits (`FICHIER_CABLE_ELECTRIQUE`) ou a vingt (`CHAMP_STATUT`).

Perimetre, pour eviter d'y verser des constantes qui n'y ont pas leur place :

- **Couches** : la liste est complete et fermee. Elle decrit le format, pas son
  usage ; la scinder selon le nombre de controles qui lisent chaque couche
  produirait un vocabulaire a trous, et la premiere couche ajoutee serait
  declaree ailleurs.
- **Proprietes** : seules celles que **plusieurs controles** interrogent. Un
  champ propre a un seul controle (les caracteristiques de poteau du catalogue
  de support, par
  exemple) reste declare chez lui : le remonter ici n'oterait aucune
  duplication et ajouterait une indirection.
- **Selections metier** : elles n'y sont pas. Les couches qu'un controle decide
  d'analyser relevent de sa regle, non du format : E-5108 et E-6103 designent
  tous deux des ensembles de cheminements differents, l'un avec l'aerien, l'autre
  sans. Chaque controle compose son ensemble a partir des constantes ci-dessous,
  ce qui rend cette divergence lisible au lieu de la
  cacher derriere un nom commun. Seul `FICHIERS_CHEMINEMENT_SOUTERRAIN` figure
  ici : il designe une categorie du modele, et trois controles de deux familles
  en portaient la meme definition sous trois noms.

Chaque couche est declaree par son nom sans extension (`COUCHE_*`), le nom de
fichier en etant derive : la famille conteneur manipule les couches par leur nom
seul, les autres par leur fichier, et les deux formes ne doivent pas diverger.

Module pur : aucune E/S, aucun import du reste du projet.
"""

# ---------------------------------------------------------------------------
# Couches du jeu de donnees
# ---------------------------------------------------------------------------

# Extension des couches livrees apres conversion du GML.
EXTENSION_COUCHE: str = ".geojson"

# --- Liaisons ---------------------------------------------------------------
COUCHE_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco"
COUCHE_CABLE_TELECOM: str = "RPD_CableTelecommunication_Reco"
COUCHE_CABLE_TERRE: str = "RPD_CableTerre_Reco"

FICHIER_CABLE_ELECTRIQUE: str = f"{COUCHE_CABLE_ELECTRIQUE}{EXTENSION_COUCHE}"
FICHIER_CABLE_TELECOM: str = f"{COUCHE_CABLE_TELECOM}{EXTENSION_COUCHE}"
FICHIER_CABLE_TERRE: str = f"{COUCHE_CABLE_TERRE}{EXTENSION_COUCHE}"

# --- Cheminements -----------------------------------------------------------
COUCHE_FOURREAU: str = "RPD_Fourreau_Reco"
COUCHE_GALERIE: str = "RPD_Galerie_Reco"
COUCHE_PLEINE_TERRE: str = "RPD_PleineTerre_Reco"
COUCHE_PROTECTION_MECANIQUE: str = "RPD_ProtectionMecanique_Reco"
COUCHE_AERIEN: str = "RPD_Aerien_Reco"

FICHIER_FOURREAU: str = f"{COUCHE_FOURREAU}{EXTENSION_COUCHE}"
FICHIER_GALERIE: str = f"{COUCHE_GALERIE}{EXTENSION_COUCHE}"
FICHIER_PLEINE_TERRE: str = f"{COUCHE_PLEINE_TERRE}{EXTENSION_COUCHE}"
FICHIER_PROTECTION_MECANIQUE: str = f"{COUCHE_PROTECTION_MECANIQUE}{EXTENSION_COUCHE}"
FICHIER_AERIEN: str = f"{COUCHE_AERIEN}{EXTENSION_COUCHE}"

# Les cinq voies par lesquelles un cable chemine. Categorie du modele : la
# conversion alimente le cache de geometries depuis ces cinq couches, et c'est
# de leur assemblage que le cable herite sa propre geometrie.
#
# La galerie n'etait declaree nulle part avant E-9401, bien que le XSD la
# connaisse et que le convertisseur la produise : aucun controle ne la voyait.
# Son perimetre a ete etendu a tous les controles de cheminement par arbitrage
# metier, a l'exception d'E-3109, dont la regle nomme deux couches precises.
#
# Elle partage la sequence XSD `_SEQ_ELEMENT_RESEAU` des quatre autres : memes
# champs, donc memes regles applicables.
COUCHES_CHEMINEMENT: tuple[str, ...] = (
    COUCHE_FOURREAU,
    COUCHE_GALERIE,
    COUCHE_PLEINE_TERRE,
    COUCHE_PROTECTION_MECANIQUE,
    COUCHE_AERIEN,
)

# Cheminements enterres, par opposition a l'aerien. Categorie du modele, et non
# selection d'un controle : E-3111, E-6205 et E-6103 en portaient la meme
# definition sous trois noms differents.
FICHIERS_CHEMINEMENT_SOUTERRAIN: tuple[str, ...] = (
    FICHIER_FOURREAU,
    FICHIER_GALERIE,
    FICHIER_PLEINE_TERRE,
    FICHIER_PROTECTION_MECANIQUE,
)

# Les cinq voies de cheminement, aerien compris. Pendant de COUCHES_CHEMINEMENT
# pour les controles qui raisonnent en noms de fichiers.
FICHIERS_CHEMINEMENT: tuple[str, ...] = FICHIERS_CHEMINEMENT_SOUTERRAIN + (FICHIER_AERIEN,)

# --- Noeuds et conteneurs ---------------------------------------------------
COUCHE_JONCTION: str = "RPD_Jonction_Reco"
COUCHE_COFFRET: str = "RPD_Coffret_Reco"
COUCHE_SUPPORT: str = "RPD_Support_Reco"
COUCHE_POSTE: str = "RPD_PosteElectrique_Reco"
COUCHE_BATIMENT: str = "RPD_BatimentTechnique_Reco"
COUCHE_ENCEINTE_CLOTUREE: str = "RPD_EnceinteCloturee_Reco"
COUCHE_TERRE: str = "RPD_Terre_Reco"

FICHIER_JONCTION: str = f"{COUCHE_JONCTION}{EXTENSION_COUCHE}"
FICHIER_COFFRET: str = f"{COUCHE_COFFRET}{EXTENSION_COUCHE}"
FICHIER_SUPPORT: str = f"{COUCHE_SUPPORT}{EXTENSION_COUCHE}"
FICHIER_POSTE: str = f"{COUCHE_POSTE}{EXTENSION_COUCHE}"
FICHIER_BATIMENT: str = f"{COUCHE_BATIMENT}{EXTENSION_COUCHE}"
FICHIER_TERRE: str = f"{COUCHE_TERRE}{EXTENSION_COUCHE}"

# --- Noeuds du reseau -------------------------------------------------------
# Types de noeuds raccordant les cables. Quatre controles de la famille conteneur
# en selectionnent chacun un sous-ensemble different : la chaine de localisation
# ecarte l'ouvrage collectif, les references noeud/cable incluent la jonction,
# E-6108 ecarte le poste. Ces selections
# relevent de leur regle ; les noms de couches, eux, sont ceux du format.
COUCHE_COUPE_CIRCUIT: str = "RPD_CoupeCircuitAFusibles_Reco"
COUCHE_JEU_BARRES: str = "RPD_JeuBarres_Reco"
COUCHE_MODULE_RACCORDEMENT: str = "RPD_ModuleRaccordement_Reco"
COUCHE_OUVRAGE_COLLECTIF: str = "RPD_OuvrageCollectifBranchement_Reco"
COUCHE_POINT_DE_COMPTAGE: str = "RPD_PointDeComptage_Reco"
COUCHE_SUPPORT_MODULES: str = "RPD_SupportModules_Reco"


# --- Elements rapportes -----------------------------------------------------
COUCHE_MATERIEL: str = "RPD_Materiel_Reco"
COUCHE_GEOM_SUPP: str = "RPD_GeometrieSupplementaire_Reco"
COUCHE_POINT_LEVE: str = "RPD_PointLeveOuvrageReseau_Reco"

FICHIER_MATERIEL: str = f"{COUCHE_MATERIEL}{EXTENSION_COUCHE}"
FICHIER_GEOM_SUPP: str = f"{COUCHE_GEOM_SUPP}{EXTENSION_COUCHE}"
FICHIER_POINT_LEVE: str = f"{COUCHE_POINT_LEVE}{EXTENSION_COUCHE}"


# ---------------------------------------------------------------------------
# Proprietes interrogees par plusieurs controles
# ---------------------------------------------------------------------------

# Etat de l'ouvrage : discrimine le perimetre controle dans vingt controles.
CHAMP_STATUT: str = "Statut"

# Domaine de tension (BT, HTA, HTB).
CHAMP_DOMAINE_TENSION: str = "DomaineTension"

# Type de jonction (Derivation, Jonction, ExtremiteReseau, RAS...).
CHAMP_TYPE_JONCTION: str = "TypeJonction"

# Type de leve : present en RecoStaR V1.0, absent en V1.1. Ce seul fait suffit a
# discriminer les deux versions d'un jeu (cf. fonctions_communes.version).
CHAMP_TYPE_LEVE: str = "TypeLeve"

# Valeur relevee sur le terrain par un point leve, et les deux types de leve qui
# la qualifient. Le triplet n'existe qu'en V1.0 : la V1.1 l'a remplace par le
# seul ChargeGeneratrice, et le leve d'altitude y a disparu. Les controles qui
# les lisent sont donc restreints a la V1.0.
CHAMP_LEVE: str = "Leve"
TYPE_LEVE_ALTITUDE: str = "AltitudeGeneratrice"
TYPE_LEVE_CHARGE: str = "ChargeGeneratrice"

# Etat de la coupe-type d'un cheminement souterrain (Fourreau, PleineTerre,
# ProtectionMecanique ; absent de l'aerien). Champ optionnel au XSD.
CHAMP_ETAT_COUPE_TYPE: str = "EtatCoupeType"

# --- Relations entre entites (suffixe _href du GML) -------------------------

# Cables raccordes a un noeud du reseau.
CHAMP_CABLES_HREF: str = "cables_href"

# Conteneur portant un noeud sans geometrie propre.
CHAMP_CONTENEUR_HREF: str = "conteneur_href"

# Geometrie supplementaire decrivant l'emprise d'un conteneur.
CHAMP_GEOMSUPP_HREF: str = "geometriesupplementaire_href"

# Materiel installe dans une jonction.
CHAMP_MATERIEL_HREF: str = "materiel_href"


# ---------------------------------------------------------------------------
# Valeurs du champ Statut
# ---------------------------------------------------------------------------

# Ouvrage en cours de mise en service : c'est le perimetre de la plupart des
# controles, un recolement ne portant que sur ce qui vient d'etre pose. La
# valeur etait recopiee dans seize modules sous quatre noms differents
# (STATUT_CONTROLE, VALEUR_STATUT_CONTROLE, VALEUR_STATUT_ELIGIBLE,
# VALEUR_STATUT_V1_1) : les noms disaient le role de la valeur dans chaque
# controle, la valeur elle-meme n'a lieu d'etre ecrite qu'une fois.
STATUT_MISE_EN_SERVICE: str = "UnderCommissionning"

# Ouvrage deja en service.
STATUT_FONCTIONNEL: str = "Functional"

# Statuts sous lesquels un ouvrage fait partie du reseau exploite. frozenset :
# appartenance en O(1), la verification etant faite par entite.
STATUTS_EN_SERVICE: frozenset[str] = frozenset({STATUT_MISE_EN_SERVICE, STATUT_FONCTIONNEL})

# Coupe-type provisoire : le trace est pose mais son contenu n'est pas arrete.
# Les deux valeurs de l'enumeration EtatCoupeTypeValueRecoType du XSD sont
# « Provisoire » et « Definitive ».
ETAT_COUPE_PROVISOIRE: str = "Provisoire"


# ---------------------------------------------------------------------------
# Differences entre versions du format
# ---------------------------------------------------------------------------

# Couches de cables presentes selon la version : la couche de telecommunication
# n'apparait qu'en V1.1. Fait du format, et non regle d'un controle — c'est la
# raison pour laquelle plusieurs controles doivent resoudre leurs couches
# sources depuis la version detectee du jeu.
FICHIERS_CABLES_PAR_VERSION: dict[str, tuple[str, ...]] = {
    "1.0": (FICHIER_CABLE_ELECTRIQUE, FICHIER_CABLE_TERRE),
    "1.1": (FICHIER_CABLE_ELECTRIQUE, FICHIER_CABLE_TERRE, FICHIER_CABLE_TELECOM),
}


# ---------------------------------------------------------------------------
# Valeurs du champ TypeJonction
# ---------------------------------------------------------------------------

# Types de jonction abritant du materiel (une boite). E-9600 y controle la
# conformite du materiel au catalogue, E-7102 son rattachement : les deux
# designent le meme sous-ensemble, qui releve du modele et non de l'un ou
# l'autre controle. frozenset : appartenance en O(1).
TYPES_JONCTION_AVEC_MATERIEL: frozenset[str] = frozenset({"Derivation", "Jonction"})

# Jonction de telecommunication : le seul noeud que le modele autorise a porter
# un cable de telecommunication. Valeur de l'enumeration TypeJonction du XSD
# (cf. xsd_structuration/regles_valeurs._ENUM_TYPE_JONCTION, PDF §10.4.1), tenue
# ici plutot que dans un controle : E-6116 l'exige et E-6113 l'interdit ailleurs,
# aucun des deux n'en est proprietaire.
TYPE_JONCTION_TELECOM: str = "Telecom"

# Coffret de telecommunication : valeur de l'enumeration TypeCoffret du XSD
# (cf. xsd_structuration/regles_valeurs._CL_TYPE_COFFRET, PDF §10.3.2). Le
# GeoJSON ne porte pas TypeCoffret mais une reference de code-list, resolue par
# `proprietes.valeur_code_liste`.
CHAMP_TYPE_COFFRET_HREF: str = "TypeCoffret_href"
TYPE_COFFRET_TELECOM: str = "Telecom"

# Couches de noeuds du reseau electrique admises dans un coffret. Categorie du
# modele : E-6108 signale les couches qui n'en font pas partie, E-6114 celles qui
# en font partie mais visent un coffret de telecommunication. Les deux lisent la
# meme liste, aucun n'en est proprietaire. Le nom de la couche est celui du
# fichier GeoJSON, convention de nommage RecoStaR `RPD_<Type>_Reco`.
# frozenset : appartenance en O(1).
COUCHES_NOEUDS_COFFRET: frozenset[str] = frozenset(
    {
        COUCHE_COUPE_CIRCUIT,
        COUCHE_JEU_BARRES,
        COUCHE_MODULE_RACCORDEMENT,
        COUCHE_OUVRAGE_COLLECTIF,
        COUCHE_POINT_DE_COMPTAGE,
        COUCHE_SUPPORT_MODULES,
        COUCHE_TERRE,
    }
)


# Couches dont une entite peut heriter sa position lorsqu'elle n'en porte pas.
# Categorie du modele : ce sont les couches dont le convertisseur alimente le
# cache de geometries, et les trois controles de chaine de localisation
# (E-6105, E-6204, E-6109) s'y referent tous.
COUCHES_CONTENEUR: tuple[str, ...] = (
    COUCHE_COFFRET,
    COUCHE_SUPPORT,
    COUCHE_BATIMENT,
    COUCHE_ENCEINTE_CLOTUREE,
)
