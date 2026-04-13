"""
Controle de la geometrie des cables electriques.
Verifie que chaque cable possede une geometrie de type LineString
avec au moins 2 points de coordonnees.

Usage CLI : python controle_geometrie.py --repertoire <chemin> [--sortie <chemin>]
Sorties : rapport_controle_geometrie.json + ecarts_geometrie.geojson
"""

import argparse
import json
import os
import sys
from typing import Any


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Lit un fichier GeoJSON et retourne son contenu. Retourne None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def obtenir_id_feature(feature: dict[str, Any]) -> str | int | None:
    """Retourne l'identifiant d'une feature GeoJSON."""
    props = feature.get("properties", {})
    id_val = props.get("id")
    if id_val is not None:
        return id_val
    return feature.get("id")


# Fichier des cables electriques
FICHIER_CABLES: str = "RPD_CableElectrique_Reco.geojson"

# Noms des fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_geometrie.json"
FICHIER_ECARTS_GEOJSON: str = "ecarts_geometrie.geojson"


def valider_geometrie_cable(cable: dict[str, Any]) -> dict[str, Any]:
    """Valide la geometrie d'un cable individuel.

    Retourne un dictionnaire contenant l'id, la validite, et l'erreur eventuelle.
    """
    id_cable = obtenir_id_feature(cable)
    if id_cable is None:
        return {
            "id_cable": "inconnu",
            "valide": False,
            "erreur": "ID du cable manquant",
        }

    geometrie = cable.get("geometry")
    if geometrie is None:
        return {"id_cable": id_cable, "valide": False, "erreur": "Geometrie absente"}

    type_geometrie = geometrie.get("type")
    if type_geometrie != "LineString":
        return {
            "id_cable": id_cable,
            "valide": False,
            "erreur": f"Geometrie invalide (type {type_geometrie}, attendu LineString)",
        }

    coordonnees = geometrie.get("coordinates", [])
    if len(coordonnees) < 2:
        return {
            "id_cable": id_cable,
            "valide": False,
            "erreur": "Geometrie invalide (moins de 2 points)",
        }

    return {"id_cable": id_cable, "valide": True}


def controler_geometrie(
    cables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute le controle de geometrie sur tous les cables.

    Retourne la liste des resultats par cable.
    """
    return [valider_geometrie_cable(cable) for cable in cables]


def construire_rapport_json(
    resultats: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construit le rapport JSON synthetique du controle de geometrie."""
    total = len(resultats)
    conformes = sum(1 for r in resultats if r.get("valide", False))

    return {
        "controle": "geometrie_cables",
        "nombre_cables": total,
        "cables_conformes": conformes,
        "cables_non_conformes": total - conformes,
        "resultats": resultats,
    }


def construire_geojson_ecarts(
    resultats: list[dict[str, Any]],
    cables: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un GeoJSON FeatureCollection des cables en erreur geometrique.

    Les cables sans geometrie valide sont representes avec une geometrie nulle.
    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    # Indexer les cables par ID pour retrouver leur geometrie
    cables_par_id: dict[str, dict[str, Any]] = {}
    for cable in cables:
        id_cable = obtenir_id_feature(cable)
        if id_cable is not None:
            cables_par_id[str(id_cable)] = cable

    features: list[dict[str, Any]] = []

    for resultat in resultats:
        if resultat.get("valide", False):
            continue

        id_cable = str(resultat.get("id_cable", "inconnu"))
        cable_source = cables_par_id.get(id_cable)
        geometrie = cable_source.get("geometry") if cable_source else None

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id_cable": id_cable,
                    "erreur": resultat.get("erreur", ""),
                    "type_anomalie": "geometrie_invalide",
                    "priorite": "bloquant",
                },
                "geometry": geometrie,
            }
        )

    resultat_geojson: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features,
    }
    if crs is not None:
        resultat_geojson["crs"] = crs
    return resultat_geojson


def _ecrire_json(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un dictionnaire au format JSON dans un fichier."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de geometrie en mode CLI.

    Charge le GeoJSON depuis le repertoire, execute le controle,
    et ecrit les fichiers de sortie (rapport JSON + GeoJSON des ecarts).
    """
    dossier_sortie = sortie if sortie is not None else repertoire

    # Chargement des cables
    chemin_cables = os.path.join(repertoire, FICHIER_CABLES)
    collection = lire_geojson(chemin_cables)
    if collection is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_CABLES} introuvable dans {repertoire}",
        }

    cables = collection.get("features", [])
    crs = collection.get("crs")

    # Controle de geometrie
    resultats = controler_geometrie(cables)

    # Generation du rapport JSON
    rapport = construire_rapport_json(resultats)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_rapport = os.path.join(dossier_sortie, FICHIER_RAPPORT_JSON)
    _ecrire_json(rapport, chemin_rapport)

    # Generation du GeoJSON des ecarts
    geojson_ecarts = construire_geojson_ecarts(resultats, cables, crs)
    chemin_ecarts = os.path.join(dossier_sortie, FICHIER_ECARTS_GEOJSON)
    _ecrire_json(geojson_ecarts, chemin_ecarts)

    return {"succes": True, "rapport": chemin_rapport, "ecarts": chemin_ecarts}


def main() -> None:
    """Point d'entree CLI du controle de geometrie."""
    parseur = argparse.ArgumentParser(
        description="Controle de geometrie des cables electriques"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant " + FICHIER_CABLES,
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
