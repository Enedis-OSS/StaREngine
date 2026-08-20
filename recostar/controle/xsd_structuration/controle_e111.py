#!/usr/bin/env python3
"""
Outil de contrôle des règles métier conditionnelles RecoStaR RPD.

Complémentaire du contrôle d'ordre de structure (validation structurelle XSD),
ce contrôle encode les obligations conditionnelles que le schéma XSD ne peut
exprimer :
- champs requis selon le statut administratif (« En attente d'exploitation »)
- champs requis selon le domaine de tension (BT)
- champs requis selon la nature du support (Poteau vs Façade)

Le moteur est version-agnostique : il applique le catalogue de règles du
`ProfilVersion` fourni. Le code du contrôle suit la version contrôlée —
**E111** en V1.1, **E011** en V1.0 (point d'entrée dédié `controle_e011.py`).

Référence : PDF "Structuration des informations attendue pour les
fichiers de récolement des ouvrages RécoStaR".

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les erreurs métier détectées

Usage :
    python controle_e111.py <fichier.gml> [--output-dir <repertoire>] \
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
from codes_controle import RANG_METIER, identite_controle
from priorites_structuration import statut_conformite, ventiler_par_priorite
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
        arbre: ElementTree[Element] = DefusedET.parse(str(self.chemin_gml))
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
    # Ventilation par priorité : E111 n'accorde aucune dérogation, toutes ses
    # erreurs sont bloquantes. La conformité en découle sans cas particulier.
    par_priorite = ventiler_par_priorite(erreurs)
    conformite = statut_conformite(par_priorite)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        "type_controle": identite_controle(version, RANG_METIER).type_controle,
        "version_controlee": version,
        "conformite": conformite,
        "nb_erreurs": nb_erreurs,
        # E111 ne produit que des erreurs : ventilation alignée sur E114.
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

    Le suffixe porte le code du contrôle appliqué : `_controle_e111.json` en
    V1.1, `_controle_e011.json` en V1.0.
    """
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + identite_controle(version, RANG_METIER).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurMetier],
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
    "Contrôle des règles métier conditionnelles RecoStaR RPD sur un fichier GML (E111 en V1.1, E011 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "erreur(s) metier detectee(s)"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurMetier]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurGML(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle des règles métier."""
    executer_controle(
        rang=RANG_METIER,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
