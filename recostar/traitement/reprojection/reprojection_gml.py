"""
Reprojection d'un fichier GML RecoStaR vers une projection de sortie.

La projection d'entree n'est pas demandee : elle est lue dans le fichier, ou le
CRS figure a deux endroits — le champ `Metadata/SRS` et l'attribut `srsName`
porte par chaque geometrie GML. Le champ des metadonnees fait foi, les
`srsName` servant de repli quand il est absent.

Seules les coordonnees planimetriques sont transformees. L'altitude est
reportee telle quelle : elle est exprimee en NGF, systeme altimetrique
independant de la projection planimetrique retenue.

Usage : python reprojection_gml.py --chemin-gml <entree> --epsg-sortie EPSG:3947
Sortie : GML reprojete + compte rendu JSON sur la sortie standard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree as ET  # nosec B405

import defusedxml.ElementTree as DefusedET  # type: ignore
from pyproj import CRS, Transformer

_racine_depot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _racine_depot not in sys.path:
    sys.path.insert(0, _racine_depot)

from recostar.controle.projection.detection_projection import normaliser_epsg  # noqa: E402

# Namespaces du format, declares pour que l'ecriture conserve les prefixes
# d'origine plutot que des ns0/ns1 generes.
NAMESPACES: dict[str, str] = {
    "RecoStaR": "http://StaR-Elec.com",
    "gml": "http://www.opengis.net/gml/3.2",
    "xlink": "http://www.w3.org/1999/xlink",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# Balises GML porteuses de positions. `posList` en groupe plusieurs, `pos` n'en
# porte qu'une, `coordinates` est la forme heritee de GML 2.
BALISES_POSITIONS: tuple[str, ...] = ("posList", "pos", "coordinates")

# Dimension retenue quand `srsDimension` n'est pas porte par la balise : le
# format impose la 3D, les geometries RecoStaR etant altimetrees.
DIMENSION_DEFAUT: int = 3

# Nombre de decimales a l'ecriture. Un CRS geographique s'exprime en degres :
# 3 decimales y vaudraient une centaine de metres, d'ou une precision distincte.
DECIMALES_PROJETE: int = 3
DECIMALES_GEOGRAPHIQUE: int = 9


class ResultatReprojection:
    """Resultat de l'execution de la reprojection."""

    __slots__ = (
        "succes",
        "erreur",
        "chemin_sortie",
        "epsg_source",
        "epsg_cible",
        "nb_geometries",
        "nb_positions",
        "avertissements",
    )

    def __init__(self) -> None:
        self.succes: bool = False
        self.erreur: str = ""
        self.chemin_sortie: str = ""
        self.epsg_source: str = ""
        self.epsg_cible: str = ""
        self.nb_geometries: int = 0
        self.nb_positions: int = 0
        self.avertissements: list[str] = []

    def vers_dict(self) -> dict:
        """Convertit le resultat en dictionnaire serialisable."""
        resultat: dict = {"succes": self.succes}
        if self.erreur:
            resultat["erreur"] = self.erreur
        if self.chemin_sortie:
            resultat["chemin_sortie"] = self.chemin_sortie
        resultat["epsg_source"] = self.epsg_source
        resultat["epsg_cible"] = self.epsg_cible
        resultat["nb_geometries"] = self.nb_geometries
        resultat["nb_positions"] = self.nb_positions
        if self.avertissements:
            resultat["avertissements"] = self.avertissements
        return resultat


def tag_qualifie(prefixe: str, element: str) -> str:
    """Construit un tag qualifie : {namespace}element."""
    return f"{{{NAMESPACES[prefixe]}}}{element}"


def _srs_names(racine: ET.Element) -> list[str]:
    """Liste les valeurs d'attribut srsName rencontrees dans l'arbre."""
    return [srs for element in racine.iter() if (srs := element.get("srsName"))]


