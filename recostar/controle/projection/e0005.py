#!/usr/bin/env python3
"""
Controle E-0005 : le numero de dossier ne correspond pas aux modeles attendus.

Le numero de dossier d'une livraison suit l'un des six modeles du projet, tous
termines par un indice de version — `-1`, `-12`, `-003` — qui distingue les depots
successifs d'un meme dossier :

    type1   DA21/256553-1              prefixe de dossier, lettre + 2 chiffres
    type2   A743/256553-1              prefixe de dossier des DR outre-mer
    type3   RAC-CVL-25-007998-1        trigramme RACING de la DR
    type4   RAC-25-ABC123456789-1      identifiant RACING opaque
    type5   12345678-1                 numero interne
    type6   OSR20250114-1              dossier OSR

Un numero qui n'en suit aucun est signale ici. La resolution de la direction
regionale, quand le modele en porte une, releve d'E-0006 : les deux regles sont
exclusives, un numero hors modele n'ayant aucune reference a resoudre.

Les modeles vivent dans `fonctions_communes.numero_affaire` et sont ancres aux
deux bouts ; seuls les espaces de bord sont tolares.

Le moteur `detection_numero_affaire` evalue les deux
constats en cascade, ce controle ne retenant que celui de son code. L'autre
controle issu du meme moteur est **E-0006**, dans `e0006.py`.

Entree  : repertoire de GeoJSON RecoStaR et le numero d'affaire de la livraison
Sortie  : ecarts_e0005_numero_dossier_hors_modele.geojson

Usage CLI :
    python -m recostar.controle.projection.e0005 --repertoire <chemin> \
        --numero_affaire <numero> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.projection.detection_numero_affaire import COUCHE_SOURCE, executer_analyse

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e0005_numero_dossier_hors_modele.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-0005"

# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"numero_dossier_hors_modele"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "numero_dossier_hors_modele": ("Le numéro de dossier ne correspond à aucun des six modèles attendus."),
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
    """Execute le controle E-0005 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, numero_affaire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-0005."""
    parseur = argparse.ArgumentParser(
        description="Controle E-0005 : un numero de dossier ne suivant aucun des six modeles attendus."
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
