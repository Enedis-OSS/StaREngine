"""
Controle E209 : detection des points de leve orphelins.

Verifie que chaque entite RPD_PointLeveOuvrageReseau_Reco est en superposition
planimetrique (2D) avec au moins une entite provenant d'un AUTRE fichier GeoJSON
du jeu de donnees RecoStaR. Un point de leve qui n'est superpose a aucun objet
metier d'un autre fichier est considere comme orphelin et signale en anomalie
mineure : l'ecart est reporte sans declasser la famille.

Les entites du fichier RPD_PointLeveOuvrageReseau_Reco lui-meme ne sont pas
prises en compte dans la recherche de superposition ; les fichiers d'ecarts
(prefixe « ecarts_ ») sont egalement exclus.

Mecanisme : toutes les geometries des autres fichiers sont chargees en 2D et
indexees dans un unique STRtree Shapely. Chaque point de leve est ensuite
interroge (predicat « dwithin », tolerance TOLERANCE_SUPERPOSITION) ; l'absence
de resultat constitue une anomalie E209. C'est le meme moteur de superposition
que E205, applique en sens inverse (l'arbre contient les objets metier, les
points sont les requetes).

Fichier source :
  - RPD_PointLeveOuvrageReseau_Reco.geojson (points de leve controles)

Usage CLI :
    python controle_e209.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e209_points_leve_orphelins.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from shapely import STRtree, force_2d
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Tolerance planimetrique partagee avec E205 : meme cause (arrondi millimetrique
# de la posList GML), donc meme valeur, definie une seule fois.
from utils_geometrie import TOLERANCE_SUPERPOSITION

# Fichier des points de leve controles (exclu de la recherche de superposition)
FICHIER_SOURCE: str = "RPD_PointLeveOuvrageReseau_Reco.geojson"

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e209_points_leve_orphelins.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E209"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "point_leve_orphelin": ("Le point levé n'est superposé à aucune autre entité du jeu de données."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


# Niveau de priorite : mineur — l'ecart est signale et compte dans le rapport,
# mais ne declasse pas la famille (cf. PRIORITES_DECLASSANTES dans
# synthese_controles).
PRIORITE_ANOMALIE: str = "mineur"


# ---------------------------------------------------------------------------
# Chargement des geometries en 2D
# ---------------------------------------------------------------------------


def _charger_geometries_2d(features: list[dict[str, Any]]) -> list[BaseGeometry]:
    """Convertit les geometries de features en geometries Shapely planimetriques.

    Tous les types de geometrie sont acceptes. Les Z sont supprimes (force_2d)
    pour une comparaison planimetrique. Les geometries absentes ou malformees
    sont ignorees sans lever d'exception.
    """
    geometries: list[BaseGeometry] = []
    for feat in features:
        geom_dict = feat.get("geometry")
        if geom_dict is None:
            continue
        try:
            geometries.append(force_2d(shape(geom_dict)))
        except Exception:  # nosec B112
            continue
    return geometries


def charger_geometries_autres_fichiers(
    repertoire: str,
    fichier_source: str,
) -> tuple[list[BaseGeometry], int]:
    """Charge en 2D les geometries de tous les GeoJSON hormis le fichier source.

    Les fichiers d'ecarts sont deja exclus par lister_fichiers_geojson. Le
    fichier source (points de leve) est explicitement retire pour ne pas
    comparer les points de leve entre eux.

    Retourne (geometries, nombre_fichiers_analyses).
    """
    geometries: list[BaseGeometry] = []
    fichiers_analyses = 0
    for nom_fichier in lister_fichiers_geojson(repertoire):
        if nom_fichier == fichier_source:
            continue
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        geometries.extend(_charger_geometries_2d(collection.get("features", [])))
        fichiers_analyses += 1
    return geometries, fichiers_analyses


# ---------------------------------------------------------------------------
# Detection des points de leve orphelins
# ---------------------------------------------------------------------------


def detecter_points_leve_orphelins(
    features_points: list[dict[str, Any]],
    geometries_autres: list[BaseGeometry],
) -> list[dict[str, Any]]:
    """Detecte les points de leve non superposes a une entite d'un autre fichier.

    Interroge un STRtree construit sur les geometries des autres fichiers avec
    le predicat 'dwithin', en 2D, a TOLERANCE_SUPERPOSITION metres. Un point de
    leve sans aucun resultat est orphelin. Les geometries malformees sont
    ignorees sans lever d'exception.

    Retourne une liste d'anomalies {id_entite, geometrie}.
    """
    arbre = STRtree(geometries_autres)
    interroger = arbre.query  # alias local : evite le lookup global en boucle
    tolerance = TOLERANCE_SUPERPOSITION  # idem : constante lue une seule fois
    anomalies: list[dict[str, Any]] = []

    for feat in features_points:
        geom_dict = feat.get("geometry")
        if geom_dict is None or geom_dict.get("type") != "Point":
            continue
        try:
            point_2d = force_2d(shape(geom_dict))
        except Exception:  # nosec B112
            continue
        if len(interroger(point_2d, predicate="dwithin", distance=tolerance)) == 0:
            anomalies.append({"id_entite": obtenir_id_feature(feat), "geometrie": geom_dict})

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des points de leve orphelins.

    Chaque feature conserve la geometrie du point de leve pour permettre sa
    localisation dans QGIS. Le champ crs est propage depuis le fichier source.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": a["id_entite"],
                "type_anomalie": "point_leve_orphelin",
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
    """Execute le controle E209 en mode CLI.

    Charge les points de leve, indexe les geometries des autres fichiers dans un
    STRtree, detecte les points orphelins puis ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    collection_source = lire_geojson(os.path.join(repertoire_resolu, FICHIER_SOURCE))
    if collection_source is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_SOURCE} introuvable dans {repertoire_resolu}",
        }

    features_points = collection_source.get("features", [])
    crs = collection_source.get("crs")

    geometries_autres, fichiers_analyses = charger_geometries_autres_fichiers(repertoire_resolu, FICHIER_SOURCE)
    anomalies = detecter_points_leve_orphelins(features_points, geometries_autres)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_points_controles": len(features_points),
        "fichiers_analyses": fichiers_analyses,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E209."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E209 : detection des points de leve orphelins (non superposes a une entite d'un autre GeoJSON)."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant {FICHIER_SOURCE} et les autres couches GeoJSON",
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
