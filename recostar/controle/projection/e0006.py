#!/usr/bin/env python3
"""
Controle E-0006 : le numero de dossier ne renvoie pas a une DR connue.

Le numero suit bien l'un des modeles, mais la reference qu'il porte — prefixe de
dossier (`DA21`, `A743`) ou trigramme RACING (`CVL`) — ne figure pas dans
`projection/fichiers_dr/reference_dr.json`, le referentiel des directions
regionales que lisent deja les controles d'emprise.

Trois modeles hors perimetre
----------------------------
`type4`, `type5` et `type6` sont bien formes mais ne designent aucune direction
regionale : il n'y a rien a resoudre, et ce controle les laisse passer. Ce sont
exactement les numeros qu'`affaire_exclue_du_controle` ecarte deja des controles
d'emprise, pour la meme raison.

Un numero ne suivant aucun modele releve d'E-0005, et non d'ici : les deux regles
sont exclusives, evaluees en cascade.

Le moteur `detection_numero_affaire` evalue les deux
constats en cascade, ce controle ne retenant que celui de son code. L'autre
controle issu du meme moteur est **E-0005**, dans `e0005.py`.

Entree  : repertoire de GeoJSON RecoStaR et le numero d'affaire de la livraison
Sortie  : ecarts_e0006_numero_dossier_dr_inconnue.geojson

Usage CLI :
    python -m recostar.controle.projection.e0006 --repertoire <chemin> \
        --numero_affaire <numero> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.projection.detection_numero_affaire import COUCHE_SOURCE, executer_analyse

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e0006_numero_dossier_dr_inconnue.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-0006"

# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"numero_dossier_dr_inconnue"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "numero_dossier_dr_inconnue": (
        "La référence du numéro de dossier ne correspond à aucune direction régionale connue."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    # L'entite en anomalie est le numero lui-meme : il n'y a pas d'objet du
    # reseau a designer, et la couche source le dit explicitement.
    champs_id=("id_entite",),
    couche_source=COUCHE_SOURCE,
)


def executer_controle_cli(
    repertoire: str,
    numero_affaire: str | None = None,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-0006 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, numero_affaire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-0006."""
    parseur = argparse.ArgumentParser(
        description="Controle E-0006 : un numero de dossier dont la reference ne renvoie a aucune DR connue."
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les fichiers GeoJSON")
    parseur.add_argument("--numero_affaire", required=True, help="Numero de dossier de la livraison")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.numero_affaire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
