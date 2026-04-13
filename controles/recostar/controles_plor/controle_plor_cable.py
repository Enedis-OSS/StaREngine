"""
Controle de superposition des points leves sur les sommets des cables.

Verifie que chaque entite du fichier RPD_PointLeveOuvrageReseau_Reco.geojson
se superpose exactement (X, Y, Z) a au moins un sommet des entites presentes
dans RPD_CableElectrique_Reco.geojson. Les points qui coincident avec un
sommet de toute autre entite RPD_ du repertoire sont exclus du controle.

Les points non conformes sont exportes dans un fichier GeoJSON d'ecarts,
avec la projection CRS du fichier source pour assurer la visibilite dans QGIS.

Usage CLI :
    python controle_plor_cable.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_plor_cable.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

# Nom du fichier des points leves d'ouvrage reseau
FICHIER_PLOR: str = "RPD_PointLeveOuvrageReseau_Reco.geojson"

# Nom du fichier des cables electriques
FICHIER_CABLES: str = "RPD_CableElectrique_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_plor_cable.geojson"

# Prefixe des fichiers de donnees RPD analysables
PREFIXE_RPD: str = "RPD_"

# Extension des fichiers analyses
EXTENSION_GEOJSON: str = ".geojson"

# Prefixe des fichiers d'ecarts (exclus de l'analyse)
PREFIXE_ECARTS: str = "ecarts_"

# Niveau de priorite affecte aux points en ecart (controle bloquant)
PRIORITE_ANOMALIE: str = "bloquant"


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


def lister_fichiers_rpd(repertoire: str, exclus: str) -> list[str]:
    """Liste les fichiers RPD_*.geojson du repertoire, hors fichier exclu et ecarts.

    Le parametre exclus permet d'ignorer le fichier PLOR lui-meme
    afin de ne pas comparer les points avec eux-memes.
    """
    fichiers: list[str] = []
    exclus_lower = exclus.lower()
    for nom in sorted(os.listdir(repertoire)):
        nom_lower = nom.lower()
        if not nom_lower.endswith(EXTENSION_GEOJSON):
            continue
        if not nom_lower.startswith(PREFIXE_RPD.lower()):
            continue
        if nom_lower.startswith(PREFIXE_ECARTS):
            continue
        if nom_lower == exclus_lower:
            continue
        fichiers.append(nom)
    return fichiers


def _aplatir_anneaux(
    anneaux: list[list[Sequence[float]]],
) -> list[Sequence[float]]:
    """Aplatit une liste d'anneaux ou de lignes en une liste plate de points."""
    points: list[Sequence[float]] = []
    for anneau in anneaux:
        points.extend(anneau)
    return points


def _aplatir_polygones(
    polygones: list[list[list[Sequence[float]]]],
) -> list[Sequence[float]]:
    """Aplatit une liste de polygones en une liste plate de points."""
    anneaux: list[list[Sequence[float]]] = []
    for polygone in polygones:
        anneaux.extend(polygone)
    return _aplatir_anneaux(anneaux)


# Correspondance type de geometrie -> fonction d'extraction des points bruts
_EXTRACTEURS_POINTS: dict[str, Any] = {
    "Point": lambda coords: [coords],
    "LineString": lambda coords: coords,
    "MultiPoint": lambda coords: coords,
    "Polygon": _aplatir_anneaux,
    "MultiLineString": _aplatir_anneaux,
    "MultiPolygon": _aplatir_polygones,
}


def _extraire_sommets_geometrie(
    geometrie: dict[str, Any],
    sommets: set[tuple[float, float, float]],
) -> None:
    """Ajoute les sommets 3D d'une geometrie au set de sommets.

    Supporte tous les types GeoJSON : Point, LineString, Polygon,
    MultiPoint, MultiLineString, MultiPolygon.
    Les sommets 2D (sans composante Z) sont ignores.
    """
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return

    extracteur = _EXTRACTEURS_POINTS.get(geometrie.get("type", ""))
    if extracteur is None:
        return

    for point in extracteur(coordonnees):
        if len(point) >= 3:
            sommets.add((point[0], point[1], point[2]))


def extraire_sommets_features(
    features: list[dict[str, Any]],
) -> set[tuple[float, float, float]]:
    """Construit l'ensemble des sommets 3D de toutes les features.

    Chaque sommet est stocke sous forme de tuple (X, Y, Z) dans un set
    pour garantir un test d'appartenance en O(1).
    Tous les types de geometrie GeoJSON sont supportes.
    """
    sommets: set[tuple[float, float, float]] = set()
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        _extraire_sommets_geometrie(geometrie, sommets)
    return sommets


