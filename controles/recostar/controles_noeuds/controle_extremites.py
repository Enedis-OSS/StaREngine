"""
Controle des extremites des cables electriques.
Verifie que chaque extremite de cable est liee a une jonction, un support,
un coffret ou un poste electrique.

Criteres de liaison selon le type d'entite :
- Jonctions et supports : cables_href + proximite geometrique (≤ seuil).
- Coffrets : proximite geometrique uniquement.
- Postes electriques : cables_href uniquement (structure de grande emprise).

Usage CLI : python controle_extremites.py --repertoire <chemin> [--sortie <chemin>]
Sorties : rapport_controle_extremites.json + ecarts_extremites.geojson
"""

import argparse
import json
import math
import os
import sys
from typing import Any

SEUIL_DISTANCE: float = 0.5

FICHIERS_NOEUDS_AVEC_CABLES_HREF: list[str] = [
    "RPD_Jonction_Reco.geojson",
    "RPD_Support_Reco.geojson",
]

FICHIER_COFFRETS: str = "RPD_Coffret_Reco.geojson"
FICHIER_POSTES_ELECTRIQUES: str = "RPD_PosteElectrique_Reco.geojson"


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


def extraire_coordonnees(feature: dict[str, Any]) -> list[float] | None:
    """Extrait les coordonnees d'une feature ponctuelle."""
    geometrie = feature.get("geometry")
    if geometrie is None:
        return None
    coords = geometrie.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return None
    return coords


def calculer_distance_2d(coords1: list[float], coords2: list[float]) -> float:
    """Calcule la distance euclidienne 2D entre deux points."""
    dx = coords1[0] - coords2[0]
    dy = coords1[1] - coords2[1]
    return math.sqrt(dx * dx + dy * dy)


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


def cable_est_lie_dans_href(feature: dict[str, Any], id_cable: str | int) -> bool:
    """Verifie si un cable est reference dans le cables_href d'une feature."""
    ids = extraire_ids_cables_href(feature)
    return str(id_cable) in ids


# Fichier des cables electriques
FICHIER_CABLES: str = "RPD_CableElectrique_Reco.geojson"

# Noms des fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_extremites.json"
FICHIER_ECARTS_GEOJSON: str = "ecarts_extremites.geojson"


def _creer_entite_liee(
    id_feature: str | int,
    nom_fichier: str,
    distance: float,
    domaine_tension: str | None = None,
) -> dict[str, Any]:
    """Cree un dictionnaire representant une entite liee a une extremite de cable."""
    type_entite = nom_fichier.replace("RPD_", "").replace("_Reco.geojson", "")
    entite: dict[str, Any] = {
        "id": id_feature,
        "type": type_entite,
        "nom_fichier": nom_fichier,
        "distance": round(distance, 6),
    }
    if domaine_tension is not None:
        entite["domaine_tension"] = domaine_tension
    return entite


def _evaluer_noeud_lie(
    feature: dict[str, Any],
    coordonnees: list[float],
    id_cable: str | int,
    nom_fichier: str,
) -> dict[str, Any] | None:
    """Evalue si un noeud est lie a une extremite de cable.

    Retourne l'entite liee ou None si les criteres ne sont pas remplis.
    """
    if not cable_est_lie_dans_href(feature, id_cable):
        return None

    coords_entite = extraire_coordonnees(feature)
    if coords_entite is None:
        return None

    distance = calculer_distance_2d(coordonnees, coords_entite)
    if distance > SEUIL_DISTANCE:
        return None

    id_feature = obtenir_id_feature(feature)
    if id_feature is None:
        return None

    valeur_tension = feature.get("properties", {}).get("DomaineTension")
    domaine_tension = valeur_tension if isinstance(valeur_tension, str) else None

    return _creer_entite_liee(id_feature, nom_fichier, distance, domaine_tension)


