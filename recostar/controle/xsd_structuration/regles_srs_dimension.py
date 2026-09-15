"""
Règles portant sur l'attribut `srsDimension` des géométries d'un GML RecoStaR.

Un seul contrôle y puise, au rang 9 de la famille, et rend trois codes :

    E-1201   un nœud de positions ponctuel ne déclare pas `srsDimension`
    E-1300   la valeur déclarée n'est pas celle du modèle (3)
    E-0009   le nombre de valeurs ne se divise pas par la dimension déclarée

Pourquoi ces trois règles vivent ensemble
-----------------------------------------
Elles interrogent le même attribut et se lisent en cascade sur un même nœud :
l'attribut est-il là ? sa valeur est-elle celle attendue ? les coordonnées la
respectent-elles ? Les séparer en trois parcours relirait trois fois le même
document pour les mêmes nœuds.

Elles sont **exclusives sur un même nœud**, dans cet ordre : un attribut absent
ne peut pas avoir une valeur fautive, et une valeur illisible ne permet pas de
diviser quoi que ce soit. C'est aussi l'ordre des corrections : déclarer, puis
corriger la valeur, puis reprendre les coordonnées.

Pourquoi la structuration, et pas l'altimétrie
----------------------------------------------
`srsDimension` est un artefact **du GML** : la conversion en GeoJSON le fait
disparaître, la dimension devenant celle du tableau de coordonnées. Le défaut
n'a donc aucune trace en aval, et relève du document — comme les doublons de
table de jointure (E-0012).

La dimension attendue
---------------------
Le modèle RecoStaR est tridimensionnel : X, Y, Z. Une géométrie déclarée en 2D
n'est pas en faute de forme — deux valeurs suffisent à définir une position —
mais elle annonce une donnée sans altitude, ce que le vérificateur signale en
priorité `basse` sous E-1300. La cohérence entre la dimension déclarée et le
nombre de valeurs, elle, est `bloquante` : une posList qui ne se divise pas
produit des positions fausses, pas seulement incomplètes.

Lecture de l'attribut
---------------------
`srsDimension` se déclare à des niveaux variables — sur le nœud de positions,
sur la géométrie qui l'englobe, parfois plus haut. Le parcours propage donc la
dernière valeur rencontrée en descendant, exactement comme `compter_positions`
de `regles_geometrie`, dont ce module reprend les balises et la convention de
repli. Un nœud qui **hérite** sa dimension n'est pas en défaut de déclaration :
E-1201 ne vise que les positions dont aucun ascendant ne la porte.
"""

from dataclasses import dataclass

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element  # nosec B405

from recostar.controle.xsd_structuration.codes_controle import RANG_SRS_DIMENSION
from recostar.controle.xsd_structuration.priorites_structuration import priorite_par_regle
from recostar.controle.xsd_structuration.regles_geometrie import BALISES_POSITIONS

# Codes de regle, un par code d'erreur rendu.
CODE_ABSENTE: str = "SRS_DIMENSION_ABSENTE"
CODE_INCORRECTE: str = "SRS_DIMENSION_INCORRECTE"
CODE_INCOHERENTE: str = "SRS_DIMENSION_INCOHERENTE"

# Attribut porte par les geometries GML.
ATTR_SRS_DIMENSION: str = "srsDimension"

# Dimension du modele RecoStaR : X, Y, Z.
DIMENSION_ATTENDUE: int = 3

# Balise ne portant qu'une seule position, quel que soit son nombre de valeurs.
BALISE_POSITION_UNIQUE: str = "pos"


def _nom_local(tag: str) -> str:
    """Extrait le nom local d'un tag qualifié « {namespace}nom »."""
    return tag.rsplit("}", 1)[-1]


@dataclass(frozen=True, slots=True)
class NoeudPositions:
    """Nœud de positions, avec la dimension qui s'y applique et son origine.

    - `dimension` : valeur effective, héritée le cas échéant ; None si aucun
      ascendant ne la déclare, ou si la valeur n'est pas un entier ;
    - `declaree_ici` : l'attribut est porté par ce nœud même, et non hérité.
      C'est ce qui distingue une déclaration manquante d'une déclaration faite
      plus haut, parfaitement licite ;
    - `brut` : la valeur textuelle, conservée pour le message d'anomalie.
    """

    nom: str
    nombre_valeurs: int
    dimension: int | None
    declaree_ici: bool
    brut: str | None


def _entier(brut: str | None) -> int | None:
    """Convertit la valeur de l'attribut en entier positif, ou None."""
    if brut is None:
        return None
    try:
        valeur = int(brut)
    except ValueError:
        return None
    return valeur if valeur > 0 else None


