"""
Controle de coherence des projections des fichiers GeoJSON.

Verifie que tous les fichiers GeoJSON d'un repertoire partagent le meme
systeme de reference de coordonnees (CRS). Le CRS de reference est determine
par vote majoritaire parmi les fichiers analyses. Les entites issues de
fichiers dont le CRS differe du CRS de reference sont exportees dans un
fichier GeoJSON d'ecarts.

Usage CLI :
    python controle_proj_ensemble.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecart_proj_ensemble.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any, Mapping

from controle_proj import (
    _extraire_nom_crs_brut,
    _obtenir_id_feature,
    extraire_code_epsg,
    lire_geojson,
    lister_fichiers_geojson,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecart_proj_ensemble.geojson"

# Niveau de priorite affecte aux entites non conformes
PRIORITE_ANOMALIE: str = "bloquant"

# Valeur utilisee quand le CRS est absent ou non interpretable
_CRS_ABSENT: str = "absent"


# --------------------------------------------------------------------------- #
# Determination du CRS de reference
# --------------------------------------------------------------------------- #


def determiner_crs_reference(
    codes_par_fichier: Mapping[str, int | None],
) -> int | None:
    """Determine le CRS de reference par vote majoritaire.

    Seuls les codes EPSG valides participent au vote. Retourne le code
    le plus frequent, ou None si aucun code n'est disponible.
    """
    codes_valides = [c for c in codes_par_fichier.values() if c is not None]
    if not codes_valides:
        return None

    compteur = Counter(codes_valides)
    return compteur.most_common(1)[0][0]


def formater_crs_reference(code_reference: int | None) -> str:
    """Formate le code EPSG de reference en chaine lisible."""
    if code_reference is None:
        return _CRS_ABSENT
    return f"EPSG:{code_reference}"


# --------------------------------------------------------------------------- #
# Collecte des entites en ecart
# --------------------------------------------------------------------------- #


def _collecter_entites_ecart(
    features: list[dict[str, Any]],
    nom_fichier: str,
    crs_brut: str,
    crs_reference_brut: str,
) -> list[dict[str, Any]]:
    """Collecte les entites d'un fichier en ecart pour le rapport.

    Chaque entite conserve sa geometrie d'origine et recoit les
    metadonnees de controle (CRS detecte et CRS de reference).
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
                "crs_reference": crs_reference_brut,
                "geometrie": geometrie,
            }
        )
    return entites


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
                "crs_reference": a["crs_reference"],
                "type_anomalie": "projection_incoherente",
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
    """Execute le controle de coherence des projections en mode CLI.

    Parcourt tous les GeoJSON du repertoire, determine le CRS majoritaire
    et signale les fichiers dont le CRS differe.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire

    fichiers = lister_fichiers_geojson(repertoire)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    # Phase 1 : extraction des CRS de tous les fichiers
    codes_par_fichier: dict[str, int | None] = {}
    collections_par_fichier: dict[str, dict[str, Any]] = {}
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        collections_par_fichier[nom_fichier] = collection
        codes_par_fichier[nom_fichier] = extraire_code_epsg(collection)
        if crs is None:
            crs = collection.get("crs")

    if not codes_par_fichier:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON lisible"}

    # Phase 2 : determination du CRS de reference par vote majoritaire
    code_reference = determiner_crs_reference(codes_par_fichier)
    crs_reference_brut = formater_crs_reference(code_reference)

    # Phase 3 : identification des fichiers en ecart
    toutes_anomalies: list[dict[str, Any]] = []
    fichiers_conformes = 0
    fichiers_non_conformes = 0
    detail_fichiers: list[dict[str, Any]] = []

    for nom_fichier, code_epsg in codes_par_fichier.items():
        conforme = code_epsg == code_reference
        crs_brut = _extraire_nom_crs_brut(collections_par_fichier[nom_fichier])

        detail_fichiers.append(
            {
                "fichier": nom_fichier,
                "conforme": conforme,
                "code_epsg": code_epsg,
                "crs_brut": crs_brut,
            }
        )

        if conforme:
            fichiers_conformes += 1
            continue

        fichiers_non_conformes += 1
        features = collections_par_fichier[nom_fichier].get("features", [])
        entites = _collecter_entites_ecart(
            features, nom_fichier, crs_brut, crs_reference_brut
        )
        toutes_anomalies.extend(entites)

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "fichiers_analyses": len(codes_par_fichier),
        "fichiers_conformes": fichiers_conformes,
        "fichiers_non_conformes": fichiers_non_conformes,
        "nombre_anomalies": len(toutes_anomalies),
        "crs_reference": crs_reference_brut,
        "sortie": chemin_sortie,
        "detail": detail_fichiers,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence des projections."""
    parseur = argparse.ArgumentParser(
        description="Controle de coherence des projections des fichiers GeoJSON"
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
