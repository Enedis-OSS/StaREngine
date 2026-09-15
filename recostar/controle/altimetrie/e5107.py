"""
Controle E-5107 : altitude Z non renseignee.

Le verificateur ne connait qu'une anomalie — « Le Z n'est pas renseigné » —, que
la donnee exprime de deux facons distinctes :

- la geometrie ne porte aucune troisieme coordonnee (entite 2D) ;
- la troisieme coordonnee est presente mais vaut 0.0, valeur que le format
  RecoStaR emploie pour une altitude absente.

Les deux cas relevent de ce seul code et ont chacun leur moteur :
`detection_z_absent` parcourt toutes les couches, `detection_z_nul` restreint son
perimetre aux couches de la version detectee et aux entites en cours de mise en
service.

Les deux perimetres restent distincts a dessein : une entite 2D est une anomalie
quel que soit son statut, alors qu'un Z a zero ne se juge que sur les ouvrages
que le recolement declare poser.

Le `type_anomalie` de chaque ecart conserve la distinction, que le code seul
n'exprime pas.

Usage CLI :
    python -m recostar.controle.altimetrie.e5107 --repertoire <chemin> [--sortie <chemin>]
                                                 [--version {auto,1.0,1.1}]

Sortie : ecarts_e5107_z_non_renseigne.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.altimetrie.detection_z_absent import detecter_entites_2d
from recostar.controle.altimetrie.detection_z_nul import (
    Z_NULL,
    detecter_z_null_collection,
    filtrer_features_a_controler,
    resoudre_fichiers_a_controler,
)
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
)
from recostar.controle.fonctions_communes.resultats import (
    MOTIF_AUCUN_GEOJSON,
    rapport_sans_objet,
)
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    determiner_version_depuis_repertoire,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e5107_z_non_renseigne.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-5107"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "absence_coordonnee_z": ("L'entité ne porte pas de coordonnée Z : sa géométrie n'est pas en 3D."),
    "z_null": ("Le sommet porte une altitude Z nulle, valeur non exploitable."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def _feature_z_absent(anomalie: dict[str, Any]) -> dict[str, Any]:
    """Feature d'ecart pour une entite depourvue de coordonnee Z.

    La geometrie de l'entite est conservee telle quelle : l'anomalie porte sur
    l'entite entiere, pas sur un sommet en particulier.
    """
    return {
        "type": "Feature",
        "properties": {
            "fichier_source": anomalie["fichier_source"],
            "id_entite": anomalie["id_entite"],
            "type_geometrie": anomalie["type_geometrie"],
            "type_anomalie": "absence_coordonnee_z",
        },
        "geometry": anomalie["geometrie"],
    }


def _feature_z_nul(anomalie: dict[str, Any], version: str) -> dict[str, Any]:
    """Feature d'ecart pour un sommet a altitude nulle.

    La geometrie emise est le sommet lui-meme : l'anomalie est localisee, et
    l'operateur doit pouvoir la pointer sans parcourir toute l'entite.
    """
    return {
        "type": "Feature",
        "properties": {
            "fichier_source": anomalie["fichier_source"],
            "id_entite": anomalie["id_entite"],
            "type_geometrie": anomalie["type_geometrie"],
            "indice_sommet": anomalie["indice_sommet"],
            "z_detecte": Z_NULL,
            "type_anomalie": "z_null",
            "version": version,
        },
        "geometry": {"type": "Point", "coordinates": anomalie["coordonnees"]},
    }


def construire_geojson_ecarts(
    anomalies_z_absent: list[dict[str, Any]],
    anomalies_z_nul: list[dict[str, Any]],
    version: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le FeatureCollection des deux formes de Z non renseigne.

    Les deux jeux d'anomalies n'ont ni la meme geometrie ni les memes proprietes
    metier ; seul le socle commun leur est applique. Le champ crs est propage
    depuis les couches sources pour l'affichage dans un SIG.
    """
    features: list[dict[str, Any]] = [_feature_z_absent(a) for a in anomalies_z_absent]
    features.extend(_feature_z_nul(a, version) for a in anomalies_z_nul)
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def _detecter_entites_sans_z(repertoire: str) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
    """Parcourt toutes les couches et releve les entites 2D.

    Aucun filtrage de statut : une entite plane est une anomalie quel que soit
    l'etat de l'ouvrage qu'elle decrit.
    """
    anomalies: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None
    analyses = 0
    for nom_fichier in lister_fichiers_geojson(repertoire):
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        anomalies.extend(detecter_entites_2d(collection.get("features", []), nom_fichier))
        analyses += 1
    return anomalies, analyses, crs


def _detecter_sommets_a_z_nul(
    repertoire: str,
    version: str,
) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
    """Parcourt les couches de la version et releve les sommets a Z nul.

    Le perimetre est restreint aux entites en cours de mise en service : un Z a
    zero sur un ouvrage deja en service ne releve pas du recolement.
    """
    anomalies: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None
    analyses = 0
    for nom_fichier in resoudre_fichiers_a_controler(repertoire, version):
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        features = filtrer_features_a_controler(collection.get("features", []))
        anomalies.extend(detecter_z_null_collection(features, nom_fichier))
        analyses += 1
    return anomalies, analyses, crs


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle du Z non renseigne en mode CLI.

    Les deux moteurs sont executes independamment, sur leurs perimetres
    respectifs, et leurs ecarts sont reunis dans un fichier unique — le code du
    verificateur ne distingue pas les deux formes.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire_resolu}"}

    if not lister_fichiers_geojson(repertoire_resolu):
        return rapport_sans_objet(MOTIF_AUCUN_GEOJSON)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    version_effective = determiner_version_depuis_repertoire(repertoire_resolu, version)

    anomalies_z_absent, analyses_z_absent, crs = _detecter_entites_sans_z(repertoire_resolu)
    anomalies_z_nul, analyses_z_nul, crs_z_nul = _detecter_sommets_a_z_nul(repertoire_resolu, version_effective)
    if crs is None:
        crs = crs_z_nul

    geojson_ecarts = construire_geojson_ecarts(anomalies_z_absent, anomalies_z_nul, version_effective, crs)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, os.path.join(dossier_sortie, FICHIER_SORTIE))

    return {
        "succes": True,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies_z_absent) + len(anomalies_z_nul),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        # Les deux moteurs n'ont pas le meme perimetre de couches : le detail
        # evite de laisser croire qu'ils ont lu les memes fichiers.
        "fichiers_analyses": analyses_z_absent,
        "fichiers_analyses_z_nul": analyses_z_nul,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-5107."""
    parseur = argparse.ArgumentParser(
        description="Controle E-5107 : altitude Z non renseignee (entite 2D ou sommet a Z nul)."
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les GeoJSON a analyser")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--version",
        choices=(JETON_AUTO, *VERSIONS_SUPPORTEES),
        default=JETON_AUTO,
        help="Version RecoStaR a controler. 'auto' (defaut) la deduit des proprietes GeoJSON.",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
