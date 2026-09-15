#!/usr/bin/env python3
"""
Point d'entrée du contrôle E0018 : exploitabilite du document d'un fichier GML RecoStaR **V1.0**.

E0018 est l'équivalent V1.0 du contrôle E0118 (V1.1) : même moteur, même format
de rapport, mais appliqué au profil de version 1.0. Le rapport produit porte le
`type_controle` « E0018_DOCUMENT » et est écrit sous `<nom_gml>_controle_e0018.json`.

E0018 rend E-0001 (GML illisible) et E-0004 (GML vide).
La règle est identique d'une version à l'autre ; seule l'identité du contrôle change.

Aucune logique de contrôle n'est dupliquée ici : ce module se contente de figer
la version appliquée par le moteur de `e0118.py`. L'option `--version` n'est donc
pas offerte, le code du contrôle désignant déjà la version.

Entrée  : Fichier GML RecoStaR V1.0 à contrôler
Sortie  : Fichier JSON `<nom_gml>_controle_e0018.json`

Usage :
    python -m recostar.controle.xsd_structuration.e0018 <fichier.gml> [--output-dir <repertoire>]
"""

from recostar.controle.xsd_structuration.e0118 import main as _main
from recostar.controle.xsd_structuration.versions.v1_0 import PROFIL_V1_0

# Version figée appliquée par ce point d'entrée.
VERSION: str = PROFIL_V1_0.code


def main() -> None:
    """Exécute le contrôle E0018 en imposant la version RecoStaR 1.0."""
    _main(version_imposee=VERSION)


if __name__ == "__main__":
    main()
