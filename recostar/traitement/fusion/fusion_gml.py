"""
Fusion de deux fichiers GML RecoStaR en un seul.

Les deux fichiers sont lus, leur projection est deduite de leur contenu, puis
confrontee : identiques, la fusion est directe ; differentes, le fichier qui
s'ecarte de la projection cible est reprojete avant d'etre fusionne. La cible
est celle passee en ligne de commande, ou a defaut celle du premier fichier.

Deux ecueils traites a la fusion :

- **Unicite des gml:id.** Le format l'impose sur l'ensemble du fichier, et les
  exports d'un meme outil partagent des identifiants derives de compteurs
  (`RPD_Support_Reco_1.geom0`, `Reseau`). Les identifiants du second fichier
  entrant en collision sont renommes, et les `xlink:href` qui les designent
  suivent le renommage.
- **Unicite du Metadata.** Le modele n'en admet qu'un par fichier : celui du
  second est ecarte. Les `ReseauUtilite`, eux, sont tous conserves, le modele
  en admettant plusieurs (tranches de travaux).

Usage : python fusion_gml.py --chemin-gml-1 <a> --chemin-gml-2 <b> [--epsg-cible EPSG:NNNN]
Sortie : GML fusionne + compte rendu JSON sur la sortie standard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree as ET  # nosec B405

_racine_depot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _racine_depot not in sys.path:
    sys.path.insert(0, _racine_depot)

from recostar.controle.projection.detection_projection import normaliser_epsg  # noqa: E402
from recostar.traitement.reprojection.reprojection_gml import (  # noqa: E402
    NAMESPACES,
    creer_transformateur,
    ecrire_arbre_gml,
    lire_arbre_gml,
    lire_crs_source,
    reprojeter_arbre,
    tag_qualifie,
)

# Attribut porteur de l'identifiant unique, et attribut qui le reference.
ATTRIBUT_ID: str = f"{{{NAMESPACES['gml']}}}id"
ATTRIBUT_HREF: str = f"{{{NAMESPACES['xlink']}}}href"
ATTRIBUT_SCHEMA: str = f"{{{NAMESPACES['xsi']}}}schemaLocation"

# Suffixe du fichier produit quand aucun chemin de sortie n'est demande.
SUFFIXE_SORTIE: str = "_fusion"


class ResultatFusion:
    """Resultat de l'execution de la fusion."""

    __slots__ = (
        "succes",
        "erreur",
        "chemin_sortie",
        "epsg_cible",
        "epsg_sources",
        "nb_reprojetes",
        "nb_entites_ajoutees",
        "nb_ids_remappes",
        "avertissements",
    )

    def __init__(self) -> None:
        self.succes: bool = False
        self.erreur: str = ""
        self.chemin_sortie: str = ""
        self.epsg_cible: str = ""
        self.epsg_sources: list[str] = []
        self.nb_reprojetes: int = 0
        self.nb_entites_ajoutees: int = 0
        self.nb_ids_remappes: int = 0
        self.avertissements: list[str] = []

    def vers_dict(self) -> dict:
        """Convertit le resultat en dictionnaire serialisable."""
        resultat: dict = {"succes": self.succes}
        if self.erreur:
            resultat["erreur"] = self.erreur
        if self.chemin_sortie:
            resultat["chemin_sortie"] = self.chemin_sortie
        resultat["epsg_cible"] = self.epsg_cible
        resultat["epsg_sources"] = self.epsg_sources
        resultat["nb_reprojetes"] = self.nb_reprojetes
        resultat["nb_entites_ajoutees"] = self.nb_entites_ajoutees
        resultat["nb_ids_remappes"] = self.nb_ids_remappes
        if self.avertissements:
            resultat["avertissements"] = self.avertissements
        return resultat


def collecter_identifiants(racine: ET.Element) -> set[str]:
    """Recense les gml:id portes par l'arbre."""
    return {identifiant for element in racine.iter() if (identifiant := element.get(ATTRIBUT_ID))}


def _nouvel_identifiant() -> str:
    """Genere un identifiant respectant le format xsd:ID (NCName)."""
    return f"id{uuid.uuid4()}"


