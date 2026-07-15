"""
Controle de coherence spatiale des entites GeoJSON.

Identifie les entites dont la position est aberrante : detachees du reseau,
signe d'une faute de saisie de coordonnee. Chaque entite est representee par son
centroide (moyenne de ses coordonnees).

Principe : les entites sont regroupees par proximite (composantes connexes). Deux
entites distantes de moins de SEUIL_RATTACHEMENT appartiennent au meme groupe.
Le groupe le plus nombreux constitue le reseau ; tout autre groupe en est detache
et genere une anomalie.

Pourquoi ce critere plutot qu'un ecart a un point central : un reseau de
distribution est lineaire et ramifie, jamais circulaire autour de son centre. Sa
peripherie est donc naturellement eloignee de tout point de reference, sans etre
aberrante pour autant. Mesurer l'ecart a un centre revient a mesurer
l'excentricite, pas l'aberration. Le rattachement au reseau, lui, ne depend pas
de la forme du jeu de donnees.

Le regroupement — et non l'isolement entite par entite — permet de detecter un
lot d'entites decalees en bloc : chacune conserve alors des voisins immediats,
mais leur groupe est detache du reseau.

Prerequis : les coordonnees doivent etre dans une projection en metres.
Ce point est verifie via pyproj lorsque le champ crs est present.

Usage CLI :
    python controle_e301.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_coherence_spatiale.geojson
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from pyproj import CRS
from utils_geojson import (
    ecrire_geojson,
    lire_geojson,
    lister_fichiers_geojson,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_coherence_spatiale.geojson"

# Niveau de priorite affecte aux entites aberrantes
PRIORITE_ANOMALIE: str = "bloquant"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "groupe_detache_du_reseau"

# Distance en deca de laquelle deux entites sont considerees rattachees au meme
# groupe. Calibre sur les jeux de reference : l'ecart le plus large a l'interieur
# d'un reseau reel y atteint 245 m (portion desservie par une antenne). Le seuil
# retenu offre donc une marge de 2x, tandis qu'une faute de saisie de coordonnee
# (chiffre errone en Lambert 93) deplace l'entite d'au moins un kilometre.
SEUIL_RATTACHEMENT: float = 500.0

# Nombre minimal d'entites : en deca, la notion de groupe majoritaire n'a pas
# de sens et aucune position ne peut etre qualifiee d'aberrante.
NB_ENTITES_MIN: int = 2


# Correspondance type de geometrie -> extracteur de paires (x, y)
_EXTRACTEURS_XY: dict[str, Any] = {
    "Point": lambda c: [(c[0], c[1])],
    "LineString": lambda c: [(pt[0], pt[1]) for pt in c],
    "MultiPoint": lambda c: [(pt[0], pt[1]) for pt in c],
    "Polygon": lambda c: [(pt[0], pt[1]) for pt in c[0]],
    "MultiLineString": lambda c: [(pt[0], pt[1]) for ligne in c for pt in ligne],
    "MultiPolygon": lambda c: [(pt[0], pt[1]) for poly in c for pt in poly[0]],
}


def _extraire_coordonnees_xy(
    geometrie: dict[str, Any],
) -> list[tuple[float, float]]:
    """Extrait toutes les paires (x, y) d'une geometrie GeoJSON."""
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return []
    extracteur = _EXTRACTEURS_XY.get(geometrie.get("type", ""))
    if extracteur is None:
        return []
    return extracteur(coordonnees)


def _calculer_centroide(
    points: list[tuple[float, float]],
) -> tuple[float, float]:
    """Calcule le centroide (moyenne) d'une liste de points (x, y) non vide."""
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def _extraire_point_representatif(
    geometrie: dict[str, Any],
) -> tuple[float, float] | None:
    """Retourne le centroide d'une geometrie comme point representatif.

    Retourne None si la geometrie est vide ou de type inconnu.
    """
    points = _extraire_coordonnees_xy(geometrie)
    if not points:
        return None
    return _calculer_centroide(points)


