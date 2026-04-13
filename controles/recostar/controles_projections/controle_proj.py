"""
Controle des projections des fichiers GeoJSON.

Verifie que le systeme de reference de coordonnees (CRS) declare dans chaque
fichier GeoJSON appartient a la liste des projections autorisees. Les entites
issues de fichiers dont la projection est absente ou non conforme sont
exportees dans un fichier GeoJSON d'ecarts.

Usage CLI :
    python controle_proj.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_proj.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_proj.geojson"

# Niveau de priorite affecte aux entites non conformes
PRIORITE_ANOMALIE: str = "bloquant"

# Extension des fichiers analyses
EXTENSION_GEOJSON: str = ".geojson"

# Prefixes des fichiers d'ecarts (exclus de l'analyse)
PREFIXES_ECARTS: tuple[str, str] = ("ecarts_", "ecart_")

# Projections autorisees : code EPSG -> alias lisible
PROJECTIONS_AUTORISEES: dict[int, str] = {
    3942: "CC42",
    3943: "CC43",
    3944: "CC44",
    3945: "CC45",
    3946: "CC46",
    3947: "CC47",
    3948: "CC48",
    3949: "CC49",
    3950: "CC50",
    9842: "CC42 V2b",
    9843: "CC43 V2b",
    9844: "CC44 V2b",
    9845: "CC45 V2b",
    9846: "CC46 V2b",
    9847: "CC47 V2b",
    9848: "CC48 V2b",
    9849: "CC49 V2b",
    9850: "CC50 V2b",
    2154: "RGF93LAMB93",
    9794: "RGF93LAMB93 V2b",
    5490: "RGAF09UTM20",
    2972: "RGFG95UTM22",
    2975: "RGR92UTM40S",
    4471: "RGM04UTM38S",
    4467: "RGSPM06U21",
}

# Set des codes autorises pour verification d'appartenance en O(1)
_CODES_AUTORISES: frozenset[int] = frozenset(PROJECTIONS_AUTORISEES)

# Expressions regulieres precompilees pour l'extraction du code EPSG
_PATTERN_URN_EPSG: re.Pattern[str] = re.compile(
    r"urn:ogc:def:crs:EPSG::(\d+)", re.IGNORECASE
)
_PATTERN_EPSG_COURT: re.Pattern[str] = re.compile(r"^EPSG:(\d+)$", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Lecture et listing des fichiers GeoJSON
# --------------------------------------------------------------------------- #


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu ou None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def lister_fichiers_geojson(repertoire: str) -> list[str]:
    """Liste les fichiers GeoJSON eligibles dans le repertoire.

    Exclut les fichiers d'ecarts (prefixes 'ecarts_' et 'ecart_') pour eviter
    l'analyse des sorties de controles precedents.
    """
    fichiers: list[str] = []
    for nom in sorted(os.listdir(repertoire)):
        if not nom.lower().endswith(EXTENSION_GEOJSON):
            continue
        if nom.lower().startswith(PREFIXES_ECARTS):
            continue
        fichiers.append(nom)
    return fichiers


# --------------------------------------------------------------------------- #
# Extraction et verification du CRS
# --------------------------------------------------------------------------- #


def extraire_code_epsg(collection: dict[str, Any]) -> int | None:
    """Extrait le code EPSG du CRS d'une collection GeoJSON.

    Gere les formats :
    - urn:ogc:def:crs:EPSG::<code> (URN OGC standard)
    - EPSG:<code> (format court)

    Retourne le code EPSG en entier ou None si absent ou non interpretable.
    """
    crs = collection.get("crs")
    if not isinstance(crs, dict):
        return None

    proprietes = crs.get("properties")
    if not isinstance(proprietes, dict):
        return None

    nom_crs = proprietes.get("name")
    if not isinstance(nom_crs, str):
        return None

    # Tentative d'extraction via URN OGC
    correspondance = _PATTERN_URN_EPSG.search(nom_crs)
    if correspondance is not None:
        return int(correspondance.group(1))

    # Tentative d'extraction via format court
    correspondance = _PATTERN_EPSG_COURT.match(nom_crs)
    if correspondance is not None:
        return int(correspondance.group(1))

    return None


def _extraire_nom_crs_brut(collection: dict[str, Any]) -> str:
    """Extrait la valeur brute du champ CRS pour le rapport d'ecart.

    Retourne la chaine du CRS tel que declare dans le fichier,
    ou 'absent' si le CRS n'est pas defini.
    """
    crs = collection.get("crs")
    if not isinstance(crs, dict):
        return "absent"

    proprietes = crs.get("properties")
    if not isinstance(proprietes, dict):
        return "absent"

    nom_crs = proprietes.get("name")
    if isinstance(nom_crs, str):
        return nom_crs

    return "absent"


def est_projection_autorisee(code_epsg: int) -> bool:
    """Verifie si un code EPSG appartient aux projections autorisees."""
    return code_epsg in _CODES_AUTORISES


# --------------------------------------------------------------------------- #
# Controle de projection par fichier
# --------------------------------------------------------------------------- #


def _obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None


def _collecter_entites_ecart(
    features: list[dict[str, Any]],
    nom_fichier: str,
    crs_brut: str,
) -> list[dict[str, Any]]:
    """Collecte les entites d'un fichier non conforme pour le rapport d'ecarts.

    Chaque entite conserve sa geometrie d'origine et recoit les
    metadonnees de controle dans ses proprietes.
    """
    entites: list[dict[str, Any]] = []
    for feature in features:
        geometrie = feature.get("geometry")
        identifiant = _obtenir_id_feature(feature)
        entites.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": identifiant,
                "crs_detecte": crs_brut,
                "geometrie": geometrie,
            }
        )
    return entites


def _construire_resultat_non_conforme(
    collection: dict[str, Any],
    nom_fichier: str,
    crs_brut: str,
    code_epsg: int | None,
    message: str,
) -> dict[str, Any]:
    """Construit le resultat de controle pour un fichier non conforme.

    Collecte toutes les entites du fichier comme ecarts.
    """
    features = collection.get("features", [])
    entites_ecart = _collecter_entites_ecart(features, nom_fichier, crs_brut)

    return {
        "conforme": False,
        "code_epsg": code_epsg,
        "alias": None,
        "crs_brut": crs_brut,
        "message": message,
        "entites_ecart": entites_ecart,
    }


def controler_projection_fichier(
    collection: dict[str, Any],
    nom_fichier: str,
) -> dict[str, Any]:
    """Controle la projection d'un fichier GeoJSON.

    Retourne un dictionnaire contenant :
    - conforme : True si la projection est autorisee
    - code_epsg : code EPSG detecte (ou None)
    - alias : alias de la projection (ou None)
    - crs_brut : valeur brute du CRS
    - message : description du resultat
    - entites_ecart : liste des entites en ecart (vide si conforme)
    """
    code_epsg = extraire_code_epsg(collection)
    crs_brut = _extraire_nom_crs_brut(collection)

    if code_epsg is None:
        return _construire_resultat_non_conforme(
            collection,
            nom_fichier,
            crs_brut,
            None,
            "CRS absent ou non interpretable",
        )

    if not est_projection_autorisee(code_epsg):
        return _construire_resultat_non_conforme(
            collection,
            nom_fichier,
            crs_brut,
            code_epsg,
            f"EPSG:{code_epsg} non autorise",
        )

    alias = PROJECTIONS_AUTORISEES[code_epsg]
    return {
        "conforme": True,
        "code_epsg": code_epsg,
        "alias": alias,
        "crs_brut": crs_brut,
        "message": f"Projection conforme : EPSG:{code_epsg} ({alias})",
        "entites_ecart": [],
    }


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites en ecart de projection.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "crs_detecte": a["crs_detecte"],
                "type_anomalie": "projection_non_conforme",
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
    """Execute le controle des projections en mode CLI.

    Parcourt tous les GeoJSON du repertoire, verifie leur CRS
    et ecrit le fichier d'ecarts.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire

    fichiers = lister_fichiers_geojson(repertoire)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    toutes_anomalies: list[dict[str, Any]] = []
    fichiers_conformes = 0
    fichiers_non_conformes = 0
    detail_fichiers: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue

        if crs is None:
            crs = collection.get("crs")

        resultat = controler_projection_fichier(collection, nom_fichier)

        detail_fichiers.append(
            {
                "fichier": nom_fichier,
                "conforme": resultat["conforme"],
                "code_epsg": resultat["code_epsg"],
                "alias": resultat["alias"],
                "message": resultat["message"],
            }
        )

        if resultat["conforme"]:
            fichiers_conformes += 1
        else:
            fichiers_non_conformes += 1
            toutes_anomalies.extend(resultat["entites_ecart"])

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "fichiers_analyses": fichiers_conformes + fichiers_non_conformes,
        "fichiers_conformes": fichiers_conformes,
        "fichiers_non_conformes": fichiers_non_conformes,
        "nombre_anomalies": len(toutes_anomalies),
        "sortie": chemin_sortie,
        "detail": detail_fichiers,
    }


def main() -> None:
    """Point d'entree CLI du controle des projections."""
    parseur = argparse.ArgumentParser(
        description="Controle des projections des fichiers GeoJSON"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON a analyser",
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
