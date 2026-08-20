"""
Controle E205 : coherence points de leve / geometries supplementaires de coffrets.

Pour chaque geometrie supplementaire referencee par un coffret eligible,
verifie qu'au moins un point de leve (RPD_PointLeveOuvrageReseau_Reco) est
en superposition geographique 2D avec la geometrie supplementaire. La
superposition est evaluee avec le predicat « dwithin » a
TOLERANCE_SUPERPOSITION metres, afin d'admettre un point pose sur le contour
du polygone malgre l'arrondi millimetrique de la donnee source.

La selection des coffrets eligibles depend de la version RecoStaR :
- v1.0 : tous les coffrets possedant un geometriesupplementaire_href.
- v1.1 : uniquement les coffrets dont le champ Statut vaut
         « UnderCommissionning ».

La version est detectee automatiquement depuis les features de
RPD_PointLeveOuvrageReseau_Reco (presence du champ TypeLeve → v1.0 ;
absence → v1.1), identiquement au controle E204. Elle peut etre imposee
via l'option --version.

Fichiers sources :
  - RPD_Coffret_Reco.geojson (relation vers geom supp + filtrage par Statut)
  - RPD_GeometrieSupplementaire_Reco.geojson (polygones des coffrets)
  - RPD_PointLeveOuvrageReseau_Reco.geojson (points de leve)

Usage CLI :
    python controle_e205.py --repertoire <chemin> [--sortie <chemin>]
                            [--version {auto,1.0,1.1}]

Sortie : ecarts_e205_point_leve_geom_supp.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Mecanisme de detection de version partage avec controle_e204
from controle_e204 import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    resoudre_version,
)
from shapely import STRtree, force_2d
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from utils_geojson import ProfilEcarts, ecrire_geojson_si_anomalies, lire_geojson, normaliser_geojson_ecarts

# Tolerance planimetrique partagee avec E209 : meme cause (arrondi millimetrique
# de la posList GML), donc meme valeur, definie une seule fois.
from utils_geometrie import TOLERANCE_SUPERPOSITION

# Fichiers sources analyses par ce controle
FICHIER_COFFRET: str = "RPD_Coffret_Reco.geojson"
FICHIER_GEOM_SUPP: str = "RPD_GeometrieSupplementaire_Reco.geojson"
FICHIER_POINT_LEVE: str = "RPD_PointLeveOuvrageReseau_Reco.geojson"

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e205_point_leve_geom_supp.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E205"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "point_leve_absent": ("La géométrie supplémentaire de coffret n'est superposée à aucun point levé."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


# Niveau de priorite : bloquant
PRIORITE_ANOMALIE: str = "bloquant"

# Champ du coffret referencant sa geometrie supplementaire
CHAMP_HREF_GEOM_SUPP: str = "geometriesupplementaire_href"

# Champ et valeur de filtrage specifique a la version 1.1
CHAMP_STATUT: str = "Statut"
VALEUR_STATUT_V1_1: str = "UnderCommissionning"


# ---------------------------------------------------------------------------
# Extraction des references coffret -> geometrie supplementaire
# ---------------------------------------------------------------------------


def extraire_hrefs_geomsupp_liees_coffrets(
    features_coffrets: list[dict[str, Any]],
    version: str,
) -> frozenset[str]:
    """Extrait les identifiants de geometries supplementaires references par les coffrets.

    En version 1.1, seuls les coffrets dont le champ Statut vaut
    VALEUR_STATUT_V1_1 sont pris en compte.
    En version 1.0, tous les coffrets portant un href sont inclus.
    Retourne un frozenset pour le lookup O(1) en aval.
    """
    hrefs: set[str] = set()
    for feat in features_coffrets:
        props = feat.get("properties") or {}
        if version == "1.1" and props.get(CHAMP_STATUT) != VALEUR_STATUT_V1_1:
            continue
        href = props.get(CHAMP_HREF_GEOM_SUPP)
        if isinstance(href, str) and href:
            hrefs.add(href)
    return frozenset(hrefs)


# ---------------------------------------------------------------------------
# Chargement des points de leve comme geometries Shapely 2D
# ---------------------------------------------------------------------------


def _charger_points_leve(features: list[dict[str, Any]]) -> list[BaseGeometry]:
    """Convertit les features ponctuelles en geometries Shapely planimetriques.

    Seules les geometries de type Point sont traitees.
    Les Z sont supprimes (force_2d) pour une comparaison planimetrique.
    Les geometries malformees sont ignorees sans lever d'exception.
    """
    points: list[BaseGeometry] = []
    for feat in features:
        geom_dict = feat.get("geometry")
        if geom_dict is None or geom_dict.get("type") != "Point":
            continue
        try:
            points.append(force_2d(shape(geom_dict)))
        except Exception:  # nosec B112
            continue
    return points


# ---------------------------------------------------------------------------
# Detection spatiale
# ---------------------------------------------------------------------------


def detecter_geomsupp_sans_point_leve(
    features_geomsupp: list[dict[str, Any]],
    ids_lies: frozenset[str],
    points_leve: list[BaseGeometry],
) -> list[dict[str, Any]]:
    """Detecte les geometries supplementaires liees a un coffret eligible sans point de leve.

    Seules les geometries dont l'id figure dans ids_lies sont verifiees.
    Pour chaque geometrie, interroge l'arbre spatial avec le predicat
    'dwithin' a TOLERANCE_SUPERPOSITION metres : l'absence de resultat constitue
    une anomalie E205.

    La tolerance couvre le point de leve pose sur le CONTOUR de la geometrie
    supplementaire, contact de mesure nulle que l'arrondi millimetrique de la
    donnee source suffit a rompre. Un point interieur au polygone etait deja
    detecte sans elle, ce test etant numeriquement robuste.

    La detection est planimetrique : les geometries sont forcees en 2D
    avant interrogation pour ignorer les ecarts altimetriques.
    Les geometries malformees sont ignorees sans lever d'exception.

    Retourne une liste d'anomalies {id_geomsupp, geometrie}.
    """
    arbre = STRtree(points_leve)
    interroger = arbre.query  # alias local : evite le lookup global en boucle
    tolerance = TOLERANCE_SUPERPOSITION  # idem : constante lue une seule fois
    anomalies: list[dict[str, Any]] = []

    for feat in features_geomsupp:
        props = feat.get("properties") or {}
        id_gs = props.get("id")
        if not isinstance(id_gs, str) or id_gs not in ids_lies:
            continue
        geom_dict = feat.get("geometry")
        if geom_dict is None:
            continue
        try:
            geom_2d = force_2d(shape(geom_dict))
        except Exception:  # nosec B112
            continue
        if len(interroger(geom_2d, predicate="dwithin", distance=tolerance)) == 0:
            anomalies.append({"id_geomsupp": id_gs, "geometrie": geom_dict})

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    version: str,
    crs: dict[str, Any] | None = None,
    profil: ProfilEcarts = PROFIL_ECARTS,
) -> dict[str, Any]:
    """Construit un FeatureCollection des geometries supplementaires sans point de leve.

    Chaque feature conserve la geometrie du polygone de la geometrie
    supplementaire pour permettre la localisation dans QGIS.
    Le champ crs est propage depuis les fichiers sources.
    Le parametre `profil` permet a E207, qui reutilise ce moteur pour les
    supports, de produire ses propres code de controle et description.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": a["id_geomsupp"],
                "type_anomalie": "point_leve_absent",
                "priorite": PRIORITE_ANOMALIE,
                "version": version,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E205 en mode CLI.

    Charge les trois fichiers sources, resout la version RecoStaR depuis
    les features de RPD_PointLeveOuvrageReseau_Reco (meme mecanisme qu'E204),
    filtre les coffrets eligibles selon la version, verifie la presence de
    points de leve en superposition, puis ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())

    collection_coffret = lire_geojson(os.path.join(repertoire_resolu, FICHIER_COFFRET))
    if collection_coffret is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_COFFRET} introuvable dans {repertoire_resolu}",
        }

    collection_geomsupp = lire_geojson(os.path.join(repertoire_resolu, FICHIER_GEOM_SUPP))
    if collection_geomsupp is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_GEOM_SUPP} introuvable dans {repertoire_resolu}",
        }

    collection_points = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POINT_LEVE))
    if collection_points is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_POINT_LEVE} introuvable dans {repertoire_resolu}",
        }

    features_coffrets = collection_coffret.get("features", [])
    features_geomsupp = collection_geomsupp.get("features", [])
    features_points = collection_points.get("features", [])
    crs = collection_coffret.get("crs")

    # Meme mecanisme de detection de version qu'E204 (TypeLeve dans PointLeve)
    version_effective = resoudre_version(version, features_points)

    ids_lies = extraire_hrefs_geomsupp_liees_coffrets(features_coffrets, version_effective)
    points_leve = _charger_points_leve(features_points)
    anomalies = detecter_geomsupp_sans_point_leve(features_geomsupp, ids_lies, points_leve)
    geojson_ecarts = construire_geojson_ecarts(anomalies, version_effective, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "nombre_geomsupp_controlees": len(ids_lies),
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E205."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E205 : detection des geometries supplementaires de coffrets sans point de leve en superposition."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=(f"Repertoire contenant {FICHIER_COFFRET}, {FICHIER_GEOM_SUPP} et {FICHIER_POINT_LEVE}"),
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
            "'1.0' ou '1.1'."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
