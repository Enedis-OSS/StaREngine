"""
Controle des extremites des cables electriques.
Verifie que chaque extremite de cable est reliee a un noeud du reseau
via la relation attributaire cables_href.

La validation repose exclusivement sur les liens explicites (cables_href)
entre noeuds et cables. Aucune notion de proximite geometrique n'est
utilisee, ce qui elimine les faux positifs lies aux positions spatiales.

Types de noeuds verifies (tous porteurs de cables_href) :
- Jonction, CoupeCircuitAFusibles, PointDeComptage
- PosteElectrique, JeuBarres, SupportModules
- OuvrageCollectifBranchement

Usage CLI : python controle_extremites.py --repertoire <chemin> [--sortie <chemin>]
Sorties : rapport_controle_extremites.json + ecarts_extremites.geojson
"""

import argparse
import json
import os
import sys
from typing import Any

# Fichiers de noeuds possedant la propriete cables_href (relation CableElectrique_NoeudReseau)
FICHIERS_NOEUDS: tuple[str, ...] = (
    "RPD_CoupeCircuitAFusibles_Reco.geojson",
    "RPD_JeuBarres_Reco.geojson",
    "RPD_Jonction_Reco.geojson",
    "RPD_OuvrageCollectifBranchement_Reco.geojson",
    "RPD_PointDeComptage_Reco.geojson",
    "RPD_PosteElectrique_Reco.geojson",
    "RPD_SupportModules_Reco.geojson",
)


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


def extraire_ids_cables_href(feature: dict[str, Any]) -> set[str]:
    """Extrait les identifiants des cables references dans cables_href."""
    props = feature.get("properties", {})
    cables_href = props.get("cables_href")
    if cables_href is None:
        return set()
    if isinstance(cables_href, str):
        return {x.strip() for x in cables_href.split(",") if x.strip()}
    if not isinstance(cables_href, list):
        return set()
    ids: set[str] = set()
    for ref in cables_href:
        if isinstance(ref, str):
            ids.add(ref)
        elif isinstance(ref, (int, float)):
            ids.add(str(ref))
        elif isinstance(ref, dict):
            val = ref.get("id") or ref.get("href", "")
            if val:
                ids.add(str(val))
    return ids


# Fichier des cables electriques
FICHIER_CABLES: str = "RPD_CableElectrique_Reco.geojson"

# Noms des fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_extremites.json"
FICHIER_ECARTS_GEOJSON: str = "ecarts_extremites.geojson"


def _extraire_type_entite(nom_fichier: str) -> str:
    """Derive le type d'entite depuis le nom du fichier GeoJSON."""
    return nom_fichier.replace("RPD_", "").replace("_Reco.geojson", "")


def _creer_entite_liee(
    id_feature: str | int,
    nom_fichier: str,
    domaine_tension: str | None = None,
) -> dict[str, Any]:
    """Cree un dictionnaire representant une entite liee a une extremite de cable."""
    entite: dict[str, Any] = {
        "id": id_feature,
        "type": _extraire_type_entite(nom_fichier),
        "nom_fichier": nom_fichier,
    }
    if domaine_tension is not None:
        entite["domaine_tension"] = domaine_tension
    return entite


