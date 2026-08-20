"""
Pipeline de controle des cables GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de cable.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Coherence du DomaineTension jonction / cables electriques (controle_e500)
    2. Coherence metier FonctionCable / DomaineTension / HierarchieBT (controle_e501)
    3. Coherence de la designation des cables avec le referentiel (controle_e502)
    4. Precision XY/Z des cheminements associes a un cable electrique (controle_e503)
    5. Densite de sommets des cables electriques (controle_e504)
    6. Coherence longueur / DomaineTension des cables electriques (controle_e505)
    7. Raccordement des cables aux noeuds du reseau (controle_e506)
    8. Position des jonctions sur les extremites des cables (controle_e507)
    9. Cables HTB situes dans l'emprise DR (controle_e508)
   10. Discretisation des courbes des cables electriques (controle_e509)

Usage CLI :
    python pipeline_controle_cable.py --repertoire <chemin> [--sortie <chemin>]
                                      [--numero_affaire <numero>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from controle_e500 import executer_controle_cli as executer_controle_domaine_tension
from controle_e501 import executer_controle_cli as executer_controle_fonction_cable
from controle_e502 import executer_controle_cli as executer_controle_designation
from controle_e503 import executer_controle_cli as executer_controle_precision_cheminement
from controle_e504 import executer_controle_cli as executer_controle_densite_sommets
from controle_e505 import executer_controle_cli as executer_controle_longueur_domaine
from controle_e506 import executer_controle_cli as executer_controle_raccordement
from controle_e507 import executer_controle_cli as executer_controle_position_jonction
from controle_e508 import executer_controle_cli as executer_controle_cable_htb_emprise
from controle_e509 import executer_controle_cli as executer_controle_discretisation_courbe

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_e500",
    "controle_e501",
    "controle_e502",
    "controle_e503",
    "controle_e504",
    "controle_e505",
    "controle_e506",
    "controle_e507",
    "controle_e508",
    "controle_e509",
)


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
    numero_affaire: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de cable.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees.

    numero_affaire est requis pour E508 (emprise DR). Sans ce parametre, E508
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
        "controle_e500": executer_controle_domaine_tension(rep, dst),
        "controle_e501": executer_controle_fonction_cable(rep, dst),
        "controle_e502": executer_controle_designation(rep, dst),
        "controle_e503": executer_controle_precision_cheminement(rep, dst),
        "controle_e504": executer_controle_densite_sommets(rep, dst),
        "controle_e505": executer_controle_longueur_domaine(rep, dst),
        "controle_e506": executer_controle_raccordement(rep, dst),
        "controle_e507": executer_controle_position_jonction(rep, dst),
        "controle_e508": executer_controle_cable_htb_emprise(rep, numero_affaire, dst),
        "controle_e509": executer_controle_discretisation_courbe(rep, dst),
    }

    nb_anomalies_total = sum(r.get("nombre_anomalies", 0) for r in resultats_controles.values() if r.get("succes"))

    return {
        "succes": True,
        "controles": resultats_controles,
        "nombre_anomalies_total": nb_anomalies_total,
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
        help="Numero d'affaire pour E508 (format RAC-XXX-YY-NNNNNN ou XXNN/NNNNNN)",
    )
    arguments = parseur.parse_args()
    resultat = executer_pipeline(arguments.repertoire, arguments.sortie, arguments.numero_affaire)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
