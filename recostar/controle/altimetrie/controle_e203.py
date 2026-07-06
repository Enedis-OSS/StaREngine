"""
Controle altimetrique des geometries supplementaires via l'API IGN.

Compare les altitudes Z des sommets du fichier RPD_GeometrieSupplementaire_Reco
avec les altitudes de reference fournies par l'API altimetrique IGN. Les sommets
dont l'ecart depasse le seuil de 40 cm sont signales et exportes dans un fichier
GeoJSON d'ecarts.

Les coordonnees du projet sont en Lambert 93 (EPSG:2154). La conversion vers
WGS84 est effectuee en interne avant chaque appel a l'API IGN.

Gestion des versions RecoStaR :
- v1.1 : seules les entites dont le champ Statut vaut « UnderCommissionning »
         sont soumises au controle altimetrique.
- autres versions : comportement historique (toutes les entites controlees).
La version est detectee via le mecanisme partage d'E204 (presence du champ
TypeLeve dans RPD_PointLeveOuvrageReseau_Reco) et peut etre imposee en CLI.

Usage CLI :
    python controle_e203.py --repertoire <chemin> [--sortie <chemin>]
                            [--version {auto,1.0,1.1}]

Sortie : ecarts_z_ign.geojson
"""

import argparse
import json
import math
import os
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import requests

# Mecanisme de detection de version partage avec controle_e204 (et E205).
# Le wrapper par repertoire est factorise dans E204 ; on le reexpose sous le
# nom historique determiner_version_effective pour preserver l'API du module.
from controle_e204 import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
)
from controle_e204 import (
    determiner_version_depuis_repertoire as determiner_version_effective,
)
from pyproj import Transformer
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature

# Nom du fichier source analyse
FICHIER_SOURCE: str = "RPD_GeometrieSupplementaire_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_z_ign.geojson"

# Seuil d'ecart altimetrique au-dela duquel un sommet est signale (metres)
SEUIL_ECART: float = 0.40

# Niveau de priorite affecte aux sommets signales
PRIORITE_ANOMALIE: str = "information"

# Le fichier de detection de version (RPD_PointLeveOuvrageReseau_Reco) et le
# wrapper determiner_version_effective sont factorises dans E204.

# Filtrage specifique a la version 1.1. Memes valeurs que dans E205, definies
# localement pour ne pas dependre du module E205 (qui charge shapely).
CHAMP_STATUT: str = "Statut"
VALEUR_STATUT_V1_1: str = "UnderCommissionning"

# URL de l'API IGN altimetrie
URL_API_IGN: str = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"

# Sources IGN par ordre de priorite (fallback)
SOURCES_IGN: tuple[tuple[str, str], ...] = (
    ("ign_lidar_hd_mnt_mono_wld", "LIDAR HD IGN"),
    ("ign_rge_alti_wld", "RGE Alti IGN"),
)

# Limite de points par requete API
MAX_POINTS_PAR_REQUETE: int = 5000

# Timeout des requetes HTTP (secondes)
TIMEOUT_REQUETE: int = 30

# Valeur sentinelle renvoyee par l'API IGN quand l'altitude est inconnue
_Z_INCONNU_IGN: float = -99999.0

# --------------------------------------------------------------------------- #
# Conversion de coordonnees Lambert 93 -> WGS84
# --------------------------------------------------------------------------- #

# Transformer instancie une seule fois au chargement du module (thread-safe).
_TRANSFORMER = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)


