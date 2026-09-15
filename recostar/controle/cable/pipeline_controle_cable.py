"""
Pipeline de controle des cables GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de cable.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Coherence du DomaineTension jonction / cables electriques (e9500)
    2. Coherence metier FonctionCable / DomaineTension / HierarchieBT (detection_coherence_cable)
    3. Coherence de la designation des cables avec le referentiel (e2101)
    4. Precision XY/Z des cheminements associes a un cable electrique (e6103)
    5. Densite de sommets des cables electriques (e5100)
    6. Longueur excessive d'un cable BT (e4200) puis HTA (e4201)
    7. Raccordement des cables aux noeuds du reseau (detection_raccordement_cable)
    8. Position des jonctions sur les extremites des cables (e9502)
    9. Cables HTB situes dans l'emprise DR (e3304)
   10. Discretisation des courbes des cables electriques (detection_discretisation)

Usage CLI :
    python -m recostar.controle.cable.pipeline_controle_cable --repertoire <chemin> [--sortie <chemin>]
                                                              [--numero_affaire <numero>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.cable.e2101 import executer_controle_cli as executer_controle_designation
from recostar.controle.cable.e3104 import executer_controle_cli as executer_3104
from recostar.controle.cable.e3302 import executer_controle_cli as executer_3302
from recostar.controle.cable.e3304 import executer_controle_cli as executer_controle_cable_htb_emprise
from recostar.controle.cable.e4200 import executer_controle_cli as executer_controle_longueur_bt
from recostar.controle.cable.e4201 import executer_controle_cli as executer_controle_longueur_hta
from recostar.controle.cable.e5100 import executer_controle_cli as executer_controle_densite_sommets
from recostar.controle.cable.e5101 import executer_controle_cli as executer_5101
from recostar.controle.cable.e5200 import executer_controle_cli as executer_5200
from recostar.controle.cable.e6102 import executer_controle_cli as executer_6102
from recostar.controle.cable.e6103 import executer_controle_cli as executer_controle_precision_cheminement
from recostar.controle.cable.e6110 import executer_controle_cli as executer_6110
from recostar.controle.cable.e6111 import executer_controle_cli as executer_6111
from recostar.controle.cable.e9500 import executer_controle_cli as executer_controle_domaine_tension
from recostar.controle.cable.e9501 import executer_controle_cli as executer_9501
from recostar.controle.cable.e9502 import executer_controle_cli as executer_controle_position_jonction
from recostar.controle.fonctions_communes.sortie_famille import agreger_ecarts_famille

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "E-9500",
    "E-3104",
    "E-3302",
    "E-2101",
    "E-6103",
    "E-5100",
    "E-4200",
    "E-4201",
    "E-6110",
    "E-6111",
    "E-6102",
    "E-9501",
    "E-9502",
    "E-3304",
    "E-5101",
    "E-5200",
)


# Cle de la famille, reportee dans le champ FAMILLE_CONTROLE de chaque ecart.
FAMILLE: str = "cable"


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
    numero_affaire: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de cable.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees.

    numero_affaire est requis pour E-3304 (emprise DR). Sans ce parametre, E-3304
    retourne une erreur qui n'impacte pas les autres controles.
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
        "E-9500": executer_controle_domaine_tension(rep, dst),
        "E-3104": executer_3104(rep, dst),
        "E-3302": executer_3302(rep, dst),
        "E-2101": executer_controle_designation(rep, dst),
        "E-6103": executer_controle_precision_cheminement(rep, dst),
        "E-5100": executer_controle_densite_sommets(rep, dst),
        "E-4200": executer_controle_longueur_bt(rep, dst),
        "E-4201": executer_controle_longueur_hta(rep, dst),
        "E-6110": executer_6110(rep, dst),
        "E-6111": executer_6111(rep, dst),
        "E-6102": executer_6102(rep, dst),
        "E-9501": executer_9501(rep, dst),
        "E-9502": executer_controle_position_jonction(rep, dst),
        "E-3304": executer_controle_cable_htb_emprise(rep, numero_affaire, dst),
        "E-5101": executer_5101(rep, dst),
        "E-5200": executer_5200(rep, dst),
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
    """Point d'entree CLI du pipeline de controles de cable."""
    parseur = argparse.ArgumentParser(description="Pipeline de controle des cables GeoJSON")
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
        help="Numero d'affaire pour E-3304 (format RAC-XXX-YY-NNNNNN ou XXNN/NNNNNN)",
    )
    arguments = parseur.parse_args()
    resultat = executer_pipeline(arguments.repertoire, arguments.sortie, arguments.numero_affaire)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
