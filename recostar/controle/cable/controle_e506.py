"""
Controle E506 : raccordement des cables aux noeuds du reseau.

Regle 1 — cables electriques (priorite bloquante) :
  Chaque RPD_CableElectrique_Reco au Statut UnderCommissionning doit etre
  raccorde a un noeud a chacune de ses deux extremites. La relation cable/noeud
  est portee par le champ cables_href des entites de type noeud (la liste de ces
  types est importee du module de conversion, cf. utils_cable). Deux defauts
  distincts sont detectes :
    - defaut relationnel : moins de deux noeuds distincts referencent le cable
      (types cable_sans_noeud et cable_noeud_unique) ;
    - defaut topologique : au moins deux noeuds referencent le cable mais l'un
      de ses bouts n'est couvert par aucun d'eux (type extremite_non_raccordee).
  Les deux defauts s'excluent : le controle topologique n'a de sens qu'a partir
  de deux noeuds raccordes.

Regle 2 — cables de terre (priorite information) :
  Chaque RPD_CableTerre_Reco au Statut UnderCommissionning doit etre relie a au
  moins une entite RPD_Terre_Reco. Les deux sens de liaison du modele RecoStaR
  sont acceptes (cf. detecter_anomalies_cable_terre).

Versions :
  Les champs exploites (Statut, cables_href, noeudreseau_href) et la liste des
  types de noeuds sont identiques en RecoStaR V1.0 et V1.1. Le controle est donc
  agnostique de version, comme E500 a E505.

Usage CLI :
    python controle_e506.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_raccordement_cable.geojson
"""

import argparse
import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils_cable import charger_types_noeuds_reseau
from utils_cable import extraire_ids_cables_href as _extraire_ids_cables_href
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature
from utils_geometrie import extraire_extremites

# Fichiers source des cables controles
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"
FICHIER_CABLE_TERRE: str = "RPD_CableTerre_Reco.geojson"

# Fichier des prises de terre (cible de la regle 2)
FICHIER_TERRE: str = "RPD_Terre_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_raccordement_cable.geojson"

# Priorites : la regle 1 est bloquante, la regle 2 est informative
PRIORITE_CABLE_ELECTRIQUE: str = "bloquant"
PRIORITE_CABLE_TERRE: str = "information"

# Types d'anomalie produits par le controle
TYPE_SANS_NOEUD: str = "cable_sans_noeud"
TYPE_NOEUD_UNIQUE: str = "cable_noeud_unique"
TYPE_EXTREMITE_NON_RACCORDEE: str = "extremite_non_raccordee"
TYPE_CABLE_TERRE_NON_RACCORDE: str = "cable_terre_non_raccorde"

# Priorite applicable a chaque type d'anomalie
PRIORITES_PAR_TYPE: dict[str, str] = {
    TYPE_SANS_NOEUD: PRIORITE_CABLE_ELECTRIQUE,
    TYPE_NOEUD_UNIQUE: PRIORITE_CABLE_ELECTRIQUE,
    TYPE_EXTREMITE_NON_RACCORDEE: PRIORITE_CABLE_ELECTRIQUE,
    TYPE_CABLE_TERRE_NON_RACCORDE: PRIORITE_CABLE_TERRE,
}

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_CABLES_HREF: str = "cables_href"
CHAMP_NOEUD_RESEAU_HREF: str = "noeudreseau_href"

# Statut des cables a controler
STATUT_CONTROLE: str = "UnderCommissionning"

# Nombre de noeuds attendu par cable electrique (un par extremite)
NB_NOEUDS_ATTENDU: int = 2


@dataclass(slots=True)
class NoeudRaccorde:
    """Noeud referencant un cable, avec le point servant a le localiser."""

    type_entite: str
    id_entite: str | None
    point: tuple[float, float] | None  # None si le noeud n'a pas de geometrie Point


# ---------------------------------------------------------------------------
# Chargement des noeuds du reseau
# ---------------------------------------------------------------------------


def _extraire_point(geometrie: dict[str, Any] | None) -> tuple[float, float] | None:
    """Retourne les coordonnees XY d'une geometrie Point, sinon None.

    Seule la composante planimetrique est retenue : l'affectation d'un noeud a
    une extremite est une comparaison relative (le plus proche l'emporte), pour
    laquelle le Z n'apporte rien et introduirait le bruit altimetrique que les
    controles E200 a E209 ont precisement pour role de detecter.
    """
    if not geometrie or geometrie.get("type") != "Point":
        return None
    coordonnees = geometrie.get("coordinates")
    if not coordonnees or len(coordonnees) < 2:
        return None
    return (coordonnees[0], coordonnees[1])


