#!/usr/bin/env python3
"""
Point d'entrée du contrôle E0015 : validité des géométries d'un fichier GML RecoStaR **V1.0**.

E0015 est l'équivalent V1.0 du contrôle E0115 (V1.1) : même moteur, même
format de rapport, mais appliqué au profil de version 1.0 (types RPD dérivés du
XSD V1.0, sans le type télécom). Le rapport produit porte le `type_controle`
« E015_GEOMETRIE » et est écrit sous `<nom_gml>_controle_e0015.json`.

Aucune logique de contrôle n'est dupliquée ici : ce module se contente de figer
la version appliquée par le moteur de `e0115.py`. L'option `--version` n'est
donc pas offerte, le code du contrôle désignant déjà la version.

Entrée  : Fichier GML RecoStaR V1.0 à contrôler
Sortie  : Fichier JSON `<nom_gml>_controle_e0015.json`

Usage :
    python -m recostar.controle.xsd_structuration.e0015 <fichier.gml> [--output-dir <repertoire>]
"""

from recostar.controle.xsd_structuration.e0115 import main as _main
from recostar.controle.xsd_structuration.versions.v1_0 import PROFIL_V1_0

# Version figée appliquée par ce point d'entrée.
VERSION: str = PROFIL_V1_0.code


def main() -> None:
    """Exécute le contrôle E0015 en imposant la version RecoStaR 1.0."""
    _main(version_imposee=VERSION)


if __name__ == "__main__":
    main()
