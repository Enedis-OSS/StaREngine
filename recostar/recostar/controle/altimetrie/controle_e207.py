"""
Controle E207 : coherence points de leve / geometries supplementaires de supports.

Pour chaque geometrie supplementaire referencee par un support eligible
(RPD_Support_Reco), verifie qu'au moins un point de leve
(RPD_PointLeveOuvrageReseau_Reco) est en superposition geographique 2D avec
l'ENSEMBLE de la geometrie supplementaire (ligne, surface, bord et interieur),
strictement comme le controle E205 (et non uniquement sur les sommets, ce qui
distingue E207 d'E206).

Perimetre :
- E207 ne s'applique qu'en version RecoStaR 1.1. En version 1.0, le controle est
  desactive : il ne produit aucune anomalie (champ « applicable » a False).
- Sont controles les supports dont le champ Statut vaut « UnderCommissionning ».

La version est detectee automatiquement depuis les features de
RPD_PointLeveOuvrageReseau_Reco (presence du champ TypeLeve → v1.0 ; absence →
v1.1), identiquement aux controles E204/E205. Elle peut etre imposee via
l'option --version.

Ce controle reutilise le moteur de detection spatiale d'E205 :
- _charger_points_leve : chargement des points de leve en geometries 2D ;
- detecter_geomsupp_sans_point_leve : interrogation STRtree (predicat
  'intersects') sur l'ensemble de la geometrie supplementaire ;
- construire_geojson_ecarts : construction du FeatureCollection de sortie ;
- extraire_hrefs_geomsupp_liees_coffrets : filtrage v1.1 par Statut, identique
  pour les supports (memes champs geometriesupplementaire_href et Statut).

Fichiers sources :
  - RPD_Support_Reco.geojson (relation vers geom supp + filtrage par Statut)
  - RPD_GeometrieSupplementaire_Reco.geojson (geometries des supports)
  - RPD_PointLeveOuvrageReseau_Reco.geojson (points de leve)

Usage CLI :
    python controle_e207.py --repertoire <chemin> [--sortie <chemin>]
                            [--version {auto,1.0,1.1}]

Sortie : ecarts_e207_point_leve_geom_supp_support.geojson
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

# Reutilisation du moteur de detection et des conventions d'E205
from controle_e205 import (
    FICHIER_GEOM_SUPP,
    FICHIER_POINT_LEVE,
    PRIORITE_ANOMALIE,
    _charger_points_leve,
    construire_geojson_ecarts,
    detecter_geomsupp_sans_point_leve,
    extraire_hrefs_geomsupp_liees_coffrets,
)
from utils_geojson import ProfilEcarts, ecrire_geojson_si_anomalies, lire_geojson

# Fichier source specifique a E207 (support au lieu de coffret)
FICHIER_SUPPORT: str = "RPD_Support_Reco.geojson"

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e207_point_leve_geom_supp_support.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
# Le moteur d'E205 est reutilise, mais le code et la description sont ceux d'E207.
CODE_CONTROLE: str = "E207"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "point_leve_absent": ("La géométrie supplémentaire de support n'est superposée à aucun point levé."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)

# Version RecoStaR pour laquelle E207 est actif (desactive en 1.0)
VERSION_APPLICABLE: str = "1.1"


# ---------------------------------------------------------------------------
# Extraction des references support -> geometrie supplementaire
# ---------------------------------------------------------------------------


def extraire_hrefs_geomsupp_liees_supports(
    features_supports: list[dict[str, Any]],
) -> frozenset[str]:
    """Extrait les geometries supplementaires des supports eligibles.

    Sont retenus les supports dont le champ Statut vaut VALEUR_STATUT_V1_1.
    La logique de filtrage est identique a celle des coffrets en version 1.1
    (memes champs geometriesupplementaire_href et Statut) : le moteur d'E205
    est reutilise directement. Retourne un frozenset pour le lookup O(1).
    """
    return extraire_hrefs_geomsupp_liees_coffrets(features_supports, VERSION_APPLICABLE)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def _rapport_non_applicable(
    version_effective: str,
    crs: dict[str, Any] | None,
    chemin_sortie: str,
) -> dict[str, Any]:
    """Construit le rapport pour une version ou le controle est desactive.

    En version 1.0, E207 n'est pas applicable : aucune anomalie n'est possible,
    donc aucun fichier d'ecarts n'est produit et le rapport indique
    applicable=False. Un eventuel fichier d'une execution precedente est
    supprime pour eviter de signaler des ecarts obsoletes.
    """
    ecrire_geojson_si_anomalies(construire_geojson_ecarts([], version_effective, crs, PROFIL_ECARTS), chemin_sortie)
    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "applicable": False,
        "nombre_anomalies": 0,
        "nombre_geomsupp_controlees": 0,
        "sortie": None,
    }


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E207 en mode CLI.

    Resout d'abord la version depuis RPD_PointLeveOuvrageReseau_Reco. En
    version 1.0, le controle est desactive (rapport applicable=False, sortie
    vide) sans exiger la presence du fichier des supports. En version 1.1,
    charge les supports et les geometries supplementaires, filtre les supports
    eligibles, verifie la presence de points de leve en superposition avec
    l'ensemble de la geometrie, puis ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())

    collection_points = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POINT_LEVE))
    if collection_points is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_POINT_LEVE} introuvable dans {repertoire_resolu}",
        }

    features_points = collection_points.get("features", [])
    crs = collection_points.get("crs")

    # Meme mecanisme de detection de version qu'E204/E205 (TypeLeve dans PointLeve)
    version_effective = resoudre_version(version, features_points)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)

    # E207 est desactive en version 1.0 : sortie vide, aucune anomalie.
    if version_effective != VERSION_APPLICABLE:
        return _rapport_non_applicable(version_effective, crs, chemin_sortie)

    collection_support = lire_geojson(os.path.join(repertoire_resolu, FICHIER_SUPPORT))
    if collection_support is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_SUPPORT} introuvable dans {repertoire_resolu}",
        }

    collection_geomsupp = lire_geojson(os.path.join(repertoire_resolu, FICHIER_GEOM_SUPP))
    if collection_geomsupp is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_GEOM_SUPP} introuvable dans {repertoire_resolu}",
        }

    features_supports = collection_support.get("features", [])
    features_geomsupp = collection_geomsupp.get("features", [])

    ids_lies = extraire_hrefs_geomsupp_liees_supports(features_supports)
    points_leve = _charger_points_leve(features_points)
    anomalies = detecter_geomsupp_sans_point_leve(features_geomsupp, ids_lies, points_leve)
    chemin_ecrit = ecrire_geojson_si_anomalies(
        construire_geojson_ecarts(anomalies, version_effective, crs, PROFIL_ECARTS), chemin_sortie
    )

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "applicable": True,
        "nombre_anomalies": len(anomalies),
        "nombre_geomsupp_controlees": len(ids_lies),
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E207."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E207 : detection des geometries supplementaires de "
            "supports (v1.1 uniquement) sans point de leve en superposition."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=(f"Repertoire contenant {FICHIER_SUPPORT}, {FICHIER_GEOM_SUPP} et {FICHIER_POINT_LEVE}"),
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
            "'1.0' ou '1.1'. E207 est desactive en 1.0."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
