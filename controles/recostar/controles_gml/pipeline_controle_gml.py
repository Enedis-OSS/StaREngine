"""
Pipeline de controle des fichiers GML/GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles GML
et centralise les resultats. Chaque controle est execute via sa
fonction `executer_controle_cli`.

Controles enchaines :
    1. Unicite des identifiants (controle_unicite_id)
    2. Conformite des valeurs aux listes XSD (controle_valeur_xsd)
    3. Generation du rapport PDF (rapport_pdf_gml)

Usage CLI :
    python pipeline_controle_gml.py --repertoire <chemin> [--sortie <chemin>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from controle_unicite_id import executer_controle_cli as executer_controle_unicite
from controle_valeur_xsd import executer_controle_cli as executer_controle_valeur_xsd
from rapport_pdf_gml import executer_rapport_cli


def _compter_anomalies_depuis_ecarts(chemin_ecarts: str) -> int:
    """Compte le nombre d'anomalies dans un fichier GeoJSON d'ecarts."""
    if not os.path.isfile(chemin_ecarts):
        return 0
    with open(chemin_ecarts, "r", encoding="utf-8") as fichier:
        donnees = json.load(fichier)
    return len(donnees.get("features", []))


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles GML et centralise les resultats.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire
    os.makedirs(dossier_sortie, exist_ok=True)

    # Association nom -> fonction d'execution
    fonctions_controles: tuple[tuple[str, Any], ...] = (
        ("controle_unicite_id", executer_controle_unicite),
        ("controle_valeur_xsd", executer_controle_valeur_xsd),
    )

    resultats_controles: dict[str, dict[str, Any]] = {}
    nb_anomalies_total = 0

    for nom, fonction in fonctions_controles:
        resultat = fonction(repertoire, dossier_sortie)
        resultats_controles[nom] = resultat

        if not resultat.get("succes"):
            continue

        # Comptage : utiliser le nombre direct si disponible, sinon compter
        # depuis le fichier d'ecarts (unicite_id ne fournit pas nombre_anomalies)
        if "nombre_anomalies" in resultat:
            nb_anomalies_total += resultat["nombre_anomalies"]
        elif "ecarts" in resultat:
            nb_anomalies_total += _compter_anomalies_depuis_ecarts(resultat["ecarts"])

    # Le rapport PDF lit les fichiers d'ecarts dans le dossier de sortie
    resultat_rapport = executer_rapport_cli(dossier_sortie, dossier_sortie)

    return {
        "succes": True,
        "controles": resultats_controles,
        "rapport": resultat_rapport,
        "nombre_anomalies_total": nb_anomalies_total,
    }


def main() -> None:
    """Point d'entree CLI du pipeline de controles GML."""
    parseur = argparse.ArgumentParser(
        description="Pipeline de controle des fichiers GML/GeoJSON"
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
