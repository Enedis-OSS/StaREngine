"""
Controle altimetrique des sommets des cables electriques.

Detecte les incoherences altimetriques locales le long des cables en analysant
des fenetres glissantes de 4 sommets consecutifs. Pour chaque fenetre, l'ecart
entre les 2 sommets centraux est compare a la tendance altimetrique definie par
les sommets extremes. Si l'ecart residuel est superieur a 25 cm, les sommets
centraux sont signales en anomalie.

Les entites RPD_CableElectrique_Reco dont l'identifiant apparait dans un
cheminement aerien (RPD_Aerien_Reco.cables_href) sont exclues du controle.

Usage CLI :
    python controle_alti_sommets.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_controle_alti_sommets.geojson
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Iterable, Sequence

# Nom du fichier des cables electriques (source principale du controle)
FICHIER_CABLES: str = "RPD_CableElectrique_Reco.geojson"

# Nom du fichier des cheminements aeriens (source des entites exclues)
FICHIER_AERIEN: str = "RPD_Aerien_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_controle_alti_sommets.geojson"

# Seuil d'ecart altimetrique residuel au-dela duquel une anomalie est declaree (metres)
SEUIL_ECART_ALTI: float = 0.25

# Niveau de priorite affecte aux sommets signales en anomalie
PRIORITE_ANOMALIE: str = "bloquant"

# Nombre de sommets ignores en debut et en fin de chaque cable
NB_SOMMETS_IGNORES: int = 3

# Taille de la fenetre glissante analysee
TAILLE_FENETRE: int = 4


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu ou None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None


def _normaliser_reference_cables(valeur: Any) -> Iterable[str]:
    """Normalise le champ cables_href en iterable de chaines d'identifiants."""
    # Le champ peut contenir soit une chaine unique, soit une liste d'identifiants
    if isinstance(valeur, str):
        # Les references multiples sont parfois concatenees par des espaces
        return (element for element in valeur.split() if element)
    if isinstance(valeur, list):
        return (str(element) for element in valeur if element is not None)
    return ()


def collecter_ids_cables_aeriens(features_aerien: list[dict[str, Any]]) -> set[str]:
    """Construit l'ensemble des identifiants de cables referencees par l'aerien."""
    # L'utilisation d'un set garantit un test d'appartenance en O(1)
    ids_cables: set[str] = set()
    for feature in features_aerien:
        proprietes = feature.get("properties") or {}
        for identifiant in _normaliser_reference_cables(proprietes.get("cables_href")):
            ids_cables.add(identifiant)
    return ids_cables


def _distance_2d(point_a: Sequence[float], point_b: Sequence[float]) -> float:
    """Calcule la distance planaire entre deux sommets 3D."""
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def _ecart_residuel_centraux(fenetre: Sequence[Sequence[float]]) -> float:
    """Calcule l'ecart altimetrique residuel entre les 2 sommets centraux.

    La tendance altimetrique definie par le premier et le dernier sommet de la
    fenetre est retranchee de l'ecart brut observe entre les sommets centraux.
    Cela neutralise les pentes naturelles du trace et limite les faux positifs.
    """
    p0, p1, p2, p3 = fenetre
    longueur_totale = _distance_2d(p0, p3)
    # Ecart altimetrique brut observe entre les deux sommets centraux
    ecart_brut = p2[2] - p1[2]

    # Si la fenetre est degeneree en 2D, la tendance est indefinie : on conserve l'ecart brut
    if longueur_totale <= 0.0:
        return math.fabs(ecart_brut)

    # Pente altimetrique contextuelle estimee entre les sommets extremes
    pente = (p3[2] - p0[2]) / longueur_totale
    # Ecart altimetrique attendu entre les sommets centraux selon cette pente
    ecart_attendu = pente * _distance_2d(p1, p2)
    return math.fabs(ecart_brut - ecart_attendu)


def _indices_centraux_valides(nb_sommets: int) -> range:
    """Retourne la plage des indices de sommets centraux analyses.

    Les NB_SOMMETS_IGNORES premiers et derniers sommets sont exclus de l'analyse.
    Une fenetre est valide si ses deux sommets centraux sont dans la plage autorisee.
    """
    debut_fenetre_min = NB_SOMMETS_IGNORES - 1
    debut_fenetre_max = nb_sommets - NB_SOMMETS_IGNORES - TAILLE_FENETRE + 2
    return range(max(0, debut_fenetre_min), max(0, debut_fenetre_max))


