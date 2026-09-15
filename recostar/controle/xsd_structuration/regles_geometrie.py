#!/usr/bin/env python3
"""
Validité des géométries portées par les objets RPD d'un fichier GML.

Deux codes du vérificateur relèvent de ce module :

  - **E-1108** « La géométrie n'est pas valide (vertex manquant) » : un objet
    porte bien un élément `Geometrie`, mais la géométrie qu'il contient n'a pas
    assez de positions pour être définie — un `posList` vide, une `LineString`
    réduite à un point, un anneau de moins de trois sommets ;
  - **E-1109** « Géométrie supplémentaire sans géométrie » : une entité
    `RPD_GeometrieSupplementaire_Reco` dépourvue de géométrie exploitable. Le
    cas est le même, mais le vérificateur lui réserve un code, l'objet n'ayant
    précisément pas d'autre raison d'exister que sa géométrie.

Pourquoi ce contrôle ne peut pas être rendu par la validation XSD (E0112)
------------------------------------------------------------------------
`gml:posList` est typé comme une liste de doubles, et **une liste vide est une
liste valide**. Un GML dont tous les tracés sont vides passe donc la validation
de schéma sans une erreur — vérifié sur un jeu réel : lxml le déclare conforme.
Le défaut est sémantique, pas structurel : il faut compter les positions, ce
qu'un schéma XSD ne sait pas exprimer. D'où un contrôle dédié.

Seuils de validité
------------------
Le nombre minimal de positions dépend de la dimension de la géométrie :

    Point                      1 position
    LineString / LinearRing    2 positions — une courbe joint deux points
    Polygon (anneau)           3 positions — une surface a trois sommets au moins

Un anneau GML est fermé, son dernier point répétant le premier : trois positions
distinctes s'y écrivent donc quatre fois. Le seuil porte sur les positions
écrites, la fermeture ne relevant pas de ce contrôle.

Lecture des coordonnées
-----------------------
GML offre plusieurs écritures pour la même information : `gml:posList` (toutes
les positions dans un seul nœud texte), `gml:pos` (une position par nœud) et
`gml:coordinates` (forme héritée). Les trois sont lues, et leurs positions
cumulées : un tracé mixte reste correctement dénombré.

Module sans E/S en dehors de la lecture du fichier confiée à l'appelant : les
fonctions de règle travaillent sur des éléments déjà analysés, et sont donc
testables sans jeu de données.
"""

from collections.abc import Iterator

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element  # nosec B405

from recostar.controle.xsd_structuration.codes_controle import RANG_GEOMETRIE
from recostar.controle.xsd_structuration.priorites_structuration import priorite_par_regle

# Namespaces du modèle.
NS_GML: str = "http://www.opengis.net/gml/3.2"
NS_RECOSTAR: str = "http://StaR-Elec.com"

# Élément portant la géométrie d'un objet RPD.
BALISE_GEOMETRIE: str = "Geometrie"

# Type d'entité dont la géométrie est la raison d'être : son absence porte un
# code distinct (E-1109) plutôt que le code général E-1108.
TYPE_GEOMETRIE_SUPPLEMENTAIRE: str = "RPD_GeometrieSupplementaire_Reco"

# Codes de règle émis, repris tels quels par `codes_verificateur_xsd`.
CODE_GEOMETRIE_INVALIDE: str = "GEOMETRIE_INVALIDE"
CODE_GEOMSUPP_SANS_GEOMETRIE: str = "GEOMSUPP_SANS_GEOMETRIE"

# Nœuds GML porteurs de positions. `posList` en groupe toutes les positions,
# `pos` n'en porte qu'une, `coordinates` est la forme héritée de GML 2.
BALISES_POSITIONS: tuple[str, ...] = ("posList", "pos", "coordinates")

# Nombre minimal de positions par type de géométrie GML. Un type absent de la
# table est ramené au seuil d'une courbe : mieux vaut contrôler une géométrie
# inconnue que la laisser passer.
POSITIONS_MINIMALES: dict[str, int] = {
    "Point": 1,
    "LineString": 2,
    "Curve": 2,
    "LineStringSegment": 2,
    "LinearRing": 3,
    "Polygon": 3,
    "Surface": 3,
    "PolygonPatch": 3,
}

