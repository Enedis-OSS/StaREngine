#!/usr/bin/env python3
"""
Outil de contrôle E111 : vérification des règles métier RecoStaR RPD V1.1.

Complémentaire de E110 (validation structurelle XSD), E111 encode les
obligations conditionnelles que le schéma XSD ne peut exprimer :
- champs requis selon le statut administratif (« En attente d'exploitation »)
- champs requis selon le domaine de tension (BT)
- champs requis selon la nature du support (Poteau vs Façade)

Référence : PDF "Structuration des informations attendue pour les
fichiers de récolement des ouvrages RécoStaR" V1.1.

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les erreurs métier détectées

Usage :
    python controle_e111.py <fichier.gml> [--output-dir <repertoire>]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree

import defusedxml.ElementTree as DefusedET  # type: ignore
from cli_version import ajouter_argument_version, resoudre_profil_cli
from regles_metier import ErreurMetier, evaluer_regles
from versions import VERSION_DEFAUT, resoudre_profil
from versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Namespaces GML / RecoStaR / XLink
# ---------------------------------------------------------------------------

NS_GML = "http://www.opengis.net/gml/3.2"
NS_RECOSTAR = "http://StaR-Elec.com"
NS_XLINK = "http://www.w3.org/1999/xlink"

TAG_FEATURE_MEMBER = f"{{{NS_GML}}}featureMember"
ATTR_GML_ID = f"{{{NS_GML}}}id"
ATTR_XLINK_HREF = f"{{{NS_XLINK}}}href"

# Préfixe des types Eclairage Public (hors périmètre RPD).
PREFIXE_EP = "EP_"


# ---------------------------------------------------------------------------
# Utilitaires de manipulation XML
# ---------------------------------------------------------------------------


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


def _extraire_gml_id(element: Element) -> str:
    """Extrait la valeur de gml:id d'un élément, ou '<sans id>' si absent."""
    return element.get(ATTR_GML_ID, "<sans id>")


def _extraire_valeur(element: Element) -> str | None:
    """Extrait la valeur scalaire portée par un élément RPD.

    Les énumérations RecoStaR sont représentées de deux façons dans le GML :
    - valeur littérale dans le texte de l'élément (ex: '<Statut>UnderCommissionning</Statut>')
    - référence xlink:href vers une code-list (ex: '<TypeCoffret xlink:href="...#RMBT300"/>')

    Ordre de résolution :
      1. Contenu textuel non vide
      2. Fragment final de l'attribut xlink:href
      3. None (élément présent mais sans valeur exploitable)
    """
    texte = element.text
    if texte is not None:
        texte_strip = texte.strip()
        if texte_strip:
            return texte_strip

    href = element.get(ATTR_XLINK_HREF)
    if href:
        # Fragment situé après '#' (ex: "...#UnderCommissionning" -> "UnderCommissionning").
        fragment = href.rsplit("#", 1)[-1]
        if fragment:
            return fragment
    return None


# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurGML:
    """Analyse un fichier GML RecoStaR et applique les règles métier."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Profil par défaut : V1.1 (comportement historique préservé).
        self.profil = profil if profil is not None else resoudre_profil()

    def analyser(self) -> list[ErreurMetier]:
        """Parcourt tous les featureMember RPD et évalue les règles métier.

        Retourne la liste complète des erreurs détectées (vide si conforme).
        """
        arbre: ElementTree = DefusedET.parse(str(self.chemin_gml))
        racine = arbre.getroot()
        erreurs: list[ErreurMetier] = []

        for membre in racine.iter(TAG_FEATURE_MEMBER):  # type: ignore
            erreurs.extend(self._evaluer_membre(membre))

        return erreurs

    def _evaluer_membre(self, membre: Element) -> list[ErreurMetier]:
        """Évalue les règles métier sur un featureMember RPD si concerné."""
        enfants = list(membre)
        if not enfants:
            return []

        # Un featureMember contient exactement un élément enfant (l'objet RPD).
        element = enfants[0]
        type_rpd = _nom_local(element.tag)

        # Filtrage rapide : EP et types RPD sans règle métier sont écartés
        # avant l'extraction coûteuse des valeurs.
        if type_rpd.startswith(PREFIXE_EP) or type_rpd not in self.profil.types_rpd_avec_regles:
            return []

        gml_id = _extraire_gml_id(element)
        valeurs = self._extraire_valeurs(element)
        return evaluer_regles(type_rpd, gml_id, valeurs, regles_par_type=self.profil.regles_par_type)

    @staticmethod
    def _extraire_valeurs(element: Element) -> dict[str, str | None]:
        """Construit le dictionnaire {nom_champ : valeur} des enfants directs.

        Quand plusieurs enfants portent le même nom local (cas des éléments
        répétables comme 'reseau' ou 'Ligne3D'), seule la dernière valeur
        rencontrée est conservée — les règles métier actuelles ne dépendent
        pas de répétitions, donc cette simplification est sans incidence.
        """
        return {_nom_local(enfant.tag): _extraire_valeur(enfant) for enfant in element}


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurMetier],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport métier à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    # Conformité dérivée directement du nombre d'erreurs détectées.
    conformite = "CONFORME" if nb_erreurs == 0 else "NON_CONFORME"
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        "type_controle": "E111_METIER",
        "version_controlee": version,
        "conformite": conformite,
        "nb_erreurs": nb_erreurs,
        # E111 ne produit que des erreurs : ventilation alignée sur E114.
        "nb_par_severite": {"ERREUR": nb_erreurs} if nb_erreurs else {},
        "erreurs": [e.vers_dict() for e in erreurs],
    }


def _resoudre_chemin_sortie(chemin_gml: Path, repertoire_sortie: Path | None) -> Path:
    """Détermine le chemin du fichier JSON de sortie."""
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + "_controle_e111.json"
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurMetier],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Écrit le rapport au format JSON et retourne le chemin du fichier créé."""
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
        description=("Contrôle E111 : vérifie les règles métier conditionnelles RecoStaR RPD V1.1 sur un fichier GML."),
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
    ajouter_argument_version(parseur)
    return parseur


def _valider_arguments(args: argparse.Namespace) -> None:
    """Vérifie la validité des arguments CLI. Termine le programme si invalides."""
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
    """Point d'entrée principal du contrôle E111."""
    parseur = _construire_parseur()
    args = parseur.parse_args()
    _valider_arguments(args)

    profil = resoudre_profil_cli(args.fichier_gml, args.version)
    print(f"Controle E111 du fichier : {args.fichier_gml}")
    print(f"Version controlee        : {profil.code}")

    analyseur = AnalyseurGML(args.fichier_gml, profil)
    erreurs = analyseur.analyser()

    chemin_rapport = generer_rapport(args.fichier_gml, erreurs, args.output_dir, profil.code)

    nb = len(erreurs)
    statut = "CONFORME" if nb == 0 else f"{nb} erreur(s) metier detectee(s)"
    print(f"Resultat : {statut}")
    print(f"Rapport genere : {chemin_rapport}")


if __name__ == "__main__":
    main()