def _indexer_couche(
    features: list[dict[str, Any]],
    type_noeud: str,
    index: dict[str, list[NoeudRaccorde]],
) -> None:
    """Ajoute les noeuds d'une couche a l'index {id_cable: [noeuds]}.

    L'index est enrichi en place : aucune copie n'est produite pour chaque
    couche parcourue. Un noeud referencant plusieurs cables alimente autant
    d'entrees, mais n'est instancie qu'une fois (l'objet est partage entre les
    entrees, il n'est jamais mute).
    """
    extraire_ids = _extraire_ids_cables_href  # alias locaux (boucle critique)
    obtenir_id = obtenir_id_feature
    extraire_point = _extraire_point
    for feature in features:
        props = feature.get("properties") or {}
        ids_cables = extraire_ids(props.get(CHAMP_CABLES_HREF))
        if not ids_cables:
            continue
        noeud = NoeudRaccorde(
            type_entite=type_noeud,
            id_entite=obtenir_id(feature),
            point=extraire_point(feature.get("geometry")),
        )
        for id_cable in ids_cables:
            index.setdefault(id_cable, []).append(noeud)


def indexer_noeuds_par_cable(repertoire: str) -> tuple[dict[str, list[NoeudRaccorde]], list[str]]:
    """Construit l'index {id_cable: [noeuds raccordes]} depuis toutes les couches noeud.

    Retourne (index, fichiers_absents). Les types de noeuds proviennent du module
    de conversion (source de verite unique). Chaque couche n'est parcourue qu'une
    fois ; un noeud referencant plusieurs cables alimente autant d'entrees.
    """
    index: dict[str, list[NoeudRaccorde]] = {}
    fichiers_absents: list[str] = []
    for type_noeud in charger_types_noeuds_reseau():
        nom_fichier = f"{type_noeud}.geojson"
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
        if collection is None:
            fichiers_absents.append(nom_fichier)
            continue
        _indexer_couche(collection.get("features", []), type_noeud, index)
    return index, fichiers_absents


# ---------------------------------------------------------------------------
# Regle 1 : raccordement des cables electriques
# ---------------------------------------------------------------------------


def _compter_extremites_couvertes(
    extremites: list[tuple[float, float]],
    points_noeuds: list[tuple[float, float]],
) -> list[int]:
    """Compte les noeuds affectes a chaque extremite (le plus proche l'emporte).

    L'affectation est relative : aucun seuil de distance n'est applique. Un
    noeud est toujours rattache a l'extremite dont il est le plus proche, ce
    qui rend le controle insensible a l'ecart residuel constate entre un noeud
    et le bout de cable qu'il raccorde (jusqu'a quelques metres pour un poste).

    Les points recus sont deja localises (l'appelant ecarte les noeuds sans
    geometrie Point) : la liste retournee compte autant d'entrees que
    d'extremites, dans le meme ordre.
    """
    couverture = [0] * len(extremites)
    distance = math.dist  # alias local (boucle critique)
    for point in points_noeuds:
        distances = [distance(point, extremite) for extremite in extremites]
        couverture[distances.index(min(distances))] += 1
    return couverture


def _anomalie_defaut_relationnel(
    id_cable: str | None,
    noeuds: list[NoeudRaccorde],
    geometrie: dict[str, Any] | None,
) -> dict[str, Any]:
    """Construit l'anomalie d'un cable referencé par moins de deux noeuds."""
    return {
        "type_anomalie": TYPE_SANS_NOEUD if not noeuds else TYPE_NOEUD_UNIQUE,
        "id_cable": id_cable,
        "nombre_noeuds": len(noeuds),
        "types_noeuds": ",".join(sorted({n.type_entite for n in noeuds})),
        "geometrie": geometrie,
    }


def _anomalie_extremite(
    id_cable: str | None,
    noeuds: list[NoeudRaccorde],
    nb_extremites_libres: int,
    geometrie: dict[str, Any] | None,
) -> dict[str, Any]:
    """Construit l'anomalie d'un cable dont une extremite n'est couverte par aucun noeud."""
    return {
        "type_anomalie": TYPE_EXTREMITE_NON_RACCORDEE,
        "id_cable": id_cable,
        "nombre_noeuds": len(noeuds),
        "types_noeuds": ",".join(sorted({n.type_entite for n in noeuds})),
        "nombre_extremites_libres": nb_extremites_libres,
        "geometrie": geometrie,
    }