def _construire_index_cables(
    collections_noeuds: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Construit un index inverse cable_id -> liste d'entites liees.

    Parcourt toutes les collections de noeuds et indexe chaque noeud
    par les identifiants de cables references dans son cables_href.
    """
    index: dict[str, list[dict[str, Any]]] = {}

    for nom_fichier, features in collections_noeuds.items():
        for feature in features:
            id_noeud = obtenir_id_feature(feature)
            if id_noeud is None:
                continue

            ids_cables = extraire_ids_cables_href(feature)
            if not ids_cables:
                continue

            props = feature.get("properties", {})
            valeur_tension = props.get("DomaineTension")
            domaine_tension = (
                valeur_tension if isinstance(valeur_tension, str) else None
            )
            entite = _creer_entite_liee(id_noeud, nom_fichier, domaine_tension)

            for id_cable in ids_cables:
                index.setdefault(id_cable, []).append(entite)

    return index


def _valider_extremite(
    coordonnees: list[float],
    id_cable: str,
    index_cables: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Valide une extremite de cable via l'index des relations cables_href."""
    entites_liees = index_cables.get(id_cable, [])

    return {
        "coordonnees": coordonnees,
        "entites_liees": entites_liees,
        "lien_valide": len(entites_liees) > 0,
    }


def _valider_cable(
    cable: dict[str, Any],
    index_cables: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Valide les extremites d'un cable individuel.

    Retourne None si le cable n'a pas de geometrie LineString valide.
    """
    id_cable = obtenir_id_feature(cable)
    if id_cable is None:
        return None

    geometrie = cable.get("geometry", {})
    if geometrie.get("type") != "LineString":
        return None

    coordonnees = geometrie.get("coordinates", [])
    if len(coordonnees) < 2:
        return None

    coords_depart = coordonnees[0]
    coords_arrivee = coordonnees[-1]

    extremite_depart = _valider_extremite(coords_depart, str(id_cable), index_cables)
    extremite_arrivee = _valider_extremite(coords_arrivee, str(id_cable), index_cables)

    return {
        "id_cable": id_cable,
        "extremite_depart": extremite_depart,
        "extremite_arrivee": extremite_arrivee,
    }


def controler_extremites(
    cables: list[dict[str, Any]],
    collections_noeuds: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Execute le controle des extremites sur tous les cables.

    Construit un index inverse des relations cables_href puis valide
    chaque cable par consultation de cet index en O(1).
    """
    index_cables = _construire_index_cables(collections_noeuds)
    resultats: list[dict[str, Any]] = []
    for cable in cables:
        resultat = _valider_cable(cable, index_cables)
        if resultat is not None:
            resultats.append(resultat)
    return resultats


def construire_rapport_json(
    resultats: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construit le rapport JSON synthetique du controle des extremites."""
    total = len(resultats)
    conformes = 0
    for r in resultats:
        depart_ok = r.get("extremite_depart", {}).get("lien_valide", False)
        arrivee_ok = r.get("extremite_arrivee", {}).get("lien_valide", False)
        if depart_ok and arrivee_ok:
            conformes += 1

    return {
        "controle": "extremites_cables",
        "nombre_cables": total,
        "cables_conformes": conformes,
        "cables_non_conformes": total - conformes,
        "resultats": resultats,
    }


def construire_geojson_ecarts(
    resultats: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un GeoJSON FeatureCollection des extremites non liees.

    Chaque extremite sans lien valide est representee par un Point GeoJSON.
    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = []

    for resultat in resultats:
        id_cable = resultat.get("id_cable", "")

        for cle_extremite in ("extremite_depart", "extremite_arrivee"):
            extremite = resultat.get(cle_extremite, {})
            if extremite.get("lien_valide", True):
                continue

            coordonnees = extremite.get("coordonnees", [0.0, 0.0])
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id_cable": id_cable,
                        "extremite": cle_extremite,
                        "type_anomalie": "extremite_non_liee",
                        "priorite": "bloquant",
                    },
                    "geometry": {"type": "Point", "coordinates": coordonnees},
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


def _charger_collections_noeuds(
    repertoire: str,
) -> dict[str, list[dict[str, Any]]]:
    """Charge les collections GeoJSON de tous les noeuds avec cables_href."""
    collections: dict[str, list[dict[str, Any]]] = {}
    for nom_fichier in FICHIERS_NOEUDS:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is not None:
            collections[nom_fichier] = collection.get("features", [])
    return collections


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle des extremites en mode CLI.

    Charge les GeoJSON depuis le repertoire, execute le controle,
    et ecrit les fichiers de sortie (rapport JSON + GeoJSON des ecarts).
    """
    dossier_sortie = sortie if sortie is not None else repertoire

    # Chargement des cables
    chemin_cables = os.path.join(repertoire, FICHIER_CABLES)
    collection_cables = lire_geojson(chemin_cables)
    if collection_cables is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_CABLES} introuvable dans {repertoire}",
        }

    cables = collection_cables.get("features", [])
    crs = collection_cables.get("crs")

    # Chargement de tous les noeuds avec cables_href
    collections_noeuds = _charger_collections_noeuds(repertoire)

    # Controle des extremites
    resultats = controler_extremites(cables, collections_noeuds)

    # Generation du rapport JSON
    rapport = construire_rapport_json(resultats)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_rapport = os.path.join(dossier_sortie, FICHIER_RAPPORT_JSON)
    _ecrire_json(rapport, chemin_rapport)

    # Generation du GeoJSON des ecarts
    geojson_ecarts = construire_geojson_ecarts(resultats, crs)
    chemin_ecarts = os.path.join(dossier_sortie, FICHIER_ECARTS_GEOJSON)
    _ecrire_json(geojson_ecarts, chemin_ecarts)

    return {"succes": True, "rapport": chemin_rapport, "ecarts": chemin_ecarts}


def main() -> None:
    """Point d'entree CLI du controle des extremites."""
    parseur = argparse.ArgumentParser(
        description="Controle des extremites des cables electriques"
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
