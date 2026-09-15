#!/usr/bin/env python3
"""
Point d'entrée du contrôle E0017 : champs de jointure manquants d'un fichier GML RecoStaR **V1.0**.

E0017 est l'équivalent V1.0 du contrôle E0117 (V1.1) : même moteur, même format
de rapport, mais appliqué au profil de version 1.0. Le rapport produit porte le
`type_controle` « E0017_JOINTURES_CHAMPS » et est écrit sous `<nom_gml>_controle_e0017.json`.

Les trois tables de jointure existent dans les deux versions : la règle est donc
identique, seule l'identité du contrôle change. E0017 est le complément d'E0016
(doublons), sur les mêmes objets et exclusif de lui.

Aucune logique de contrôle n'est dupliquée ici : ce module se contente de figer
la version appliquée par le moteur de `e0117.py`. L'option `--version` n'est donc
pas offerte, le code du contrôle désignant déjà la version.

Entrée  : Fichier GML RecoStaR V1.0 à contrôler
Sortie  : Fichier JSON `<nom_gml>_controle_e0017.json`

Usage :
    python -m recostar.controle.xsd_structuration.e0017 <fichier.gml> [--output-dir <repertoire>]
"""

from recostar.controle.xsd_structuration.e0117 import main as _main
from recostar.controle.xsd_structuration.versions.v1_0 import PROFIL_V1_0

# Version figée appliquée par ce point d'entrée.
VERSION: str = PROFIL_V1_0.code


def main() -> None:
    """Exécute le contrôle E0017 en imposant la version RecoStaR 1.0."""
    _main(version_imposee=VERSION)


if __name__ == "__main__":
    main()