def lire_crs_source(racine: ET.Element) -> tuple[str | None, list[str]]:
    """Determine la projection d'entree depuis le contenu du GML.

    Le champ `Metadata/SRS` fait foi ; a defaut, le premier `srsName` rencontre
    sert de repli. Retourne (epsg_normalise, avertissements) : l'EPSG vaut None
    quand aucune source exploitable n'a ete trouvee.
    """
    avertissements: list[str] = []
    srs_metadata = None
    element_srs = racine.find(f".//{tag_qualifie('RecoStaR', 'Metadata')}/{tag_qualifie('RecoStaR', 'SRS')}")
    if element_srs is not None and element_srs.text:
        srs_metadata = element_srs.text.strip()

    # Les geometries portant un CRS different du declare signalent un fichier
    # heterogene : la reprojection reste possible, mais le fait est remonte.
    normalises = {epsg for srs in _srs_names(racine) if (epsg := normaliser_epsg(srs))}
    if len(normalises) > 1:
        avertissements.append(f"Projections heterogenes dans les geometries : {sorted(normalises)}")

    if srs_metadata is not None:
        epsg = normaliser_epsg(srs_metadata)
        if epsg is None:
            avertissements.append(f"Valeur Metadata/SRS non reconnue : {srs_metadata!r}")
        else:
            if normalises and normalises != {epsg}:
                avertissements.append(
                    f"Metadata/SRS ({epsg}) differe des srsName des geometries : {sorted(normalises)}"
                )
            return epsg, avertissements

    if len(normalises) == 1:
        epsg_geometries = next(iter(normalises))
        avertissements.append(f"Metadata/SRS absent : projection deduite des geometries ({epsg_geometries})")
        return epsg_geometries, avertissements

    return None, avertissements


def _formater(valeur: float, decimales: int) -> str:
    """Formate une coordonnee sans notation scientifique ni zeros superflus."""
    texte = f"{valeur:.{decimales}f}".rstrip("0").rstrip(".")
    return texte or "0"


def reprojeter_positions(texte: str, transformer: Transformer, dimension: int, decimales: int) -> tuple[str, int]:
    """Reprojette une liste de positions GML et retourne (texte, nb_positions).

    Le texte suit la forme « x1 y1 z1 x2 y2 z2 » : les couples X/Y sont
    transformes, les composantes suivantes (altitude) reportees inchangees.
    """
    valeurs = texte.split()
    if not valeurs or dimension < 2 or len(valeurs) % dimension:
        return texte, 0

    sortie: list[str] = []
    nb_positions = 0
    for debut in range(0, len(valeurs), dimension):
        position = valeurs[debut : debut + dimension]
        abscisse, ordonnee = transformer.transform(float(position[0]), float(position[1]))
        sortie.append(_formater(abscisse, decimales))
        sortie.append(_formater(ordonnee, decimales))
        # L'altitude et les composantes au-dela sont conservees telles quelles.
        sortie.extend(position[2:])
        nb_positions += 1

    return " ".join(sortie), nb_positions


def _decimales_pour(epsg: str) -> int:
    """Nombre de decimales adapte a la nature du CRS cible."""
    return DECIMALES_GEOGRAPHIQUE if CRS(epsg).is_geographic else DECIMALES_PROJETE


def creer_transformateur(epsg_source: str, epsg_cible: str) -> Transformer:
    """Cree le transformateur pyproj entre deux projections.

    `always_xy` impose l'ordre longitude/latitude en sortie, quel que soit
    l'ordre des axes declare par le CRS cible.
    """
    return Transformer.from_crs(CRS(epsg_source), CRS(epsg_cible), always_xy=True)


def reprojeter_arbre(racine: ET.Element, transformer: Transformer, epsg_cible: str) -> tuple[int, int]:
    """Reprojette toutes les positions de l'arbre et realigne les CRS declares.

    Retourne (nb_geometries, nb_positions). Les balises `srsName` et le champ
    `Metadata/SRS` sont mis a jour pour rester coherents avec les coordonnees.
    """
    decimales = _decimales_pour(epsg_cible)
    balises_positions = {tag_qualifie("gml", nom) for nom in BALISES_POSITIONS}

    nb_geometries = 0
    nb_positions = 0
    for element in racine.iter():
        if element.get("srsName") is not None:
            element.set("srsName", epsg_cible)
            nb_geometries += 1

        if element.tag not in balises_positions or not element.text:
            continue

        attribut_dimension = element.get("srsDimension")
        dimension = int(attribut_dimension) if attribut_dimension else DIMENSION_DEFAUT
        element.text, positions = reprojeter_positions(element.text, transformer, dimension, decimales)
        nb_positions += positions

    element_srs = racine.find(f".//{tag_qualifie('RecoStaR', 'Metadata')}/{tag_qualifie('RecoStaR', 'SRS')}")
    if element_srs is not None:
        element_srs.text = epsg_cible

    return nb_geometries, nb_positions


