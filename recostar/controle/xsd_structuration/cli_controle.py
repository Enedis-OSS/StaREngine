#!/usr/bin/env python3
"""
Squelette CLI mutualisé des contrôles de structuration XSD.

Les cinq contrôles partagent la même enveloppe en ligne de commande : un
fichier GML en argument, un `--output-dir` optionnel, la résolution du profil de
version, puis l'exécution d'un analyseur suivie de l'écriture d'un rapport JSON.
Ce module factorise cette enveloppe afin que les points d'entrée V1.1 (E110 à
E114) et V1.0 (E010 à E014) n'aient à déclarer que ce qui leur est propre.

Deux modes de sélection de version :
- `version_imposee=None` : l'option `--version {auto,1.0,1.1}` est offerte, la
  version est détectée ou imposée par l'utilisateur (points d'entrée E11x) ;
- `version_imposee="1.0"` : la version est figée, l'option n'est pas offerte —
  le point d'entrée porte déjà la version dans son code (points d'entrée E01x).
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from cli_version import ajouter_argument_version, resoudre_profil_cli
from codes_controle import identite_controle
from versions import resoudre_profil
from versions.profil import ProfilVersion

# Signatures des deux fonctions injectées par chaque point d'entrée.
Analyseur = Callable[[Path, ProfilVersion], Sequence[Any]]
GenerateurRapport = Callable[[Path, Any, Path | None, str], Path]


def construire_parseur(description: str, version_imposee: str | None = None) -> argparse.ArgumentParser:
    """Construit le parseur commun (fichier GML, --output-dir, --version)."""
    parseur = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parseur.add_argument(
        "fichier_gml",
        type=Path,
        help="Fichier GML RecoStaR à contrôler",
    )
    parseur.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help=("Répertoire de sortie pour le rapport JSON (par défaut : même répertoire que le fichier GML)"),
    )
    # Version figée : offrir --version induirait en erreur, le code du contrôle
    # (E01x) désignant déjà sans ambiguïté la version appliquée.
    if version_imposee is None:
        ajouter_argument_version(parseur)
    return parseur


def valider_arguments(args: argparse.Namespace) -> None:
    """Vérifie la validité des arguments CLI. Termine le programme si invalides."""
    args.fichier_gml = args.fichier_gml.resolve()
    if not args.fichier_gml.exists():
        print(f"Erreur : le fichier '{args.fichier_gml}' n'existe pas.", file=sys.stderr)
        sys.exit(1)

    if not args.fichier_gml.is_file():
        print(f"Erreur : '{args.fichier_gml}' n'est pas un fichier.", file=sys.stderr)
        sys.exit(1)

    if args.output_dir is not None:
        args.output_dir = args.output_dir.resolve()
        if not args.output_dir.is_dir():
            print(
                f"Erreur : le répertoire de sortie '{args.output_dir}' n'existe pas.",
                file=sys.stderr,
            )
            sys.exit(1)


def resoudre_profil_argument(args: argparse.Namespace, version_imposee: str | None = None) -> ProfilVersion:
    """Résout le profil de version à appliquer, selon le mode de sélection."""
    if version_imposee is not None:
        return resoudre_profil(version_imposee)
    return resoudre_profil_cli(args.fichier_gml, args.version)


def executer_controle(
    rang: int,
    description: str,
    analyser: Analyseur,
    generer_rapport: GenerateurRapport,
    libelle_anomalies: str = "erreur(s) detectee(s)",
    version_imposee: str | None = None,
) -> None:
    """Exécute l'enveloppe CLI complète d'un contrôle de structuration XSD.

    Le code affiché (E110/E010…) est dérivé du rang du contrôle et de la version
    effectivement appliquée : un même moteur s'annonce sous le code de sa version.
    """
    parseur = construire_parseur(description, version_imposee)
    args = parseur.parse_args()
    valider_arguments(args)

    profil = resoudre_profil_argument(args, version_imposee)
    code = identite_controle(profil.code, rang).code

    print(f"Controle {code} du fichier : {args.fichier_gml}")
    print(f"Version controlee        : {profil.code}")

    erreurs = analyser(args.fichier_gml, profil)
    chemin_rapport = generer_rapport(args.fichier_gml, erreurs, args.output_dir, profil.code)

    nb = len(erreurs)
    statut = "CONFORME" if nb == 0 else f"{nb} {libelle_anomalies}"
    print(f"Resultat : {statut}")
    print(f"Rapport genere : {chemin_rapport}")
