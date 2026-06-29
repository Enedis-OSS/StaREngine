#!/usr/bin/env python3
"""
Génération automatique des séquences XSD attendues par type RPD.

Reconstruit, pour un schéma XSD RecoStaR donné, la table
`{type_rpd: [SlotSequence, ...]}` consommée par le contrôle E110 — c'est-à-dire
l'équivalent dérivé automatiquement de la table `SEQUENCES_RPD` écrite à la main
dans `sequenceur_xsd` pour la V1.1.

Principe : chaque élément `RPD_X_Reco` a un type `RPD_X_RecoType` dont la chaîne
d'héritage `xs:extension` remonte jusqu'à `gml:AbstractFeatureType`. La séquence
GML attendue est la concaténation des séquences locales de chaque maillon, de la
base vers le type dérivé (ordre dans lequel `xs:extension` empile les éléments).

Intérêt : les différences structurelles entre versions (éléments renommés,
champs devenus optionnels, types ajoutés/retirés) sont toutes encodées dans le
XSD. Dériver la table directement du XSD de chaque version évite toute recopie
manuelle et garantit que la table suit le schéma officiel.

Usage (diagnostic) :
    python generateur_sequences.py <chemin.xsd>
"""

import argparse
import sys
from pathlib import Path
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as DefusedET  # type: ignore
from sequenceur_xsd import SlotSequence

# Namespace XSD et préfixes RecoStaR.
_NS_XSD = "http://www.w3.org/2001/XMLSchema"
_TAG_ELEMENT = f"{{{_NS_XSD}}}element"
_TAG_COMPLEX_TYPE = f"{{{_NS_XSD}}}complexType"
_TAG_COMPLEX_CONTENT = f"{{{_NS_XSD}}}complexContent"
_TAG_EXTENSION = f"{{{_NS_XSD}}}extension"
_TAG_SEQUENCE = f"{{{_NS_XSD}}}sequence"
_TAG_SIMPLE_TYPE = f"{{{_NS_XSD}}}simpleType"
_TAG_ENUMERATION = f"{{{_NS_XSD}}}enumeration"

# Préfixe des types métier RecoStaR (les bases gml: arrêtent la remontée).
_PREFIXE_RECOSTAR = "RecoStaR:"
# Préfixe des types RPD à extraire (les types EP_ sont hors périmètre).
_PREFIXE_RPD = "RPD_"

# Valeur XSD signalant une cardinalité non bornée, traduite en -1 dans SlotSequence.
_MAX_NON_BORNE = "unbounded"


def _nom_local(valeur: str) -> str:
    """Retourne le nom local d'une référence qualifiée 'prefixe:nom'."""
    return valeur.rsplit(":", 1)[-1]


def _convertir_occurs(valeur: str | None, defaut: int) -> int:
    """Traduit un attribut minOccurs/maxOccurs XSD en entier (unbounded → -1)."""
    if valeur is None:
        return defaut
    if valeur == _MAX_NON_BORNE:
        return -1
    return int(valeur)


def _base_recostar(complex_type: Element) -> str | None:
    """Retourne le nom local du type de base RecoStaR, ou None si base gml/absente.

    Seule l'extension la plus externe est considérée (premier nœud en ordre
    documentaire), ce qui correspond à l'héritage du type lui-même.
    """
    extension = complex_type.find(f"{_TAG_COMPLEX_CONTENT}/{_TAG_EXTENSION}")
    if extension is None:
        return None
    base = extension.get("base")
    if base is None or not base.startswith(_PREFIXE_RECOSTAR):
        return None
    return _nom_local(base)


def _sequence_locale(complex_type: Element) -> Element | None:
    """Localise le nœud xs:sequence propre au type (sous extension ou direct)."""
    sous_extension = complex_type.find(f"{_TAG_COMPLEX_CONTENT}/{_TAG_EXTENSION}/{_TAG_SEQUENCE}")
    if sous_extension is not None:
        return sous_extension
    return complex_type.find(_TAG_SEQUENCE)


def _slots_locaux(complex_type: Element) -> list[SlotSequence]:
    """Extrait les slots déclarés par le type lui-même (hors héritage)."""
    sequence = _sequence_locale(complex_type)
    if sequence is None:
        return []
    slots: list[SlotSequence] = []
    # iter() capture aussi les éléments d'un éventuel xs:choice imbriqué, en
    # conservant l'ordre documentaire — suffisant pour les types RPD à plat.
    for element in sequence.iter(_TAG_ELEMENT):
        nom = element.get("name") or element.get("ref")
        if nom is None:
            continue
        slots.append(
            SlotSequence(
                _nom_local(nom),
                _convertir_occurs(element.get("minOccurs"), 1),
                _convertir_occurs(element.get("maxOccurs"), 1),
            )
        )
    return slots


