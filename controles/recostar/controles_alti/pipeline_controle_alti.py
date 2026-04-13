"""
Pipeline de controle altimetrique des GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles altimetriques
puis genere un rapport PDF de synthese. Chaque controle est execute via sa
fonction `executer_controle_cli` et les resultats sont centralises.

Controles enchaines :
    1. Conformite 3D (controle_3d)
    2. Coordonnees Z nulles (controle_z_null)
    3. Altimetrie des sommets (controle_alti_sommets)
    4. Altimetrie IGN (controle_alti_ign)
    5. Generation du rapport PDF (rapport_pdf_alti)

Usage CLI :
    python pipeline_controle_alti.py --repertoire <chemin> [--sortie <chemin>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from controle_3d import executer_controle_cli as executer_controle_3d
from controle_alti_ign import executer_controle_cli as executer_controle_ign
from controle_alti_sommets import executer_controle_cli as executer_controle_sommets
from controle_z_null import executer_controle_cli as executer_controle_z_null
from rapport_pdf_alti import executer_rapport_cli

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_3d",
    "controle_z_null",
    "controle_alti_sommets",
    "controle_alti_ign",
)


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles altimetriques puis genere le rapport.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Le rapport PDF est genere dans
    le repertoire de sortie, en lisant les fichiers d'ecarts produits.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire
    os.makedirs(dossier_sortie, exist_ok=True)

    resultats_controles: dict[str, dict[str, Any]] = {}

    resultats_controles["controle_3d"] = executer_controle_3d(
        repertoire, dossier_sortie
    )
    resultats_controles["controle_z_null"] = executer_controle_z_null(
        repertoire, dossier_sortie
    )
    resultats_controles["controle_alti_sommets"] = executer_controle_sommets(
        repertoire, dossier_sortie
    )
    resultats_controles["controle_alti_ign"] = executer_controle_ign(
        repertoire, dossier_sortie
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
    """Point d'entree CLI du pipeline de controles altimetriques."""
    parseur = argparse.ArgumentParser(
        description="Pipeline de controle altimetrique des GeoJSON"
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
