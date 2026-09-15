#!/usr/bin/env python3
"""
Controle E-9701 : le cable n'est pas altimetre — tous les points de leve
rattaches a ses sommets intermediaires portent une altitude nulle.

Un point de leve superpose a un sommet **intermediaire** de cable mesure le
terrain a cet endroit du trace : c'est lui qui atteste que le cable a ete leve
en altitude. Quand tous ces points portent un Z nul, le trace du cable n'est pas
altimetre, quel que soit le nombre de sommets qu'il decrit.

Une anomalie par cable
----------------------
Le defaut se corrige cable par cable, en reprenant le leve de son trace : le
controle en rend donc un ecart par cable, et non un constat de jeu. Un cable
altimetre, meme partiellement, n'en porte aucun — une seule mesure reelle suffit
a attester que son trace a ete leve.

Cette maille est celle du defaut, non celle de la livraison : un jeu peut
parfaitement porter des cables leves et d'autres non, et c'est alors la liste des
seconds qui interesse le correcteur.

Pourquoi ecarter les extremites
-------------------------------
Un cable se raccorde a ses extremites a un ouvrage — jonction, coffret, support —
dont le point de leve peut tenir son altitude d'ailleurs que du trace. Les
sommets intermediaires, eux, ne sont leves que pour decrire le cheminement : leur
altitude est la mesure, et c'est sur elle que porte le controle.

Ce que le controle ne dit pas
-----------------------------
Un sommet intermediaire sans point de leve rattache ne le concerne pas : cette
absence releve d'E-5102. Le controle ne juge que les altitudes des points
effectivement rattaches, et reste muet sur un cable qui n'en a aucun.

Le moteur `detection_sommets_cables` porte la detection. Autres controles servis
par ce moteur : e5102, e5103.

Usage CLI :
    python -m recostar.controle.altimetrie.e9701 --repertoire <chemin> [--sortie <chemin>]
                                                 [--version {auto,1.0,1.1}]

Sortie : ecarts_e9701_cable_non_altimetre.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.altimetrie.detection_sommets_cables import analyser_cables_non_altimetres
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.version_recostar import JETON_AUTO, VERSIONS_SUPPORTEES

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9701_cable_non_altimetre.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-9701"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_points_leve_altitude_nulle": (
        "Tous les points de levé rattachés aux sommets intermédiaires du câble portent "
        "une altitude nulle : le tracé du câble n'est pas altimétré."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E-9701 et ecrit ses ecarts."""
    return analyser_cables_non_altimetres(repertoire, PROFIL_ECARTS, FICHIER_SORTIE, sortie, version)


def main() -> None:
    """Point d'entree CLI du controle E-9701."""
    parseur = argparse.ArgumentParser(
        description="Controle E-9701 : le câble n'est pas altimétré (points de levé tous à zéro)"
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les GeoJSON a analyser")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--version",
        default=JETON_AUTO,
        choices=(JETON_AUTO, *VERSIONS_SUPPORTEES),
        help="Version RecoStaR appliquee (defaut : detection automatique)",
    )
    arguments = parseur.parse_args()

    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    if not resultat.get("succes"):
        print(f"Erreur : {resultat.get('erreur', 'echec non precise')}", file=sys.stderr)

    json.dump(resultat, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
