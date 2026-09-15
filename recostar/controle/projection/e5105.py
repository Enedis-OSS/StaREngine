#!/usr/bin/env python3
"""
Controle E-5105 : le systeme de projection du GML differe de celui des objets.

Le fichier GeoJSON portant l'entite declare un `crs`, mais qui ne correspond
pas au SRS annonce par `_metadata.json`. L'entite doit etre reprojetee, ou la
declaration corrigee.

Un fichier sans `crs` du tout releve d'E-2200 : sa projection n'est pas
differente, elle est absente. Les deux codes sont exclusifs par construction.

Le moteur `detection_projection` confronte en un seul
parcours la projection de chaque fichier au SRS declare par `_metadata.json`, et
les fichiers entre eux. Ce controle ne retient que les anomalies de son code ;
les deux autres controles qu'il sert sont **E-2200 et E-9302**.

Entree  : repertoire de GeoJSON RecoStaR et son `_metadata.json`
Sortie  : ecarts_e5105_projection_differente.geojson

Usage CLI :
    python -m recostar.controle.projection.e5105 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.projection.detection_projection import executer_analyse

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e5105_projection_differente.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-5105"

# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"projection_differente"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "projection_differente": ("Le système de projection du fichier diffère de celui déclaré par les métadonnées."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-5105 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-5105."""
    parseur = argparse.ArgumentParser(
        description="Controle E-5105 : une entite dont le fichier n'est pas dans la projection declaree par les metadonnees."
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON et le _metadata.json",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
