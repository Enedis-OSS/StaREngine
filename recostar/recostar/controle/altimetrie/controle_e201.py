"""
Controle E201 : coordonnees Z nulles dans les entites GeoJSON.

Detecte les sommets dont l'altitude est exactement egale a 0.0. Chaque sommet
concerne est exporte sous forme de point dans un fichier GeoJSON d'ecarts,
accompagne de ses metadonnees de localisation (fichier source, identifiant,
indice du sommet).

Le perimetre d'analyse depend de la version RecoStaR :
- v1.0 : seul RPD_CableElectrique_Reco.geojson est controle.
- v1.1 : l'ensemble des GeoJSON du repertoire est controle.

Dans les deux versions, seules les entites dont le champ Statut vaut
« UnderCommissionning » sont soumises au controle. La version est detectee
automatiquement depuis les features de RPD_PointLeveOuvrageReseau_Reco
(presence du champ TypeLeve → v1.0 ; absence → v1.1), identiquement a E202,
E203, E204 et E205. Elle peut etre imposee via l'option --version.

Les entites sans geometrie ou en 2D (sans composante Z) sont ignorees :
seuls les sommets 3D portant une valeur Z = 0.0 sont signales.

Usage CLI :
    python controle_e201.py --repertoire <chemin> [--sortie <chemin>]
                            [--version {auto,1.0,1.1}]

Sortie : ecarts_e201_z_null.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Mecanisme de detection de version partage avec E204 (meme convention que E202/E203)
from controle_e204 import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    determiner_version_depuis_repertoire,
)
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e201_z_null.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E201"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "z_null": ("Le sommet porte une altitude Z nulle, valeur non exploitable."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


# Niveau de priorite affecte aux sommets signales. Bloquant : une altitude nulle
# est un defaut avere qui declasse la famille en « Non conforme »
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "bloquant"

# Valeur Z consideree comme nulle
Z_NULL: float = 0.0

# Fichier unique controle en version 1.0 (les cables electriques)
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"

# Filtrage metier : seules les entites en cours de mise en service sont controlees
CHAMP_STATUT: str = "Statut"
VALEUR_STATUT_CONTROLE: str = "UnderCommissionning"


def _indexer_anneaux(
    anneaux: list[list[Sequence[float]]],
) -> list[tuple[int, Sequence[float]]]:
    """Indexe sequentiellement les points d'une liste d'anneaux ou de lignes."""
    resultat: list[tuple[int, Sequence[float]]] = []
    indice = 0
    for anneau in anneaux:
        for point in anneau:
            resultat.append((indice, point))
            indice += 1
    return resultat


def _indexer_polygones(
    polygones: list[list[list[Sequence[float]]]],
) -> list[tuple[int, Sequence[float]]]:
    """Indexe sequentiellement les points d'une liste de polygones."""
    anneaux_aplatis: list[list[Sequence[float]]] = []
    for polygone in polygones:
        anneaux_aplatis.extend(polygone)
    return _indexer_anneaux(anneaux_aplatis)


# Correspondance type de geometrie -> extracteur indexe
_EXTRACTEURS: dict[str, Any] = {
    "Point": lambda coords: [(0, coords)],
    "LineString": lambda coords: list(enumerate(coords)),
    "MultiPoint": lambda coords: list(enumerate(coords)),
    "Polygon": _indexer_anneaux,
    "MultiLineString": _indexer_anneaux,
    "MultiPolygon": _indexer_polygones,
}


def _extraire_points_indexes(
    geometrie: dict[str, Any],
) -> list[tuple[int, Sequence[float]]]:
    """Extrait les points d'une geometrie avec leur indice sequentiel.

    Retourne une liste de tuples (indice, coordonnees) couvrant tous les
    sommets de la geometrie, quel que soit son type.
    """
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return []
    extracteur = _EXTRACTEURS.get(geometrie.get("type", ""))
    if extracteur is None:
        return []
    return extracteur(coordonnees)


