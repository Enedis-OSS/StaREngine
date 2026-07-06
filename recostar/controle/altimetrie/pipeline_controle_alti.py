"""
Pipeline de controle altimetrique des GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles altimetriques.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Conformite 3D (controle_e200)
    2. Coordonnees Z nulles (controle_e201)
    3. Altimetrie des sommets (controle_e202)
    4. Altimetrie IGN (controle_e203)
    5. Doublons spatiaux (controle_e204)

Usage CLI :
    python pipeline_controle_alti.py --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from controle_e200 import executer_controle_cli as executer_controle_3d
from controle_e201 import executer_controle_cli as executer_controle_z_null
from controle_e202 import executer_controle_cli as executer_controle_sommets
from controle_e203 import executer_controle_cli as executer_controle_ign
from controle_e204 import executer_controle_cli as executer_controle_doublons_spatiaux
from controle_e205 import (
    executer_controle_cli as executer_controle_point_leve_geom_supp,
)

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_e200",
    "controle_e201",
    "controle_e202",
    "controle_e203",
    "controle_e204",
    "controle_e205",
)


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles altimetriques.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees.
    """
    repertoire_resolu = Path(repertoire).resolve()
    if not repertoire_resolu.is_dir():
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = Path(sortie).resolve() if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)

    resultats_controles: dict[str, dict[str, Any]] = {
        "controle_e200": executer_controle_3d(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e201": executer_controle_z_null(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e202": executer_controle_sommets(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e203": executer_controle_ign(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e204": executer_controle_doublons_spatiaux(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e205": executer_controle_point_leve_geom_supp(str(repertoire_resolu), str(dossier_sortie)),
    }

    nb_anomalies_total = sum(r.get("nombre_anomalies", 0) for r in resultats_controles.values() if r.get("succes"))

    return {
        "succes": True,
        "controles": resultats_controles,
        "nombre_anomalies_total": nb_anomalies_total,
    }


def main() -> None:
    """Point d'entree CLI du pipeline de controles altimetriques."""
    parseur = argparse.ArgumentParser(description="Pipeline de controle altimetrique des GeoJSON")
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
