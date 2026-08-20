"""
Controle d'appartenance a l'emprise geographique de la direction regionale.

Verifie que les entites presentes dans les GeoJSON analyses se situent
a l'interieur de l'emprise DR correspondant au numero d'affaire fourni.

Formats acceptes pour le numero d'affaire :
  RAC : RAC-CVL-25-007998  -> trigramme CVL recherche dans trigramme_racing
  DA  : DA21/256553        -> prefixe DA21 recherche dans ref_dossier

La reference DR est resolue via fichiers_dr/reference_dr.json.
L'emprise spatiale est chargee depuis fichiers_dr/emprise_dr.geojson (EPSG:2154).
Si les GeoJSON analyses sont dans un autre CRS projete, les coordonnees sont
reprojetees vers EPSG:2154 via pyproj avant le test de containment.

Un seul numero d'affaire est accepte. Les cas situes a la frontiere entre
plusieurs DR sont geres par la resolution multi-repertoire : si un trigramme
ou une reference correspond a plusieurs codes DR, toutes les emprises associees
sont considerees comme autorisees.

Usage CLI :
    python controle_e303.py --repertoire <chemin> --numero_affaire <numero>
                            [--sortie <chemin>]

Sortie : ecarts_e303_emprise_dr.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pyproj import Transformer
from utils_emprise_dr import (
    CHEMIN_EMPRISE_DR,
    CHEMIN_REFERENCE_DR,
    affaire_exclue_du_controle,
    point_dans_emprises,
    resoudre_repertoires,
)
from utils_emprise_dr import appliquer_transformation as _appliquer_transformation
from utils_emprise_dr import charger_emprises_dr as _charger_emprises_dr
from utils_emprise_dr import charger_references as _charger_references
from utils_emprise_dr import construire_index as _construire_index
from utils_emprise_dr import creer_transformateur as _creer_transformateur
from utils_emprise_dr import extraire_nom_crs as _extraire_nom_crs
from utils_emprise_dr import extraire_point_representatif as _extraire_point_representatif
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e303_emprise_dr.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E303"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "hors_emprise_dr": ("L'entité est située hors de l'emprise de la direction régionale de l'affaire."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


# Niveau de priorite affecte aux entites hors emprise
PRIORITE_ANOMALIE: str = "bloquant"


def detecter_entites_hors_emprise(
    features: list[dict[str, Any]],
    nom_fichier: str,
    emprises: list[dict[str, Any]],
    transformateur: Transformer | None,
) -> tuple[list[dict[str, Any]], int]:
    """Detecte les entites situees hors des emprises DR autorisees.

    Le transformateur est applique une fois par entite pour reprojeter son
    centroide vers EPSG:2154 avant le test de containment.
    Retourne (anomalies, nb_entites_analysees).
    """
    anomalies: list[dict[str, Any]] = []
    nb_analysees = 0
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        point = _extraire_point_representatif(geometrie)
        if point is None:
            continue
        nb_analysees += 1
        x, y = _appliquer_transformation(point[0], point[1], transformateur)
        if not point_dans_emprises(x, y, emprises):
            anomalies.append(
                {
                    "fichier_source": nom_fichier,
                    "id_entite": obtenir_id_feature(feature),
                    "type_geometrie": geometrie.get("type", "inconnu"),
                    "geometrie": geometrie,
                }
            )
    return anomalies, nb_analysees


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    codes_dr: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites situees hors emprise DR."""
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "codes_dr_autorises": codes_dr,
                "type_anomalie": "hors_emprise_dr",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


def _resoudre_emprises_affaire(
    numero_affaire: str,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Resout un numero d'affaire vers les emprises DR a controler.

    Enchaine les trois etapes du referentiel : chargement de reference_dr.json,
    resolution du numero vers un ou plusieurs codes repertoire, puis chargement
    des emprises geographiques correspondantes.

    Retourne (emprises, codes_dr, erreur). En cas d'echec de l'une des etapes,
    les emprises sont vides et le message d'erreur est renseigne.
    """
    references, erreur = _charger_references(CHEMIN_REFERENCE_DR)
    if references is None or erreur is not None:
        return [], "", erreur

    index_trigramme, index_dossier = _construire_index(references)

    repertoires, erreur = resoudre_repertoires(numero_affaire, index_trigramme, index_dossier)
    if repertoires is None or erreur is not None:
        return [], "", erreur

    emprises, erreur = _charger_emprises_dr(CHEMIN_EMPRISE_DR, repertoires)
    if erreur is not None:
        return [], "", erreur

    return emprises, ", ".join(sorted(repertoires)), None


def executer_controle_cli(
    repertoire: str,
    numero_affaire: str | None = None,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle d'appartenance a l'emprise DR.

    Resout le numero d'affaire vers un ou plusieurs codes DR, charge les emprises
    correspondantes et verifie que chaque entite GeoJSON s'y trouve bien incluse.
    """
    if not numero_affaire:
        return {"succes": False, "erreur": "Parametre --numero_affaire requis"}

    # Exception metier : certains numeros d'affaire desactivent entierement E303
    # (regle partagee avec E508, portee par utils_emprise_dr).
    # Verifie avant tout traitement (repertoire, references, emprises) afin
    # qu'aucune verification ne soit effectuee ni aucune anomalie generee.
    if affaire_exclue_du_controle(numero_affaire):
        return {
            "succes": True,
            "controle_ignore": True,
            "motif": "numero d'affaire exclu du controle E303",
            "priorite": PRIORITE_ANOMALIE,
            "nombre_anomalies": 0,
            "numero_affaire": numero_affaire,
        }

    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    emprises, codes_dr_str, erreur = _resoudre_emprises_affaire(numero_affaire)
    if erreur is not None:
        return {"succes": False, "erreur": erreur}

    fichiers = lister_fichiers_geojson(repertoire_resolu)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    toutes_anomalies: list[dict[str, Any]] = []
    nb_entites_total = 0
    fichiers_analyses = 0
    crs_sortie: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire_resolu, nom_fichier))
        if collection is None:
            continue
        # Le transformateur est cree une seule fois par fichier, hors boucle entite
        nom_crs = _extraire_nom_crs(collection)
        transformateur = _creer_transformateur(nom_crs)
        if crs_sortie is None:
            crs_sortie = collection.get("crs")
        features = collection.get("features", [])
        anomalies, nb = detecter_entites_hors_emprise(features, nom_fichier, emprises, transformateur)
        toutes_anomalies.extend(anomalies)
        nb_entites_total += nb
        fichiers_analyses += 1

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, codes_dr_str, crs_sortie)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(toutes_anomalies),
        "entites_analysees": nb_entites_total,
        "fichiers_analyses": fichiers_analyses,
        "numero_affaire": numero_affaire,
        "codes_dr": codes_dr_str,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle d'appartenance a l'emprise DR."""
    parseur = argparse.ArgumentParser(description="Controle d'appartenance des entites a l'emprise DR")
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON a analyser",
    )
    parseur.add_argument(
        "--numero_affaire",
        required=True,
        help="Numero d'affaire (format RAC-XXX-YY-NNNNNN ou XXNN/NNNNNN)",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(
        arguments.repertoire,
        arguments.numero_affaire,
        arguments.sortie,
    )
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
