"""
Pipeline de controle des cheminements GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de cheminement.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Superpositions geometriques entre cheminements (e5108)
    2. Integrite des relations cables / cheminements (detection_relations_cheminement)
    3. Coherence cable de terre / cheminement incompatible (e3109)
    4. Coherence d'implantation des cables electriques (e3111)
    5. Profondeur manquante aux charges generatrices (e6205)

Usage CLI :
    python -m recostar.controle.cheminement.pipeline_controle_cheminement --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.cheminement.e3102 import executer_controle_cli as executer_3102
from recostar.controle.cheminement.e3103 import executer_controle_cli as executer_3103
from recostar.controle.cheminement.e3109 import executer_controle_cli as executer_controle_cable_terre
from recostar.controle.cheminement.e3111 import executer_controle_cli as executer_controle_implantation_cables
from recostar.controle.cheminement.e5108 import executer_controle_cli as executer_controle_superpositions
from recostar.controle.cheminement.e6205 import executer_controle_cli as executer_controle_charge_generatrice
from recostar.controle.cheminement.e9400 import executer_controle_cli as executer_9400
from recostar.controle.cheminement.e9401 import executer_controle_cli as executer_9401
from recostar.controle.fonctions_communes.sortie_famille import agreger_ecarts_famille

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "E-5108",
    "E-3102",
    "E-3103",
    "E-9400",
    "E-9401",
    "E-3109",
    "E-3111",
    "E-6205",
)


# Cle de la famille, reportee dans le champ FAMILLE_CONTROLE de chaque ecart.
FAMILLE: str = "cheminement"


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de cheminement.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees. Le controle E-6205 deduit
    seul la version RecoStaR (mode auto), comme en execution unitaire.
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
        "E-5108": executer_controle_superpositions(rep, dst),
        "E-3102": executer_3102(rep, dst),
        "E-3103": executer_3103(rep, dst),
        "E-9400": executer_9400(rep, dst),
        "E-9401": executer_9401(rep, dst),
        "E-3109": executer_controle_cable_terre(rep, dst),
        "E-3111": executer_controle_implantation_cables(rep, dst),
        "E-6205": executer_controle_charge_generatrice(rep, dst),
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
    """Point d'entree CLI du pipeline de controles de cheminement."""
    parseur = argparse.ArgumentParser(description="Pipeline de controle des cheminements GeoJSON")
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