def _analyser_cable_electrique(
    id_cable: str | None,
    geometrie: dict[str, Any] | None,
    noeuds: list[NoeudRaccorde],
) -> dict[str, Any] | None:
    """Analyse le raccordement d'un cable electrique ; retourne l'anomalie ou None.

    Les deux defauts sont exclusifs : sous deux noeuds, le defaut est
    relationnel et le controle topologique n'aurait aucun sens (deux extremites
    ne peuvent pas etre couvertes par moins de deux noeuds).
    """
    if len(noeuds) < NB_NOEUDS_ATTENDU:
        return _anomalie_defaut_relationnel(id_cable, noeuds, geometrie)

    extremites = extraire_extremites(geometrie)
    if len(extremites) != NB_NOEUDS_ATTENDU:
        # Geometrie absente, fermee ou ramifiee : la notion de « deux bouts »
        # n'est pas definie, seul le controle relationnel ci-dessus s'applique.
        return None

    points_noeuds = [n.point for n in noeuds if n.point is not None]
    if len(points_noeuds) < NB_NOEUDS_ATTENDU:
        # Sans au moins deux noeuds localises, une extremite paraitrait libre
        # alors que le defaut porte sur la geometrie des noeuds, pas sur le
        # raccordement lui-meme (deja valide par le controle relationnel).
        return None

    couverture = _compter_extremites_couvertes(extremites, points_noeuds)
    nb_libres = sum(1 for nb in couverture if nb == 0)
    if nb_libres == 0:
        return None
    return _anomalie_extremite(id_cable, noeuds, nb_libres, geometrie)


def detecter_anomalies_cable_electrique(
    features: list[dict[str, Any]],
    index_noeuds: dict[str, list[NoeudRaccorde]],
) -> list[dict[str, Any]]:
    """Detecte les cables electriques mal raccordes aux noeuds du reseau.

    Seuls les cables au statut UnderCommissionning sont analyses. Une anomalie
    au maximum est produite par cable.
    """
    anomalies: list[dict[str, Any]] = []
    analyser = _analyser_cable_electrique  # alias local
    for feature in features:
        props = feature.get("properties") or {}
        if props.get(CHAMP_STATUT) != STATUT_CONTROLE:
            continue
        id_cable = obtenir_id_feature(feature)
        noeuds = index_noeuds.get(id_cable, []) if id_cable is not None else []
        anomalie = analyser(id_cable, feature.get("geometry"), noeuds)
        if anomalie is not None:
            anomalies.append(anomalie)
    return anomalies


# ---------------------------------------------------------------------------
# Regle 2 : raccordement des cables de terre
# ---------------------------------------------------------------------------


def charger_liaisons_terre(repertoire: str) -> tuple[set[str], set[str], bool]:
    """Charge les deux sens de liaison portes par RPD_Terre_Reco.

    Retourne (ids_terre, ids_cables_references, fichier_absent) :
      - ids_terre : identifiants des prises de terre, cibles de noeudreseau_href ;
      - ids_cables_references : cables cites par le cables_href des prises de terre.
    Les deux sont des set pour un test d'appartenance en O(1).
    """
    chemin = os.path.join(repertoire, FICHIER_TERRE)
    collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
    if collection is None:
        return set(), set(), True

    ids_terre: set[str] = set()
    ids_cables_references: set[str] = set()
    for feature in collection.get("features", []):
        id_terre = obtenir_id_feature(feature)
        if id_terre is not None:
            ids_terre.add(id_terre)
        props = feature.get("properties") or {}
        ids_cables_references.update(_extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)))
    return ids_terre, ids_cables_references, False


def detecter_anomalies_cable_terre(
    features: list[dict[str, Any]],
    ids_terre: set[str],
    ids_cables_references: set[str],
) -> list[dict[str, Any]]:
    """Detecte les cables de terre relies a aucune entite RPD_Terre_Reco.

    Les deux sens de liaison du modele RecoStaR sont acceptes, un seul suffit :
      - le cable designe la prise de terre via son champ noeudreseau_href
        (sens produit par la conversion, cf. mapper_cable_terre) ;
      - la prise de terre designe le cable via son champ cables_href (sens
        entretenu par la propagation en conteneur, cf. recostar_to_geojson).
    La reference doit pointer vers une prise de terre existante : un
    noeudreseau_href designant une entite absente ou d'un autre type ne vaut
    pas raccordement.
    """
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        if props.get(CHAMP_STATUT) != STATUT_CONTROLE:
            continue
        id_cable = obtenir_id_feature(feature)
        noeud_href = props.get(CHAMP_NOEUD_RESEAU_HREF)
        if noeud_href in ids_terre or id_cable in ids_cables_references:
            continue
        anomalies.append(
            {
                "type_anomalie": TYPE_CABLE_TERRE_NON_RACCORDE,
                "id_cable": id_cable,
                "noeudreseau_href": noeud_href,
                "geometrie": feature.get("geometry"),
            }
        )
    return anomalies


