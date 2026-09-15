"""
Pipeline de controle de projection des GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de projection.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Numero de dossier hors modele (e0005) ou sans DR connue (e0006)
    2. Projection non definie (e2200), differente du declare (e5105) ou
       minoritaire dans le jeu (e9302)
    2. Coherence spatiale (e9300)
    3. Superficie des geometries supplementaires (e9301)
    4. Appartenance a l'emprise DR (e5106)

Usage CLI :
    python -m recostar.controle.projection.pipeline_controle_projection --repertoire <chemin>
                                                                        [--sortie <chemin>]
                                                                        [--numero_affaire <numero>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.sortie_famille import agreger_ecarts_famille
from recostar.controle.projection.e0005 import executer_controle_cli as executer_controle_numero_modele
from recostar.controle.projection.e0006 import executer_controle_cli as executer_controle_numero_dr
from recostar.controle.projection.e2200 import executer_controle_cli as executer_controle_projection_absente
from recostar.controle.projection.e5105 import executer_controle_cli as executer_controle_projection_differente
from recostar.controle.projection.e5106 import executer_controle_cli as executer_controle_emprise_dr
from recostar.controle.projection.e9300 import executer_controle_cli as executer_controle_coherence_spatiale
from recostar.controle.projection.e9301 import (
    executer_controle_cli as executer_controle_geometrie_supplementaire,
)
from recostar.controle.projection.e9302 import executer_controle_cli as executer_controle_projection_non_unique

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "E-0005",
    "E-0006",
    "E-2200",
    "E-5105",
    "E-9302",
    "E-9300",
    "E-9301",
    "E-5106",
)


# Cle de la famille, reportee dans le champ FAMILLE_CONTROLE de chaque ecart.
FAMILLE: str = "projection"


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
    numero_affaire: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de projection.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees.

    numero_affaire est requis par E-5106 (emprise DR) ainsi que par E-0005 et
    E-0006, qui jugent le numero lui-meme. Sans ce parametre, ces trois
    controles retournent une erreur qui n'impacte pas les autres.
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
        "E-0005": executer_controle_numero_modele(str(repertoire_resolu), numero_affaire, str(dossier_sortie)),
        "E-0006": executer_controle_numero_dr(str(repertoire_resolu), numero_affaire, str(dossier_sortie)),
        "E-2200": executer_controle_projection_absente(str(repertoire_resolu), str(dossier_sortie)),
        "E-5105": executer_controle_projection_differente(str(repertoire_resolu), str(dossier_sortie)),
        "E-9302": executer_controle_projection_non_unique(str(repertoire_resolu), str(dossier_sortie)),
        "E-9300": executer_controle_coherence_spatiale(str(repertoire_resolu), str(dossier_sortie)),
        "E-9301": executer_controle_geometrie_supplementaire(str(repertoire_resolu), str(dossier_sortie)),
        "E-5106": executer_controle_emprise_dr(str(repertoire_resolu), numero_affaire, str(dossier_sortie)),
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
            str(dossier_sortie),
            FAMILLE,
        ),
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
        help="Numero d'affaire pour E-5106 (format RAC-XXX-YY-NNNNNN ou XXNN/NNNNNN)",
    )
    arguments = parseur.parse_args()
    resultat = executer_pipeline(arguments.repertoire, arguments.sortie, arguments.numero_affaire)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
