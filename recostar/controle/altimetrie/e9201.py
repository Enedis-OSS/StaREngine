"""
Controle E-9201 : coherence points de leve / geometries supplementaires de coffrets.

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
absence → v1.1), par le mecanisme commun `version_recostar`. Elle peut etre imposee
via l'option --version.

Fichiers sources :
  - RPD_Coffret_Reco.geojson (relation vers geom supp + filtrage par Statut)
  - RPD_GeometrieSupplementaire_Reco.geojson (polygones des coffrets)
  - RPD_PointLeveOuvrageReseau_Reco.geojson (points de leve)

Usage CLI :
    python -m recostar.controle.altimetrie.e9201 --repertoire <chemin> [--sortie <chemin>]
                                                 [--version {auto,1.0,1.1}]

Sortie : ecarts_e9201_point_leve_geom_supp.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
)

# Tolerance planimetrique partagee avec E-6211 : meme cause (arrondi millimetrique
# de la posList GML), donc meme valeur, definie une seule fois.
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_COFFRET,
    FICHIER_GEOM_SUPP,
    FICHIER_POINT_LEVE,
    STATUT_MISE_EN_SERVICE,
)
from recostar.controle.fonctions_communes.points_leve import (
    charger_points_leve,
    construire_geojson_ecarts,
    detecter_geomsupp_sans_point_leve,
    extraire_hrefs_geomsupp_liees,
)
from recostar.controle.fonctions_communes.resultats import (
    motif_couche_absente,
    rapport_sans_objet,
)

# Mecanisme de detection de version partage avec e0204
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    resoudre_version,
)

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9201_point_leve_geom_supp.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E-9201"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "point_leve_absent": ("La géométrie supplémentaire de coffret n'est superposée à aucun point levé."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
    # Couche de l'entite en anomalie, que les ecarts ne nomment pas.
    couche_source=FICHIER_GEOM_SUPP,
)


# Champ du coffret referencant sa geometrie supplementaire

# Champ et valeur de filtrage specifique a la version 1.1
VALEUR_STATUT_V1_1: str = STATUT_MISE_EN_SERVICE


# ---------------------------------------------------------------------------
# Extraction des references coffret -> geometrie supplementaire
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Chargement des points de leve comme geometries Shapely 2D
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Detection spatiale
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E-9201 en mode CLI.

    Charge les trois fichiers sources, resout la version RecoStaR depuis
    les features de RPD_PointLeveOuvrageReseau_Reco (mecanisme commun),
    filtre les coffrets eligibles selon la version, verifie la presence de
    points de leve en superposition, puis ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())

    collection_coffret = lire_geojson(os.path.join(repertoire_resolu, FICHIER_COFFRET))
    if collection_coffret is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_COFFRET, repertoire_resolu))

    collection_geomsupp = lire_geojson(os.path.join(repertoire_resolu, FICHIER_GEOM_SUPP))
    if collection_geomsupp is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_GEOM_SUPP, repertoire_resolu))

    collection_points = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POINT_LEVE))
    if collection_points is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_POINT_LEVE, repertoire_resolu))

    features_coffrets = collection_coffret.get("features", [])
    features_geomsupp = collection_geomsupp.get("features", [])
    features_points = collection_points.get("features", [])
    crs = collection_coffret.get("crs")

    # Detection de version commune (TypeLeve dans PointLeve)
    version_effective = resoudre_version(version, features_points)

    ids_lies = extraire_hrefs_geomsupp_liees(features_coffrets, version_effective)
    points_leve = charger_points_leve(features_points)
    anomalies = detecter_geomsupp_sans_point_leve(features_geomsupp, ids_lies, points_leve)
    geojson_ecarts = construire_geojson_ecarts(anomalies, version_effective, PROFIL_ECARTS, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "nombre_geomsupp_controlees": len(ids_lies),
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-9201."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-9201 : detection des geometries supplementaires de coffrets sans point de leve en superposition."
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
