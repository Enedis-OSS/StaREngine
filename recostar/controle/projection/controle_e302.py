"""
Controle de coherence geometrique des entites de geometrie supplementaire.

Verifie que la superficie de chaque entite presente dans le fichier
RPD_GeometrieSupplementaire_Reco.geojson ne depasse pas 100 m². Au-dela,
l'entite est signalee comme anomalie bloquante.

La superficie est calculee par la formule de Shoelace (Gauss), applicable
aux coordonnees projetees en metres. Les geometries non surfaciques
(Point, LineString, etc.) sont ignorees.

Usage CLI :
    python controle_e302.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_geometrie_supplementaire.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from utils_geojson import (
    ecrire_geojson,
    lire_geojson,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON cible analyse par ce controle
NOM_FICHIER_CIBLE: str = "RPD_GeometrieSupplementaire_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_geometrie_supplementaire.geojson"

# Niveau de priorite affecte aux entites signalees
PRIORITE_ANOMALIE: str = "bloquant"

# Seuil de superficie au-dela duquel une entite est consideree non coherente
SEUIL_AIRE_M2: float = 100.0


def _aire_anneau(anneau: list[list[float]]) -> float:
    """Calcule l'aire d'un anneau par la formule de Shoelace.

    Applicable aux coordonnees projetees (en metres). Un anneau GeoJSON est
    ferme (dernier point == premier point), ce qui n'affecte pas le resultat.
    """
    n = len(anneau)
    return abs(sum(anneau[i][0] * anneau[(i + 1) % n][1] - anneau[(i + 1) % n][0] * anneau[i][1] for i in range(n))) / 2


def _aire_polygon(coordonnees: list[Any]) -> float:
    """Calcule l'aire d'un Polygon en soustrayant les trous a l'anneau exterieur."""
    aire = _aire_anneau(coordonnees[0])
    for trou in coordonnees[1:]:
        aire -= _aire_anneau(trou)
    return max(aire, 0.0)


def _aire_multipolygon(coordonnees: list[Any]) -> float:
    """Calcule l'aire totale d'un MultiPolygon (somme des polygones)."""
    return sum(_aire_polygon(poly) for poly in coordonnees)


# Correspondance type de geometrie surfacique -> calculateur d'aire
_CALCULATEURS_AIRE: dict[str, Any] = {
    "Polygon": _aire_polygon,
    "MultiPolygon": _aire_multipolygon,
}


def calculer_aire_m2(geometrie: dict[str, Any]) -> float | None:
    """Calcule la superficie d'une geometrie surfacique en m² via Shoelace.

    Retourne None pour les geometries non surfaciques (Point, LineString, etc.)
    ou si les coordonnees sont absentes.
    """
    calculateur = _CALCULATEURS_AIRE.get(geometrie.get("type", ""))
    if calculateur is None:
        return None
    coordonnees = geometrie.get("coordinates")
    if not coordonnees:
        return None
    return calculateur(coordonnees)


def detecter_entites_trop_grandes(
    features: list[dict[str, Any]],
    nom_fichier: str,
) -> tuple[list[dict[str, Any]], int]:
    """Signale les entites surfaciques dont la superficie depasse le seuil.

    Les entites sans geometrie ou de type non surfacique sont ignorees.
    Retourne (anomalies, nb_entites_analysees).
    """
    anomalies: list[dict[str, Any]] = []
    nb_analysees = 0
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        aire = calculer_aire_m2(geometrie)
        if aire is None:
            continue
        nb_analysees += 1
        if aire > SEUIL_AIRE_M2:
            anomalies.append(
                {
                    "fichier_source": nom_fichier,
                    "id_entite": obtenir_id_feature(feature),
                    "type_geometrie": geometrie.get("type", "inconnu"),
                    "geometrie": geometrie,
                    "aire_m2": round(aire, 2),
                }
            )
    return anomalies, nb_analysees


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites dont la superficie est excessive.

    La geometrie originale est conservee pour la localisation dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "aire_m2": a["aire_m2"],
                "seuil_m2": SEUIL_AIRE_M2,
                "type_anomalie": "aire_excessive",
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


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de superficie des geometries supplementaires.

    Charge le fichier RPD_GeometrieSupplementaire_Reco.geojson du repertoire,
    calcule la superficie de chaque entite surfacique et signale celles dont
    l'aire depasse le seuil de 100 m².
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    chemin_fichier = os.path.join(repertoire_resolu, NOM_FICHIER_CIBLE)
    if not os.path.isfile(chemin_fichier):
        return {
            "succes": False,
            "erreur": f"Fichier {NOM_FICHIER_CIBLE} introuvable dans {repertoire_resolu}",
        }

    collection = lire_geojson(chemin_fichier)
    if collection is None:
        return {
            "succes": False,
            "erreur": f"Impossible de lire {NOM_FICHIER_CIBLE}",
        }

    features = collection.get("features", [])
    crs = collection.get("crs")
    anomalies, nb_analysees = detecter_entites_trop_grandes(features, NOM_FICHIER_CIBLE)

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "entites_analysees": nb_analysees,
        "seuil_aire_m2": SEUIL_AIRE_M2,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de superficie des geometries supplementaires."""
    parseur = argparse.ArgumentParser(
        description=(f"Controle de superficie de {NOM_FICHIER_CIBLE} (seuil : {SEUIL_AIRE_M2} m²)")
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant le fichier GeoJSON cible",
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