def detecter_z_null_feature(
    feature: dict[str, Any],
    nom_fichier: str,
) -> list[dict[str, Any]]:
    """Detecte les sommets a Z nul dans une feature GeoJSON.

    Seuls les sommets 3D (possedant une composante Z) sont inspectes.
    Un sommet 2D est ignore (relevant du controle 3D, pas de ce controle).
    """
    geometrie = feature.get("geometry")
    if geometrie is None:
        return []

    identifiant = obtenir_id_feature(feature)
    type_geom = geometrie.get("type", "inconnu")
    points = _extraire_points_indexes(geometrie)

    anomalies: list[dict[str, Any]] = []
    for indice, point in points:
        if len(point) < 3:
            continue
        if point[2] != Z_NULL:
            continue
        anomalies.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": identifiant,
                "type_geometrie": type_geom,
                "indice_sommet": indice,
                "coordonnees": list(point),
            }
        )
    return anomalies


def detecter_z_null_collection(
    features: list[dict[str, Any]],
    nom_fichier: str,
) -> list[dict[str, Any]]:
    """Analyse une collection de features et retourne toutes les anomalies Z nul."""
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        anomalies.extend(detecter_z_null_feature(feature, nom_fichier))
    return anomalies


def filtrer_features_a_controler(
    features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Restreint les entites au statut « UnderCommissionning ».

    Ce filtrage s'applique dans toutes les versions : seules les entites en
    cours de mise en service sont soumises au controle des Z nuls. Meme
    convention que E202.
    """
    return [
        feature for feature in features if (feature.get("properties") or {}).get(CHAMP_STATUT) == VALEUR_STATUT_CONTROLE
    ]


def resoudre_fichiers_a_controler(
    repertoire: str,
    version: str,
) -> list[str]:
    """Retourne les fichiers GeoJSON a analyser selon la version RecoStaR.

    - v1.0 : perimetre restreint au seul RPD_CableElectrique_Reco.geojson.
    - v1.1 (et repli) : l'ensemble des GeoJSON du repertoire, hors fichiers
      d'ecarts deja exclus par lister_fichiers_geojson.
    """
    if version == "1.0":
        return [FICHIER_CABLE_ELECTRIQUE]
    return lister_fichiers_geojson(repertoire)


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    version: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des sommets a Z nul.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS. La version RecoStaR appliquee est
    reportee dans les proprietes de chaque anomalie (comme E204/E205).
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "indice_sommet": a["indice_sommet"],
                "z_detecte": Z_NULL,
                "type_anomalie": "z_null",
                "priorite": PRIORITE_ANOMALIE,
                "version": version,
            },
            "geometry": {
                "type": "Point",
                "coordinates": a["coordonnees"],
            },
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle des Z nuls en mode CLI.

    Resout la version RecoStaR (meme mecanisme qu'E202/E204), determine le
    perimetre de fichiers a analyser selon cette version, filtre les entites
    au statut « UnderCommissionning », detecte les sommets a Z nul et ecrit
    le fichier d'ecarts.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    version_effective = determiner_version_depuis_repertoire(repertoire_resolu, version)
    fichiers = resoudre_fichiers_a_controler(repertoire_resolu, version_effective)

    toutes_anomalies: list[dict[str, Any]] = []
    fichiers_analyses = 0
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire_resolu, nom_fichier))
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        # Seules les entites en cours de mise en service sont controlees
        features = filtrer_features_a_controler(collection.get("features", []))
        anomalies = detecter_z_null_collection(features, nom_fichier)
        toutes_anomalies.extend(anomalies)
        fichiers_analyses += 1

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, version_effective, crs)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "nombre_anomalies": len(toutes_anomalies),
        "fichiers_analyses": fichiers_analyses,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle des coordonnees Z nulles."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description="Controle E201 : detection des coordonnees Z nulles dans les entites GeoJSON"
    )
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
    parseur.add_argument(
        "--version",
        choices=choix_version,
        default=JETON_AUTO,
        help=(
            "Version RecoStaR a controler. 'auto' (defaut) la deduit des "
            "proprietes GeoJSON (TypeLeve dans PointLeve) ; sinon imposer "
            "'1.0' (RPD_CableElectrique_Reco uniquement) ou '1.1' (tous les GeoJSON)."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
