"""
Controle E507 : coherence geometrique jonction / extremite de cable electrique.

Verifie que chaque entite RPD_Jonction_Reco liee a un cable electrique en cours
de mise en service est positionnee exactement sur l'une des extremites de la
geometrie de ce cable. Une jonction superposee a un sommet intermediaire, ou a
un point quelconque du trace, n'est pas conforme.

Regle de gestion :
  - Parcourir les entites RPD_Jonction_Reco et leurs references cables_href.
  - Ne retenir que les references pointant vers un RPD_CableElectrique_Reco au
    Statut UnderCommissionning.
  - Comparer le point de la jonction aux extremites du cable : toute jonction ne
    coincidant avec aucune d'elles genere une anomalie E507.

Comparaison planimetrique (XY) : la coincidence est evaluee sur X et Y par
egalite stricte, sans tolerance. Les donnees de reference le confirment (96
liens jonction/cable exacts au bit pres sur les jeux d'echantillons). Le Z est
ecarte : un ecart altimetrique residuel (arrondi au centimetre) ne traduit pas
un defaut de raccordement et releve des controles E200 a E209, dont c'est le
role. Meme convention que le controle E506.

Extremites : la geometrie d'un cable est decomposee via extraire_extremites
(controle E506), qui identifie les extremites topologiques. Les parties d'un
MultiLineString RecoStaR n'etant ni ordonnees ni orientees, prendre le premier
et le dernier sommet apres mise a plat donnerait des extremites fausses (10
fausses anomalies constatees sur les echantillons).

Perimetre :
  - Cables : RPD_CableElectrique_Reco au Statut UnderCommissionning. Les
    references vers un cable d'un autre statut, d'un autre type ou inexistant
    sont hors perimetre (l'integrite referentielle releve d'E401, la presence
    d'un noeud a chaque extremite d'E506).
  - Compatible RecoStaR V1.0 et V1.1 : champs et geometries identiques, controle
    agnostique de version.

Usage CLI :
    python controle_e507.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_jonction_extremite_cable.geojson
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

from controle_e506 import _extraire_point
from utils_cable import extraire_ids_cables_href as _extraire_ids_cables_href
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature
from utils_geometrie import extraire_extremites

# Fichiers source
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"
FICHIER_JONCTION: str = "RPD_Jonction_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_jonction_extremite_cable.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "jonction_hors_extremite"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_CABLES_HREF: str = "cables_href"

# Statut des cables a controler
STATUT_CONTROLE: str = "UnderCommissionning"


@dataclass(slots=True)
class EntiteJonction:
    """Jonction avec son point planimetrique et ses references cables."""

    id_entite: str | None
    point: tuple[float, float] | None  # None si la jonction n'a pas de geometrie Point
    ids_cables: list[str]  # identifiants extraits du champ cables_href
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_geometries_cables_controles(
    repertoire: str,
) -> tuple[dict[str, dict[str, Any] | None], bool]:
    """Charge l'index {id_cable: geometrie} des cables electriques controles.

    Retourne (index, fichier_absent). Seuls les cables au Statut
    UnderCommissionning sont indexes : le dictionnaire sert donc a la fois de
    filtre de perimetre (appartenance en O(1)) et d'acces a la geometrie.
    """
    chemin = os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE)
    collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
    if collection is None:
        return {}, True

    index: dict[str, dict[str, Any] | None] = {}
    for feature in collection.get("features", []):
        props = feature.get("properties") or {}
        if props.get(CHAMP_STATUT) != STATUT_CONTROLE:
            continue
        id_cable = obtenir_id_feature(feature)
        if id_cable is None:
            continue
        index[id_cable] = feature.get("geometry")
    return index, False


def _creer_entite_jonction(feature: dict[str, Any]) -> EntiteJonction:
    """Cree une EntiteJonction depuis une feature GeoJSON."""
    props = feature.get("properties") or {}
    return EntiteJonction(
        id_entite=obtenir_id_feature(feature),
        point=_extraire_point(feature.get("geometry")),
        ids_cables=_extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)),
        geometrie=feature.get("geometry"),
    )


def charger_jonctions(
    repertoire: str,
) -> tuple[list[EntiteJonction], bool, dict[str, Any] | None]:
    """Charge les jonctions portant au moins une reference cable.

    Retourne (jonctions, fichier_absent, crs). Les jonctions sans cables_href
    sont ecartees des le chargement : elles ne peuvent produire aucun lien a
    controler, les conserver serait un traitement inutile.
    """
    chemin = os.path.join(repertoire, FICHIER_JONCTION)
    collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
    if collection is None:
        return [], True, None

    creer = _creer_entite_jonction  # alias local
    jonctions = [j for f in collection.get("features", []) if (j := creer(f)).ids_cables]
    return jonctions, False, collection.get("crs")


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _obtenir_extremites(
    id_cable: str,
    geometries_cables: Mapping[str, dict[str, Any] | None],
    cache: dict[str, frozenset[tuple[float, float]]],
) -> frozenset[tuple[float, float]]:
    """Retourne les extremites planimetriques d'un cable, avec memorisation.

    Un cable est generalement reference par deux jonctions : le cache evite de
    redecomposer sa geometrie a chaque lien. Le frozenset permet un test
    d'appartenance en O(1).

    geometries_cables est un Mapping : l'index est seulement consulte. Seul le
    cache, lui, est enrichi en place — d'ou son type dict.
    """
    extremites = cache.get(id_cable)
    if extremites is None:
        extremites = frozenset(extraire_extremites(geometries_cables[id_cable]))
        cache[id_cable] = extremites
    return extremites


def _distance_extremite_plus_proche(
    point: tuple[float, float],
    extremites: frozenset[tuple[float, float]],
) -> float:
    """Distance planimetrique du point a l'extremite la plus proche.

    Valeur de diagnostic uniquement : elle indique l'ampleur du decalage
    (quelques centimetres ou plusieurs dizaines de metres) sans intervenir dans
    la decision de conformite, qui reste une egalite stricte.
    """
    distance = math.dist  # alias local
    return min(distance(point, extremite) for extremite in extremites)


def _anomalie_jonction_hors_extremite(
    jonction: EntiteJonction,
    id_cable: str,
    point: tuple[float, float],
    extremites: frozenset[tuple[float, float]],
) -> dict[str, Any]:
    """Construit l'anomalie d'une jonction non posee sur une extremite du cable."""
    return {
        "id_jonction": jonction.id_entite,
        "id_cable": id_cable,
        "distance_extremite": round(_distance_extremite_plus_proche(point, extremites), 3),
        "geometrie": jonction.geometrie,
    }


def _analyser_jonction(
    jonction: EntiteJonction,
    geometries_cables: Mapping[str, dict[str, Any] | None],
    cache: dict[str, frozenset[tuple[float, float]]],
    cables_non_exploitables: set[str],
) -> list[dict[str, Any]]:
    """Detecte les liens (jonction, cable) dont la jonction n'est pas sur une extremite.

    Les references hors perimetre (cable d'un autre statut, d'un autre type ou
    inexistant) sont ignorees : elles relevent d'E401 et d'E506.
    """
    point = jonction.point
    if point is None:
        return []

    anomalies: list[dict[str, Any]] = []
    for id_cable in jonction.ids_cables:
        if id_cable not in geometries_cables:
            continue
        extremites = _obtenir_extremites(id_cable, geometries_cables, cache)
        if not extremites:
            # Geometrie absente, non lineaire ou fermee : aucune extremite n'est
            # definie, la conformite ne peut pas etre tranchee ici.
            cables_non_exploitables.add(id_cable)
            continue
        if point in extremites:
            continue
        anomalies.append(_anomalie_jonction_hors_extremite(jonction, id_cable, point, extremites))
    return anomalies


def detecter_anomalies(
    jonctions: list[EntiteJonction],
    geometries_cables: Mapping[str, dict[str, Any] | None],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Detecte les jonctions mal positionnees sur les cables qu'elles referencent.

    Retourne (anomalies, cables_non_exploitables). Une anomalie est produite par
    lien (jonction, cable) non conforme : une jonction liee a deux cables mal
    raccordes en genere deux.
    """
    anomalies: list[dict[str, Any]] = []
    cache: dict[str, frozenset[tuple[float, float]]] = {}
    cables_non_exploitables: set[str] = set()
    analyser = _analyser_jonction  # alias local
    for jonction in jonctions:
        anomalies.extend(analyser(jonction, geometries_cables, cache, cables_non_exploitables))
    return anomalies, cables_non_exploitables


