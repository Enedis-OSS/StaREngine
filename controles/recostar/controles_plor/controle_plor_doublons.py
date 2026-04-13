"""
Controle des doublons de points leves d'ouvrage reseau.

Detecte les entites du fichier RPD_PointLeveOuvrageReseau_Reco.geojson
dont les coordonnees geographiques (X, Y, Z) sont identiques. Pour chaque
groupe de points superposes, toutes les entites du groupe sont signalees
et exportees dans un fichier GeoJSON d'ecarts.

Lorsque le champ TypeLeve est present dans les proprietes des features,
le controle segmente les doublons par type de leve : seules les entites
partageant le meme TypeLeve sont comparees entre elles. En l'absence de
ce champ, tous les points sont compares indifferemment.

Usage CLI :
    python controle_plor_doublons.py --repertoire <chemin> [--sortie <chemin>]

Sortie : plor_doublons.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Nom du fichier des points leves d'ouvrage reseau
FICHIER_PLOR: str = "RPD_PointLeveOuvrageReseau_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "plor_doublons.geojson"

# Niveau de priorite affecte aux doublons detectes
PRIORITE_ANOMALIE: str = "information"

# Champ de segmentation optionnel (TypeLeve)
CHAMP_TYPE_LEVE: str = "TypeLeve"


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


def champ_type_leve_present(features: list[dict[str, Any]]) -> bool:
    """Detecte si le champ TypeLeve est present dans au moins une feature."""
    for feature in features:
        proprietes = feature.get("properties") or {}
        if CHAMP_TYPE_LEVE in proprietes:
            return True
    return False


def _obtenir_type_leve(feature: dict[str, Any]) -> str | None:
    """Retourne la valeur du champ TypeLeve ou None si absent."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get(CHAMP_TYPE_LEVE)
    if valeur is None:
        return None
    return str(valeur)


def indexer_points_par_coordonnees(
    features: list[dict[str, Any]],
    segmenter_par_type: bool = False,
) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    """Regroupe les features Point par coordonnees (X, Y, Z).

    Si segmenter_par_type est True, la cle d'indexation inclut la valeur
    du champ TypeLeve. Ainsi, seules les entites de meme type sont
    comparees entre elles pour la detection de doublons.

    Les features sans geometrie Point ou sans composante Z sont ignorees.
    """
    index: dict[tuple[Any, ...], list[dict[str, Any]]] = {}

    for feature in features:
        geometrie = feature.get("geometry") or {}
        if geometrie.get("type") != "Point":
            continue

        coordonnees = geometrie.get("coordinates")
        if coordonnees is None or len(coordonnees) < 3:
            continue

        if segmenter_par_type:
            type_leve = _obtenir_type_leve(feature)
            cle = (coordonnees[0], coordonnees[1], coordonnees[2], type_leve)
        else:
            cle = (coordonnees[0], coordonnees[1], coordonnees[2])

        groupe = index.get(cle)
        if groupe is None:
            groupe = []
            index[cle] = groupe
        groupe.append(feature)

    return index


def detecter_doublons(
    index_coordonnees: dict[tuple[Any, ...], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Identifie les entites en doublon a partir de l'index par coordonnees.

    Un groupe est considere comme doublon des lors qu'il contient au moins
    deux features. Toutes les features du groupe sont retournees comme anomalies,
    accompagnees du nombre total de doublons pour cette position.
    Les coordonnees sont extraites des 3 premiers elements de la cle.
    """
    anomalies: list[dict[str, Any]] = []

    for cle, groupe in index_coordonnees.items():
        if len(groupe) < 2:
            continue

        coordonnees = list(cle[:3])
        nb_doublons = len(groupe)
        for feature in groupe:
            identifiant = _obtenir_id_feature(feature)
            anomalies.append(
                {
                    "id_entite": identifiant,
                    "coordonnees": coordonnees,
                    "nb_doublons": nb_doublons,
                }
            )

    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des doublons detectes.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": anomalie["id_entite"],
                "nb_doublons": anomalie["nb_doublons"],
                "type_anomalie": "doublon_geometrique",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": {
                "type": "Point",
                "coordinates": anomalie["coordonnees"],
            },
        }
        for anomalie in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def _ecrire_geojson(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un FeatureCollection GeoJSON sur disque."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle des doublons PLOR en mode CLI.

    Charge le fichier PLOR, indexe les features par coordonnees,
    detecte les groupes de doublons et ecrit le fichier de sortie.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire

    chemin_plor = os.path.join(repertoire, FICHIER_PLOR)
    collection_plor = lire_geojson(chemin_plor)
    if collection_plor is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_PLOR} introuvable dans {repertoire}",
        }

    features_plor = collection_plor.get("features", [])
    crs = collection_plor.get("crs")

    segmenter = champ_type_leve_present(features_plor)
    index = indexer_points_par_coordonnees(features_plor, segmenter)
    anomalies = detecter_doublons(index)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    nb_groupes = sum(1 for g in index.values() if len(g) >= 2)

    return {
        "succes": True,
        "nombre_points_plor": len(features_plor),
        "nombre_groupes_doublons": nb_groupes,
        "nombre_anomalies": len(anomalies),
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle des doublons de points leves."""
    parseur = argparse.ArgumentParser(
        description="Controle des doublons de points leves d'ouvrage reseau"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant {FICHIER_PLOR}",
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
