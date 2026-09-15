"""
Controle E-6206 : Le fichier possède des PLOR superposés en X,Y avec un mode de levé identique (Z identique ou différent)

Deux points leves poses au meme endroit et mesurant la **meme grandeur** font
double emploi : l'un des deux est une saisie en trop, et rien ne dit lequel des
deux releves fait foi. Deux leves superposes de types differents sont en revanche
normaux — une charge et une altitude se mesurent au meme point, c'est meme ce
qu'E-6104 exige.

La maille est **planimetrique** : seuls X, Y et le type de leve entrent dans
la comparaison, le Z etant indifferent — le libelle du code le dit lui-meme,
« Z identique ou different ».

Ce code **englobe** E-3300, arbitrage metier : deux leves superposes en X, Y, Z le
sont a fortiori en X, Y, et un meme groupe ressort alors sous les deux codes. Le
verificateur nomme deux defauts distincts, celui-ci plus large et plus grave
(`moyenne` contre `basse`) ; masquer l'un sous l'autre priverait le rapport d'une
des deux mailles.

Le moteur `detection_superposition_plor` releve les
deux mailles, ce controle ne retenant que la sienne. Il lit le **GML source**,
`conversion_V1_1` supprimant `TypeLeve`, et ne vaut qu'en RecoStaR V1.0 ; en
V1.1 le rapport est celui d'un controle sans objet. L'autre controle issu du meme
moteur : e3300.

Usage CLI :
    python -m recostar.controle.altimetrie.e6206 --repertoire <chemin> [--sortie <chemin>]
                                                 [--gml <fichier.gml>] [--version {auto,1.0,1.1}]

Sortie : ecarts_e6206_plor_superpose_xy.geojson
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from recostar.controle.altimetrie.detection_superposition_plor import FICHIER_SOURCE, executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.version_recostar import JETON_AUTO, VERSIONS_SUPPORTEES

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6206_plor_superpose_xy.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6206"

# Types d'anomalie relevant de ce code. Le moteur en detecte un autre, qui
# appartient au controle voisin.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "plor_superpose_xy_meme_type",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "plor_superpose_xy_meme_type": ("Plusieurs points levés de même type de levé sont superposés en X,Y."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("ids_entites",),
    couche_source=FICHIER_SOURCE,
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6206 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(
        repertoire,
        TYPES_RETENUS,
        PROFIL_ECARTS,
        FICHIER_SORTIE,
        sortie,
        version,
        chemin_gml,
    )


def main() -> None:
    """Point d'entree CLI du controle E-6206."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description="Controle E-6206 : Le fichier possède des PLOR superposés en X,Y avec un mode de levé identique (Z identique ou différent)"
    )
    parseur.add_argument("--repertoire", required=True, help=f"Repertoire contenant {FICHIER_SOURCE}")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--gml",
        default=None,
        help="Fichier GML source (defaut : le GML present dans le repertoire, s'il est unique)",
    )
    parseur.add_argument(
        "--version",
        default=JETON_AUTO,
        choices=choix_version,
        help="Version RecoStaR du jeu (defaut : detection automatique)",
    )
    arguments = parseur.parse_args()
    chemin_gml = Path(arguments.gml) if arguments.gml is not None else None
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version, chemin_gml)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