def convertir_lambert93_vers_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convertit des coordonnees Lambert 93 (EPSG:2154) vers WGS84 (lon, lat)."""
    lon, lat = _TRANSFORMER.transform(x, y)
    return (lon, lat)


# --------------------------------------------------------------------------- #
# Appel API IGN
# --------------------------------------------------------------------------- #


def _requeter_api_ign(
    longitudes: list[float],
    latitudes: list[float],
    source_id: str,
) -> list[dict[str, Any]] | None:
    """Interroge l'API IGN pour recuperer les altitudes d'un lot de points.

    Retourne la liste des elevations ou None en cas d'erreur.
    """
    params = {
        "lon": "|".join(str(v) for v in longitudes),
        "lat": "|".join(str(v) for v in latitudes),
        "resource": source_id,
        "delimiter": "|",
        "indent": "false",
        "measures": "true",
        "zonly": "false",
    }

    try:
        reponse = requests.get(URL_API_IGN, params=params, timeout=TIMEOUT_REQUETE)
        reponse.raise_for_status()
        donnees = reponse.json()
        return donnees.get("elevations")
    except (requests.RequestException, json.JSONDecodeError, TimeoutError):
        return None


def _extraire_altitudes_reponse(
    elevations: list[dict[str, Any]],
) -> tuple[list[float | None], bool]:
    """Extrait les altitudes valides d'une reponse API IGN.

    Retourne (altitudes, au_moins_une_valide).
    """
    altitudes: list[float | None] = []
    valide = False

    for elev in elevations:
        z = elev.get("z")
        if isinstance(z, (int, float)) and z != _Z_INCONNU_IGN:
            altitudes.append(float(z))
            valide = True
        else:
            altitudes.append(None)

    return altitudes, valide


def _decouper_lots(sequence: Sequence[Any], taille: int) -> Iterator[Sequence[Any]]:
    """Decoupe une sequence en lots de taille fixe."""
    for debut in range(0, len(sequence), taille):
        yield sequence[debut : debut + taille]


def _requeter_lots_source(
    points_wgs84: list[tuple[float, float]],
    source_id: str,
) -> list[float | None] | None:
    """Interroge l'API IGN par lots pour une source donnee.

    Retourne la liste complete des altitudes ou None si la source echoue.
    """
    altitudes: list[float | None] = [None] * len(points_wgs84)
    offset = 0

    for lot in _decouper_lots(points_wgs84, MAX_POINTS_PAR_REQUETE):
        lons = [pt[0] for pt in lot]
        lats = [pt[1] for pt in lot]

        elevations = _requeter_api_ign(lons, lats, source_id)
        if elevations is None:
            return None

        alts_lot, lot_valide = _extraire_altitudes_reponse(elevations)
        if not lot_valide:
            return None

        for i, alt in enumerate(alts_lot):
            altitudes[offset + i] = alt
        offset += len(lot)

    return altitudes


def recuperer_altitudes_ign(
    points_wgs84: list[tuple[float, float]],
) -> tuple[list[float | None], str]:
    """Recupere les altitudes IGN pour une liste de points WGS84 (lon, lat).

    Gere le decoupage en lots et le fallback sur les sources IGN.
    Retourne (altitudes, source_utilisee).
    """
    for source_id, source_nom in SOURCES_IGN:
        altitudes = _requeter_lots_source(points_wgs84, source_id)
        if altitudes is not None:
            return altitudes, source_nom

    return [None] * len(points_wgs84), ""


# --------------------------------------------------------------------------- #
# Extraction des sommets et comparaison
# --------------------------------------------------------------------------- #


def _aplatir_anneaux(
    anneaux: Sequence[Sequence[Sequence[float]]],
) -> list[tuple[int, Sequence[float]]]:
    """Indexe sequentiellement les points d'une liste d'anneaux."""
    resultat: list[tuple[int, Sequence[float]]] = []
    indice = 0
    for anneau in anneaux:
        for point in anneau:
            resultat.append((indice, point))
            indice += 1
    return resultat


def _aplatir_polygones(
    polygones: Sequence[Sequence[Sequence[Sequence[float]]]],
) -> list[tuple[int, Sequence[float]]]:
    """Indexe sequentiellement les points d'une liste de polygones."""
    anneaux: list[list[Sequence[float]]] = []
    for polygone in polygones:
        anneaux.extend(list(anneau) for anneau in polygone)
    return _aplatir_anneaux(anneaux)


# Correspondance type de geometrie -> extracteur indexe (specifique au module IGN)
_EXTRACTEURS: dict[str, Any] = {
    "Point": lambda c: [(0, c)],
    "LineString": lambda c: list(enumerate(c)),
    "MultiPoint": lambda c: list(enumerate(c)),
    "Polygon": _aplatir_anneaux,
    "MultiLineString": _aplatir_anneaux,
    "MultiPolygon": _aplatir_polygones,
}


