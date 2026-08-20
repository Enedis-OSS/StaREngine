#!/usr/bin/env python3
"""
Outil de contrôle des valeurs portées par les éléments d'un fichier GML
RecoStaR, contre les énumérations et CodeLists du PDF §10.

Complémentaire des autres contrôles de structuration :
- ordre des éléments : présence des champs requis
- règles métier : champs conditionnellement requis (statut, BT…)
- XSD natif : énumérations strictes via xs:enumeration du XSD officiel
- en-tête : namespaces, schemaLocation, Metadata, ReseauUtilite, SRS

Ce contrôle vise spécifiquement les valeurs littérales/référencées par
xlink:href sur les enfants des objets RPD, et complète la validation XSD native
en couvrant aussi les CodeLists ouvertes (que le XSD traite comme des
CharacterString) et les contraintes RPD plus strictes que le XSD
(Theme=ELECTRD, NumeroPRM 14 chiffres).

Le moteur est version-agnostique : il applique le catalogue de valeurs du
`ProfilVersion` fourni. Le code du contrôle suit la version contrôlée —
**E114** en V1.1, **E014** en V1.0 (point d'entrée dédié `controle_e014.py`).

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les erreurs détectées (sévérité ERREUR unique)

Usage :
    python controle_e114.py <fichier.gml> [--output-dir <repertoire>] \
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
from codes_controle import RANG_VALEURS, identite_controle
from priorites_structuration import statut_conformite, ventiler_par_priorite
from regles_valeurs import (
    SEVERITE_ERREUR,
    ErreurValeur,
    evaluer_valeur,
)
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

# Préfixe des types Éclairage Public (hors périmètre RPD).
PREFIXE_EP = "EP_"


# ---------------------------------------------------------------------------
# Utilitaires XML — repris à l'identique de controle_e111 pour cohérence
# inter-contrôles. La duplication est volontaire (3 fonctions, 6 lignes)
# afin de garder E114 importable de manière autonome sans coupler les
# contrôles entre eux.
# ---------------------------------------------------------------------------


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


def _extraire_gml_id(element: Element) -> str:
    """Extrait la valeur de gml:id d'un élément, ou '<sans id>' si absent."""
    return element.get(ATTR_GML_ID, "<sans id>")


def _extraire_valeur(element: Element) -> str | None:
    """Extrait la valeur scalaire portée par un élément RPD.

    Ordre de résolution identique à controle_e111._extraire_valeur :
    1. Contenu textuel non vide
    2. Fragment final de l'attribut xlink:href
    3. None
    """
    texte = element.text
    if texte is not None:
        texte_strip = texte.strip()
        if texte_strip:
            return texte_strip

    href = element.get(ATTR_XLINK_HREF)
    if href:
        fragment = href.rsplit("#", 1)[-1]
        if fragment:
            return fragment
    return None


# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurValeurs:
    """Analyse un fichier GML RecoStaR et évalue les valeurs des champs."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Profil par défaut : V1.1 (comportement historique préservé).
        self.profil = profil if profil is not None else resoudre_profil()

    def analyser(self) -> list[ErreurValeur]:
        """Parcourt les featureMember RPD et évalue chaque champ porteur.

        Retourne la liste exhaustive des erreurs détectées (vide si le fichier
        respecte intégralement les domaines de valeurs).
        """
        arbre: ElementTree[Element] = DefusedET.parse(str(self.chemin_gml))
        racine = arbre.getroot()
        erreurs: list[ErreurValeur] = []

        for membre in racine.iter(TAG_FEATURE_MEMBER):  # type: ignore
            erreurs.extend(self._evaluer_membre(membre))

        return erreurs

    def _evaluer_membre(self, membre: Element) -> list[ErreurValeur]:
        """Évalue les valeurs d'un featureMember RPD si concerné."""
        enfants = list(membre)
        if not enfants:
            return []

        # Un featureMember porte exactement un objet RPD/Metadata/ReseauUtilite.
        objet = enfants[0]
        type_rpd = _nom_local(objet.tag)

        # Filtres rapides : EP et types sans aucune règle sont écartés
        # avant la boucle sur les enfants (économise l'extraction des valeurs).
        if type_rpd.startswith(PREFIXE_EP):
            return []
        if type_rpd not in self.profil.types_avec_regles:
            return []

        gml_id = _extraire_gml_id(objet)
        return self._evaluer_enfants(objet, type_rpd, gml_id)

    def _evaluer_enfants(
        self,
        objet: Element,
        type_rpd: str,
        gml_id: str,
    ) -> list[ErreurValeur]:
        """Itère sur les enfants directs et délègue à evaluer_valeur."""
        # Référence locale à l'index du profil : évite un accès attribut par
        # itération dans cette boucle potentiellement chaude.
        index = self.profil.index_regles_valeurs
        erreurs: list[ErreurValeur] = []
        for enfant in objet:
            champ = _nom_local(enfant.tag)
            valeur = _extraire_valeur(enfant)
            erreur = evaluer_valeur(type_rpd, champ, valeur, gml_id, index=index)
            if erreur is not None:
                erreurs.append(erreur)
        return erreurs


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _compter_par_severite(erreurs: list[ErreurValeur]) -> dict[str, int]:
    """Compte le nombre d'entrées par sévérité (ERREUR uniquement en E114)."""
    compteur: dict[str, int] = {}
    for erreur in erreurs:
        compteur[erreur.severite] = compteur.get(erreur.severite, 0) + 1
    return compteur


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurValeur],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport E114 à sérialiser en JSON."""
    par_severite = _compter_par_severite(erreurs)
    # nb_erreurs = nombre d'entrées de sévérité ERREUR (unique sévérité E114).
    # Clé harmonisée avec E110-E113.
    nb_erreurs = par_severite.get(SEVERITE_ERREUR, 0)
    # E114 est mono-sévérité mais multi-priorités : la règle E_THEME_RPD est
    # mineure, toutes les autres restent bloquantes. Seules ces dernières
    # invalident la conformité.
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        "type_controle": identite_controle(version, RANG_VALEURS).type_controle,
        "version_controlee": version,
        "conformite": statut_conformite(par_priorite),
        "nb_erreurs": nb_erreurs,
        "nb_par_severite": par_severite,
        "nb_par_priorite": par_priorite,
        "erreurs": [e.vers_dict() for e in erreurs],
    }


def _resoudre_chemin_sortie(
    chemin_gml: Path,
    repertoire_sortie: Path | None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Détermine le chemin du fichier JSON de sortie.

    Le suffixe porte le code du contrôle appliqué : `_controle_e114.json` en
    V1.1, `_controle_e014.json` en V1.0.
    """
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + identite_controle(version, RANG_VALEURS).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurValeur],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Écrit le rapport au format JSON et retourne le chemin du fichier créé."""
    chemin_sortie = _resoudre_chemin_sortie(chemin_gml, repertoire_sortie, version)
    rapport = _construire_rapport(chemin_gml, erreurs, version)

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    return chemin_sortie


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------

DESCRIPTION_CLI: str = (
    "Contrôle des valeurs des champs des objets RPD d'un fichier GML "
    "RecoStaR : énumérations, CodeLists et formats (E114 en V1.1, E014 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "anomalie(s) de valeur detectee(s)"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurValeur]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurValeurs(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle des valeurs."""
    executer_controle(
        rang=RANG_VALEURS,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
