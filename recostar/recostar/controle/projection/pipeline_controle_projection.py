"""
Pipeline de controle de projection des GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de projection.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Conformite de projection (controle_e300)
    2. Coherence spatiale (controle_e301)
    3. Superficie des geometries supplementaires (controle_e302)
    4. Appartenance a l'emprise DR (controle_e303)

Usage CLI :
    python pipeline_controle_projection.py --repertoire <chemin>
                                           [--sortie <chemin>]
                                           [--numero_affaire <numero>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from controle_e300 import executer_controle_cli as executer_controle_projection
from controle_e301 import executer_controle_cli as executer_controle_coherence_spatiale
from controle_e302 import (
    executer_controle_cli as executer_controle_geometrie_supplementaire,
)
from controle_e303 import executer_controle_cli as executer_controle_emprise_dr

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_e300",
    "controle_e301",
    "controle_e302",
    "controle_e303",
)


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
    numero_affaire: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de projection.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees.

    numero_affaire est requis pour E303 (controle d'emprise DR). Sans ce
    parametre, E303 retourne une erreur qui n'impacte pas les autres controles.
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
        "controle_e300": executer_controle_projection(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e301": executer_controle_coherence_spatiale(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e302": executer_controle_geometrie_supplementaire(str(repertoire_resolu), str(dossier_sortie)),
        "controle_e303": executer_controle_emprise_dr(str(repertoire_resolu), numero_affaire, str(dossier_sortie)),
    }

    nb_anomalies_total = sum(r.get("nombre_anomalies", 0) for r in resultats_controles.values() if r.get("succes"))

    return {
        "succes": True,
        "controles": resultats_controles,
        "nombre_anomalies_total": nb_anomalies_total,
    }


def main() -> None:
    """Point d'entree CLI du pipeline de controles de projection."""
    parseur = argparse.ArgumentParser(description="Pipeline de controle de projection des GeoJSON")
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
    parseur.add_argument(
        "--numero_affaire",
        default=None,
        help="Numero d'affaire pour E303 (format RAC-XXX-YY-NNNNNN ou XXNN/NNNNNN)",
    )
    arguments = parseur.parse_args()
    resultat = executer_pipeline(arguments.repertoire, arguments.sortie, arguments.numero_affaire)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
