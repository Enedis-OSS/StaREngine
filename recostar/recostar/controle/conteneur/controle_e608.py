"""
Controle E608 : coherence entre type de jonction et nombre de cables raccordes.

Verifie qu'une entite RPD_Jonction_Reco est raccordee au nombre de cables
qu'impose son type :

    Derivation       : au moins 3 cables ;
    Jonction         : au moins 2 cables ;
    ExtremiteReseau  : exactement 1 cable.

    Telecom          : au moins un cable de telecommunication raccorde.

Perimetre : entites RPD_Jonction_Reco au Statut UnderCommissionning et dont le
TypeJonction figure parmi ces quatre valeurs. Les autres types — la remontee
aero-souterraine notamment — sont ignores.

Regle propre au type Telecom : une telle jonction doit declarer, dans son champ
cables_href, au moins une reference resolvant une entite
RPD_CableTelecommunication_Reco. Aucun nombre minimal de cables ne lui est
impose par ailleurs : la contrainte porte sur la **nature** d'au moins un cable
rattache, non sur leur compte.

  Source de l'enumeration : les valeurs admises de TypeJonction sont declarees
  par `xsd_structuration/regles_valeurs.py` (_ENUM_TYPE_JONCTION, regle
  E_TYPE_JONCTION, source PDF §10.4.1), qui fait foi pour le projet. « Telecom »
  y figure, aux cotes de Derivation, ExtremiteReseau, Jonction,
  RemonteeAeroSouterraine et EpanouissementHTA. Le XSD V1.1 l'enumere egalement ;
  celui de la V1.0 ne le fait pas, un TypeJonction Telecom sur un jeu V1.0 etant
  alors signale par le controle de structuration, non par E608 — qui reste
  agnostique de version et applique sa regle des que la valeur est presente.

Un raccordement confirme sur les deux plans
-------------------------------------------
Un cable n'est compte comme raccorde que si le raccordement est etabli **des
deux cotes** :

  - **attributaire** : l'identifiant du cable figure dans le champ cables_href
    de la jonction, et resout un cable existant ;
  - **geographique** : le point de la jonction coincide avec l'une des
    extremites topologiques du cable.

Compter les seules references de cables_href reviendrait a faire confiance a une
declaration sans la verifier ; compter les seules coincidences geometriques
reviendrait a inventer un lien que la donnee ne declare pas. Le nombre retenu
est donc celui de l'intersection.

Les deux ensembles sont par ailleurs compares : leur divergence est signalee
pour elle-meme (`raccordement_incoherent`), independamment du compte. Une
jonction peut ainsi etre au bon nombre de raccordements tout en declarant une
reference sans realite geometrique.

Geometrie des extremites : la decomposition reutilise `extraire_extremites`
(module commun), qui identifie les extremites **topologiques** d'une geometrie
lineaire. Les parties d'un MultiLineString RecoStaR n'etant ni ordonnees ni
orientees, prendre le premier et le dernier sommet apres mise a plat donnerait
des extremites fausses.

Tolerance de coincidence : la comparaison est planimetrique et admet un ecart
de 1 mm — `TOLERANCE_SUPERPOSITION` du module commun, deja partagee par E205,
E208 et E209. Le contact d'un noeud et d'une extremite est de mesure nulle : les
coordonnees RecoStaR etant arrondies au millimetre des le GML source, une
egalite exacte se heurte a l'arrondi. La valeur reste tres en deca de toute
precision de leve — un cable reellement ecarte, meme au centimetre, demeure
detecte. Le Z est ecarte, l'ecart altimetrique relevant des controles E200 a
E209.

Cables dont les extremites sont indeterminables : une geometrie fermee, ou dont
les parties se neutralisent deux a deux, ne livre aucune extremite. Un tel cable
ne peut pas etre confirme geographiquement : il n'est donc pas compte comme
raccorde, et leur nombre est reporte a l'anomalie (`cables_sans_extremite`) afin
que la cause reelle — la geometrie du cable, non le compte de la jonction —
reste lisible. E507 isole ces memes cables sous `nombre_cables_geometrie_non_exploitable`.

Couches de cable analysees : RPD_CableElectrique_Reco, RPD_CableTerre_Reco et
RPD_CableTelecommunication_Reco. Une reference ne resolvant aucune de ces
couches n'est pas un raccordement attributaire valide ; son integrite relevant
du controle E401, elle n'est ici que comptee.

Versions : jonction et cables ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Priorite : majeur.

Usage CLI :
    python controle_e608.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e608_jonction_nombre_cables.geojson
"""