def remapper_collisions(racine: ET.Element, identifiants_pris: set[str]) -> dict[str, str]:
    """Renomme les gml:id de l'arbre deja presents dans `identifiants_pris`.

    Retourne la table des renommages appliques. Les `xlink:href` de l'arbre
    designant un identifiant renomme sont mis a jour, sous leurs deux formes :
    reference directe et fragment local prefixe de '#'.
    """
    table: dict[str, str] = {}
    for element in racine.iter():
        identifiant = element.get(ATTRIBUT_ID)
        if identifiant is None or identifiant not in identifiants_pris:
            continue
        if identifiant not in table:
            table[identifiant] = _nouvel_identifiant()
        element.set(ATTRIBUT_ID, table[identifiant])

    if not table:
        return table

    for element in racine.iter():
        href = element.get(ATTRIBUT_HREF)
        if not href:
            continue
        if href.startswith("#"):
            cible = table.get(href[1:])
            if cible is not None:
                element.set(ATTRIBUT_HREF, f"#{cible}")
        elif href in table:
            element.set(ATTRIBUT_HREF, table[href])

    return table


def _est_metadata(membre: ET.Element) -> bool:
    """Indique si un featureMember porte l'objet Metadata."""
    return membre.find(tag_qualifie("RecoStaR", "Metadata")) is not None


def fusionner_arbres(racine_cible: ET.Element, racine_source: ET.Element) -> tuple[int, int]:
    """Verse les featureMember de `racine_source` dans `racine_cible`.

    Retourne (nb_membres_ajoutes, nb_metadata_ecartes). Le Metadata du second
    fichier est ecarte : le modele n'en admet qu'un seul par fichier.
    """
    balise_membre = tag_qualifie("gml", "featureMember")

    nb_ajoutes = 0
    nb_metadata_ecartes = 0
    for membre in racine_source.findall(balise_membre):
        if _est_metadata(membre):
            nb_metadata_ecartes += 1
            continue
        racine_cible.append(membre)
        nb_ajoutes += 1

    return nb_ajoutes, nb_metadata_ecartes


def _version_schema(racine: ET.Element) -> str | None:
    """Extrait l'URL de schema declaree par le document."""
    declaration = racine.get(ATTRIBUT_SCHEMA)
    if not declaration:
        return None
    # La declaration associe un namespace a une URL, separes par des espaces.
    parties = declaration.split()
    return parties[-1] if parties else None


def _chemin_sortie_par_defaut(chemin_gml: str) -> str:
    """Derive un nom de sortie du premier fichier d'entree."""
    racine, extension = os.path.splitext(chemin_gml)
    return f"{racine}{SUFFIXE_SORTIE}{extension}"


def _charger(chemin: str, rang: int) -> tuple[ET.ElementTree[ET.Element] | None, str]:
    """Charge un GML et retourne (arbre, message_erreur)."""
    if not os.path.isfile(chemin):
        return None, f"Fichier GML {rang} introuvable : {chemin}"
    try:
        arbre = lire_arbre_gml(chemin)
    except Exception as erreur:
        return None, f"GML {rang} illisible : {erreur}"
    if arbre.getroot() is None:
        return None, f"GML {rang} illisible : document sans element racine"
    return arbre, ""


def _resoudre_projections(
    racine_1: ET.Element,
    racine_2: ET.Element,
    epsg_cible: str | None,
) -> tuple[list[str], str, list[str], str]:
    """Determine les projections des deux fichiers et la cible retenue.

    Retourne (epsg_sources, epsg_cible, avertissements, message_erreur). La
    cible demandee prime ; a defaut c'est la projection du premier fichier qui
    sert de reference.
    """
    avertissements: list[str] = []

    sources: list[str] = []
    for rang, racine in enumerate((racine_1, racine_2), start=1):
        epsg, avertissements_fichier = lire_crs_source(racine)
        avertissements.extend(f"GML {rang} : {message}" for message in avertissements_fichier)
        if epsg is None:
            return [], "", avertissements, f"Projection du GML {rang} introuvable dans le fichier"
        sources.append(epsg)

    if epsg_cible is None:
        # Sans consigne, le premier fichier fait office de reference.
        return sources, sources[0], avertissements, ""

    cible = normaliser_epsg(epsg_cible)
    if cible is None:
        return [], "", avertissements, f"Projection cible non reconnue : {epsg_cible!r}"
    return sources, cible, avertissements, ""