# ---------------------------------------------------------------------------
# Comptages du rapport
# ---------------------------------------------------------------------------


def compter_cables_controles(features: list[dict[str, Any]]) -> int:
    """Compte les cables au statut UnderCommissionning d'une couche."""
    return sum(1 for f in features if (f.get("properties") or {}).get(CHAMP_STATUT) == STATUT_CONTROLE)


def compter_anomalies_par_type(anomalies: list[dict[str, Any]]) -> dict[str, int]:
    """Ventile les anomalies par type pour le rapport JSON."""
    return dict(Counter(a["type_anomalie"] for a in anomalies))


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def _construire_feature(anomalie: dict[str, Any]) -> dict[str, Any]:
    """Construit la feature d'ecart d'une anomalie, geometrie du cable conservee."""
    proprietes: dict[str, Any] = {
        "type_anomalie": anomalie["type_anomalie"],
        "id_cable": anomalie["id_cable"],
        "priorite": PRIORITES_PAR_TYPE[anomalie["type_anomalie"]],
    }
    # Champs propres a chaque regle, ajoutes uniquement lorsqu'ils sont pertinents
    for champ in ("nombre_noeuds", "types_noeuds", "nombre_extremites_libres", "noeudreseau_href"):
        if champ in anomalie:
            proprietes[champ] = anomalie[champ]
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": anomalie["geometrie"],
    }


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des defauts de raccordement detectes.

    Chaque feature conserve la geometrie du cable en cause pour la localisation
    dans QGIS. Le crs est propage depuis le fichier des cables electriques.
    """
    features = [_construire_feature(a) for a in anomalies]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def _charger_couche(repertoire: str, nom_fichier: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool]:
    """Charge une couche GeoJSON : retourne (features, crs, fichier_absent)."""
    chemin = os.path.join(repertoire, nom_fichier)
    collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
    if collection is None:
        return [], None, True
    return collection.get("features", []), collection.get("crs"), False


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de raccordement des cables en mode CLI.

    Applique les deux regles, fusionne les anomalies dans un fichier d'ecarts
    unique et retourne le rapport. Les fichiers absents sont signales sans
    bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    index_noeuds, fichiers_noeuds_absents = indexer_noeuds_par_cable(repertoire_resolu)
    ids_terre, ids_cables_terre_references, fichier_terre_absent = charger_liaisons_terre(repertoire_resolu)

    features_electrique, crs, fichier_cable_electrique_absent = _charger_couche(
        repertoire_resolu, FICHIER_CABLE_ELECTRIQUE
    )
    features_terre, crs_terre, fichier_cable_terre_absent = _charger_couche(repertoire_resolu, FICHIER_CABLE_TERRE)

    anomalies = detecter_anomalies_cable_electrique(features_electrique, index_noeuds)
    anomalies.extend(detecter_anomalies_cable_terre(features_terre, ids_terre, ids_cables_terre_references))

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs if crs is not None else crs_terre)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorites": dict(PRIORITES_PAR_TYPE),
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_cables_electriques_controles": compter_cables_controles(features_electrique),
        "nombre_cables_terre_controles": compter_cables_controles(features_terre),
        "nombre_noeuds_indexes": len(index_noeuds),
        "nombre_terres": len(ids_terre),
        "fichier_cable_electrique_absent": fichier_cable_electrique_absent,
        "fichier_cable_terre_absent": fichier_cable_terre_absent,
        "fichier_terre_absent": fichier_terre_absent,
        "fichiers_noeuds_absents": fichiers_noeuds_absents,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de raccordement des cables."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E506 : raccordement des cables aux noeuds du reseau — "
            "un noeud a chaque extremite des cables electriques "
            "(RPD_CableElectrique_Reco) et au moins une prise de terre "
            "(RPD_Terre_Reco) par cable de terre (RPD_CableTerre_Reco), "
            "au statut UnderCommissionning."
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