def _rechercher_noeuds_lies(
    coordonnees: list[float],
    id_cable: str | int,
    collections_noeuds: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Recherche les noeuds lies a une extremite via cables_href et proximite."""
    entites_liees: list[dict[str, Any]] = []

    for nom_fichier, features in collections_noeuds.items():
        for feature in features:
            entite = _evaluer_noeud_lie(feature, coordonnees, id_cable, nom_fichier)
            if entite is not None:
                entites_liees.append(entite)

    return entites_liees


def _rechercher_postes_lies(
    coordonnees: list[float],
    id_cable: str | int,
    features_postes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recherche les postes electriques lies a un cable via cables_href.

    La validation se fait par cables_href uniquement, sans contrainte de
    proximite, car les postes sont des structures de grande emprise dont
    le point de reference ne coincide pas avec les extremites des cables.
    """
    entites_liees: list[dict[str, Any]] = []
    distance_2d = calculer_distance_2d

    for feature in features_postes:
        if not cable_est_lie_dans_href(feature, id_cable):
            continue

        id_feature = obtenir_id_feature(feature)
        if id_feature is None:
            continue

        coords_poste = extraire_coordonnees(feature)
        distance = (
            distance_2d(coordonnees, coords_poste) if coords_poste is not None else 0.0
        )

        entites_liees.append(
            _creer_entite_liee(id_feature, FICHIER_POSTES_ELECTRIQUES, distance)
        )

    return entites_liees


def _rechercher_coffrets_proches(
    coordonnees: list[float],
    features_coffrets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recherche les coffrets proches d'une extremite par proximite uniquement."""
    entites_liees: list[dict[str, Any]] = []

    for feature in features_coffrets:
        coords_entite = extraire_coordonnees(feature)
        if coords_entite is None:
            continue

        distance = calculer_distance_2d(coordonnees, coords_entite)
        if distance > SEUIL_DISTANCE:
            continue

        id_feature = obtenir_id_feature(feature)
        if id_feature is None:
            continue

        entites_liees.append(_creer_entite_liee(id_feature, FICHIER_COFFRETS, distance))

    return entites_liees


def _valider_extremite(
    coordonnees: list[float],
    id_cable: str | int,
    collections_noeuds: dict[str, list[dict[str, Any]]],
    features_coffrets: list[dict[str, Any]],
    features_postes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Valide une extremite de cable en cherchant les entites liees."""
    noeuds_lies = _rechercher_noeuds_lies(coordonnees, id_cable, collections_noeuds)
    coffrets_proches = _rechercher_coffrets_proches(coordonnees, features_coffrets)
    postes_lies = _rechercher_postes_lies(coordonnees, id_cable, features_postes)
    toutes_entites = noeuds_lies + coffrets_proches + postes_lies

    return {
        "coordonnees": coordonnees,
        "entites_liees": toutes_entites,
        "lien_valide": len(toutes_entites) > 0,
    }


def _charger_postes_electriques(repertoire: str) -> list[dict[str, Any]]:
    """Charge les features des postes electriques."""
    chemin = os.path.join(repertoire, FICHIER_POSTES_ELECTRIQUES)
    collection = lire_geojson(chemin)
    if collection is None:
        return []
    return collection.get("features", [])


def _charger_collections_noeuds(
    repertoire: str,
) -> dict[str, list[dict[str, Any]]]:
    """Charge les collections GeoJSON des noeuds (jonctions, supports)."""
    collections: dict[str, list[dict[str, Any]]] = {}
    for nom_fichier in FICHIERS_NOEUDS_AVEC_CABLES_HREF:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is not None:
            collections[nom_fichier] = collection.get("features", [])
    return collections


def _charger_coffrets(repertoire: str) -> list[dict[str, Any]]:
    """Charge les features des coffrets."""
    chemin = os.path.join(repertoire, FICHIER_COFFRETS)
    collection = lire_geojson(chemin)
    if collection is None:
        return []
    return collection.get("features", [])


def _valider_cable(
    cable: dict[str, Any],
    collections_noeuds: dict[str, list[dict[str, Any]]],
    features_coffrets: list[dict[str, Any]],
    features_postes: list[dict[str, Any]],
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

    extremite_depart = _valider_extremite(
        coords_depart, id_cable, collections_noeuds, features_coffrets, features_postes
    )
    extremite_arrivee = _valider_extremite(
        coords_arrivee, id_cable, collections_noeuds, features_coffrets, features_postes
    )

    return {
        "id_cable": id_cable,
        "extremite_depart": extremite_depart,
        "extremite_arrivee": extremite_arrivee,
    }


def controler_extremites(
    cables: list[dict[str, Any]],
    collections_noeuds: dict[str, list[dict[str, Any]]],
    features_coffrets: list[dict[str, Any]],
    features_postes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Execute le controle des extremites sur tous les cables.

    Retourne la liste des resultats par cable.
    """
    postes = features_postes if features_postes is not None else []
    resultats: list[dict[str, Any]] = []
    for cable in cables:
        resultat = _valider_cable(cable, collections_noeuds, features_coffrets, postes)
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

    # Chargement des collections de reference
    collections_noeuds = _charger_collections_noeuds(repertoire)
    features_coffrets = _charger_coffrets(repertoire)
    features_postes = _charger_postes_electriques(repertoire)

    # Controle des extremites
    resultats = controler_extremites(
        cables, collections_noeuds, features_coffrets, features_postes
    )

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