def _analyser_sommets_cable(
    coordonnees: list[list[float]],
) -> dict[int, float]:
    """Analyse un cable et retourne les indices de sommets anomaux avec leur ecart max.

    Chaque sommet central peut apparaitre dans plusieurs fenetres ; l'ecart
    residuel maximal observe est conserve afin de refleter la situation la plus severe.
    """
    # Dictionnaire indice_sommet -> ecart maximal observe
    anomalies_par_indice: dict[int, float] = {}

    # Fonctions locales pour limiter le cout des acces globaux dans la boucle critique
    maj_max = anomalies_par_indice.__setitem__
    lecture_max = anomalies_par_indice.get

    # Si le cable est trop court, _indices_centraux_valides retourne une plage vide
    for debut in _indices_centraux_valides(len(coordonnees)):
        fenetre = coordonnees[debut : debut + TAILLE_FENETRE]
        ecart = _ecart_residuel_centraux(fenetre)
        if ecart <= SEUIL_ECART_ALTI:
            continue
        # Les deux sommets centraux sont signales en anomalie
        for indice_central in (debut + 1, debut + 2):
            if ecart > lecture_max(indice_central, -1.0):
                maj_max(indice_central, ecart)

    return anomalies_par_indice


def _cable_est_eligible(
    cable: dict[str, Any],
    ids_exclus: set[str],
) -> list[list[float]] | None:
    """Retourne les coordonnees 3D du cable s'il est eligible au controle.

    Un cable est eligible s'il possede une geometrie LineString en 3D et si son
    identifiant n'est pas reference par un cheminement aerien.
    """
    identifiant = obtenir_id_feature(cable)
    if identifiant is None or identifiant in ids_exclus:
        return None

    geometrie = cable.get("geometry") or {}
    if geometrie.get("type") != "LineString":
        return None

    coordonnees = geometrie.get("coordinates") or []
    # Le controle altimetrique exige des coordonnees 3D
    if len(coordonnees) < TAILLE_FENETRE:
        return None
    if len(coordonnees[0]) < 3:
        return None

    return coordonnees


def controler_altimetrie_sommets(
    cables: list[dict[str, Any]],
    ids_cables_exclus: set[str],
) -> list[dict[str, Any]]:
    """Execute le controle altimetrique sur l'ensemble des cables eligibles.

    Retourne une liste d'anomalies avec, pour chaque sommet signale, son
    identifiant de cable, son indice dans la geometrie, ses coordonnees et
    l'ecart residuel associe.
    """
    anomalies: list[dict[str, Any]] = []

    for cable in cables:
        coordonnees = _cable_est_eligible(cable, ids_cables_exclus)
        if coordonnees is None:
            continue

        identifiant = obtenir_id_feature(cable)
        anomalies_cable = _analyser_sommets_cable(coordonnees)
        for indice, ecart in anomalies_cable.items():
            anomalies.append(
                {
                    "id_cable": identifiant,
                    "indice_sommet": indice,
                    "coordonnees": coordonnees[indice],
                    "ecart_residuel": round(ecart, 4),
                }
            )

    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des sommets en ecart altimetrique.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    # La compréhension pré-alloue la liste sans type: ignore et reste lisible
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_cable": anomalie["id_cable"],
                "indice_sommet": anomalie["indice_sommet"],
                "ecart_residuel_m": anomalie["ecart_residuel"],
                "seuil_m": SEUIL_ECART_ALTI,
                "type_anomalie": "ecart_altimetrique_sommet",
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


def _charger_cables_et_exclusions(
    repertoire: str,
) -> tuple[list[dict[str, Any]] | None, set[str], dict[str, Any] | None, str | None]:
    """Charge les cables et l'ensemble des identifiants exclus via l'aerien.

    Retourne (features_cables, ids_exclus, crs, message_erreur).
    """
    chemin_cables = os.path.join(repertoire, FICHIER_CABLES)
    collection_cables = lire_geojson(chemin_cables)
    if collection_cables is None:
        return (
            None,
            set(),
            None,
            f"Fichier {FICHIER_CABLES} introuvable dans {repertoire}",
        )

    collection_aerien = lire_geojson(os.path.join(repertoire, FICHIER_AERIEN))
    features_aerien = collection_aerien.get("features", []) if collection_aerien else []
    ids_exclus = collecter_ids_cables_aeriens(features_aerien)
    crs = collection_cables.get("crs")

    return collection_cables.get("features", []), ids_exclus, crs, None


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle altimetrique en mode CLI.

    Charge les fichiers GeoJSON, execute le controle et ecrit le fichier de sortie.
    """
    dossier_sortie = sortie if sortie is not None else repertoire

    cables, ids_exclus, crs, erreur = _charger_cables_et_exclusions(repertoire)
    if erreur is not None or cables is None:
        return {"succes": False, "erreur": erreur or "Chargement impossible"}

    anomalies = controler_altimetrie_sommets(cables, ids_exclus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "cables_exclus": len(ids_exclus),
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle altimetrique des sommets."""
    parseur = argparse.ArgumentParser(
        description="Controle altimetrique des sommets des cables electriques"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant {FICHIER_CABLES} et {FICHIER_AERIEN}",
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