def extraire_sommets(
    features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extrait tous les sommets 3D de la collection avec leurs metadonnees.

    Retourne une liste de dictionnaires contenant l'identifiant de l'entite,
    l'indice du sommet et ses coordonnees.
    """
    sommets: list[dict[str, Any]] = []

    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue

        extracteur = _EXTRACTEURS.get(geometrie.get("type", ""))
        if extracteur is None:
            continue

        coordonnees = geometrie.get("coordinates")
        if coordonnees is None:
            continue

        identifiant = obtenir_id_feature(feature)
        type_geom = geometrie.get("type", "inconnu")

        for indice, point in extracteur(coordonnees):
            if len(point) < 3:
                continue
            sommets.append(
                {
                    "id_entite": identifiant,
                    "type_geometrie": type_geom,
                    "indice_sommet": indice,
                    "coordonnees": list(point[:3]),
                }
            )

    return sommets


def convertir_sommets_wgs84(
    sommets: list[dict[str, Any]],
) -> list[tuple[float, float]]:
    """Convertit les coordonnees Lambert 93 des sommets en WGS84.

    Retourne une liste de tuples (longitude, latitude) dans le meme ordre.
    """
    convertir = convertir_lambert93_vers_wgs84
    return [convertir(s["coordonnees"][0], s["coordonnees"][1]) for s in sommets]


def comparer_altitudes(
    sommets: list[dict[str, Any]],
    altitudes_ign: list[float | None],
    source_ign: str,
) -> list[dict[str, Any]]:
    """Compare les altitudes des sommets avec les altitudes IGN.

    Retourne la liste des anomalies (ecart >= SEUIL_ECART).
    """
    anomalies: list[dict[str, Any]] = []
    fabs = math.fabs

    for i, sommet in enumerate(sommets):
        alt_ign = altitudes_ign[i] if i < len(altitudes_ign) else None
        if alt_ign is None:
            continue

        alt_geojson = sommet["coordonnees"][2]
        ecart = fabs(alt_geojson - alt_ign)

        if ecart < SEUIL_ECART:
            continue

        anomalies.append(
            {
                "id_entite": sommet["id_entite"],
                "type_geometrie": sommet["type_geometrie"],
                "indice_sommet": sommet["indice_sommet"],
                "coordonnees": sommet["coordonnees"],
                "altitude_geojson": round(alt_geojson, 4),
                "altitude_ign": round(alt_ign, 4),
                "ecart_m": round(ecart, 4),
                "source_ign": source_ign,
            }
        )

    return anomalies


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des sommets en ecart altimetrique IGN.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "indice_sommet": a["indice_sommet"],
                "altitude_geojson_m": a["altitude_geojson"],
                "altitude_ign_m": a["altitude_ign"],
                "ecart_m": a["ecart_m"],
                "seuil_m": SEUIL_ECART,
                "source_ign": a["source_ign"],
                "type_anomalie": "ecart_altimetrique_ign",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": {
                "type": "Point",
                "coordinates": a["coordonnees"],
            },
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


# --------------------------------------------------------------------------- #
# Gestion des versions RecoStaR
# --------------------------------------------------------------------------- #


def filtrer_features_selon_statut(
    features: list[dict[str, Any]],
    version: str,
) -> list[dict[str, Any]]:
    """Restreint les entites a controler en fonction de la version RecoStaR.

    En version 1.1, seules les entites dont le champ Statut vaut
    VALEUR_STATUT_V1_1 sont conservees. Pour toute autre version, la liste
    d'origine est retournee telle quelle (comportement historique d'E203),
    sans copie afin d'eviter une duplication memoire inutile.
    """
    if version != "1.1":
        return features
    return [
        feature for feature in features if (feature.get("properties") or {}).get(CHAMP_STATUT) == VALEUR_STATUT_V1_1
    ]


# --------------------------------------------------------------------------- #
# Orchestration CLI
# --------------------------------------------------------------------------- #


def _analyser_sommets(
    features: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]], str]:
    """Extrait les sommets 3D, interroge l'API IGN et compare les altitudes.

    Retourne (nombre_sommets, anomalies, source_ign). Si aucun sommet 3D n'est
    exploitable, retourne (0, [], "") sans interroger l'API.
    """
    sommets = extraire_sommets(features)
    if not sommets:
        return 0, [], ""
    points_wgs84 = convertir_sommets_wgs84(sommets)
    altitudes_ign, source_ign = recuperer_altitudes_ign(points_wgs84)
    anomalies = comparer_altitudes(sommets, altitudes_ign, source_ign)
    return len(sommets), anomalies, source_ign


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle altimetrique IGN en mode CLI.

    Charge le fichier source, resout la version RecoStaR, restreint les entites
    a controler selon le Statut en v1.1, extrait les sommets, interroge l'API
    IGN et ecrit le fichier d'ecarts.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    chemin_source = os.path.join(repertoire_resolu, FICHIER_SOURCE)
    collection = lire_geojson(chemin_source)
    if collection is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_SOURCE} introuvable dans {repertoire_resolu}",
        }

    features = collection.get("features", [])
    crs = collection.get("crs")
    if not features:
        return {"succes": False, "erreur": "Aucune entite dans le fichier source"}

    version_effective = determiner_version_effective(repertoire_resolu, version)
    features_a_controler = filtrer_features_selon_statut(features, version_effective)

    nombre_sommets, anomalies, source_ign = _analyser_sommets(features_a_controler)
    # Hors v1.1, l'absence de sommet 3D reste une anomalie de donnees (comportement
    # historique). En v1.1, l'absence d'entite UnderCommissionning est nominale.
    if nombre_sommets == 0 and version_effective != "1.1":
        return {"succes": False, "erreur": "Aucun sommet 3D exploitable"}

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "nombre_sommets": nombre_sommets,
        "nombre_anomalies": len(anomalies),
        "source_ign": source_ign,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle altimetrique IGN."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(description="Controle altimetrique IGN des geometries supplementaires")
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
            "proprietes GeoJSON (TypeLeve dans PointLeve) ; sinon imposer "
            "'1.0' ou '1.1'."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