# Seuil appliqué à un type de géométrie hors de la table.
POSITIONS_MINIMALES_DEFAUT: int = 2

# Dimensions par défaut d'une position, quand `srsDimension` n'est pas déclaré.
# Le modèle RecoStaR est tridimensionnel ; deux valeurs suffisent toutefois à
# définir une position, d'où le repli sur 2 pour ne pas sous-compter.
DIMENSION_DEFAUT: int = 2


class ErreurGeometrie:
    """Géométrie d'un objet RPD dépourvue des positions qui la définiraient."""

    __slots__ = (
        "type_rpd",
        "gml_id",
        "type_erreur",
        "type_geometrie",
        "positions_trouvees",
        "positions_attendues",
        "message",
    )

    # Sévérité fixe, comme les autres contrôles de structuration : ce moteur ne
    # produit pas d'avertissement.
    severite = "ERREUR"

    @property
    def priorite(self) -> str:
        """Priorité déduite du code d'erreur du vérificateur (E-1108, E-1109)."""
        return priorite_par_regle(RANG_GEOMETRIE, self.type_erreur)

    def __init__(
        self,
        type_rpd: str,
        gml_id: str,
        type_erreur: str,
        type_geometrie: str | None,
        positions_trouvees: int,
        positions_attendues: int,
        message: str,
    ) -> None:
        self.type_rpd = type_rpd
        self.gml_id = gml_id
        self.type_erreur = type_erreur
        self.type_geometrie = type_geometrie
        self.positions_trouvees = positions_trouvees
        self.positions_attendues = positions_attendues
        self.message = message

    def vers_dict(self) -> dict:
        """Convertit l'erreur en dictionnaire pour sérialisation JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "type_erreur": self.type_erreur,
            "type_geometrie": self.type_geometrie,
            "positions_trouvees": self.positions_trouvees,
            "positions_attendues": self.positions_attendues,
            "severite": self.severite,
            "priorite": self.priorite,
            "message": self.message,
        }


def _nom_local(tag: str) -> str:
    """Extrait le nom local d'un tag qualifié « {namespace}nom »."""
    return tag.rsplit("}", 1)[-1]


def _dimension(element: Element) -> int:
    """Lit srsDimension sur l'élément ou l'un de ses ascendants portés.

    L'attribut est déclaré tantôt sur le nœud de positions, tantôt sur la
    géométrie qui l'englobe ; l'appelant fournit celui qui le porte. Une valeur
    absente ou illisible retombe sur DIMENSION_DEFAUT plutôt que de faire
    échouer le comptage.
    """
    brut = element.get("srsDimension")
    if brut is None:
        return DIMENSION_DEFAUT
    try:
        dimension = int(brut)
    except ValueError:
        return DIMENSION_DEFAUT
    return dimension if dimension > 0 else DIMENSION_DEFAUT


def compter_positions(geometrie: Element) -> int:
    """Compte les positions portées par une géométrie GML.

    Les trois écritures (`posList`, `pos`, `coordinates`) sont cumulées. Pour
    `posList`, le nombre de positions est le nombre de valeurs divisé par la
    dimension : c'est la seule balise qui en groupe plusieurs.

    `srsDimension` est déclaré à des niveaux variables — sur le nœud de
    positions, sur la géométrie, parfois sur un conteneur plus haut. Le parcours
    est donc récursif et propage la dernière valeur rencontrée en descendant :
    la lire sur le seul conteneur `Geometrie`, qui ne la porte jamais, ferait
    compter toute position tridimensionnelle comme une et demie.
    """
    return _compter_recursif(geometrie, _dimension(geometrie))


def _compter_recursif(noeud: Element, dimension_heritee: int) -> int:
    """Parcourt un sous-arbre GML en propageant la dimension déclarée."""
    dimension = _dimension(noeud) if noeud.get("srsDimension") else dimension_heritee
    nom = _nom_local(noeud.tag)

    if nom in BALISES_POSITIONS:
        valeurs = (noeud.text or "").replace(",", " ").split()
        if not valeurs:
            return 0
        # `pos` ne porte qu'une position, quel que soit le nombre de valeurs.
        return 1 if nom == "pos" else len(valeurs) // dimension

    return sum(_compter_recursif(enfant, dimension) for enfant in noeud)


