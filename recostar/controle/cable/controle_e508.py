"""
Controle E508 : cables electriques HTB situes dans l'emprise DR.

Verifie qu'aucun cable electrique en cours de mise en service et de domaine de
tension HTB ne se trouve dans l'emprise geographique de la direction regionale
resolue depuis le numero d'affaire. Le reseau HTB relevant du transport, sa
presence dans une emprise de distribution est signalee pour analyse.

Regle de gestion :
  - Ne retenir que les RPD_CableElectrique_Reco au Statut UnderCommissionning.
  - Parmi eux, ne conserver que ceux dont le DomaineTension vaut HTB.
  - Toute entite retenue situee DANS l'emprise DR genere une anomalie E508.
    Le sens est donc l'inverse d'E303, qui signale les entites HORS emprise.

Perimetre :
  - Certains numeros d'affaire excluent entierement le controle (12345678 et
    tout numero prefixe OSR) : non resolvables dans le referentiel DR, ils sont
    ignores sans verification ni anomalie. Meme regle metier que E303.
  - Un seul numero d'affaire est accepte ; sa resolution peut designer
    plusieurs codes DR (cas des zones frontalieres du referentiel), auquel cas
    l'appartenance a l'une quelconque des emprises suffit.
  - Compatible RecoStaR V1.0 et V1.1 : champs et geometries identiques,
    controle agnostique de version.

Referentiel et geometrie : la resolution du numero d'affaire, le chargement des
emprises (EPSG:2154) et le test de containment planimetrique reutilisent
utils_emprise_dr (module commun partage avec le controle E303). Si le fichier
cable est dans un autre CRS projete, ses coordonnees sont reprojetees vers
EPSG:2154 via pyproj avant le test.

Usage CLI :
    python controle_e508.py --repertoire <chemin> --numero_affaire <numero>
                            [--sortie <chemin>]

Sortie : ecarts_e508_cable_htb_emprise_dr.geojson
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyproj import Transformer
from utils_emprise_dr import (
    affaire_exclue_du_controle,
    appliquer_transformation,
    creer_transformateur,
    extraire_nom_crs,
    extraire_point_representatif,
    point_dans_emprises,
    resoudre_emprises_affaire,
)
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source analyse
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e508_cable_htb_emprise_dr.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E508"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_htb_dans_emprise_dr": (
        "Le câble HTB est situé dans l'emprise de la direction régionale, alors que le réseau HTB relève du transport."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "information"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "cable_htb_dans_emprise_dr"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_DOMAINE_TENSION: str = "DomaineTension"

# Statut et domaine de tension delimitant le perimetre du controle
STATUT_CONTROLE: str = "UnderCommissionning"
DOMAINE_TENSION_CONTROLE: str = "HTB"


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SourceCables:
    """Cables HTB a controler et contexte de projection du fichier source."""

    cables: list[dict[str, Any]]
    fichier_absent: bool
    crs: dict[str, Any] | None  # bloc crs propage tel quel dans le fichier d'ecarts
    nom_crs: str | None  # nom textuel du CRS, utilise pour la reprojection


def charger_cables_htb(repertoire: str) -> SourceCables:
    """Charge les cables electriques HTB en cours de mise en service.

    Le filtre statut / domaine de tension est applique des le chargement : les
    cables hors perimetre ne sont pas conserves en memoire, seul le
    sous-ensemble a controler l'est.
    """
    chemin = os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE)
    collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
    if collection is None:
        return SourceCables([], True, None, None)

    cables = [
        feature
        for feature in collection.get("features", [])
        if (props := feature.get("properties") or {}).get(CHAMP_STATUT) == STATUT_CONTROLE
        and props.get(CHAMP_DOMAINE_TENSION) == DOMAINE_TENSION_CONTROLE
    ]
    return SourceCables(cables, False, collection.get("crs"), extraire_nom_crs(collection))


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_cables_dans_emprise(
    cables: list[dict[str, Any]],
    emprises: list[dict[str, Any]],
    transformateur: Transformer | None,
) -> tuple[list[dict[str, Any]], int]:
    """Detecte les cables HTB situes dans l'une des emprises DR autorisees.

    Le point representatif (centroide) de chaque cable est reprojete vers
    EPSG:2154 avant le test de containment. Retourne (anomalies, nb_analyses) :
    les cables sans geometrie exploitable ne sont pas comptes comme analyses.
    """
    anomalies: list[dict[str, Any]] = []
    nb_analyses = 0
    for cable in cables:
        geometrie = cable.get("geometry")
        if geometrie is None:
            continue
        point = extraire_point_representatif(geometrie)
        if point is None:
            continue
        nb_analyses += 1
        x, y = appliquer_transformation(point[0], point[1], transformateur)
        if point_dans_emprises(x, y, emprises):
            anomalies.append(
                {
                    "id_cable": obtenir_id_feature(cable),
                    "type_geometrie": geometrie.get("type", "inconnu"),
                    "geometrie": geometrie,
                }
            )
    return anomalies, nb_analyses


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    codes_dr: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des cables HTB situes dans l'emprise DR.

    La geometrie de chaque feature est celle du cable : c'est l'entite a
    analyser, donc l'objet a localiser dans QGIS. Le crs est propage depuis le
    fichier source des cables.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": TYPE_ANOMALIE,
                "id_cable": a["id_cable"],
                "type_geometrie": a["type_geometrie"],
                "domaine_tension": DOMAINE_TENSION_CONTROLE,
                "codes_dr": codes_dr,
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


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    numero_affaire: str | None = None,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle des cables HTB dans l'emprise DR en mode CLI.

    Resout le numero d'affaire vers une ou plusieurs emprises DR, charge les
    cables HTB en cours de mise en service et signale ceux qui s'y trouvent.
    L'absence du fichier cable n'est pas bloquante : elle est reportee dans le
    rapport, comme pour les autres controles de la famille.
    """
    if not numero_affaire:
        return {"succes": False, "erreur": "Parametre --numero_affaire requis"}

    # Exception metier : certains numeros d'affaire desactivent entierement le
    # controle d'emprise (regle partagee avec E303, portee par utils_emprise_dr).
    # Verifiee avant tout traitement afin qu'aucune anomalie ne soit generee.
    if affaire_exclue_du_controle(numero_affaire):
        return {
            "succes": True,
            "controle_ignore": True,
            "motif": "numero d'affaire exclu du controle E508",
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

    emprises, codes_dr, erreur = resoudre_emprises_affaire(numero_affaire)
    if erreur is not None:
        return {"succes": False, "erreur": erreur}

    source = charger_cables_htb(repertoire_resolu)
    # Le transformateur est cree une seule fois pour le fichier, hors boucle entite
    transformateur = creer_transformateur(source.nom_crs)
    anomalies, nb_analyses = detecter_cables_dans_emprise(source.cables, emprises, transformateur)

    geojson_ecarts = construire_geojson_ecarts(anomalies, codes_dr, source.crs)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_cables_htb": len(source.cables),
        "nombre_cables_analyses": nb_analyses,
        "numero_affaire": numero_affaire,
        "codes_dr": codes_dr,
        "fichier_cable_absent": source.fichier_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle des cables HTB dans l'emprise DR."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E508 : cables HTB dans l'emprise DR — tout "
            "RPD_CableElectrique_Reco au statut UnderCommissionning et de "
            "DomaineTension HTB situe dans l'emprise de la DR est signale."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
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