def collecter_sommets_rpd(
    repertoire: str,
) -> tuple[set[tuple[float, float, float]], int]:
    """Collecte tous les sommets 3D des fichiers RPD_ du repertoire.

    Parcourt tous les fichiers RPD_*.geojson sauf le fichier PLOR
    et les fichiers d'ecarts. Retourne l'ensemble des sommets et
    le nombre de fichiers analyses.
    """
    fichiers = lister_fichiers_rpd(repertoire, FICHIER_PLOR)
    sommets: set[tuple[float, float, float]] = set()
    fichiers_analyses = 0

    for nom_fichier in fichiers:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue

        features = collection.get("features", [])
        if not features:
            fichiers_analyses += 1
            continue

        for feature in features:
            geometrie = feature.get("geometry")
            if geometrie is None:
                continue
            _extraire_sommets_geometrie(geometrie, sommets)

        fichiers_analyses += 1

    return sommets, fichiers_analyses


def detecter_points_hors_cables(
    features_plor: list[dict[str, Any]],
    sommets_cables: set[tuple[float, float, float]],
    sommets_autres_rpd: set[tuple[float, float, float]],
) -> list[dict[str, Any]]:
    """Identifie les points PLOR non superposes aux sommets des cables.

    Un point PLOR est en ecart s'il ne coincide avec aucun sommet de cable.
    Toutefois, si ce point coincide avec un sommet d'une autre entite RPD_,
    il est ignore (considere comme justifie par une autre couche).
    """
    anomalies: list[dict[str, Any]] = []

    # References locales pour limiter le cout des acces dans la boucle
    dans_cables = sommets_cables.__contains__
    dans_autres = sommets_autres_rpd.__contains__

    for feature in features_plor:
        geometrie = feature.get("geometry") or {}
        if geometrie.get("type") != "Point":
            continue

        coordonnees = geometrie.get("coordinates")
        if coordonnees is None or len(coordonnees) < 3:
            continue

        cle = (coordonnees[0], coordonnees[1], coordonnees[2])

        # Conforme : present sur un sommet de cable
        if dans_cables(cle):
            continue

        # Exclu : present sur un sommet d'une autre entite RPD
        if dans_autres(cle):
            continue

        identifiant = _obtenir_id_feature(feature)
        anomalies.append(
            {
                "id_entite": identifiant,
                "coordonnees": list(coordonnees[:3]),
            }
        )

    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des points PLOR en ecart.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": anomalie["id_entite"],
                "type_anomalie": "point_hors_cable",
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


def _charger_plor_et_cables(
    repertoire: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, str | None]:
    """Charge la collection PLOR et les features cables depuis le repertoire.

    Retourne (collection_plor, features_cables, message_erreur).
    La collection complete PLOR est retournee pour permettre l'extraction du CRS.
    """
    chemin_plor = os.path.join(repertoire, FICHIER_PLOR)
    collection_plor = lire_geojson(chemin_plor)
    if collection_plor is None:
        return None, None, f"Fichier {FICHIER_PLOR} introuvable dans {repertoire}"

    chemin_cables = os.path.join(repertoire, FICHIER_CABLES)
    collection_cables = lire_geojson(chemin_cables)
    if collection_cables is None:
        return None, None, f"Fichier {FICHIER_CABLES} introuvable dans {repertoire}"

    return collection_plor, collection_cables.get("features", []), None


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de superposition PLOR/cables en mode CLI.

    Charge le fichier PLOR et le fichier cables, collecte les sommets
    de toutes les autres couches RPD_ pour exclure les points justifies,
    puis detecte les points en ecart et ecrit le fichier de sortie.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire

    collection_plor, features_cables, erreur = _charger_plor_et_cables(repertoire)
    if erreur is not None or collection_plor is None or features_cables is None:
        return {"succes": False, "erreur": erreur or "Chargement impossible"}

    features_plor = collection_plor.get("features", [])
    crs = collection_plor.get("crs")

    sommets_cables = extraire_sommets_features(features_cables)

    # Collecter les sommets des autres couches RPD_ pour la regle d'exclusion
    sommets_autres, fichiers_rpd = collecter_sommets_rpd(repertoire)
    # Retirer les sommets cables deja connus pour eviter la double recherche
    sommets_exclusion = sommets_autres - sommets_cables

    anomalies = detecter_points_hors_cables(
        features_plor, sommets_cables, sommets_exclusion
    )
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_points_plor": len(features_plor),
        "nombre_sommets_cables": len(sommets_cables),
        "nombre_anomalies": len(anomalies),
        "fichiers_rpd_analyses": fichiers_rpd,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de superposition PLOR/cables."""
    parseur = argparse.ArgumentParser(
        description="Controle de superposition des points leves sur les sommets des cables"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant {FICHIER_PLOR} et {FICHIER_CABLES}",
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
