"""
Moteur de detection : coordonnees Z nulles dans les entites GeoJSON.

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
(presence du champ TypeLeve → v1.0 ; absence → v1.1), par le mecanisme commun
`fonctions_communes.version_recostar`. Elle peut etre imposee via l'option
--version.

Les entites sans geometrie ou en 2D (sans composante Z) sont ignorees :
seuls les sommets 3D portant une valeur Z = 0.0 sont signales.

"""

from collections.abc import Sequence
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    lister_fichiers_geojson,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_STATUT,
    FICHIER_CABLE_ELECTRIQUE,
    STATUT_MISE_EN_SERVICE,
)

# Detection de version, commune a tous les controles GeoJSON


# Valeur Z consideree comme nulle
Z_NULL: float = 0.0


# Filtrage metier : seules les entites en cours de mise en service sont controlees
VALEUR_STATUT_CONTROLE: str = STATUT_MISE_EN_SERVICE


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
    convention que E-5201.
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
