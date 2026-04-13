"""
Pipeline de controle PLOR des GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles PLOR
puis genere un rapport PDF de synthese. Chaque controle est execute via
sa fonction `executer_controle_cli` et les resultats sont centralises.

Controles enchaines :
    1. Superposition PLOR / cables (controle_plor_cable)
    2. Doublons de points (controle_plor_doublons)
    3. Superposition de cheminements (controle_cheminement_superpose)
    4. Generation du rapport PDF (rapport_pdf_plor)

Usage CLI :
    python pipeline_controle_plor.py --repertoire <chemin> [--sortie <chemin>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from controle_cheminement_superpose import (
    executer_controle_cli as executer_controle_cheminement,
)
from controle_plor_cable import executer_controle_cli as executer_controle_cable
from controle_plor_doublons import executer_controle_cli as executer_controle_doublons
from rapport_pdf_plor import executer_rapport_cli

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_plor_cable",
    "controle_plor_doublons",
    "controle_cheminement_superpose",
)


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles PLOR puis genere le rapport.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Le rapport PDF est genere dans
    le repertoire de sortie, en lisant les fichiers d'ecarts produits.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire
    os.makedirs(dossier_sortie, exist_ok=True)

    resultats_controles: dict[str, dict[str, Any]] = {}

    resultats_controles["controle_plor_cable"] = executer_controle_cable(
        repertoire, dossier_sortie
    )
    resultats_controles["controle_plor_doublons"] = executer_controle_doublons(
        repertoire, dossier_sortie
    )
    resultats_controles["controle_cheminement_superpose"] = (
        executer_controle_cheminement(repertoire, dossier_sortie)
    )

    # Le rapport PDF lit les fichiers d'ecarts dans le dossier de sortie
    resultat_rapport = executer_rapport_cli(dossier_sortie, dossier_sortie)

    nb_anomalies_total = sum(
        r.get("nombre_anomalies", 0)
        for r in resultats_controles.values()
        if r.get("succes")
    )

    return {
        "succes": True,
        "controles": resultats_controles,
        "rapport": resultat_rapport,
        "nombre_anomalies_total": nb_anomalies_total,
    }


def main() -> None:
    """Point d'entree CLI du pipeline de controles PLOR."""
    parseur = argparse.ArgumentParser(
        description="Pipeline de controle PLOR des GeoJSON"
    )
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