import argparse
import json
import math
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controle_e600 import _charger_features
from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from utils_geometrie import TOLERANCE_SUPERPOSITION, extraire_extremites

# Fichier source des entites controlees
FICHIER_JONCTION: str = "RPD_Jonction_Reco.geojson"

# Couches de cable dont une reference cables_href peut designer une entite
COUCHES_CABLE: tuple[str, ...] = (
    "RPD_CableElectrique_Reco",
    "RPD_CableTerre_Reco",
    "RPD_CableTelecommunication_Reco",
)

# Couche de telecommunication, seule admise par la regle du type Telecom
COUCHE_CABLE_TELECOM: str = "RPD_CableTelecommunication_Reco"

# Extension des fichiers de couche
EXTENSION: str = ".geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e608_jonction_nombre_cables.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E608"

# Types d'anomalie produits par ce controle
TYPE_CABLES_INSUFFISANTS: str = "nombre_cables_insuffisant"
TYPE_CABLES_EXCESSIFS: str = "nombre_cables_excessif"
TYPE_RACCORDEMENT_INCOHERENT: str = "raccordement_incoherent"
TYPE_CABLE_TELECOM_ABSENT: str = "cable_telecommunication_absent"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_CABLES_INSUFFISANTS: ("Le nombre de câbles raccordés est inférieur au minimum requis par le TypeJonction."),
    TYPE_CABLES_EXCESSIFS: ("Le nombre de câbles raccordés dépasse le maximum admis par le TypeJonction."),
    TYPE_RACCORDEMENT_INCOHERENT: (
        "Les raccordements déclarés par cables_href et les raccordements géographiques divergent."
    ),
    TYPE_CABLE_TELECOM_ABSENT: ("La jonction Telecom ne référence aucun câble de télécommunication dans cables_href."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction",),
)

# Niveau de priorite affecte a toutes les anomalies. Majeur : l'ecart est
# signale et compte dans le rapport, mais ne declasse pas la famille
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "majeur"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_TYPE_JONCTION: str = "TypeJonction"
CHAMP_CABLES_HREF: str = "cables_href"

# Statut des jonctions a controler
STATUT_CONTROLE: str = "UnderCommissionning"


@dataclass(frozen=True, slots=True)
class RegleJonction:
    """Attendu de raccordement pour un type de jonction.

    - `minimum` / `maximum` : nombre de cables raccordes ; `maximum` a None
      signifie « sans plafond », `minimum` a 0 « sans exigence de compte » ;
    - `cable_telecom_requis` : au moins un cable de telecommunication doit
      figurer dans cables_href. Contrainte de **nature**, independante du compte.
    """

    minimum: int
    maximum: int | None
    cable_telecom_requis: bool = False


# Regles par type de jonction. Le dictionnaire tient lieu de filtre de
# perimetre : un type absent n'est pas controle.
REGLES_PAR_TYPE: dict[str, RegleJonction] = {
    "Derivation": RegleJonction(3, None),
    "Jonction": RegleJonction(2, None),
    "ExtremiteReseau": RegleJonction(1, 1),
    # Aucun compte impose : seule la nature d'un cable rattache est exigee.
    "Telecom": RegleJonction(0, None, cable_telecom_requis=True),
}


@dataclass(frozen=True, slots=True)
class BilanRaccordement:
    """Confrontation des raccordements attributaires et geographiques.

    - `references` : cables designes par cables_href et resolus dans une couche
      de cable ;
    - `geographiques` : cables dont une extremite coincide avec la jonction ;
    - `raccordes` : intersection des deux, seuls raccordements confirmes ;
    - `references_non_resolues` : references ne designant aucun cable connu ;
    - `sans_extremite` : references dont les extremites sont indeterminables,
      donc non confirmables geographiquement ;
    - `references_telecom` : references resolvant un cable de telecommunication.
    """

    references: frozenset[str]
    geographiques: frozenset[str]
    raccordes: frozenset[str]
    references_non_resolues: frozenset[str]
    sans_extremite: frozenset[str]
    references_telecom: frozenset[str]

    @property
    def references_sans_coincidence(self) -> frozenset[str]:
        """Cables declares par cables_href mais non confirmes geographiquement."""
        return self.references - self.geographiques

    @property
    def coincidences_non_declarees(self) -> frozenset[str]:
        """Cables coincidant avec la jonction mais absents de cables_href."""
        return self.geographiques - self.references

    @property
    def est_coherent(self) -> bool:
        """Indique si les deux sources de raccordement concordent."""
        return not self.references_sans_coincidence and not self.coincidences_non_declarees


