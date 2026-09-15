"""
Lecture et normalisation des proprietes des entites RecoStaR.

Deux traitements que les controles appliquent avant toute regle metier : suivre
une relation `_href` vers une autre entite, et ramener une valeur textuelle a une
forme comparable. Ni l'un ni l'autre ne depend d'un controle.

A ne pas confondre avec `cable.e2101._normaliser_valeur`, qui applique un
typage par champ propre a la designation normalisee des cables : meme intention
de nom, traitement different, aucune mutualisation possible.
"""

from collections.abc import Mapping
from typing import Any

# Separateur du fragment d'une reference de code-list (« ...#RMBT300 »)
SEPARATEUR_FRAGMENT: str = "#"


def reference_href(proprietes: Mapping[str, Any], champ: str) -> str | None:
    """Retourne la reference portee par un champ `_href`, ou None si absente.

    Une chaine vide vaut une absence : le GML serialise indifferemment un lien
    non renseigne par un champ manquant ou par un champ vide, et aucun des deux
    ne designe d'entite.
    """
    valeur = proprietes.get(champ)
    if valeur is None:
        return None
    reference = str(valeur).strip()
    return reference or None


def valeur_numerique(valeur: Any) -> float | None:
    """Convertit une valeur en flottant, ou None si elle n'en decrit aucun.

    Les mesures RecoStaR arrivent tantot comme des nombres — un GeoJSON issu de
    la conversion — tantot comme du texte : le GML ne connait que des chaines, et
    un GeoJSON edite a la main peut en laisser. La conversion est donc tentee,
    sans que son echec soit une anomalie : une valeur non numerique ne decrit
    aucune mesure, et sa validite releve du controle des valeurs.

    `bool` est ecarte explicitement : c'est un sous-type de `int` que Python
    convertirait sinon en 0.0 ou 1.0, deux mesures qui n'ont jamais ete ecrites.
    """
    if valeur is None or isinstance(valeur, bool):
        return None
    if isinstance(valeur, int | float):
        return float(valeur)
    try:
        return float(str(valeur).strip())
    except ValueError:
        return None


def valeur_code_liste(proprietes: Mapping[str, Any], champ: str) -> str | None:
    """Retourne le code porte par une reference de code-list, ou None si absent.

    Les champs de code-list ne portent pas la valeur metier telle quelle : le
    convertisseur ecrit une reference, restituee brute. Elle se presente donc
    soit comme le code seul (« RMBT300 »), soit comme une reference fragmentee
    (« ...#RMBT300 ») ; le code est le fragment situe apres le dernier « # ».

    Meme resolution que `e0111._extraire_valeur` cote GML.
    """
    valeur = proprietes.get(champ)
    if valeur is None:
        return None
    code = str(valeur).rsplit(SEPARATEUR_FRAGMENT, 1)[-1].strip()
    return code or None


def normaliser_valeur(valeur: Any) -> str | None:
    """Normalise une valeur textuelle pour la comparaison a un catalogue.

    Applique la semantique « collapse » de XSD (`xs:token`) : toute suite
    d'espaces, tabulations et sauts de ligne est repliee en un espace unique,
    les bords sont supprimes, la casse est ignoree. Le repliement interne n'est
    pas cosmetique : les valeurs issues du GML portent les sauts de ligne du
    document source (« DDC 240-35 \nv2006 » pour « DDC 240-35 v2006 »), qu'un
    simple strip laisserait diverger du catalogue. Il n'introduit aucun faux
    negatif : les modeles et fabricants du catalogue restent tous distincts
    apres normalisation.

    Retourne None pour une valeur absente ou vide : aucune entree du catalogue
    ne peut lui correspondre, ce que le classement traduit en anomalie.
    """
    replie = replier_espaces(valeur)
    return None if replie is None else replie.lower()


def replier_espaces(valeur: Any) -> str | None:
    """Replie les espaces d'une valeur textuelle, **casse preservee**.

    Applique la seule moitie « collapse » de `normaliser_valeur` : toute suite
    d'espaces, tabulations et sauts de ligne devient un espace unique, les bords
    sont supprimes, mais la casse est conservee.

    C'est ce qui permet de comparer deux valeurs *a la casse pres* : deux
    chaines egales apres `normaliser_valeur` mais differentes ici ne different
    que par leur capitalisation. E-7305 en fait sa regle.

    Retourne None pour une valeur absente ou vide, comme `normaliser_valeur`.
    """
    if valeur is None:
        return None
    texte = " ".join(str(valeur).split())
    return texte or None
