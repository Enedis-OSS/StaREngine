#!/usr/bin/env python3
"""
Controle E-9502 : la jonction n'est pas positionnee sur une extremite du cable.

Verifie que chaque entite RPD_Jonction_Reco liee a un RPD_CableElectrique_Reco
en cours de mise en service est positionnee sur l'une des extremites de la
geometrie de ce cable. Une jonction superposee a un sommet intermediaire, ou a
un point quelconque du trace, n'est pas conforme.

Une anomalie par **lien** (jonction, cable) : une jonction liee a deux cables
mal raccordes en genere deux, chacune nommant le cable a reprendre. L'ecart
porte la distance a l'extremite la plus proche — quelques centimetres se
corrigent autrement qu'une inversion de reference.

Perimetre : toute RPD_Jonction_Reco declarant un cables_href, quel que soit son
TypeJonction ; une remontee aero-souterraine mal posee reste une anomalie. Cote
cable, les seuls RPD_CableElectrique_Reco au Statut UnderCommissionning : une
reference vers un cable d'un autre statut, d'un autre type ou inexistant est
hors perimetre : l'integrite referentielle releve d'E-9400 et la presence d'un
noeud a chaque extremite, d'E-6110.

Un code local a star-engine
---------------------------
Le verificateur ne nomme pas cette anomalie : `E-9502` appartient a la serie
`E-9xxx` que le projet se reserve, dont la numerotation `E-9<famille><sequence>`
reprend la famille du controle — ici `5`, le cable.

Le moteur de detection est partage
----------------------------------
`detection_cables_jonction` releve toutes les anomalies de raccordement d'une
jonction ; ce controle ne retient que celles de son code. Les autres controles
servis par ce moteur jugent le *nombre* de cables raccordes a une jonction :
E-6201, E-6202, E-6203, E-6116 et E-9609, dans `conteneur/`.

Les deux constats se completent : E-9609 dit qu'une jonction diverge de sa
declaration (`raccordement_incoherent`), E-9502 dit **lequel** de ses cables. Le
moteur commun ne calcule la coincidence qu'une fois, a
`TOLERANCE_SUPERPOSITION`, si bien que les deux ne peuvent pas diverger.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e9502_jonction_extremite_cable.geojson

Usage CLI :
    python -m recostar.controle.cable.e9502 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_cables_jonction import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.modele_recostar import FICHIER_JONCTION

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9502_jonction_extremite_cable.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-9502"

# Type d'anomalie relevant de ce code. Le moteur en detecte quatre autres, qui
# appartiennent aux controles de cardinalite du conteneur.
# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"jonction_hors_extremite"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "jonction_hors_extremite": ("La jonction n'est pas positionnée sur une extrémité du câble."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    # Les deux bouts du lien, la jonction d'abord : c'est elle que l'ecart
    # localise, le cable disant de quelle reference elle s'ecarte.
    champs_id=("id_jonction", "id_cable"),
    # Couche de l'entite en anomalie, que les ecarts ne nomment pas.
    couche_source=FICHIER_JONCTION,
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-9502 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(
        repertoire,
        TYPES_RETENUS,
        PROFIL_ECARTS,
        FICHIER_SORTIE,
        sortie,
    )


def main() -> None:
    """Point d'entree CLI du controle de position des jonctions."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-9502 : coherence geometrique jonction / extremite de cable — "
            "toute RPD_Jonction_Reco liee a un RPD_CableElectrique_Reco au statut "
            "UnderCommissionning doit etre posee sur l'une des extremites de ce "
            "cable, a 1 mm pres."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
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