def _resoudre_sequence(
    nom_type: str,
    types_par_nom: dict[str, Element],
) -> list[SlotSequence]:
    """Reconstruit la séquence complète d'un type en remontant son héritage.

    La chaîne est parcourue du type dérivé vers la base, puis inversée pour
    empiler les slots dans l'ordre GML attendu (éléments hérités d'abord).
    """
    chaine: list[str] = []
    visites: set[str] = set()
    courant: str | None = nom_type
    while courant is not None and courant in types_par_nom and courant not in visites:
        visites.add(courant)
        chaine.append(courant)
        courant = _base_recostar(types_par_nom[courant])

    slots: list[SlotSequence] = []
    # reversed : la base (dernier maillon empilé) fournit les premiers slots.
    for nom in reversed(chaine):
        slots.extend(_slots_locaux(types_par_nom[nom]))
    return slots


def _indexer_complex_types(racine: Element) -> dict[str, Element]:
    """Construit l'index nom_type → nœud complexType pour résolution O(1)."""
    index: dict[str, Element] = {}
    for complex_type in racine.iter(_TAG_COMPLEX_TYPE):
        nom = complex_type.get("name")
        if nom is not None:
            index[nom] = complex_type
    return index


def _elements_rpd(racine: Element) -> dict[str, str]:
    """Associe chaque élément RPD de premier niveau au nom local de son type."""
    associations: dict[str, str] = {}
    for element in racine.findall(_TAG_ELEMENT):
        nom = element.get("name")
        type_ = element.get("type")
        if nom is None or type_ is None or not nom.startswith(_PREFIXE_RPD):
            continue
        associations[nom] = _nom_local(type_)
    return associations


def generer_enumeration(chemin_xsd: Path, nom_simple_type: str) -> frozenset[str]:
    """Extrait les valeurs d'un xs:simpleType par énumération depuis un XSD.

    Permet de dériver du schéma les ensembles fermés version-dépendants (par
    exemple la liste des SRS autorisés, plus courte en V1.0) au lieu de les
    recopier à la main.

    Retourne un frozenset (test d'appartenance O(1)) ; vide si le type est
    absent ou n'a pas d'énumération.
    """
    arbre = DefusedET.parse(str(chemin_xsd))
    racine = arbre.getroot()
    for simple_type in racine.iter(_TAG_SIMPLE_TYPE):
        if simple_type.get("name") != nom_simple_type:
            continue
        valeurs = {enum.get("value") for enum in simple_type.iter(_TAG_ENUMERATION) if enum.get("value") is not None}
        return frozenset(valeurs)  # type: ignore[arg-type]
    return frozenset()


def generer_sequences(chemin_xsd: Path) -> dict[str, list[SlotSequence]]:
    """Génère la table {type_rpd: [SlotSequence, ...]} depuis un XSD RecoStaR.

    Parcourt les éléments `RPD_*_Reco` de premier niveau et reconstruit pour
    chacun la séquence d'éléments attendue en résolvant la chaîne d'héritage.
    """
    arbre = DefusedET.parse(str(chemin_xsd))
    racine = arbre.getroot()
    types_par_nom = _indexer_complex_types(racine)
    associations = _elements_rpd(racine)
    return {nom_element: _resoudre_sequence(nom_type, types_par_nom) for nom_element, nom_type in associations.items()}


# ---------------------------------------------------------------------------
# Point d'entrée CLI (diagnostic : affiche la table générée pour un XSD)
# ---------------------------------------------------------------------------


def main() -> None:
    """Affiche la table de séquences dérivée d'un XSD passé en argument."""
    parseur = argparse.ArgumentParser(description="Génère et affiche la table des séquences RPD d'un XSD RecoStaR.")
    parseur.add_argument("xsd", type=Path, help="Chemin du fichier XSD à analyser")
    args = parseur.parse_args()

    if not args.xsd.is_file():
        print(f"Erreur : XSD introuvable : {args.xsd}", file=sys.stderr)
        sys.exit(1)

    sequences = generer_sequences(args.xsd)
    for type_rpd in sorted(sequences):
        slots = sequences[type_rpd]
        details = ", ".join(f"{s.nom}[{s.min_occurs}:{s.max_occurs}]" for s in slots)
        print(f"{type_rpd}: {details}")


if __name__ == "__main__":
    main()