# ---------------------------------------------------------------------------
# Chargement des index
# ---------------------------------------------------------------------------


def indexer_extremites_cables(
    repertoire: str,
) -> tuple[dict[str, frozenset[tuple[float, float]]], frozenset[str], list[str]]:
    """Indexe {id_cable: extremites planimetriques} des trois couches de cable.

    Retourne (index, identifiants_telecom, couches_absentes). Les extremites sont
    decomposees une seule fois par cable : elles sont ensuite interrogees par
    toutes les jonctions, en O(1) par test d'appartenance.

    Les identifiants de la couche de telecommunication sont isoles dans la meme
    passe : la regle du type Telecom porte sur la nature du cable, que l'index
    des extremites ne conserve pas.

    Un cable dont les extremites sont indeterminables est conserve avec un
    ensemble vide : il reste une reference resolvable, mais aucune coincidence
    ne pourra l'etablir.
    """
    index: dict[str, frozenset[tuple[float, float]]] = {}
    telecom: set[str] = set()
    absentes: list[str] = []
    for couche in COUCHES_CABLE:
        features, _, absente = _charger_features(repertoire, f"{couche}{EXTENSION}")
        if absente:
            absentes.append(couche)
            continue
        for feature in features:
            identifiant = obtenir_id_feature(feature)
            if identifiant is None:
                continue
            index[identifiant] = frozenset(extraire_extremites(feature.get("geometry")))
            if couche == COUCHE_CABLE_TELECOM:
                telecom.add(identifiant)
    return index, frozenset(telecom), absentes


def extraire_references(proprietes: Mapping[str, Any]) -> frozenset[str]:
    """Extrait les identifiants de cable declares par cables_href.

    Le champ liste les identifiants separes par des virgules ; les espaces sont
    egalement acceptes, la convention variant selon les couches (meme
    permissivite que `utils_cable.extraire_ids_cables_href` du domaine cable).
    """
    valeur = proprietes.get(CHAMP_CABLES_HREF)
    if valeur is None:
        return frozenset()
    return frozenset(reference for reference in str(valeur).replace(",", " ").split() if reference)


def coincide(point: tuple[float, float], extremites: frozenset[tuple[float, float]]) -> bool:
    """Indique si le point coincide avec l'une des extremites, a la tolerance pres.

    Le contact d'un noeud et d'une extremite est de mesure nulle : une egalite
    exacte se heurterait a l'arrondi millimetrique des coordonnees RecoStaR.
    L'ecart admis est `TOLERANCE_SUPERPOSITION` (1 mm), la meme valeur que celle
    retenue par E205, E208 et E209 pour les memes raisons.

    Un cable sans extremite exploitable ne coincide avec rien : le court-circuit
    evite d'entrer dans la boucle pour rien.
    """
    if not extremites:
        return False
    distance = math.dist  # alias local (boucle critique)
    return any(distance(point, extremite) <= TOLERANCE_SUPERPOSITION for extremite in extremites)


def extraire_point(geometrie: dict[str, Any] | None) -> tuple[float, float] | None:
    """Retourne les coordonnees XY d'une geometrie Point, sinon None.

    Le Z est ecarte : la coincidence d'un noeud et d'une extremite est
    planimetrique, l'ecart altimetrique relevant des controles E200 a E209.
    Meme convention qu'E506 et E507.
    """
    if not geometrie or geometrie.get("type") != "Point":
        return None
    coordonnees = geometrie.get("coordinates")
    if not coordonnees or len(coordonnees) < 2:
        return None
    return (coordonnees[0], coordonnees[1])


# ---------------------------------------------------------------------------
# Regles metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def regle_applicable(proprietes: Mapping[str, Any]) -> RegleJonction | None:
    """Retourne la regle applicable a la jonction, ou None hors perimetre.

    Filtre et regle en une seule resolution : une jonction est controlee si son
    Statut est UnderCommissionning et si son TypeJonction porte une regle.
    """
    if proprietes.get(CHAMP_STATUT) != STATUT_CONTROLE:
        return None
    type_jonction = proprietes.get(CHAMP_TYPE_JONCTION)
    if not isinstance(type_jonction, str):
        return None
    return REGLES_PAR_TYPE.get(type_jonction)


