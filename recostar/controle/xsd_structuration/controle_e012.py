#!/usr/bin/env python3
"""
Point d'entrée du contrôle E012 : validation XSD native d'un fichier GML RecoStaR **V1.0**.

E012 est l'équivalent V1.0 du contrôle E112 (V1.1) : même moteur, même
format de rapport, mais appliqué au profil de version 1.0 (séquences dérivées du
XSD V1.0, validation adossée au XSD officiel V1.0 de
`conversion/conversion_V1/xsd/`). Le rapport produit
porte le `type_controle` « E012_XSD_NATIF » et est écrit sous
`<nom_gml>_controle_e012.json`.

Aucune logique de contrôle n'est dupliquée ici : ce module se contente de figer
la version appliquée par le moteur de `controle_e112.py`. L'option
`--version` n'est donc pas offerte, le code du contrôle désignant déjà la
version.

Entrée  : Fichier GML RecoStaR V1.0 à contrôler
Sortie  : Fichier JSON `<nom_gml>_controle_e012.json`

Usage :
    python controle_e012.py <fichier.gml> [--output-dir <repertoire>]
"""

from controle_e112 import main as _main
from versions.v1_0 import PROFIL_V1_0

# Version figée appliquée par ce point d'entrée.
VERSION: str = PROFIL_V1_0.code


def main() -> None:
    """Exécute le contrôle E012 en imposant la version RecoStaR 1.0."""
    _main(version_imposee=VERSION)


if __name__ == "__main__":
    main()
