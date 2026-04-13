"""
Pipeline de controle des noeuds du reseau electrique.

Orchestre l'execution sequentielle de l'ensemble des controles des noeuds
puis genere un rapport PDF de synthese. Chaque controle est execute via sa
fonction `executer_controle_cli` et les resultats sont centralises.

Controles enchaines :
    1. Geometrie des cables (controle_geometrie)
    2. Extremites des cables (controle_extremites)
    3. Domaine de tension (controle_domaine_tension)
    4. Coherence terre (controle_coherence_terre)
    5. Generation du rapport PDF (rapport_pdf_noeud)

Usage CLI :
    python pipeline_controle_noeud.py --repertoire <chemin> [--sortie <chemin>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from controle_coherence_terre import (
    executer_controle_cli as executer_controle_terre,
)
from controle_domaine_tension import (
    executer_controle_cli as executer_controle_tension,
)
from controle_extremites import (
    executer_controle_cli as executer_controle_extremites,
)
from controle_geometrie import (
    executer_controle_cli as executer_controle_geometrie,
)
from rapport_pdf_noeud import executer_rapport_cli

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "controle_geometrie",
    "controle_extremites",
    "controle_domaine_tension",
    "controle_coherence_terre",
)


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
    """Execute l'ensemble des controles des noeuds puis genere le rapport.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Le rapport PDF est genere dans
    le repertoire de sortie, en lisant les fichiers d'ecarts produits.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire
    os.makedirs(dossier_sortie, exist_ok=True)

    # Association nom → fonction d'execution
    fonctions_controles: tuple[tuple[str, Any], ...] = (
        ("controle_geometrie", executer_controle_geometrie),
        ("controle_extremites", executer_controle_extremites),
        ("controle_domaine_tension", executer_controle_tension),
        ("controle_coherence_terre", executer_controle_terre),
    )

    resultats_controles: dict[str, dict[str, Any]] = {}
    nb_anomalies_total = 0

    for nom, fonction in fonctions_controles:
        resultat = fonction(repertoire, dossier_sortie)
        resultats_controles[nom] = resultat

        if resultat.get("succes") and "ecarts" in resultat:
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
    """Point d'entree CLI du pipeline de controles des noeuds."""
    parseur = argparse.ArgumentParser(
        description="Pipeline de controle des noeuds du reseau electrique"
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