def construire_bilan(
    point: tuple[float, float] | None,
    references: frozenset[str],
    extremites_cables: Mapping[str, frozenset[tuple[float, float]]],
    cables_telecom: frozenset[str] = frozenset(),
) -> BilanRaccordement:
    """Confronte les raccordements declares et les coincidences geometriques.

    Le parcours geographique est restreint aux cables **declares** : un cable
    coincidant sans etre declare ne peut de toute facon pas compter comme
    raccorde, et balayer l'ensemble des cables du jeu pour chaque jonction
    serait quadratique. Les coincidences non declarees sont neanmoins
    recherchees par `detecter_coincidences_non_declarees`, sur demande du
    diagnostic d'incoherence.
    """
    resolues = frozenset(reference for reference in references if reference in extremites_cables)
    sans_extremite = frozenset(reference for reference in resolues if not extremites_cables[reference])
    if point is None:
        geographiques: frozenset[str] = frozenset()
    else:
        geographiques = frozenset(reference for reference in resolues if coincide(point, extremites_cables[reference]))
    return BilanRaccordement(
        references=resolues,
        geographiques=geographiques,
        raccordes=resolues & geographiques,
        references_non_resolues=references - resolues,
        sans_extremite=sans_extremite,
        references_telecom=resolues & cables_telecom,
    )


def classifier_bilan(regle: RegleJonction, bilan: BilanRaccordement) -> list[str]:
    """Retourne les codes d'anomalie d'une jonction au regard de sa regle.

    Le compte, la nature des cables et la coherence sont trois constats
    independants : une jonction peut etre au bon nombre de raccordements tout en
    declarant une reference sans realite geometrique. Leurs anomalies cumulent
    donc.

    L'exigence de cable de telecommunication porte sur les seules **references**
    declarees, comme l'enonce la regle : sa confirmation geometrique releve du
    constat de coherence, evalue par ailleurs.
    """
    anomalies: list[str] = []
    nombre = len(bilan.raccordes)
    if nombre < regle.minimum:
        anomalies.append(TYPE_CABLES_INSUFFISANTS)
    elif regle.maximum is not None and nombre > regle.maximum:
        anomalies.append(TYPE_CABLES_EXCESSIFS)
    if regle.cable_telecom_requis and not bilan.references_telecom:
        anomalies.append(TYPE_CABLE_TELECOM_ABSENT)
    if not bilan.est_coherent:
        anomalies.append(TYPE_RACCORDEMENT_INCOHERENT)
    return anomalies


def detecter_coincidences_non_declarees(
    point: tuple[float, float] | None,
    references: frozenset[str],
    extremites_cables: Mapping[str, frozenset[tuple[float, float]]],
) -> frozenset[str]:
    """Retourne les cables coincidant avec la jonction sans etre declares.

    Balayage complet de l'index, reserve aux jonctions deja identifiees comme
    suspectes : le realiser pour chaque jonction serait quadratique et sans
    objet, un cable non declare ne pouvant jamais compter comme raccorde.
    """
    if point is None:
        return frozenset()
    return frozenset(
        identifiant
        for identifiant, extremites in extremites_cables.items()
        if identifiant not in references and coincide(point, extremites)
    )


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _anomalie(
    type_anomalie: str,
    feature: dict[str, Any],
    proprietes: Mapping[str, Any],
    regle: RegleJonction,
    bilan: BilanRaccordement,
    non_declares: frozenset[str],
) -> dict[str, Any]:
    """Assemble une anomalie ; tous les comptes du bilan sont conserves."""
    return {
        "type_anomalie": type_anomalie,
        "id_jonction": obtenir_id_feature(feature),
        "type_jonction": proprietes.get(CHAMP_TYPE_JONCTION),
        "nombre_minimum": regle.minimum,
        "nombre_maximum": regle.maximum,
        "nombre_cables_raccordes": len(bilan.raccordes),
        "nombre_references": len(bilan.references),
        "nombre_geographiques": len(bilan.geographiques) + len(non_declares),
        "nombre_references_sans_coincidence": len(bilan.references_sans_coincidence),
        "nombre_coincidences_non_declarees": len(non_declares),
        "nombre_references_non_resolues": len(bilan.references_non_resolues),
        "nombre_cables_sans_extremite": len(bilan.sans_extremite),
        "nombre_cables_telecommunication": len(bilan.references_telecom),
        "geometrie": feature.get("geometry"),
    }


