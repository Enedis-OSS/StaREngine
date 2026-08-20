"""
Controle E610 : nomenclature de composition des coffrets.

Verifie que les noeuds rattaches a une entite RPD_Coffret_Reco respectent la
nomenclature de son TypeCoffret : types de noeuds autorises, nombre minimal et
maximal de chacun, et obligations de presence.

Nomenclature (source : specification metier des coffrets) :

    TypeCoffret       Composition admise
    ---------------   --------------------------------------------------------
    RMBT300           1 ModuleRaccordement ; PointDeComptage et SupportModules
                      sans plafond ; au plus 1 Terre
    RMBT450           1 ModuleRaccordement ; PointDeComptage,
    RMBT600           OuvrageCollectifBranchement et SupportModules sans
                      plafond ; au plus 1 Terre
    CIBE              1 CoupeCircuitAFusibles ; au plus 1 JeuBarres ;
                      PointDeComptage sans plafond ; au plus 1 Terre
    CGV               au plus 1 CoupeCircuitAFusibles ; au plus 1
                      ModuleRaccordement ; au plus 1 Terre ; PointDeComptage
                      sans plafond
    ECP2D             1 CoupeCircuitAFusibles ; au plus 1 JeuBarres ; au plus 1
                      Terre ; PointDeComptage et OuvrageCollectifBranchement
                      sans plafond
    ECP3D             au plus 2 CoupeCircuitAFusibles ; au plus 1 JeuBarres ;
                      au plus 1 Terre ; PointDeComptage et
                      OuvrageCollectifBranchement sans plafond
    ArmoireComptage   au plus 1 CoupeCircuitAFusibles ; au plus 1 Terre ;
                      PointDeComptage sans plafond

Tout type de noeud absent de la nomenclature d'un TypeCoffret est interdit dans
un coffret de ce type.

Obligations de presence : seuls les « exactement 1 » en sont — le
ModuleRaccordement des RMBT, le CoupeCircuitAFusibles des CIBE et ECP2D. Les
autres types sont admis sans minimum : la nomenclature enonce ce qu'un coffret
**peut** contenir, non ce qu'il doit contenir.

Sens de la relation : c'est le **noeud** qui porte la reference, via son champ
conteneur_href, et le coffret qui la subit. Le controle parcourt donc les
noeuds pour qualifier les coffrets, comme E604 — dont il reutilise le parcours
des couches et la lecture de la reference.

Perimetre : entites RPD_Coffret_Reco au Statut UnderCommissionning ou
Functional, dont le TypeCoffret porte une nomenclature. Le dictionnaire
NOMENCLATURES tient lieu de filtre : un type absent n'est pas controle, meme
parti que REGLES_PAR_TYPE dans E608. Sont ainsi hors perimetre les types
Telecom et Autre de la code-list, ainsi qu'un TypeCoffret absent.

  La validite de la valeur elle-meme n'est pas l'affaire d'E610 : la regle
  C_TYPE_COFFRET de `xsd_structuration/regles_valeurs.py` (_CL_TYPE_COFFRET,
  source PDF §10.3.2) la controle deja, et fait foi pour le projet. E610 s'en
  tient a la nomenclature, comme E608 renvoie l'enumeration TypeJonction a ce
  meme controle de structuration.

Resolution du TypeCoffret (indispensable)
-----------------------------------------
Le GeoJSON ne porte pas de champ TypeCoffret : le convertisseur ecrit
`TypeCoffret_href`, reference vers une code-list. La valeur s'y presente sous
deux formes, le convertisseur restituant l'attribut brut :

  - le code seul               : « RMBT300 » ;
  - une reference fragmentee   : « ...#RMBT300 ».

Le code retenu est le fragment situe apres le dernier « # », regle deja
appliquee par `controle_e111._extraire_valeur` cote GML — dont E610 reprend la
resolution plutot que d'en definir une seconde.

Pourquoi toutes les couches du repertoire sont parcourues
--------------------------------------------------------
Un type de noeud non autorise est, par definition, un type absent de la
nomenclature. Restreindre l'analyse aux types qu'elle enumere rendrait donc le
controle incapable de detecter un noeud interdit. Toutes les couches GeoJSON du
repertoire sont parcourues (les fichiers d'ecarts en sont exclus par
`lister_fichiers_geojson`), et le nom du fichier fait foi pour le type du noeud
— convention de nommage RecoStaR `RPD_<Type>_Reco`, seule information de type
disponible, les features ne portant pas leur classe. Meme parti qu'E604 et E209.

Regles de gestion (une anomalie par couple coffret / type de noeud) :
  - nombre_noeuds_insuffisant : moins de noeuds de ce type que le minimum ;
  - nombre_noeuds_excessif    : plus que le maximum ;
  - noeud_type_non_autorise   : le type n'est pas prevu par la nomenclature.

L'anomalie porte sur le **couple**, et non sur chaque noeud : c'est le compte
qui est fautif, non un lien en particulier — designer un noeud parmi cinq
lorsque quatre sont admis serait arbitraire. Chaque anomalie expose donc le
nombre attendu et le nombre trouve, seuls termes qui expliquent l'ecart. Un
coffret enfreignant deux regles porte deux anomalies.

  Recouvrement assume avec E604 : ce dernier verifie qu'un coffret n'est
  reference que par les sept types de noeuds globalement admis, sans egard au
  TypeCoffret ; E610 verifie la nomenclature propre a chaque type. Un
  RPD_Jonction_Reco rattache a un coffret est signale par les deux, un
  RPD_JeuBarres_Reco dans un RMBT300 par E610 seul. Les deux regles sont
  distinctes, leurs priorites egalement (mineur / majeur).

Geometrie des ecarts : le Point du coffret, entite controlee et porteuse de la
composition fautive. E604 retenait celle du noeud, qui portait la reference et
donc le defaut ; ici le defaut est celui du coffret.

Versions : coffret et noeuds ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Priorite : majeur.

Usage CLI :
    python controle_e610.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e610_coffret_nomenclature.geojson
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controle_e600 import _charger_features
from controle_e604 import _reference_coffret, parcourir_couches
from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source des entites controlees
FICHIER_COFFRET: str = "RPD_Coffret_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e610_coffret_nomenclature.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E610"

# Types d'anomalie produits par ce controle
TYPE_NOEUDS_INSUFFISANTS: str = "nombre_noeuds_insuffisant"
TYPE_NOEUDS_EXCESSIFS: str = "nombre_noeuds_excessif"
TYPE_NOEUD_NON_AUTORISE: str = "noeud_type_non_autorise"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_NOEUDS_INSUFFISANTS: ("Le coffret contient moins de nœuds de ce type que sa nomenclature n'en impose."),
    TYPE_NOEUDS_EXCESSIFS: ("Le coffret contient plus de nœuds de ce type que sa nomenclature n'en admet."),
    TYPE_NOEUD_NON_AUTORISE: (
        "Le type de nœud rattaché au coffret n'est pas prévu par la nomenclature de son TypeCoffret."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_coffret",),
)

# Niveau de priorite affecte a toutes les anomalies. Majeur : l'ecart est
# signale et compte dans le rapport, mais ne declasse pas la famille
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "majeur"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_TYPE_COFFRET_HREF: str = "TypeCoffret_href"

# Statuts des coffrets a controler (frozenset -> appartenance en O(1))
STATUTS_CONTROLES: frozenset[str] = frozenset({"UnderCommissionning", "Functional"})

# Separateur du fragment d'une reference de code-list (« ...#RMBT300 »)
SEPARATEUR_FRAGMENT: str = "#"


@dataclass(frozen=True, slots=True)
class RegleNoeud:
    """Nombre de noeuds d'un type admis dans un coffret.

    `maximum` a None signifie « sans plafond » ; `minimum` a 0 « sans exigence
    de presence ». Un type absent de la nomenclature vaut interdiction, et n'a
    donc pas besoin d'y figurer avec un maximum nul.
    """

    minimum: int
    maximum: int | None


# Couches de noeuds citees par les nomenclatures, nommees une fois pour que le
# tableau reste lisible et qu'une faute de frappe ne cree pas un type fantome.
COUPE_CIRCUIT: str = "RPD_CoupeCircuitAFusibles_Reco"
JEU_BARRES: str = "RPD_JeuBarres_Reco"
MODULE_RACCORDEMENT: str = "RPD_ModuleRaccordement_Reco"
OUVRAGE_COLLECTIF: str = "RPD_OuvrageCollectifBranchement_Reco"
POINT_DE_COMPTAGE: str = "RPD_PointDeComptage_Reco"
SUPPORT_MODULES: str = "RPD_SupportModules_Reco"
TERRE: str = "RPD_Terre_Reco"

# Regles reutilisees telles quelles par plusieurs nomenclatures. Les instances
# etant immuables, les partager evite d'en recreer une par entree.
EXACTEMENT_UN: RegleNoeud = RegleNoeud(1, 1)
AU_PLUS_UN: RegleNoeud = RegleNoeud(0, 1)
AU_PLUS_DEUX: RegleNoeud = RegleNoeud(0, 2)
SANS_PLAFOND: RegleNoeud = RegleNoeud(0, None)

# Composition admise par TypeCoffret. Le dictionnaire tient lieu de filtre de
# perimetre : un type absent n'est pas controle. L'ordre de declaration fixe
# celui des anomalies, qui reste ainsi deterministe.
#
# Les codes sont ceux de la code-list _CL_TYPE_COFFRET
# (xsd_structuration/regles_valeurs.py, source PDF §10.3.2), qui fait foi :
# « ArmoireComptage » s'y ecrit sans espace.
NOMENCLATURES: dict[str, dict[str, RegleNoeud]] = {
    "RMBT300": {
        MODULE_RACCORDEMENT: EXACTEMENT_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        SUPPORT_MODULES: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
    "RMBT450": {
        MODULE_RACCORDEMENT: EXACTEMENT_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        OUVRAGE_COLLECTIF: SANS_PLAFOND,
        SUPPORT_MODULES: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
    "RMBT600": {
        MODULE_RACCORDEMENT: EXACTEMENT_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        OUVRAGE_COLLECTIF: SANS_PLAFOND,
        SUPPORT_MODULES: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
    "CIBE": {
        COUPE_CIRCUIT: EXACTEMENT_UN,
        JEU_BARRES: AU_PLUS_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
    "CGV": {
        COUPE_CIRCUIT: AU_PLUS_UN,
        MODULE_RACCORDEMENT: AU_PLUS_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
    "ECP2D": {
        COUPE_CIRCUIT: EXACTEMENT_UN,
        JEU_BARRES: AU_PLUS_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        OUVRAGE_COLLECTIF: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
    "ECP3D": {
        COUPE_CIRCUIT: AU_PLUS_DEUX,
        JEU_BARRES: AU_PLUS_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        OUVRAGE_COLLECTIF: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
    "ArmoireComptage": {
        COUPE_CIRCUIT: AU_PLUS_UN,
        POINT_DE_COMPTAGE: SANS_PLAFOND,
        TERRE: AU_PLUS_UN,
    },
}


@dataclass(frozen=True, slots=True)
class Coffret:
    """Coffret du perimetre, avec son type resolu et sa geometrie."""

    type_coffret: str
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Resolution du TypeCoffret
# ---------------------------------------------------------------------------


def resoudre_type_coffret(proprietes: Mapping[str, Any]) -> str | None:
    """Resout le code de TypeCoffret porte par TypeCoffret_href.

    Le GeoJSON ne porte pas de champ TypeCoffret : le convertisseur ecrit une
    reference vers une code-list, restituee brute. La valeur se presente donc
    soit comme le code seul (« RMBT300 »), soit comme une reference fragmentee
    (« ...#RMBT300 ») ; le code est le fragment situe apres le dernier « # ».

    Meme resolution que `controle_e111._extraire_valeur` cote GML.
    """
    valeur = proprietes.get(CHAMP_TYPE_COFFRET_HREF)
    if valeur is None:
        return None
    code = str(valeur).rsplit(SEPARATEUR_FRAGMENT, 1)[-1].strip()
    return code or None


def nomenclature_applicable(proprietes: Mapping[str, Any]) -> dict[str, RegleNoeud] | None:
    """Retourne la nomenclature applicable au coffret, ou None hors perimetre.

    Filtre et nomenclature en une seule resolution : un coffret est controle si
    son Statut est UnderCommissionning ou Functional et si son TypeCoffret porte
    une nomenclature. Meme parti que `regle_applicable` dans E608.
    """
    if proprietes.get(CHAMP_STATUT) not in STATUTS_CONTROLES:
        return None
    type_coffret = resoudre_type_coffret(proprietes)
    if type_coffret is None:
        return None
    return NOMENCLATURES.get(type_coffret)


# ---------------------------------------------------------------------------
# Chargement des index
# ---------------------------------------------------------------------------


def charger_coffrets_a_controler(
    repertoire: str,
) -> tuple[dict[str, Coffret], dict[str, Any] | None, bool]:
    """Charge l'index {id_coffret: Coffret} des coffrets du perimetre.

    Retourne (index, crs, fichier_absent). Le dictionnaire sert a la fois de
    filtre de perimetre (appartenance en O(1) lors du comptage des noeuds) et
    d'acces au type et a la geometrie. Meme parti que l'index d'E604.
    """
    features, crs, absent = _charger_features(repertoire, FICHIER_COFFRET)
    index: dict[str, Coffret] = {}
    for feature in features:
        proprietes = feature.get("properties") or {}
        if nomenclature_applicable(proprietes) is None:
            continue
        id_coffret = obtenir_id_feature(feature)
        if id_coffret is None:
            continue
        type_coffret = resoudre_type_coffret(proprietes)
        if type_coffret is not None:
            index[id_coffret] = Coffret(type_coffret, feature.get("geometry"))
    return index, crs, absent


def compter_noeuds_par_coffret(
    repertoire: str,
    coffrets: Mapping[str, Coffret],
) -> tuple[dict[str, Counter[str]], int, int]:
    """Compte les noeuds rattaches a chaque coffret, par couche.

    Retourne (comptes, nombre_couches, nombre_liens). Toutes les couches du
    repertoire sont parcourues : un type de noeud non autorise est par
    definition absent de la nomenclature, restreindre le parcours aux types
    qu'elle enumere rendrait le controle aveugle a ce cas.

    Seules les references visant un coffret du perimetre sont retenues : les
    autres conteneur_href designent un support ou un batiment technique et ne
    relevent pas de cette regle.
    """
    comptes: dict[str, Counter[str]] = defaultdict(Counter)
    nombre_couches = 0
    nombre_liens = 0
    reference_de = _reference_coffret  # alias local (boucle)
    for couche, features in parcourir_couches(repertoire):
        nombre_couches += 1
        for feature in features:
            reference = reference_de(feature.get("properties") or {})
            if reference is None or reference not in coffrets:
                continue
            comptes[reference][couche] += 1
            nombre_liens += 1
    return comptes, nombre_couches, nombre_liens


# ---------------------------------------------------------------------------
# Regle metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def _formuler_attendu(minimum: int, maximum: int | None) -> str:
    """Formule l'attendu d'une regle en une locution lisible.

    « exactement 1 », « au maximum 2 », « au minimum 1 » : la formulation suit
    la regle plutot que d'exposer un intervalle, afin que le message d'ecart se
    lise comme la nomenclature dont il constate l'infraction.
    """
    if minimum == maximum:
        return f"exactement {minimum}"
    if maximum is None:
        return f"au minimum {minimum}"
    if minimum == 0:
        return f"au maximum {maximum}"
    return f"entre {minimum} et {maximum}"


def formuler_detail(
    id_coffret: str,
    type_coffret: str,
    couche_noeud: str,
    trouve: int,
    minimum: int,
    maximum: int | None,
    autorise: bool = True,
) -> str:
    """Redige le constat explicite d'une anomalie de nomenclature.

    Le socle commun impose une `description` par type d'anomalie, identique pour
    toutes les features qui le portent : elle ne peut donc pas nommer le coffret
    ni ses comptes. Ce detail les restitue, sans se substituer aux champs
    structures — qui restent la source exploitable en filtre.
    """
    if not autorise:
        return (
            f"Coffret {id_coffret} de type {type_coffret} : "
            f"{couche_noeud} n'est pas autorisé par la nomenclature "
            f"(attendu 0, trouvé {trouve})."
        )
    return (
        f"Coffret {id_coffret} de type {type_coffret} : "
        f"{couche_noeud} attendu {_formuler_attendu(minimum, maximum)}, trouvé {trouve}."
    )


def classifier_composition(
    nomenclature: Mapping[str, RegleNoeud],
    comptes: Mapping[str, int],
) -> list[tuple[str, str, int, int, int | None]]:
    """Confronte la composition d'un coffret a sa nomenclature.

    Retourne une liste de (type_anomalie, couche_noeud, trouve, minimum,
    maximum). Les regles de la nomenclature sont evaluees dans leur ordre de
    declaration, puis les types non prevus dans l'ordre alphabetique : l'ordre
    des anomalies est ainsi deterministe.

    Le compte et l'interdiction sont deux constats independants — un coffret
    peut etre au bon nombre sur les types prevus tout en hebergeant un type
    interdit — leurs anomalies cumulent donc.
    """
    anomalies: list[tuple[str, str, int, int, int | None]] = []
    for couche, regle in nomenclature.items():
        trouve = comptes.get(couche, 0)
        if trouve < regle.minimum:
            anomalies.append((TYPE_NOEUDS_INSUFFISANTS, couche, trouve, regle.minimum, regle.maximum))
        elif regle.maximum is not None and trouve > regle.maximum:
            anomalies.append((TYPE_NOEUDS_EXCESSIFS, couche, trouve, regle.minimum, regle.maximum))
    anomalies.extend(
        (TYPE_NOEUD_NON_AUTORISE, couche, trouve, 0, 0)
        for couche, trouve in sorted(comptes.items())
        if couche not in nomenclature
    )
    return anomalies


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(
    coffrets: Mapping[str, Coffret],
    comptes_par_coffret: Mapping[str, Mapping[str, int]],
) -> list[dict[str, Any]]:
    """Detecte les coffrets dont la composition enfreint leur nomenclature.

    Les coffrets sont parcourus dans l'ordre de l'index — celui du fichier
    source — et non dans celui des comptes : un coffret sans aucun noeud
    rattache doit etre evalue lui aussi, ses obligations de presence n'etant
    alors satisfaites par rien.
    """
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_composition  # alias local (boucle)
    aucun_compte: dict[str, int] = {}
    for id_coffret, coffret in coffrets.items():
        nomenclature = NOMENCLATURES[coffret.type_coffret]
        comptes = comptes_par_coffret.get(id_coffret, aucun_compte)
        anomalies.extend(
            {
                "type_anomalie": type_anomalie,
                "id_coffret": id_coffret,
                "type_coffret": coffret.type_coffret,
                "couche_noeud": couche,
                "nombre_trouve": trouve,
                "nombre_minimum": minimum,
                "nombre_maximum": maximum,
                "detail": formuler_detail(
                    id_coffret,
                    coffret.type_coffret,
                    couche,
                    trouve,
                    minimum,
                    maximum,
                    autorise=type_anomalie != TYPE_NOEUD_NON_AUTORISE,
                ),
                "geometrie": coffret.geometrie,
            }
            for type_anomalie, couche, trouve, minimum, maximum in classifier(nomenclature, comptes)
        )
    return anomalies


def compter_coffrets_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les coffrets distincts portant au moins une anomalie."""
    return len({anomalie["id_coffret"] for anomalie in anomalies})


def compter_par_type_coffret(coffrets: Mapping[str, Coffret]) -> dict[str, int]:
    """Ventile les coffrets controles par TypeCoffret, pour le rapport JSON."""
    comptes: defaultdict[str, int] = defaultdict(int)
    for coffret in coffrets.values():
        comptes[coffret.type_coffret] += 1
    return dict(comptes)


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des compositions de coffret non conformes.

    Le nombre attendu et le nombre trouve sont exposes cote a cote : c'est leur
    confrontation qui explique l'ecart. `detail` en donne la lecture redigee, le
    socle commun imposant une `description` identique pour toutes les features
    d'un meme type d'anomalie.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_COFFRET,
                "id_coffret": a["id_coffret"],
                "type_coffret": a["type_coffret"],
                "couche_noeud": a["couche_noeud"],
                "nombre_trouve": a["nombre_trouve"],
                "nombre_minimum": a["nombre_minimum"],
                "nombre_maximum": a["nombre_maximum"],
                "detail": a["detail"],
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de nomenclature des coffrets en mode CLI.

    Indexe les coffrets du perimetre, compte les noeuds qui les referencent en
    un seul parcours du repertoire, puis confronte chaque composition a sa
    nomenclature. L'absence du fichier coffret est signalee sans bloquer : sans
    coffret controle, le controle est sans objet.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    coffrets, crs, coffret_absent = charger_coffrets_a_controler(repertoire_resolu)
    comptes, nombre_couches, nombre_liens = compter_noeuds_par_coffret(repertoire_resolu, coffrets)

    anomalies = detecter_anomalies(coffrets, comptes)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_coffrets_controles": len(coffrets),
        "nombre_coffrets_non_conformes": compter_coffrets_non_conformes(anomalies),
        "coffrets_par_type": compter_par_type_coffret(coffrets),
        "nombre_couches_analysees": nombre_couches,
        "nombre_noeuds_rattaches": nombre_liens,
        "fichier_coffret_absent": coffret_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de nomenclature des coffrets."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E610 : les noeuds rattaches a une RPD_Coffret_Reco au "
            "statut UnderCommissionning ou Functional doivent respecter la "
            "nomenclature de son TypeCoffret — types autorises, nombres "
            "minimal et maximal."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