def parcourir_positions(geometrie: Element) -> list[NoeudPositions]:
    """Relève les nœuds de positions d'une géométrie et la dimension applicable.

    La dimension déclarée sur un ascendant est propagée en descendant : c'est la
    convention de `compter_positions`, et la seule lecture correcte du GML
    RecoStaR, où l'attribut est rarement porté par le nœud de positions lui-même.
    """
    releves: list[NoeudPositions] = []
    _parcourir(geometrie, _entier(geometrie.get(ATTR_SRS_DIMENSION)), geometrie.get(ATTR_SRS_DIMENSION), releves)
    return releves


def _parcourir(
    noeud: Element,
    dimension_heritee: int | None,
    brut_herite: str | None,
    releves: list[NoeudPositions],
) -> None:
    """Descend un sous-arbre GML en propageant la dimension déclarée."""
    brut_local = noeud.get(ATTR_SRS_DIMENSION)
    declaree_ici = brut_local is not None
    dimension = _entier(brut_local) if declaree_ici else dimension_heritee
    brut = brut_local if declaree_ici else brut_herite

    nom = _nom_local(noeud.tag)
    if nom in BALISES_POSITIONS:
        valeurs = (noeud.text or "").replace(",", " ").split()
        releves.append(NoeudPositions(nom, len(valeurs), dimension, declaree_ici or brut_herite is not None, brut))
        return

    for enfant in noeud:
        _parcourir(enfant, dimension, brut, releves)


class ErreurSrsDimension:
    """Attribut `srsDimension` absent, hors modèle, ou démenti par les coordonnées."""

    __slots__ = ("type_rpd", "gml_id", "type_erreur", "balise", "dimension", "nombre_valeurs", "message")

    # Severite fixe, comme les autres controles de structuration.
    severite = "ERREUR"

    @property
    def priorite(self) -> str:
        """Priorité déduite du code d'erreur du vérificateur."""
        return priorite_par_regle(RANG_SRS_DIMENSION, self.type_erreur)

    def __init__(
        self,
        type_rpd: str,
        gml_id: str,
        type_erreur: str,
        noeud: NoeudPositions,
        message: str,
    ) -> None:
        self.type_rpd = type_rpd
        self.gml_id = gml_id
        self.type_erreur = type_erreur
        self.balise = noeud.nom
        self.dimension = noeud.brut
        self.nombre_valeurs = noeud.nombre_valeurs
        self.message = message

    def vers_dict(self) -> dict:
        """Convertit l'erreur en dictionnaire pour sérialisation JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "severite": self.severite,
            "priorite": self.priorite,
            "type_erreur": self.type_erreur,
            "balise": self.balise,
            "srs_dimension": self.dimension,
            "nombre_valeurs": self.nombre_valeurs,
            "message": self.message,
        }


def classifier(noeud: NoeudPositions) -> tuple[str, str] | None:
    """Retourne (code de règle, message) du nœud fautif, ou None s'il est conforme.

    Cascade, et non trois tests indépendants : un attribut absent n'a pas de
    valeur à juger, et une valeur illisible ne divise rien. Chaque nœud porte
    donc au plus une anomalie — celle qu'il faut corriger d'abord.
    """
    if not noeud.declaree_ici:
        return CODE_ABSENTE, f"La balise « {noeud.nom} » ne déclare aucun srsDimension, ni elle ni ses ascendants"
    if noeud.dimension is None:
        return CODE_INCORRECTE, f"La valeur srsDimension « {noeud.brut} » n'est pas un entier positif"
    if noeud.dimension != DIMENSION_ATTENDUE:
        return (
            CODE_INCORRECTE,
            f"srsDimension vaut {noeud.dimension} alors que le modèle RecoStaR est en {DIMENSION_ATTENDUE}D",
        )
    # `pos` ne porte qu'une position : son compte de valeurs doit faire
    # exactement la dimension, la division ne s'y applique pas.
    attendu_exact = noeud.nom == BALISE_POSITION_UNIQUE
    if noeud.nombre_valeurs == 0:
        # Une balise vide releve du controle de geometrie (E-1108), non d'ici.
        return None
    if attendu_exact and noeud.nombre_valeurs != noeud.dimension:
        return (
            CODE_INCOHERENTE,
            f"La balise « pos » porte {noeud.nombre_valeurs} valeurs pour un srsDimension de {noeud.dimension}",
        )
    if not attendu_exact and noeud.nombre_valeurs % noeud.dimension != 0:
        return (
            CODE_INCOHERENTE,
            f"Les {noeud.nombre_valeurs} valeurs de « {noeud.nom} » ne se divisent pas "
            f"par le srsDimension déclaré ({noeud.dimension})",
        )
    return None


def detecter(type_rpd: str, gml_id: str, geometrie: Element) -> list[ErreurSrsDimension]:
    """Relève les anomalies de `srsDimension` d'une géométrie d'objet RPD."""
    erreurs: list[ErreurSrsDimension] = []
    for noeud in parcourir_positions(geometrie):
        constat = classifier(noeud)
        if constat is not None:
            code, message = constat
            erreurs.append(ErreurSrsDimension(type_rpd, gml_id, code, noeud, message))
    return erreurs
