#!/usr/bin/env python3
"""
Outil de contrôle E110 : vérification de l'ordre de structure des objets RPD
dans un fichier GML RecoStar, conformément au schéma XSD SchemaStarElecRecoStar.xsd v1.1.

Entrée  : Fichier GML RecoStar à contrôler
Sortie  : Fichier JSON listant les erreurs d'ordre détectées

Usage :
    python controle_e110.py <fichier.gml> [--output-dir <repertoire>]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree

import defusedxml.ElementTree as DefusedET  # type: ignore
from cli_version import ajouter_argument_version, resoudre_profil_cli
from sequenceur_xsd import ErreurOrdre, valider_sequence
from versions import VERSION_DEFAUT, resoudre_profil
from versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Namespaces GML et RecoStar
# ---------------------------------------------------------------------------

NS_GML = "http://www.opengis.net/gml/3.2"
NS_RECOSTAR = "http://StaR-Elec.com"

TAG_FEATURE_MEMBER = f"{{{NS_GML}}}featureMember"
ATTR_GML_ID = f"{{{NS_GML}}}id"

# Préfixe des types EP à ignorer
PREFIXE_EP = "EP_"


# ---------------------------------------------------------------------------
# Utilitaires namespace
# ---------------------------------------------------------------------------


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


def _extraire_gml_id(element: Element) -> str:
    """Extrait la valeur de gml:id d'un élément, ou '<sans id>' si absent."""
    return element.get(ATTR_GML_ID, "<sans id>")


# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurGML:
    """Analyse un fichier GML RecoStar et valide l'ordre des objets RPD."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Profil par défaut : V1.1, pour préserver le comportement historique
        # des appels qui n'indiquent pas de version.
        self.profil = profil if profil is not None else resoudre_profil()

    def analyser(self) -> list[ErreurOrdre]:
        """Parcourt tous les featureMember RPD et valide leur séquence d'éléments.

        Retourne la liste complète des erreurs détectées.
        """
        arbre: ElementTree = DefusedET.parse(str(self.chemin_gml))
        racine = arbre.getroot()
        erreurs: list[ErreurOrdre] = []

        for membre in racine.iter(TAG_FEATURE_MEMBER):  # type: ignore
            erreurs_membre = self._valider_membre(membre)
            erreurs.extend(erreurs_membre)

        return erreurs

    def _valider_membre(self, membre: Element) -> list[ErreurOrdre]:
        """Valide un featureMember si son contenu est un type RPD connu."""
        enfants = list(membre)
        if not enfants:
            return []

        # Un featureMember contient exactement un élément enfant
        element = enfants[0]
        type_rpd = _nom_local(element.tag)

        # Ignorer les objets EP et les types non-RPD (Metadata, ReseauUtilite, etc.)
        if type_rpd.startswith(PREFIXE_EP) or type_rpd not in self.profil.noms_rpd:
            return []

        gml_id = _extraire_gml_id(element)
        noms_enfants = self._extraire_noms_enfants(element)

        return valider_sequence(type_rpd, gml_id, noms_enfants, sequences=self.profil.sequences_rpd)

    @staticmethod
    def _extraire_noms_enfants(element: Element) -> list[str]:
        """Retourne la liste ordonnée des noms locaux des éléments enfants directs."""
        return [_nom_local(enfant.tag) for enfant in element]


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurOrdre],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    # Statut de conformité dérivé directement du nombre d'erreurs détectées :
    # absence d'erreur d'ordre = fichier conforme au schéma XSD ciblé.
    conformite = "CONFORME" if nb_erreurs == 0 else "NON_CONFORME"
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        "type_controle": "E110_ORDRE",
        "version_controlee": version,
        "conformite": conformite,
        "nb_erreurs": nb_erreurs,
        # E110 ne produit que des erreurs : la ventilation par sévérité est
        # donc soit vide, soit réduite à la clé ERREUR. Format aligné sur E114.
        "nb_par_severite": {"ERREUR": nb_erreurs} if nb_erreurs else {},
        "erreurs": [e.vers_dict() for e in erreurs],
    }


def _resoudre_chemin_sortie(chemin_gml: Path, repertoire_sortie: Path | None) -> Path:
    """Détermine le chemin du fichier JSON de sortie."""
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + "_controle_e110.json"
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurOrdre],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Écrit le rapport d'erreurs au format JSON et retourne le chemin du fichier créé."""
    chemin_sortie = _resoudre_chemin_sortie(chemin_gml, repertoire_sortie)
    rapport = _construire_rapport(chemin_gml, erreurs, version)

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    return chemin_sortie


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------


def _construire_parseur() -> argparse.ArgumentParser:
    """Construit et retourne le parseur d'arguments CLI."""
    parseur = argparse.ArgumentParser(
        description=(
            "Contrôle E110 : vérifie l'ordre de structure des objets RPD "
            "dans un fichier GML RecoStar (conformément au XSD v1.1)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parseur.add_argument(
        "fichier_gml",
        type=Path,
        help="Fichier GML RecoStar à contrôler",
    )
    parseur.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help=("Répertoire de sortie pour le rapport JSON (par défaut : même répertoire que le fichier GML)"),
    )
    ajouter_argument_version(parseur)
    return parseur


def _valider_arguments(args: argparse.Namespace) -> None:
    """Vérifie la validité des arguments CLI. Arrête le programme si invalides."""
    args.fichier_gml = args.fichier_gml.resolve()
    if not args.fichier_gml.exists():
        print(
            f"Erreur : le fichier '{args.fichier_gml}' n'existe pas.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.fichier_gml.is_file():
        print(
            f"Erreur : '{args.fichier_gml}' n'est pas un fichier.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output_dir is not None:
        args.output_dir = args.output_dir.resolve()
        if not args.output_dir.is_dir():
            print(
                f"Erreur : le répertoire de sortie '{args.output_dir}' n'existe pas.",
                file=sys.stderr,
            )
            sys.exit(1)


def main() -> None:
    """Point d'entrée principal du contrôle E110."""
    parseur = _construire_parseur()
    args = parseur.parse_args()
    _valider_arguments(args)

    profil = resoudre_profil_cli(args.fichier_gml, args.version)
    print(f"Contrôle E110 du fichier : {args.fichier_gml}")
    print(f"Version controlee        : {profil.code}")

    analyseur = AnalyseurGML(args.fichier_gml, profil)
    erreurs = analyseur.analyser()

    chemin_rapport = generer_rapport(args.fichier_gml, erreurs, args.output_dir, profil.code)

    nb = len(erreurs)
    statut = "CONFORME" if nb == 0 else f"{nb} erreur(s) detectee(s)"
    print(f"Resultat : {statut}")
    print(f"Rapport genere : {chemin_rapport}")


if __name__ == "__main__":
    main()