def detecter_anomalies(
    features_jonction: list[dict[str, Any]],
    extremites_cables: Mapping[str, frozenset[tuple[float, float]]],
    cables_telecom: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Detecte les jonctions dont le nombre de cables raccordes est non conforme.

    Une jonction peut porter deux anomalies : un compte fautif et une
    incoherence entre les deux sources de raccordement.
    """
    anomalies: list[dict[str, Any]] = []
    for feature in features_jonction:
        proprietes = feature.get("properties") or {}
        regle = regle_applicable(proprietes)
        if regle is None:
            continue
        point = extraire_point(feature.get("geometry"))
        references = extraire_references(proprietes)
        bilan = construire_bilan(point, references, extremites_cables, cables_telecom)
        non_declares = detecter_coincidences_non_declarees(point, references, extremites_cables)
        codes = classifier_bilan(regle, bilan)
        if non_declares and TYPE_RACCORDEMENT_INCOHERENT not in codes:
            codes.append(TYPE_RACCORDEMENT_INCOHERENT)
        anomalies.extend(_anomalie(code, feature, proprietes, regle, bilan, non_declares) for code in codes)
    return anomalies


def compter_jonctions_a_controler(features_jonction: list[dict[str, Any]]) -> int:
    """Compte les jonctions entrant dans le perimetre du controle."""
    return sum(1 for feature in features_jonction if regle_applicable(feature.get("properties") or {}) is not None)


def compter_jonctions_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les jonctions distinctes portant au moins une anomalie."""
    return len({anomalie["id_jonction"] for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des jonctions au raccordement non conforme.

    La geometrie de chaque feature est le Point de la jonction concernee. Les
    comptes des deux sources de raccordement sont exposes cote a cote : c'est
    leur confrontation qui explique l'ecart.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_JONCTION,
                "id_jonction": a["id_jonction"],
                "type_jonction": a["type_jonction"],
                "nombre_minimum": a["nombre_minimum"],
                "nombre_maximum": a["nombre_maximum"],
                "nombre_cables_raccordes": a["nombre_cables_raccordes"],
                "nombre_references": a["nombre_references"],
                "nombre_geographiques": a["nombre_geographiques"],
                "nombre_references_sans_coincidence": a["nombre_references_sans_coincidence"],
                "nombre_coincidences_non_declarees": a["nombre_coincidences_non_declarees"],
                "nombre_references_non_resolues": a["nombre_references_non_resolues"],
                "nombre_cables_sans_extremite": a["nombre_cables_sans_extremite"],
                "nombre_cables_telecommunication": a["nombre_cables_telecommunication"],
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
    """Execute le controle du nombre de cables raccordes en mode CLI.

    Indexe les extremites des cables une seule fois, controle chaque jonction du
    perimetre et ecrit le fichier d'ecarts GeoJSON. L'absence d'un fichier
    source est signalee sans bloquer.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    extremites_cables, cables_telecom, couches_cable_absentes = indexer_extremites_cables(repertoire_resolu)
    features, crs, jonction_absente = _charger_features(repertoire_resolu, FICHIER_JONCTION)

    anomalies = detecter_anomalies(features, extremites_cables, cables_telecom)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_jonctions_analysees": len(features),
        "nombre_jonctions_controlees": compter_jonctions_a_controler(features),
        "nombre_jonctions_non_conformes": compter_jonctions_non_conformes(anomalies),
        "nombre_cables_indexes": len(extremites_cables),
        "nombre_cables_sans_extremite": sum(1 for extremites in extremites_cables.values() if not extremites),
        "nombre_cables_telecommunication": len(cables_telecom),
        "tolerance_coincidence_m": TOLERANCE_SUPERPOSITION,
        "fichier_jonction_absent": jonction_absente,
        "couches_cable_absentes": couches_cable_absentes,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle du nombre de cables raccordes."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E608 : coherence entre le TypeJonction d'une "
            "RPD_Jonction_Reco au statut UnderCommissionning et le nombre de "
            "cables qui lui sont raccordes, confirme a la fois par cables_href "
            "et par la coincidence geometrique a 1 mm pres."
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
