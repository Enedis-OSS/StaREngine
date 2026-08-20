#!/usr/bin/env python3
"""
Outil de contrôle de l'ordre de structure des objets RPD dans un fichier GML
RecoStaR, conformément au schéma XSD SchemaStarElecRecoStar.xsd.

Le moteur est version-agnostique : il applique les séquences du `ProfilVersion`
qui lui est fourni. Le code du contrôle suit la version contrôlée — **E110** en
V1.1, **E010** en V1.0 (point d'entrée dédié `controle_e010.py`).

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les erreurs d'ordre détectées

Usage :
    python controle_e110.py <fichier.gml> [--output-dir <repertoire>] \
        [--version {auto,1.0,1.1}]
"""

import json
from datetime import datetime
from pathlib import Path

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import (  # nosec B405
    Element,
    ElementTree,
)

import defusedxml.ElementTree as DefusedET  # type: ignore
from cli_controle import executer_controle
from codes_controle import RANG_ORDRE, identite_controle
from priorites_structuration import statut_conformite, ventiler_par_priorite
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
        arbre: ElementTree[Element] = DefusedET.parse(str(self.chemin_gml))
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
    # Ventilation par priorité : E110 n'accorde aucune dérogation, toutes ses
    # erreurs sont bloquantes. La conformité en découle sans cas particulier.
    par_priorite = ventiler_par_priorite(erreurs)
    conformite = statut_conformite(par_priorite)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        # Le code du contrôle dépend de la version : E110 en V1.1, E010 en V1.0.
        "type_controle": identite_controle(version, RANG_ORDRE).type_controle,
        "version_controlee": version,
        "conformite": conformite,
        "nb_erreurs": nb_erreurs,
        # E110 ne produit que des erreurs : la ventilation par sévérité est
        # donc soit vide, soit réduite à la clé ERREUR. Format aligné sur E114.
        "nb_par_severite": {"ERREUR": nb_erreurs} if nb_erreurs else {},
        "nb_par_priorite": par_priorite,
        "erreurs": [e.vers_dict() for e in erreurs],
    }


def _resoudre_chemin_sortie(
    chemin_gml: Path,
    repertoire_sortie: Path | None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Détermine le chemin du fichier JSON de sortie.

    Le suffixe porte le code du contrôle appliqué : `_controle_e110.json` en
    V1.1, `_controle_e010.json` en V1.0.
    """
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + identite_controle(version, RANG_ORDRE).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurOrdre],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Écrit le rapport d'erreurs au format JSON et retourne le chemin du fichier créé."""
    chemin_sortie = _resoudre_chemin_sortie(chemin_gml, repertoire_sortie, version)
    rapport = _construire_rapport(chemin_gml, erreurs, version)

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    return chemin_sortie


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------

DESCRIPTION_CLI: str = (
    "Contrôle de l'ordre de structure des objets RPD dans un fichier GML RecoStaR (E110 en V1.1, E010 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "erreur(s) detectee(s)"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurOrdre]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurGML(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle d'ordre de structure."""
    executer_controle(
        rang=RANG_ORDRE,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