def extraire_points_representatifs(
    features: list[dict[str, Any]],
    nom_fichier: str,
) -> list[dict[str, Any]]:
    """Extrait les centroides de toutes les entites d'une collection GeoJSON.

    Les entites sans geometrie ou de type inconnu sont ignorees.
    Retourne une liste de dictionnaires portant les metadonnees de chaque entite.
    """
    donnees: list[dict[str, Any]] = []
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        point = _extraire_point_representatif(geometrie)
        if point is None:
            continue
        donnees.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": obtenir_id_feature(feature),
                "type_geometrie": geometrie.get("type", "inconnu"),
                "geometrie": geometrie,
                "x_rep": point[0],
                "y_rep": point[1],
            }
        )
    return donnees


def _indexer_par_cellule(
    points: list[tuple[float, float]],
    seuil: float,
) -> dict[tuple[int, int], list[int]]:
    """Repartit les indices des points dans une grille au pas du seuil.

    Le pas de la grille etant egal au seuil, deux points distants de moins du
    seuil tombent necessairement dans deux cellules adjacentes : il suffit donc
    d'examiner le voisinage 3x3 de chaque cellule au lieu de comparer toutes les
    paires. Le cout passe de O(n²) a O(n x k), k etant le nombre de voisins
    locaux.
    """
    grille: dict[tuple[int, int], list[int]] = {}
    for indice, (x, y) in enumerate(points):
        grille.setdefault((int(x // seuil), int(y // seuil)), []).append(indice)
    return grille


def _rattacher(parent: list[int], a: int, b: int) -> None:
    """Fusionne les groupes de deux indices (union-find, compression de chemin)."""

    def racine(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # compression : aplatit l'arbre
            i = parent[i]
        return i

    ra, rb = racine(a), racine(b)
    if ra != rb:
        parent[ra] = rb


def _voisins_cellule(
    grille: dict[tuple[int, int], list[int]],
    cellule: tuple[int, int],
) -> list[int]:
    """Retourne les indices des points du voisinage 3x3 d'une cellule."""
    cx, cy = cellule
    voisins: list[int] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            voisins.extend(grille.get((cx + dx, cy + dy), ()))
    return voisins


def _fusionner_voisinages(
    points: list[tuple[float, float]],
    grille: dict[tuple[int, int], list[int]],
    parent: list[int],
    seuil: float,
) -> None:
    """Rattache entre eux les points distants d'au plus `seuil`.

    Seul le voisinage 3x3 de chaque cellule est examine (cf. _indexer_par_cellule).
    La condition i < j evite d'evaluer deux fois la meme paire.
    """
    distance = math.dist  # alias local (boucle critique)
    for cellule, indices in grille.items():
        voisins = _voisins_cellule(grille, cellule)
        for i in indices:
            for j in voisins:
                if i < j and distance(points[i], points[j]) <= seuil:
                    _rattacher(parent, i, j)


def _collecter_groupes(parent: list[int]) -> list[list[int]]:
    """Rassemble les indices par racine commune, du groupe le plus nombreux au moins."""
    groupes: dict[int, list[int]] = {}
    for indice in range(len(parent)):
        racine = indice
        while parent[racine] != racine:
            racine = parent[racine]
        groupes.setdefault(racine, []).append(indice)
    return sorted(groupes.values(), key=len, reverse=True)


def regrouper_par_proximite(
    points: list[tuple[float, float]],
    seuil: float = SEUIL_RATTACHEMENT,
) -> list[list[int]]:
    """Regroupe les points en composantes connexes de proximite.

    Deux points distants d'au plus `seuil` appartiennent au meme groupe, la
    relation etant transitive : un reseau continu forme un groupe unique, quelle
    que soit son etendue totale.

    Retourne les groupes d'indices, du plus nombreux au moins nombreux.
    """
    grille = _indexer_par_cellule(points, seuil)
    parent = list(range(len(points)))
    _fusionner_voisinages(points, grille, parent, seuil)
    return _collecter_groupes(parent)


def _distance_au_groupe(
    points: list[tuple[float, float]],
    groupe: list[int],
    reference: list[int],
) -> float:
    """Distance minimale separant deux groupes de points.

    Calculee uniquement pour les groupes detaches, rares par nature : le cout
    quadratique reste borne.
    """
    distance = math.dist
    return min(distance(points[i], points[j]) for i in groupe for j in reference)


def _valider_crs_projete(nom_crs: str) -> bool:
    """Verifie que le CRS est projete (coordonnees en metres) via pyproj.

    Un CRS projete garantit que les distances euclidiennes sont exprimees en metres.
    Retourne False si le CRS est geographique (en degres) ou non reconnu par pyproj.
    """
    try:
        return CRS(nom_crs).is_projected
    except Exception:
        return False


def detecter_anomalies_spatiales(
    donnees: list[dict[str, Any]],
    seuil: float = SEUIL_RATTACHEMENT,
) -> tuple[list[dict[str, Any]], int]:
    """Detecte les entites appartenant a un groupe detache du reseau.

    Les entites sont regroupees par proximite ; le groupe le plus nombreux
    constitue le reseau. Chaque entite d'un autre groupe genere une anomalie,
    portant la taille de son groupe et la distance de celui-ci au reseau.

    Retourne (anomalies, nombre_de_groupes).
    """
    points = [(d["x_rep"], d["y_rep"]) for d in donnees]
    groupes = regrouper_par_proximite(points, seuil)
    if len(groupes) < 2:
        return [], len(groupes)

    reseau = groupes[0]
    anomalies: list[dict[str, Any]] = []
    for groupe in groupes[1:]:
        distance = _distance_au_groupe(points, groupe, reseau)
        for indice in groupe:
            anomalies.append(
                {
                    **donnees[indice],
                    "distance_m": round(distance, 2),
                    "seuil_m": seuil,
                    "taille_groupe": len(groupe),
                }
            )
    return anomalies, len(groupes)


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites detachees du reseau.

    La geometrie originale est conservee pour la localisation dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "distance_au_reseau_m": a["distance_m"],
                "taille_groupe": a["taille_groupe"],
                "seuil_m": a["seuil_m"],
                "type_anomalie": TYPE_ANOMALIE,
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


def _collecter_donnees_spatiales(
    repertoire: str,
    fichiers: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Charge tous les GeoJSON eligibles et extrait les donnees spatiales.

    Retourne (donnees, crs_premier_fichier).
    """
    donnees: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        donnees.extend(extraire_points_representatifs(collection.get("features", []), nom_fichier))

    return donnees, crs


def _extraire_nom_crs(crs: dict[str, Any] | None) -> str | None:
    """Extrait le nom textuel du CRS depuis un objet crs GeoJSON."""
    if crs is None:
        return None
    return (crs.get("properties") or {}).get("name") or None


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de coherence spatiale en mode CLI.

    Charge les GeoJSON du repertoire, detecte les entites dont la position
    est aberrante par rapport au reste du jeu de donnees et ecrit le fichier
    de sortie.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    fichiers = lister_fichiers_geojson(repertoire_resolu)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    donnees, crs = _collecter_donnees_spatiales(repertoire_resolu, fichiers)

    # Verification que le CRS est projete (prerequis pour les distances euclidiennes)
    nom_crs = _extraire_nom_crs(crs)
    if nom_crs is not None and not _valider_crs_projete(nom_crs):
        return {
            "succes": False,
            "erreur": (f"CRS non projete ({nom_crs}) : les distances euclidiennes ne sont pas applicables en degres"),
        }

    if len(donnees) < NB_ENTITES_MIN:
        return {
            "succes": False,
            "erreur": (
                f"Nombre d'entites insuffisant ({len(donnees)} < {NB_ENTITES_MIN}) :"
                " aucun groupe majoritaire ne peut etre determine"
            ),
        }

    anomalies, nombre_groupes = detecter_anomalies_spatiales(donnees)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "entites_analysees": len(donnees),
        "fichiers_analyses": len(fichiers),
        "nombre_groupes": nombre_groupes,
        "seuil_rattachement_m": SEUIL_RATTACHEMENT,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence spatiale."""
    parseur = argparse.ArgumentParser(description="Controle de coherence spatiale des entites GeoJSON")
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
