"""
Chargement des couches GeoJSON d'un jeu controle.

Ces fonctions se placent au-dessus de `fonctions_communes.geojson`, qui lit un
fichier : elles repondent aux besoins recurrents des controles — charger une
couche nommee en distinguant « absente » de « vide », ou parcourir toutes les
couches d'un repertoire sans les detenir toutes a la fois.

Aucune ne connait de regle de controle.
"""

import os
from collections.abc import Iterator
from typing import Any

from recostar.controle.fonctions_communes.geojson import lire_geojson, lister_fichiers_geojson
from recostar.controle.fonctions_communes.modele_recostar import EXTENSION_COUCHE


def charger_features(repertoire: str, nom_fichier: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool]:
    """Charge les entites d'une couche. Retourne (features, crs, fichier_absent).

    Le troisieme membre distingue une couche **absente** d'une couche **vide** :
    les controles ne traitent pas les deux de la meme facon — une couche absente
    est signalee dans le rapport, une couche vide ne produit simplement aucune
    anomalie.
    """
    chemin = os.path.join(repertoire, nom_fichier)
    collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
    if collection is None:
        return [], None, True
    return collection.get("features", []), collection.get("crs"), False


def nom_couche(nom_fichier: str) -> str:
    """Derive le nom de la couche du nom de son fichier GeoJSON.

    « RPD_Terre_Reco.geojson » -> « RPD_Terre_Reco ». Le nom du fichier fait foi
    pour le type de l'entite : c'est la convention de nommage RecoStaR, et la
    seule information de type disponible, les features ne portant pas leur
    classe.
    """
    if nom_fichier.lower().endswith(EXTENSION_COUCHE):
        return nom_fichier[: -len(EXTENSION_COUCHE)]
    return nom_fichier


def parcourir_couches(repertoire: str) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Parcourt les couches GeoJSON du repertoire, une seule chargee a la fois.

    Les fichiers d'ecarts sont exclus par `lister_fichiers_geojson`. Le
    generateur evite de detenir simultanement toutes les couches du jeu, dont le
    volume est sans rapport avec le nombre d'anomalies recherchees.
    """
    for nom_fichier in lister_fichiers_geojson(repertoire):
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        yield nom_couche(nom_fichier), collection.get("features", [])