def type_geometrie(geometrie: Element) -> str | None:
    """Retourne le nom local du premier élément GML contenu dans `Geometrie`.

    C'est lui qui porte le type effectif (`LineString`, `Point`, `Polygon`...) ;
    `Geometrie` n'est qu'un conteneur RecoStaR. Retourne None si le conteneur
    est vide, cas où aucun seuil ne peut être choisi.
    """
    for enfant in geometrie:
        return _nom_local(enfant.tag)
    return None


def positions_attendues(nom_geometrie: str | None) -> int:
    """Nombre minimal de positions définissant une géométrie de ce type."""
    if nom_geometrie is None:
        return POSITIONS_MINIMALES_DEFAUT
    return POSITIONS_MINIMALES.get(nom_geometrie, POSITIONS_MINIMALES_DEFAUT)


def _code_erreur(type_rpd: str) -> str:
    """Code de règle applicable au type d'objet contrôlé.

    La géométrie supplémentaire a le sien : le vérificateur distingue l'objet
    dont la géométrie est la raison d'être.
    """
    if type_rpd == TYPE_GEOMETRIE_SUPPLEMENTAIRE:
        return CODE_GEOMSUPP_SANS_GEOMETRIE
    return CODE_GEOMETRIE_INVALIDE


def _formuler_message(
    type_rpd: str,
    nom_geometrie: str | None,
    trouvees: int,
    attendues: int,
) -> str:
    """Rédige le message d'erreur, en nommant ce qui manque."""
    if nom_geometrie is None:
        return f"L'élément {BALISE_GEOMETRIE} de {type_rpd} ne contient aucune géométrie."
    if trouvees == 0:
        return (
            f"La géométrie {nom_geometrie} de {type_rpd} ne porte aucune position (au moins {attendues} attendue(s))."
        )
    return (
        f"La géométrie {nom_geometrie} de {type_rpd} ne porte que {trouvees} position(s), "
        f"au moins {attendues} attendue(s)."
    )


def valider_geometrie(type_rpd: str, gml_id: str, geometrie: Element) -> ErreurGeometrie | None:
    """Vérifie qu'une géométrie porte assez de positions pour être définie.

    Retourne None si elle est valide. Le contrôle ne se prononce ni sur la
    fermeture des anneaux, ni sur l'auto-intersection, ni sur la cohérence du
    SRS : seul le défaut que le vérificateur nomme « vertex manquant » est visé.
    """
    nom_geometrie = type_geometrie(geometrie)
    attendues = positions_attendues(nom_geometrie)
    trouvees = compter_positions(geometrie)
    if trouvees >= attendues:
        return None
    return ErreurGeometrie(
        type_rpd=type_rpd,
        gml_id=gml_id,
        type_erreur=_code_erreur(type_rpd),
        type_geometrie=nom_geometrie,
        positions_trouvees=trouvees,
        positions_attendues=attendues,
        message=_formuler_message(type_rpd, nom_geometrie, trouvees, attendues),
    )


def geometries_de(element: Element) -> Iterator[Element]:
    """Énumère les éléments `Geometrie` portés par un objet RPD.

    Le parcours est direct : seules les géométries de l'objet lui-même sont
    retenues, non celles d'objets imbriqués, qui sont contrôlées pour leur
    propre compte lors de leur passage dans le parcours principal.
    """
    for enfant in element:
        if _nom_local(enfant.tag) == BALISE_GEOMETRIE:
            yield enfant


def valider_objet(type_rpd: str, gml_id: str, element: Element) -> list[ErreurGeometrie]:
    """Valide toutes les géométries d'un objet RPD.

    Un objet dépourvu d'élément `Geometrie` ne produit aucune erreur ici : son
    caractère obligatoire relève de la séquence du schéma, que le contrôle
    d'ordre (E0110/E0010) vérifie déjà. Ce moteur ne juge que les géométries
    présentes mais vides de positions — c'est la frontière entre les deux.
    """
    erreurs: list[ErreurGeometrie] = []
    for geometrie in geometries_de(element):
        erreur = valider_geometrie(type_rpd, gml_id, geometrie)
        if erreur is not None:
            erreurs.append(erreur)
    return erreurs
