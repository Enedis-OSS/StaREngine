"""
Pipeline de controle des conteneurs GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles de conteneur.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Conformite du materiel de jonction au catalogue (controle_e600)
    2. Rattachement du materiel a une jonction de type valide (controle_e601)
    3. Unicite des identifiants de materiel entre jonctions (controle_e602)
    4. Caracteristiques de poteau conformes au catalogue (controle_e603)
    5. Types de noeuds autorises a se rattacher a un coffret (controle_e604)
    6. Chaine de localisation des noeuds sans geometrie propre (controle_e605)
    7. Localisation des remontees aero-souterraines (controle_e606)
    8. Localisation des points de comptage et ouvrages collectifs (controle_e607)
    9. Nombre de cables raccordes selon le type de jonction (controle_e608)
   10. Rattachement des noeuds du reseau a un cable existant (controle_e609)
   11. Nomenclature de composition des coffrets (controle_e610)

Usage CLI :
    python pipeline_controle_conteneur.py --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from controle_e600 import executer_controle_cli as executer_controle_materiel_jonction
from controle_e601 import executer_controle_cli as executer_controle_rattachement_materiel
from controle_e602 import executer_controle_cli as executer_controle_unicite_identifiants
from controle_e603 import executer_controle_cli as executer_controle_caracteristiques_poteau
from controle_e604 import executer_controle_cli as executer_controle_noeuds_coffret
from controle_e605 import executer_controle_cli as executer_controle_localisation_noeuds
from controle_e606 import executer_controle_cli as executer_controle_localisation_remontees
from controle_e607 import executer_controle_cli as executer_controle_localisation_ouvrages
from controle_e608 import executer_controle_cli as executer_controle_nombre_cables_jonction
from controle_e609 import executer_controle_cli as executer_controle_rattachement_cable
from controle_e610 import executer_controle_cli as executer_controle_nomenclature_coffret

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_e600",
    "controle_e601",
    "controle_e602",
    "controle_e603",
    "controle_e604",
    "controle_e605",
    "controle_e606",
    "controle_e607",
    "controle_e608",
    "controle_e609",
    "controle_e610",
)


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles de conteneur.

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

    rep = str(repertoire_resolu)
    dst = str(dossier_sortie)
    resultats_controles: dict[str, dict[str, Any]] = {
        "controle_e600": executer_controle_materiel_jonction(rep, dst),
        "controle_e601": executer_controle_rattachement_materiel(rep, dst),
        "controle_e602": executer_controle_unicite_identifiants(rep, dst),
        "controle_e603": executer_controle_caracteristiques_poteau(rep, dst),
        "controle_e604": executer_controle_noeuds_coffret(rep, dst),
        "controle_e605": executer_controle_localisation_noeuds(rep, dst),
        "controle_e606": executer_controle_localisation_remontees(rep, dst),
        "controle_e607": executer_controle_localisation_ouvrages(rep, dst),
        "controle_e608": executer_controle_nombre_cables_jonction(rep, dst),
        "controle_e609": executer_controle_rattachement_cable(rep, dst),
        "controle_e610": executer_controle_nomenclature_coffret(rep, dst),
    }

    nb_anomalies_total = sum(r.get("nombre_anomalies", 0) for r in resultats_controles.values() if r.get("succes"))

    return {
        "succes": True,
        "controles": resultats_controles,
        "nombre_anomalies_total": nb_anomalies_total,
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