def compter_liens_controles(
    jonctions: list[EntiteJonction],
    geometries_cables: Mapping[str, dict[str, Any] | None],
) -> int:
    """Compte les liens (jonction, cable electrique controle) effectivement evalues."""
    return sum(
        1
        for jonction in jonctions
        if jonction.point is not None
        for id_cable in jonction.ids_cables
        if id_cable in geometries_cables
    )


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des jonctions mal positionnees.

    La geometrie de chaque feature est celle de la jonction (Point) : c'est
    l'entite a repositionner, donc le point a localiser dans QGIS. Le crs est
    propage depuis le fichier source des jonctions.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": TYPE_ANOMALIE,
                "id_jonction": a["id_jonction"],
                "id_cable": a["id_cable"],
                "distance_extremite_m": a["distance_extremite"],
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de position des jonctions en mode CLI.

    Charge les cables controles et les jonctions, detecte les jonctions hors
    extremite et ecrit le fichier d'ecarts GeoJSON. Les fichiers absents sont
    signales dans le rapport sans bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    geometries_cables, fichier_cable_absent = charger_geometries_cables_controles(repertoire_resolu)
    jonctions, fichier_jonction_absent, crs = charger_jonctions(repertoire_resolu)

    anomalies, cables_non_exploitables = detecter_anomalies(jonctions, geometries_cables)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_cables_controles": len(geometries_cables),
        "nombre_jonctions_analysees": len(jonctions),
        "nombre_liens_controles": compter_liens_controles(jonctions, geometries_cables),
        "nombre_cables_geometrie_non_exploitable": len(cables_non_exploitables),
        "fichier_cable_absent": fichier_cable_absent,
        "fichier_jonction_absent": fichier_jonction_absent,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de position des jonctions."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E507 : coherence geometrique jonction / extremite de cable — "
            "toute RPD_Jonction_Reco liee a un RPD_CableElectrique_Reco au statut "
            "UnderCommissionning doit etre posee exactement (XY) sur l'une des "
            "extremites de ce cable."
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
