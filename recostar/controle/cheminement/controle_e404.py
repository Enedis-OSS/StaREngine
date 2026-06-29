"""
Controle E404 : profondeur manquante aux points de charge generatrice.

Verifie que les cheminements souterrains (Fourreau, PleineTerre,
ProtectionMecanique) superposes a un point de charge generatrice
possedent le champ ProfondeurMinNonReg renseigne.

Regle de conformite aux limites :
    Si un point est a la limite entre deux cheminements, au moins
    un des deux doit posseder ProfondeurMinNonReg renseigne.

Logique de detection par version :
- v1.0 : le point est une charge generatrice quand TypeLeve == 'ChargeGeneratrice'
- v1.1 : le point est une charge generatrice quand le champ ChargeGeneratrice est renseigne

Usage CLI :
    python controle_e404.py --repertoire <chemin> [--sortie <chemin>]
                            [--version {auto,1.0,1.1}]

Sortie : ecarts_charge_generatrice_profondeur_absente.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely import STRtree, force_2d
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature

# Fichier source des points de leve
FICHIER_SOURCE: str = "RPD_PointLeveOuvrageReseau_Reco.geojson"

# Fichiers de cheminement souterrain analyses
FICHIERS_CHEMINEMENT_SOUTERRAIN: tuple[str, ...] = (
    "RPD_Fourreau_Reco.geojson",
    "RPD_PleineTerre_Reco.geojson",
    "RPD_ProtectionMecanique_Reco.geojson",
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_charge_generatrice_profondeur_absente.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Identifiant du type d'anomalie produit par ce controle
TYPE_ANOMALIE: str = "cheminement_sans_profondeur_charge_generatrice"

# Distance maximale (metres) point/cheminement pour considerer une superposition —
# couvre les ecarts de precision flottante entre les geometries
EPSILON_SPATIAL: float = 0.01

# Gestion des versions RecoStaR (meme convention que xsd_structuration et E204)
VERSION_DEFAUT: str = "1.1"
VERSIONS_SUPPORTEES: tuple[str, ...] = ("1.0", "1.1")
JETON_AUTO: str = "auto"

# Champs de detection de version et de charges generatrices
CHAMP_TYPE_LEVE: str = "TypeLeve"
VALEUR_CHARGE_GENERATRICE_V10: str = "ChargeGeneratrice"
CHAMP_CHARGE_GENERATRICE_V11: str = "ChargeGeneratrice"
CHAMP_PROFONDEUR: str = "ProfondeurMinNonReg"

# Types geometriques lineaires acceptes pour les cheminements
TYPES_GEOMETRIE_LINEAIRE: frozenset[str] = frozenset({"LineString", "MultiLineString"})


@dataclass(slots=True)
class EntitePoint:
    """Point de charge generatrice avec son identifiant et sa geometrie Shapely."""

    id_entite: str | None
    geometrie: BaseGeometry  # Point Shapely en 2D
    coordonnees: list[float]  # coordonnees brutes pour la sortie GeoJSON


@dataclass(slots=True)
class EntiteCheminement:
    """Cheminement souterrain avec geometrie Shapely et indicateur de profondeur."""

    id_entite: str | None
    fichier: str
    geometrie: BaseGeometry  # LineString/MultiLineString Shapely en 2D
    profondeur_renseignee: bool  # True si ProfondeurMinNonReg est present et non null


# ---------------------------------------------------------------------------
# Detection de la version depuis le contenu GeoJSON
# ---------------------------------------------------------------------------


def detecter_version_depuis_features(features: list[dict[str, Any]]) -> str | None:
    """Deduit la version RecoStaR depuis les proprietes des entites.

    La presence du champ TypeLeve dans au moins une feature indique v1.0.
    Retourne None si la version ne peut pas etre determinee (repli sur VERSION_DEFAUT).
    """
    for feature in features:
        props = feature.get("properties") or {}
        if CHAMP_TYPE_LEVE in props:
            return "1.0"
    return None


def resoudre_version(
    version_demandee: str,
    features: list[dict[str, Any]],
) -> str:
    """Resout la version effective a appliquer pour ce controle.

    En mode auto, deduit la version depuis les proprietes GeoJSON et se
    replie sur VERSION_DEFAUT si la detection echoue. En mode explicite,
    applique directement la version demandee.
    """
    if version_demandee != JETON_AUTO:
        return version_demandee

    version_detectee = detecter_version_depuis_features(features)
    if version_detectee is None:
        print(
            f"Version non detectee dans les features : repli sur {VERSION_DEFAUT}.",
            file=sys.stderr,
        )
        return VERSION_DEFAUT
    return version_detectee


# ---------------------------------------------------------------------------
# Detection des charges generatrices selon la version
# ---------------------------------------------------------------------------


def _est_charge_generatrice_v10(props: dict[str, Any]) -> bool:
    """Retourne True si le point est une charge generatrice en version 1.0."""
    return props.get(CHAMP_TYPE_LEVE) == VALEUR_CHARGE_GENERATRICE_V10


def _est_charge_generatrice_v11(props: dict[str, Any]) -> bool:
    """Retourne True si le point est une charge generatrice en version 1.1."""
    return props.get(CHAMP_CHARGE_GENERATRICE_V11) is not None


# Registre : code de version -> predicat de detection d'une charge generatrice
_DETECTEURS_CHARGE: dict[str, Callable[[dict[str, Any]], bool]] = {
    "1.0": _est_charge_generatrice_v10,
    "1.1": _est_charge_generatrice_v11,
}


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def _creer_entite_point(
    feature: dict[str, Any],
    detecteur: Callable[[dict[str, Any]], bool],
) -> EntitePoint | None:
    """Cree une EntitePoint si la feature est un point de charge generatrice.

    Retourne None si la feature n'est pas un Point, si la geometrie est
    absente ou invalide, ou si le predicat de version ne l'identifie pas
    comme une charge generatrice.
    """
    geom = feature.get("geometry")
    if geom is None or geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates", [])
    if len(coords) < 2:
        return None
    props = feature.get("properties") or {}
    if not detecteur(props):
        return None
    try:
        pt = force_2d(shape(geom))
    except Exception:
        return None
    return EntitePoint(
        id_entite=obtenir_id_feature(feature),
        geometrie=pt,
        coordonnees=list(coords[:2]),
    )


def charger_points_charge(
    features: list[dict[str, Any]],
    version: str,
) -> list[EntitePoint]:
    """Charge les points de charge generatrice depuis la liste de features GeoJSON.

    Filtre les features selon la version : TypeLeve en v1.0, champ
    ChargeGeneratrice en v1.1. Les features non pertinentes sont ignorees.
    """
    detecteur = _DETECTEURS_CHARGE.get(version, _est_charge_generatrice_v11)
    points: list[EntitePoint] = []
    for feature in features:
        entite = _creer_entite_point(feature, detecteur)
        if entite is not None:
            points.append(entite)
    return points


def _creer_entite_cheminement(
    feature: dict[str, Any],
    nom_fichier: str,
) -> EntiteCheminement | None:
    """Cree une EntiteCheminement depuis une feature GeoJSON.

    Retourne None si la geometrie est absente, non lineaire ou invalide.
    Les cheminements degeneres (longueur < EPSILON_SPATIAL) sont ignores
    pour eviter les faux positifs spatiaux sur des segments nuls.
    """
    geom = feature.get("geometry")
    if geom is None or geom.get("type") not in TYPES_GEOMETRIE_LINEAIRE:
        return None
    try:
        ligne = force_2d(shape(geom))
    except Exception:
        return None
    if ligne.is_empty or ligne.length < EPSILON_SPATIAL:
        return None
    props = feature.get("properties") or {}
    return EntiteCheminement(
        id_entite=obtenir_id_feature(feature),
        fichier=nom_fichier,
        geometrie=ligne,
        profondeur_renseignee=props.get(CHAMP_PROFONDEUR) is not None,
    )


def charger_cheminements_souterrains(
    repertoire: str,
) -> tuple[list[EntiteCheminement], list[str], dict[str, Any] | None]:
    """Charge les cheminements souterrains depuis les trois fichiers analyses.

    Retourne (cheminements, fichiers_absents, crs). Les geometries sont
    converties en 2D pour les calculs spatiaux planimetriques.
    """
    cheminements: list[EntiteCheminement] = []
    fichiers_absents: list[str] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in FICHIERS_CHEMINEMENT_SOUTERRAIN:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        for feature in collection.get("features", []):
            entite = _creer_entite_cheminement(feature, nom_fichier)
            if entite is not None:
                cheminements.append(entite)

    return cheminements, fichiers_absents, crs


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(
    points_charge: list[EntitePoint],
    cheminements: list[EntiteCheminement],
) -> list[dict[str, Any]]:
    """Detecte les charges generatrices dont aucun cheminement n'a de profondeur.

    Un point n'est pas en anomalie si :
    - il ne se superpose a aucun cheminement souterrain (hors perimetre) ;
    - au moins un des cheminements superposes possede ProfondeurMinNonReg.

    La superposition est definie par une distance planimetrique inferieure
    a EPSILON_SPATIAL, ce qui gere le cas des points a la limite entre deux
    cheminements adjacents.
    """
    if not points_charge or not cheminements:
        return []

    geometries = [c.geometrie for c in cheminements]
    arbre = STRtree(geometries)
    anomalies: list[dict[str, Any]] = []

    for point in points_charge:
        indices = arbre.query(point.geometrie, predicate="dwithin", distance=EPSILON_SPATIAL)
        if len(indices) == 0:
            continue
        touches = [cheminements[i] for i in indices]
        if any(c.profondeur_renseignee for c in touches):
            continue
        anomalies.append(
            {
                "id_point": point.id_entite,
                "coordonnees": point.coordonnees,
                "cheminements_touches": [{"id_cheminement": c.id_entite, "fichier": c.fichier} for c in touches],
            }
        )

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    version: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des charges generatrices en anomalie.

    La geometrie de chaque feature est celle du point de charge generatrice,
    ce qui permet la localisation directe dans QGIS. Les references aux
    cheminements impliques sont serialisees en CSV dans les proprietes.
    """
    features: list[dict[str, Any]] = []
    for a in anomalies:
        touches = a["cheminements_touches"]
        ids_csv = ",".join(str(c["id_cheminement"]) if c["id_cheminement"] is not None else "" for c in touches)
        fichiers_csv = ",".join(c["fichier"] for c in touches)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "type_anomalie": TYPE_ANOMALIE,
                    "priorite": PRIORITE_ANOMALIE,
                    "version": version,
                    "id_point": (str(a["id_point"]) if a["id_point"] is not None else None),
                    "nb_cheminements_touches": len(touches),
                    "ids_cheminements_touches": ids_csv,
                    "fichiers_cheminements_touches": fichiers_csv,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": a["coordonnees"],
                },
            }
        )
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
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle de profondeur aux charges generatrices.

    Charge le fichier source, resout la version, filtre les points de charge
    generatrice, charge les cheminements souterrains, detecte les anomalies
    par superposition spatiale et ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    chemin_source = os.path.join(repertoire_resolu, FICHIER_SOURCE)
    collection = lire_geojson(chemin_source)
    if collection is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_SOURCE} introuvable dans {repertoire_resolu}",
        }

    features_source = collection.get("features", [])
    version_effective = resoudre_version(version, features_source)

    points_charge = charger_points_charge(features_source, version_effective)
    cheminements, fichiers_absents, crs = charger_cheminements_souterrains(repertoire_resolu)

    anomalies = detecter_anomalies(points_charge, cheminements)
    geojson_ecarts = construire_geojson_ecarts(anomalies, version_effective, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "nombre_points_charge_analyses": len(points_charge),
        "nombre_cheminements_analyses": len(cheminements),
        "fichiers_cheminement_absents": fichiers_absents,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de profondeur aux charges generatrices."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E404 : verifie que les cheminements souterrains "
            "superposes a un point de charge generatrice "
            "(RPD_PointLeveOuvrageReseau_Reco) possedent le champ "
            "ProfondeurMinNonReg renseigne."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant {FICHIER_SOURCE}",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--version",
        choices=choix_version,
        default=JETON_AUTO,
        help=(
            "Version RecoStaR a controler. 'auto' (defaut) la deduit des "
            "proprietes GeoJSON ; sinon imposer '1.0' ou '1.1'."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