def _aligner_projection(racine: ET.Element, epsg_source: str, epsg_cible: str) -> tuple[bool, str]:
    """Reprojette l'arbre si sa projection differe de la cible.

    Retourne (a_ete_reprojete, message_erreur).
    """
    if epsg_source == epsg_cible:
        return False, ""
    try:
        transformateur = creer_transformateur(epsg_source, epsg_cible)
    except Exception as erreur:
        return False, f"Transformation {epsg_source} vers {epsg_cible} impossible : {erreur}"
    reprojeter_arbre(racine, transformateur, epsg_cible)
    return True, ""


def executer_fusion(
    chemin_gml_1: str,
    chemin_gml_2: str,
    epsg_cible: str | None = None,
    chemin_sortie: str | None = None,
) -> ResultatFusion:
    """Fusionne deux GML RecoStaR en un seul fichier.

    Les projections sont deduites des fichiers. Celle demandee prime ; a
    defaut, le premier fichier sert de reference et le second est reprojete
    s'il s'en ecarte.
    """
    resultat = ResultatFusion()

    arbre_1, erreur = _charger(chemin_gml_1, 1)
    if arbre_1 is None:
        resultat.erreur = erreur
        return resultat

    arbre_2, erreur = _charger(chemin_gml_2, 2)
    if arbre_2 is None:
        resultat.erreur = erreur
        return resultat

    racine_1 = arbre_1.getroot()
    racine_2 = arbre_2.getroot()

    sources, cible, resultat.avertissements, erreur = _resoudre_projections(racine_1, racine_2, epsg_cible)
    if erreur:
        resultat.erreur = erreur
        return resultat
    resultat.epsg_sources = sources
    resultat.epsg_cible = cible

    # Une divergence de schema signale des fichiers de versions differentes :
    # les fusionner produirait un document incoherent.
    schemas = {schema for racine in (racine_1, racine_2) if (schema := _version_schema(racine))}
    if len(schemas) > 1:
        resultat.erreur = f"Versions de schema differentes entre les deux fichiers : {sorted(schemas)}"
        return resultat

    for racine, epsg_source in ((racine_1, sources[0]), (racine_2, sources[1])):
        reprojete, erreur = _aligner_projection(racine, epsg_source, cible)
        if erreur:
            resultat.erreur = erreur
            return resultat
        resultat.nb_reprojetes += int(reprojete)

    table = remapper_collisions(racine_2, collecter_identifiants(racine_1))
    resultat.nb_ids_remappes = len(table)

    nb_ajoutes, nb_metadata_ecartes = fusionner_arbres(racine_1, racine_2)
    resultat.nb_entites_ajoutees = nb_ajoutes
    if nb_metadata_ecartes:
        resultat.avertissements.append(
            f"Metadata du second fichier ecarte ({nb_metadata_ecartes}) : le modele n'en admet qu'un"
        )

    sortie = chemin_sortie or _chemin_sortie_par_defaut(chemin_gml_1)
    try:
        ecrire_arbre_gml(arbre_1, sortie)
    except OSError as erreur_ecriture:
        resultat.erreur = f"Ecriture impossible dans {sortie} : {erreur_ecriture}"
        return resultat

    resultat.chemin_sortie = sortie
    resultat.succes = True
    return resultat


def main() -> None:
    """Point d'entree du traitement de fusion."""
    parseur = argparse.ArgumentParser(description="Fusionne deux fichiers GML RecoStaR en un seul")
    parseur.add_argument(
        "--chemin-gml-1",
        required=True,
        help="Premier GML RecoStaR ; sa projection sert de reference par defaut",
    )
    parseur.add_argument(
        "--chemin-gml-2",
        required=True,
        help="Second GML RecoStaR, reprojete s'il s'ecarte de la projection cible",
    )
    parseur.add_argument(
        "--epsg-cible",
        required=False,
        default=None,
        help="Projection du fichier fusionne (defaut : projection du premier GML)",
    )
    parseur.add_argument(
        "--chemin-sortie",
        required=False,
        default=None,
        help="Fichier GML produit (defaut : premier GML suffixe par _fusion)",
    )
    arguments = parseur.parse_args()

    resultat = executer_fusion(
        arguments.chemin_gml_1,
        arguments.chemin_gml_2,
        arguments.epsg_cible,
        arguments.chemin_sortie,
    )

    if not resultat.succes:
        print(f"Erreur : {resultat.erreur}", file=sys.stderr)

    json.dump(resultat.vers_dict(), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
