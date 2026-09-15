"""
Primitives de lecture d'un GML RecoStaR.

Plusieurs controles lisent le GML d'entree plutot que les GeoJSON issus de la
conversion, celle-ci ne conservant pas tout ce dont ils ont besoin :

    E-3300, E-6206   le champ `TypeLeve`, retire par la normalisation V1.0 -> V1.1
    E-6104, E-6207   le couple `Leve` / `TypeLeve`, idem
    E-7100, E-7101   les relations `Ouvrage_Materiel`, dont le convertisseur ne
                     retient qu'une par ouvrage

Tous font les memes gestes : ouvrir le document, parcourir ses `featureMember`,
lire un enfant par son nom local, suivre une reference `xlink:href`. Ces gestes
sont tenus ici plutot que dans l'un des controles, qu'il faudrait sinon importer
depuis les autres.

Le namespace n'est jamais construit pour les elements RecoStaR : ils le portent
tous, et comparer les **noms locaux** evite d'en dependre — meme parti qu'E0110.
Seuls les attributs GML et XLink, dont le prefixe est normatif, sont qualifies.

`defusedxml` est employe pour l'analyse, conformement aux contraintes du projet.
"""

from collections.abc import Iterator
from pathlib import Path

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element  # nosec B405

import defusedxml.ElementTree as DefusedET  # type: ignore

from recostar.controle.fonctions_communes.proprietes import valeur_numerique

# Namespaces du GML RecoStaR, memes valeurs qu'E0110 et E0115.
NS_GML: str = "http://www.opengis.net/gml/3.2"
NS_XLINK: str = "http://www.w3.org/1999/xlink"

TAG_FEATURE_MEMBER: str = f"{{{NS_GML}}}featureMember"
ATTR_GML_ID: str = f"{{{NS_GML}}}id"
ATTR_XLINK_HREF: str = f"{{{NS_XLINK}}}href"

# Balises GML portant des coordonnees. `coordinates` est ecarte : le GML
# RecoStaR ne l'emploie pas.
BALISES_POSITIONS: frozenset[str] = frozenset({"posList", "pos"})

# Nom de l'element englobant la geometrie d'un objet RPD.
BALISE_GEOMETRIE: str = "Geometrie"


def nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifie '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


def charger_racine(chemin_gml: Path) -> Element:
    """Ouvre un GML et retourne son element racine."""
    return DefusedET.parse(str(chemin_gml)).getroot()


def parcourir_objets(racine: Element, types_retenus: frozenset[str] | None = None) -> Iterator[Element]:
    """Parcourt les objets portes par les `featureMember` du document.

    `types_retenus` filtre sur le nom local de l'objet ; a None, tous sont
    rendus. Un `featureMember` contient un objet, parfois plusieurs : la boucle
    interne les rend tous plutot que de supposer une cardinalite.
    """
    for membre in racine.iter(TAG_FEATURE_MEMBER):
        for element in membre:
            if types_retenus is None or nom_local(element.tag) in types_retenus:
                yield element


def texte_enfant(element: Element, nom: str) -> str | None:
    """Retourne le texte du premier enfant direct portant ce nom local.

    Une valeur vide vaut une absence : le GML serialise indifferemment un champ
    non renseigne par un element manquant ou par un element vide.
    """
    for enfant in element:
        if nom_local(enfant.tag) == nom:
            return (enfant.text or "").strip() or None
    return None


def href_enfant(element: Element, nom: str) -> str | None:
    """Retourne la reference `xlink:href` du premier enfant portant ce nom.

    C'est la forme des relations RecoStaR : l'element nomme la nature du lien,
    son attribut `xlink:href` en designe la cible.
    """
    for enfant in element:
        if nom_local(enfant.tag) == nom:
            reference = enfant.get(ATTR_XLINK_HREF)
            return reference.strip() if reference else None
    return None


def positions_geometrie(element: Element) -> list[float]:
    """Retourne les coordonnees de la geometrie d'un objet RPD.

    Les deux ecritures d'une position — `pos` et `posList` — sont admises, la
    premiere rencontree faisant foi. Une valeur non numerique interrompt la
    lecture plutot que de decaler les rangs : c'est un defaut de structure,
    qu'E0112 releve deja.
    """
    geometrie = next((enfant for enfant in element if nom_local(enfant.tag) == BALISE_GEOMETRIE), None)
    if geometrie is None:
        return []
    for noeud in geometrie.iter():
        if nom_local(noeud.tag) not in BALISES_POSITIONS:
            continue
        coordonnees: list[float] = []
        for valeur in (noeud.text or "").replace(",", " ").split():
            nombre = valeur_numerique(valeur)
            if nombre is None:
                return coordonnees
            coordonnees.append(nombre)
        if coordonnees:
            return coordonnees
    return []