def lire_arbre_gml(chemin_gml: str) -> ET.ElementTree[ET.Element]:
    """Charge le GML en conservant ses commentaires.

    `DefusedXMLParser` recoit une cible qui insere les commentaires : passer un
    parser standard conserverait le commentaire d'en-tete mais desactiverait
    les protections de defusedxml.
    """
    parseur = DefusedET.DefusedXMLParser(target=ET.TreeBuilder(insert_comments=True))
    return DefusedET.parse(chemin_gml, parser=parseur)


def ecrire_arbre_gml(arbre: ET.ElementTree[ET.Element], chemin_sortie: str) -> None:
    """Ecrit le GML reprojete en preservant les prefixes de namespace."""
    for prefixe, uri in NAMESPACES.items():
        ET.register_namespace(prefixe, uri)
    arbre.write(chemin_sortie, encoding="utf-8", xml_declaration=True)


def _chemin_sortie_par_defaut(chemin_gml: str, epsg_cible: str) -> str:
    """Derive un nom de sortie du fichier d'entree et de la projection visee."""
    racine, extension = os.path.splitext(chemin_gml)
    suffixe = epsg_cible.replace(":", "").lower()
    return f"{racine}_{suffixe}{extension}"


def executer_reprojection(
    chemin_gml: str,
    epsg_sortie: str,
    chemin_sortie: str | None = None,
) -> ResultatReprojection:
    """Reprojette un GML RecoStaR vers la projection demandee.

    La projection d'entree est lue dans le fichier. Sans chemin de sortie, le
    resultat est ecrit a cote de l'entree, suffixe par la projection visee.
    """
    resultat = ResultatReprojection()

    if not os.path.isfile(chemin_gml):
        resultat.erreur = f"Fichier GML introuvable : {chemin_gml}"
        return resultat

    epsg_cible = normaliser_epsg(epsg_sortie)
    if epsg_cible is None:
        resultat.erreur = f"Projection de sortie non reconnue : {epsg_sortie!r}"
        return resultat
    resultat.epsg_cible = epsg_cible

    try:
        arbre = lire_arbre_gml(chemin_gml)
    except Exception as erreur:
        resultat.erreur = f"GML illisible : {erreur}"
        return resultat

    racine = arbre.getroot()
    if racine is None:
        resultat.erreur = "GML illisible : document sans element racine"
        return resultat

    epsg_source, resultat.avertissements = lire_crs_source(racine)
    if epsg_source is None:
        resultat.erreur = "Projection d'entree introuvable : ni Metadata/SRS ni srsName exploitable"
        return resultat
    resultat.epsg_source = epsg_source

    try:
        transformer = creer_transformateur(epsg_source, epsg_cible)
    except Exception as erreur:
        resultat.erreur = f"Transformation {epsg_source} vers {epsg_cible} impossible : {erreur}"
        return resultat

    resultat.nb_geometries, resultat.nb_positions = reprojeter_arbre(racine, transformer, epsg_cible)

    sortie = chemin_sortie or _chemin_sortie_par_defaut(chemin_gml, epsg_cible)
    try:
        ecrire_arbre_gml(arbre, sortie)
    except OSError as erreur:
        resultat.erreur = f"Ecriture impossible dans {sortie} : {erreur}"
        return resultat

    resultat.chemin_sortie = sortie
    resultat.succes = True
    return resultat


def main() -> None:
    """Point d'entree du traitement de reprojection."""
    parseur = argparse.ArgumentParser(description="Reprojette un fichier GML RecoStaR vers une projection de sortie")
    parseur.add_argument(
        "--chemin-gml",
        required=True,
        help="Fichier GML RecoStaR a reprojeter",
    )
    parseur.add_argument(
        "--epsg-sortie",
        required=True,
        help="Projection de sortie, au format EPSG:NNNN ou en URN OGC",
    )
    parseur.add_argument(
        "--chemin-sortie",
        required=False,
        default=None,
        help="Fichier GML produit (defaut : entree suffixee par la projection)",
    )
    arguments = parseur.parse_args()

    resultat = executer_reprojection(
        arguments.chemin_gml,
        arguments.epsg_sortie,
        arguments.chemin_sortie,
    )

    if not resultat.succes:
        print(f"Erreur : {resultat.erreur}", file=sys.stderr)

    json.dump(resultat.vers_dict(), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
