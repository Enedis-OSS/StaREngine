"""
Pipeline de controle des cheminements GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de cheminement.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Superpositions geometriques entre cheminements (controle_e400)
    2. Integrite des relations cables / cheminements (controle_e401)
    3. Coherence cable de terre / cheminement incompatible (controle_e402)
    4. Coherence d'implantation des cables electriques (controle_e403)
    5. Profondeur manquante aux charges generatrices (controle_e404)

Usage CLI :
    python pipeline_controle_cheminement.py --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from controle_e400 import executer_controle_cli as executer_controle_superpositions
from controle_e401 import executer_controle_cli as executer_controle_integrite_cables
from controle_e402 import executer_controle_cli as executer_controle_cable_terre
from controle_e403 import executer_controle_cli as executer_controle_implantation_cables
from controle_e404 import executer_controle_cli as executer_controle_charge_generatrice

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_e400",
    "controle_e401",
    "controle_e402",
    "controle_e403",
    "controle_e404",
)


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de cheminement.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees. Le controle E404 deduit
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
        "controle_e400": executer_controle_superpositions(rep, dst),
        "controle_e401": executer_controle_integrite_cables(rep, dst),
        "controle_e402": executer_controle_cable_terre(rep, dst),
        "controle_e403": executer_controle_implantation_cables(rep, dst),
        "controle_e404": executer_controle_charge_generatrice(rep, dst),
    }

    nb_anomalies_total = sum(r.get("nombre_anomalies", 0) for r in resultats_controles.values() if r.get("succes"))

    return {
        "succes": True,
        "controles": resultats_controles,
        "nombre_anomalies_total": nb_anomalies_total,
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
