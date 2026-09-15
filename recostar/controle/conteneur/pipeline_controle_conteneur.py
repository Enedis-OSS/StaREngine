"""
Pipeline de controle des conteneurs GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de conteneur.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Conformite du materiel de jonction au catalogue (detection_catalogue_materiel)
    2. Rattachement du materiel a une jonction de type valide (e7102)
    3. Unicite des identifiants de materiel entre jonctions (e9601)
    4. Caracteristiques de poteau conformes au catalogue (detection_catalogue_support)
    5. Types de noeuds autorises a se rattacher a un coffret (e6108)
    6. Chaine de localisation des noeuds sans geometrie propre (detection_localisation_noeud)
    7. Localisation des remontees aero-souterraines (e6204)
    8. Localisation des points de comptage et ouvrages collectifs (e6109)
    9. Nombre de cables raccordes, un code par TypeJonction (e6201, e6202,
       e6203), la nature du cable telecom (e6116) et la divergence
       declaration / geometrie (e9609)
   10. Rattachement des noeuds du reseau a un cable existant (detection_references_noeud_cable)
   11. Nomenclature de composition des coffrets (detection_composition_coffret)

Usage CLI :
    python -m recostar.controle.conteneur.pipeline_controle_conteneur --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.conteneur.e2201 import executer_controle_cli as executer_2201
from recostar.controle.conteneur.e3110 import executer_controle_cli as executer_controle_geometrie_supplementaire
from recostar.controle.conteneur.e6105 import executer_controle_cli as executer_6105
from recostar.controle.conteneur.e6106 import executer_controle_cli as executer_6106
from recostar.controle.conteneur.e6107 import executer_controle_cli as executer_6107
from recostar.controle.conteneur.e6108 import executer_controle_cli as executer_controle_noeuds_coffret
from recostar.controle.conteneur.e6109 import executer_controle_cli as executer_controle_localisation_ouvrages
from recostar.controle.conteneur.e6112 import executer_controle_cli as executer_6112
from recostar.controle.conteneur.e6113 import executer_controle_cli as executer_6113
from recostar.controle.conteneur.e6114 import executer_controle_cli as executer_6114
from recostar.controle.conteneur.e6115 import executer_controle_cli as executer_6115
from recostar.controle.conteneur.e6116 import executer_controle_cli as executer_controle_jonction_telecom
from recostar.controle.conteneur.e6201 import executer_controle_cli as executer_controle_derivation
from recostar.controle.conteneur.e6202 import executer_controle_cli as executer_controle_jonction_simple
from recostar.controle.conteneur.e6203 import executer_controle_cli as executer_controle_extremite_reseau
from recostar.controle.conteneur.e6204 import executer_controle_cli as executer_controle_localisation_remontees
from recostar.controle.conteneur.e6208 import executer_controle_cli as executer_6208
from recostar.controle.conteneur.e6209 import executer_controle_cli as executer_6209
from recostar.controle.conteneur.e6213 import executer_controle_cli as executer_6213
from recostar.controle.conteneur.e7100 import executer_controle_cli as executer_7100
from recostar.controle.conteneur.e7101 import executer_controle_cli as executer_7101
from recostar.controle.conteneur.e7102 import executer_controle_cli as executer_controle_rattachement_materiel
from recostar.controle.conteneur.e7103 import executer_controle_cli as executer_7103
from recostar.controle.conteneur.e7104 import executer_controle_cli as executer_7104
from recostar.controle.conteneur.e7305 import executer_controle_cli as executer_7305
from recostar.controle.conteneur.e9600 import executer_controle_cli as executer_9600
from recostar.controle.conteneur.e9601 import executer_controle_cli as executer_controle_unicite_identifiants
from recostar.controle.conteneur.e9602 import executer_controle_cli as executer_9602
from recostar.controle.conteneur.e9603 import executer_controle_cli as executer_9603
from recostar.controle.conteneur.e9604 import executer_controle_cli as executer_9604
from recostar.controle.conteneur.e9605 import executer_controle_cli as executer_9605
from recostar.controle.conteneur.e9606 import executer_controle_cli as executer_9606
from recostar.controle.conteneur.e9607 import executer_controle_cli as executer_9607
from recostar.controle.conteneur.e9608 import executer_controle_cli as executer_9608
from recostar.controle.conteneur.e9609 import executer_controle_cli as executer_controle_raccordement
from recostar.controle.fonctions_communes.sortie_famille import agreger_ecarts_famille

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "E-7104",
    "E-7100",
    "E-7101",
    "E-7305",
    "E-9600",
    "E-7102",
    "E-7103",
    "E-9601",
    "E-2201",
    "E-9602",
    "E-9603",
    "E-6108",
    "E-3110",
    "E-6105",
    "E-6106",
    "E-6112",
    "E-6209",
    "E-6204",
    "E-6109",
    "E-6201",
    "E-6202",
    "E-6203",
    "E-6116",
    "E-9609",
    "E-9604",
    "E-9605",
    "E-9606",
    "E-9607",
    "E-9608",
    "E-6113",
    "E-6114",
    "E-6115",
    "E-6213",
    "E-6107",
    "E-6208",
)


# Cle de la famille, reportee dans le champ FAMILLE_CONTROLE de chaque ecart.
FAMILLE: str = "conteneur"


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de conteneur.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees.

    `chemin_gml` n'est utile qu'a E-7100 et E-7101, qui comptent les relations
    `Ouvrage_Materiel` que la conversion ne conserve pas. A None, ils localisent
    eux-memes un GML present dans le repertoire, et se declarent sans objet s'il
    n'y en a pas.
    """
    repertoire_resolu = Path(repertoire).resolve()
    if not repertoire_resolu.is_dir():
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = Path(sortie).resolve() if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)

    rep = str(repertoire_resolu)
    dst = str(dossier_sortie)
    resultats_controles: dict[str, dict[str, Any]] = {
        "E-7104": executer_7104(rep, dst),
        "E-7100": executer_7100(rep, dst, chemin_gml),
        "E-7101": executer_7101(rep, dst, chemin_gml),
        "E-7305": executer_7305(rep, dst),
        "E-9600": executer_9600(rep, dst),
        "E-7102": executer_controle_rattachement_materiel(rep, dst),
        "E-7103": executer_7103(rep, dst),
        "E-9601": executer_controle_unicite_identifiants(rep, dst),
        "E-2201": executer_2201(rep, dst),
        "E-9602": executer_9602(rep, dst),
        "E-9603": executer_9603(rep, dst),
        "E-6108": executer_controle_noeuds_coffret(rep, dst),
        "E-3110": executer_controle_geometrie_supplementaire(rep, dst),
        "E-6105": executer_6105(rep, dst),
        "E-6106": executer_6106(rep, dst),
        "E-6112": executer_6112(rep, dst),
        "E-6209": executer_6209(rep, dst),
        "E-6204": executer_controle_localisation_remontees(rep, dst),
        "E-6109": executer_controle_localisation_ouvrages(rep, dst),
        "E-6201": executer_controle_derivation(rep, dst),
        "E-6202": executer_controle_jonction_simple(rep, dst),
        "E-6203": executer_controle_extremite_reseau(rep, dst),
        "E-6116": executer_controle_jonction_telecom(rep, dst),
        "E-9609": executer_controle_raccordement(rep, dst),
        "E-9604": executer_9604(rep, dst),
        "E-9605": executer_9605(rep, dst),
        "E-9606": executer_9606(rep, dst),
        "E-9607": executer_9607(rep, dst),
        "E-9608": executer_9608(rep, dst),
        "E-6113": executer_6113(rep, dst),
        "E-6114": executer_6114(rep, dst),
        "E-6115": executer_6115(rep, dst),
        "E-6213": executer_6213(rep, dst),
        "E-6107": executer_6107(rep, dst),
        "E-6208": executer_6208(rep, dst),
    }

    nb_anomalies_total = sum(r.get("nombre_anomalies", 0) for r in resultats_controles.values() if r.get("succes"))

    return {
        "succes": True,
        "controles": resultats_controles,
        "nombre_anomalies_total": nb_anomalies_total,
        # Les ecarts des controles sont refondus en un fichier unique, aux
        # champs communs a toutes les familles : c'est la sortie que lisent les
        # trois modes d'execution.
        "ecarts_famille": agreger_ecarts_famille(
            (resultat.get("sortie") for resultat in resultats_controles.values()),
            dst,
            FAMILLE,
        ),
    }


def main() -> None:
    """Point d'entree CLI du pipeline de controles de conteneur."""
    parseur = argparse.ArgumentParser(description="Pipeline de controle des conteneurs GeoJSON")
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
    resultat = executer_pipeline(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
