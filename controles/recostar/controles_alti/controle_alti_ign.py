"""
Controle altimetrique des geometries supplementaires via l'API IGN.

Compare les altitudes Z des sommets du fichier RPD_GeometrieSupplementaire_Reco
avec les altitudes de reference fournies par l'API altimetrique IGN. Les sommets
dont l'ecart depasse le seuil de 40 cm sont signales et exportes dans un fichier
GeoJSON d'ecarts.

Les coordonnees du projet sont en Lambert 93 (EPSG:2154). La conversion vers
WGS84 est effectuee en interne avant chaque appel a l'API IGN.

Usage CLI :
    python controle_alti_ign.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_z_ign.geojson
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Iterator, Sequence

import requests

# Nom du fichier source analyse
FICHIER_SOURCE: str = "RPD_GeometrieSupplementaire_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_z_ign.geojson"

# Seuil d'ecart altimetrique au-dela duquel un sommet est signale (metres)
SEUIL_ECART: float = 0.40

# Niveau de priorite affecte aux sommets signales
PRIORITE_ANOMALIE: str = "information"

# URL de l'API IGN altimetrie
URL_API_IGN: str = (
    "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
)

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

# Parametres de la projection Lambert 93 (EPSG:2154)
_LAMBERT93_PARAMS = {
    "lon_0": 3.0,
    "lat_0": 46.5,
    "lat_1": 49.0,
    "lat_2": 44.0,
    "x_0": 700000.0,
    "y_0": 6600000.0,
    "a": 6378137.0,
    "f": 1.0 / 298.257222101,
}


# --------------------------------------------------------------------------- #
# Conversion de coordonnees Lambert 93 -> WGS84
# --------------------------------------------------------------------------- #


def _calculer_constantes_lambert() -> dict[str, float]:
    """Precalcule les constantes de la projection Lambert 93.

    Appellee une seule fois au chargement du module pour eviter
    les recalculs dans la boucle de conversion.
    """
    p = _LAMBERT93_PARAMS
    a: float = p["a"]
    f: float = p["f"]
    e = math.sqrt(2.0 * f - f * f)

    phi_1 = math.radians(p["lat_1"])
    phi_2 = math.radians(p["lat_2"])
    phi_0 = math.radians(p["lat_0"])
    lambda_0 = math.radians(p["lon_0"])

    sin_phi_1, sin_phi_2 = math.sin(phi_1), math.sin(phi_2)
    cos_phi_1, cos_phi_2 = math.cos(phi_1), math.cos(phi_2)

    m1 = cos_phi_1 / math.sqrt(1.0 - e * e * sin_phi_1 * sin_phi_1)
    m2 = cos_phi_2 / math.sqrt(1.0 - e * e * sin_phi_2 * sin_phi_2)

    def _t(phi: float) -> float:
        e_sin = e * math.sin(phi)
        return math.tan(math.pi / 4.0 - phi / 2.0) / (
            (1.0 - e_sin) / (1.0 + e_sin)
        ) ** (e / 2.0)

    t1, t2, t0 = _t(phi_1), _t(phi_2), _t(phi_0)

    n = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
    gf = m1 / (n * t1**n)
    rho_0 = a * gf * t0**n

    return {
        "a": a,
        "e": e,
        "n": n,
        "gf": gf,
        "rho_0": rho_0,
        "lambda_0": lambda_0,
        "x_0": p["x_0"],
        "y_0": p["y_0"],
    }


# Constantes precalculees au chargement du module
_CST = _calculer_constantes_lambert()


def convertir_lambert93_vers_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convertit des coordonnees Lambert 93 (EPSG:2154) vers WGS84 (lon, lat).

    Utilise une methode iterative basee sur la projection conique conforme.
    Les constantes de projection sont precalculees au chargement du module.
    """
    a, e, n = _CST["a"], _CST["e"], _CST["n"]
    gf, rho_0 = _CST["gf"], _CST["rho_0"]

    dx = x - _CST["x_0"]
    dy = _CST["y_0"] - y + rho_0
    rho = math.copysign(math.hypot(dx, dy), n)
    theta = math.atan2(dx, dy)
    t = (rho / (a * gf)) ** (1.0 / n)

    lon = theta / n + _CST["lambda_0"]

    # Latitude par iteration (methode de Newton)
    phi = math.pi / 2.0 - 2.0 * math.atan(t)
    for _ in range(15):
        e_sin_phi = e * math.sin(phi)
        phi_new = math.pi / 2.0 - 2.0 * math.atan(
            t * ((1.0 - e_sin_phi) / (1.0 + e_sin_phi)) ** (e / 2.0)
        )
        if math.fabs(phi_new - phi) < 1e-12:
            break
        phi = phi_new

    return (math.degrees(lon), math.degrees(phi))


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


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu ou None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def _obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None


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


# Correspondance type de geometrie -> fonction d'extraction indexee
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

        identifiant = _obtenir_id_feature(feature)
        type_geom = geometrie.get("type", "inconnu")

        for indice, point in extracteur(coordonnees):
            # Seuls les sommets 3D sont pertinents pour le controle altimetrique
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


def _ecrire_geojson(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un FeatureCollection GeoJSON sur disque."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Orchestration CLI
# --------------------------------------------------------------------------- #


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle altimetrique IGN en mode CLI.

    Charge le fichier source, extrait les sommets, interroge l'API IGN
    et ecrit le fichier d'ecarts.
    """
    chemin_source = os.path.join(repertoire, FICHIER_SOURCE)
    collection = lire_geojson(chemin_source)
    if collection is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_SOURCE} introuvable dans {repertoire}",
        }

    features = collection.get("features", [])
    crs = collection.get("crs")
    if not features:
        return {"succes": False, "erreur": "Aucune entite dans le fichier source"}

    dossier_sortie = sortie if sortie is not None else repertoire

    # Extraction et conversion des sommets
    sommets = extraire_sommets(features)
    if not sommets:
        return {"succes": False, "erreur": "Aucun sommet 3D exploitable"}

    points_wgs84 = convertir_sommets_wgs84(sommets)

    # Interrogation de l'API IGN
    altitudes_ign, source_ign = recuperer_altitudes_ign(points_wgs84)

    # Comparaison et construction du fichier de sortie
    anomalies = comparer_altitudes(sommets, altitudes_ign, source_ign)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_sommets": len(sommets),
        "nombre_anomalies": len(anomalies),
        "source_ign": source_ign,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle altimetrique IGN."""
    parseur = argparse.ArgumentParser(
        description="Controle altimetrique IGN des geometries supplementaires"
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
    arguments = parseur.parse_args()

    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
