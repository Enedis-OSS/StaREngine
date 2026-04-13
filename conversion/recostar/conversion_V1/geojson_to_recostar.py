#!/usr/bin/env python3
"""
Convertit des fichiers GeoJSON RPD_* vers un fichier GML RecoStaR unique.
Conforme au schéma XSD StaR-Elec RecoStaR v1.0.

Entrée : Dossier contenant des fichiers GeoJSON (RPD_CableElectrique_Reco.geojson, etc.)
Sortie : Fichier GML unique avec métadonnées et relations préservées

"""

import json
import math
import argparse
import sys
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Optional, Tuple
from xml.etree import ElementTree as ET
from functools import lru_cache

# Namespaces XML/GML requis par le schéma RecoStaR
NAMESPACE_GML = "http://www.opengis.net/gml/3.2"
NAMESPACE_RECOSTAR = "http://StaR-Elec.com"
NAMESPACE_XLINK = "http://www.w3.org/1999/xlink"
NAMESPACE_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# Constante pour le système de référence spatial par défaut
DEFAULT_SRS = "EPSG:2154"

NS_MAP = {
    "gml": NAMESPACE_GML,
    "RecoStaR": NAMESPACE_RECOSTAR,
    "xlink": NAMESPACE_XLINK,
    "xsi": NAMESPACE_XSI,
}

# Frozenset pour vérifications rapides (O(1) vs O(n) pour list)
REQUIRED_RPD_FILES = frozenset(
    [
        "RPD_CableElectrique_Reco",
        "RPD_CableTerre_Reco",
        "RPD_Coffret_Reco",
        "RPD_EnceinteCloturee_Reco",
        "RPD_Fourreau_Reco",
        "RPD_GeometrieSupplementaire_Reco",
        "RPD_JeuBarres_Reco",
        "RPD_Jonction_Reco",
        "RPD_OuvrageCollectifBranchement_Reco",
        "RPD_PointDeComptage_Reco",
        "RPD_PointLeveOuvrageReseau_Reco",
        "RPD_BatimentTechnique_Reco",
        "RPD_PosteElectrique_Reco",
        "RPD_ProtectionMecanique_Reco",
        "RPD_SupportModules_Reco",
        "RPD_Terre_Reco",
    ]
)


class ElementGML:
    """Classe avec __slots__ pour économiser 20-30% de mémoire"""

    __slots__ = ("tag", "attrib", "text", "children")

    def __init__(
        self, tag: str, attrib: Optional[Dict] = None, text: Optional[str] = None
    ):
        self.tag = tag
        self.attrib = attrib or {}
        self.text = text
        self.children = []


class ConvertisseurGeometrie:
    """Convertit les géométries GeoJSON en éléments GML conformes au schéma"""

    __slots__ = ("srs",)

    def __init__(self, srs: str = DEFAULT_SRS):
        self.srs = srs

    @lru_cache(maxsize=128)
    def _formater_coord(self, value: float) -> str:
        """Cache les conversions pour accélérer le traitement de géométries répétitives"""
        return str(value)

    def _coords_vers_chaine(self, coords: List) -> str:
        """Convertit une liste de coordonnées en chaîne pour posList. join est plus rapide que +="""
        return " ".join(self._formater_coord(c) for coord in coords for c in coord)

    def point_vers_gml(self, geometry: Dict, gml_id: str) -> ET.Element:
        """GeoJSON Point → gml:Point avec srsName et id"""
        point = ET.Element(f"{{{NAMESPACE_GML}}}Point")
        point.set("srsName", self.srs)

        coords = geometry["coordinates"]
        # Ajouter srsDimension="3" si coordonnées 3D
        if len(coords) > 2:
            point.set("srsDimension", "3")

        point.set(f"{{{NAMESPACE_GML}}}id", gml_id)

        pos = ET.SubElement(point, f"{{{NAMESPACE_GML}}}pos")
        pos.text = f"{coords[0]} {coords[1]}"
        if len(coords) > 2:
            pos.text += f" {coords[2]}"

        return point

    def ligne_vers_gml(self, geometry: Dict, gml_id: str) -> ET.Element:
        """GeoJSON LineString → gml:LineString avec posList"""
        linestring = ET.Element(f"{{{NAMESPACE_GML}}}LineString")
        linestring.set("srsName", self.srs)
        linestring.set(f"{{{NAMESPACE_GML}}}id", gml_id)

        coords = geometry["coordinates"]
        pos_list = ET.SubElement(linestring, f"{{{NAMESPACE_GML}}}posList")
        pos_list.set("srsDimension", "3" if len(coords[0]) > 2 else "2")

        pos_list.text = self._coords_vers_chaine(coords)

        return linestring

    def polygone_vers_gml(self, geometry: Dict, gml_id: str) -> ET.Element:
        """GeoJSON Polygon → gml:Polygon avec exterior LinearRing"""
        polygon = ET.Element(f"{{{NAMESPACE_GML}}}Polygon")
        polygon.set("srsName", self.srs)
        polygon.set(f"{{{NAMESPACE_GML}}}id", gml_id)

        coords = geometry["coordinates"]
        exterior = ET.SubElement(polygon, f"{{{NAMESPACE_GML}}}exterior")
        linear_ring = ET.SubElement(exterior, f"{{{NAMESPACE_GML}}}LinearRing")
        pos_list = ET.SubElement(linear_ring, f"{{{NAMESPACE_GML}}}posList")

        pos_list.set("srsDimension", "3" if len(coords[0][0]) > 2 else "2")
        pos_list.text = self._coords_vers_chaine(coords[0])

        return polygon

    def multipolygone_vers_gml(
        self, geometry: Dict, gml_id: str
    ) -> Optional[ET.Element]:
        """GeoJSON MultiPolygon → gml:Polygon (prend le premier polygone uniquement)"""
        if geometry["coordinates"]:
            single_polygon = {
                "type": "Polygon",
                "coordinates": geometry["coordinates"][0],
            }
            return self.polygone_vers_gml(single_polygon, gml_id)
        return None


class MappeurEntites:
    """Transforme les entités GeoJSON en éléments XML GML RecoStaR conformes au XSD"""

    __slots__ = ("geo_converter", "srs", "seen_ids", "geom_counter")

    def __init__(self, srs: str = DEFAULT_SRS):
        self.geo_converter = ConvertisseurGeometrie(srs)
        self.srs = srs
        self.seen_ids = set()  # Vérification unicité des IDs en O(1)
        self.geom_counter = {}  # Compteur pour générer des IDs de géométrie uniques

    def _ajouter_propriete(
        self, parent: ET.Element, name: str, value, uom: Optional[str] = None
    ):
        """Ajoute une balise enfant avec valeur. Ignore si la valeur est None ou vide"""
        if value is None or value == "":
            return

        elem = ET.SubElement(parent, f"{{{NAMESPACE_RECOSTAR}}}{name}")

        if uom:
            elem.set("uom", uom)

        if isinstance(value, bool):
            elem.text = "true" if value else "false"
        elif isinstance(value, float):
            # Convertir en int si la valeur est un entier (évite 35.0 → "35.0")
            elem.text = str(int(value)) if value.is_integer() else str(value)
        elif isinstance(value, int):
            elem.text = str(value)
        else:
            elem.text = str(value)

    def _ajouter_reference(
        self, parent: ET.Element, name: str, href: str, multiline_reseau: bool = False
    ):
        """Ajoute une référence xlink:href. Ignore si la référence href est vide"""
        if not href:
            return

        elem = ET.SubElement(parent, f"{{{NAMESPACE_RECOSTAR}}}{name}")
        elem.set(f"{{{NAMESPACE_XLINK}}}href", href)

        # Formatage spécial pour balise reseau (retour ligne après)
        if multiline_reseau and name == "reseau":
            elem.text = "\n"

    def _obtenir_id_geom_unique(self, feature_type: str, ogr_pkid: str) -> str:
        """Génère un ID unique pour chaque géométrie : {ogr_pkid}.geom{counter}"""
        if feature_type not in self.geom_counter:
            self.geom_counter[feature_type] = 0

        self.geom_counter[feature_type] += 1
        counter = self.geom_counter[feature_type]

        return f"{ogr_pkid}.geom{counter - 1}"

    def mapper_cable_electrique(self, feature: Dict, feature_id: str) -> ET.Element:
        """Entité GeoJSON → RPD_CableElectrique_Reco (sans géométrie, héritée du cheminement)"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_CableElectrique_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence au réseau (formatage avec retour ligne)
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Propriétés obligatoires selon XSD
        self._ajouter_propriete(element, "DomaineTension", props.get("DomaineTension"))
        self._ajouter_reference(
            element, "FonctionCable", props.get("FonctionCable_href")
        )
        self._ajouter_propriete(element, "HierarchieBT", props.get("HierarchieBT"))
        self._ajouter_propriete(element, "Isolant", props.get("Isolant"))
        self._ajouter_propriete(element, "Materiau", props.get("Materiau"))
        self._ajouter_propriete(
            element, "NombreConducteurs", props.get("NombreConducteurs")
        )

        # Section avec UOM
        section_val = props.get("Section")
        if section_val:
            self._ajouter_propriete(
                element, "Section", section_val, props.get("Section_uom", "mm-2")
            )

        section_neutre = props.get("SectionNeutre")
        if section_neutre:
            self._ajouter_propriete(
                element,
                "SectionNeutre",
                section_neutre,
                props.get("SectionNeutre_uom", "mm-2"),
            )

        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element

    def mapper_cable_terre(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_CableTerre_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_CableTerre_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # noeudReseau (optionnel) - référence RPD_Terre_Reco
        noeud_href = props.get("noeudreseau_href")
        if noeud_href:
            self._ajouter_reference(element, "noeudReseau", noeud_href)

        # Commentaire (optionnel)
        self._ajouter_propriete(element, "Commentaire", props.get("Commentaire"))

        # FonctionCable (requis)
        self._ajouter_reference(
            element, "FonctionCable", props.get("FonctionCable_href")
        )

        # Materiau (requis)
        self._ajouter_propriete(element, "Materiau", props.get("Materiau"))

        # NatureCableTerre (optionnel)
        self._ajouter_reference(
            element, "NatureCableTerre", props.get("NatureCableTerre_href")
        )

        # Section (requis, avec UOM)
        section_val = props.get("Section")
        if section_val:
            self._ajouter_propriete(
                element, "Section", section_val, props.get("Section_uom", "mm-2")
            )

        # Statut (requis)
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element

    def mapper_coffret(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_Coffret_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Coffret_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau avec style multiline
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Référence géométrie supplémentaire si présente
        geom_supp = props.get("geometriesupplementaire_href")
        if geom_supp:
            self._ajouter_reference(element, "geometriesupplementaire", geom_supp)

        # Propriétés
        self._ajouter_reference(
            element, "FonctionCoffret", props.get("FonctionCoffret_href")
        )

        # Géométrie Point avec ID unique
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_Coffret_Reco", props.get("ogr_pkid", feature_id)
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        self._ajouter_reference(
            element, "ImplantationArmoire", props.get("ImplantationArmoire_href")
        )
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))
        self._ajouter_reference(element, "TypeCoffret", props.get("TypeCoffret_href"))

        return element

    def mapper_support(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_Support_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Support_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau avec style multiline
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Classe (optionnel)
        self._ajouter_reference(element, "Classe", props.get("Classe_href"))

        # Effort (optionnel)
        effort = props.get("Effort")
        if effort is not None:
            effort_uom = props.get("Effort_uom", "kN")
            self._ajouter_propriete(element, "Effort", effort, effort_uom)

        # Géométrie Point avec ID unique
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_Support_Reco", props.get("ogr_pkid", feature_id)
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        # HauteurPoteau (optionnel)
        hauteur = props.get("HauteurPoteau")
        if hauteur is not None:
            hauteur_uom = props.get("HauteurPoteau_uom", "m")
            self._ajouter_propriete(element, "HauteurPoteau", hauteur, hauteur_uom)

        # Matiere (optionnel)
        self._ajouter_reference(element, "Matiere", props.get("Matiere_href"))

        # NatureSupport (requis)
        self._ajouter_reference(
            element, "NatureSupport", props.get("NatureSupport_href")
        )

        # Précisions
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        return element

    def mapper_fourreau(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_Fourreau_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Fourreau_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # ORDRE STRICT SELON XSD :
        # 1. reseau+
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # 2. CoupeType? (optionnel)
        coupe_type = props.get("CoupeType")
        if coupe_type:
            self._ajouter_propriete(element, "CoupeType", coupe_type)

        # 3. DiametreDuFourreau (requis)
        diametre = props.get("DiametreDuFourreau")
        if diametre:
            self._ajouter_propriete(
                element,
                "DiametreDuFourreau",
                diametre,
                props.get("DiametreDuFourreau_uom", "mm"),
            )

        # 4. EtatCoupeType? (optionnel)
        etat_coupe = props.get("EtatCoupeType")
        if etat_coupe:
            self._ajouter_propriete(element, "EtatCoupeType", etat_coupe)

        # 5. Geometrie (requis)
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_Fourreau_Reco", props.get("ogr_pkid", feature_id)
            )
            linestring = self.geo_converter.ligne_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(linestring)

        # 6. Materiau (requis)
        self._ajouter_propriete(element, "Materiau", props.get("Materiau"))

        # 7. PrecisionXY (requis)
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))

        # 8. PrecisionZ (requis)
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        # 9. ProfondeurMinNonReg? (optionnel)
        profondeur = props.get("ProfondeurMinNonReg")
        if profondeur:
            self._ajouter_propriete(
                element,
                "ProfondeurMinNonReg",
                profondeur,
                props.get("ProfondeurMinNonReg_uom", "m"),
            )

        return element

    def _normaliser_wkt_ligne(self, ligne_text: str) -> Optional[str]:
        """Normalise un texte WKT Ligne2.5D en chaîne de coordonnées posList.

        Supprime le préfixe LINESTRING, extrait les coordonnées entre parenthèses,
        et normalise les séparateurs. Retourne None si les coordonnées sont invalides.
        """
        text_clean = ligne_text.strip()
        if text_clean.upper().startswith("LINESTRING"):
            idx_open = text_clean.index("(")
            text_clean = text_clean[idx_open + 1 :].rstrip(")")

        # "x1 y1 z1,x2 y2 z2" → "x1 y1 z1 x2 y2 z2"
        normalized = text_clean.replace(",", " ")

        # Validation : au moins un triplet 3D complet
        coords_list = normalized.split()
        if len(coords_list) < 3:
            return None

        return normalized

    def _ajouter_ligne_2_5d(self, element: ET.Element, ligne_text: str, ogr_pkid: str):
        """Ajoute un élément Ligne2.5D (LineString GML) à l'élément parent."""
        normalized_text = self._normaliser_wkt_ligne(ligne_text)
        if not normalized_text:
            return

        linestring = ET.Element(f"{{{NAMESPACE_GML}}}LineString")
        linestring.set("srsName", self.srs)
        linestring.set(f"{{{NAMESPACE_GML}}}id", f"{ogr_pkid}.geom_ligne0")

        pos_list = ET.SubElement(linestring, f"{{{NAMESPACE_GML}}}posList")
        pos_list.set("srsDimension", "3")
        pos_list.text = normalized_text

        ligne_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Ligne2.5D")
        ligne_elem.append(linestring)

    def _ajouter_surface_2_5d(self, element: ET.Element, geometry: Dict, ogr_pkid: str):
        """Ajoute un élément Surface2.5D (Polygon GML) à l'élément parent."""
        geom_type = geometry["type"]
        geom_id = f"{ogr_pkid}.geom_surface0"

        if geom_type == "Polygon":
            polygon = self.geo_converter.polygone_vers_gml(geometry, geom_id)
        elif geom_type == "MultiPolygon":
            polygon = self.geo_converter.multipolygone_vers_gml(geometry, geom_id)
        else:
            return

        if polygon is not None:
            surface_elem = ET.SubElement(
                element, f"{{{NAMESPACE_RECOSTAR}}}Surface2.5D"
            )
            surface_elem.append(polygon)

    def mapper_geometrie_supplementaire(
        self, feature: Dict, feature_id: str
    ) -> ET.Element:
        """Entité GeoJSON → RPD_GeometrieSupplementaire_Reco

        Ordre XSD strict : Ligne2.5D → PrecisionXY → PrecisionZ → Surface2.5D
        """
        props = feature["properties"]

        element = ET.Element(
            f"{{{NAMESPACE_RECOSTAR}}}RPD_GeometrieSupplementaire_Reco"
        )
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        ogr_pkid = props.get("ogr_pkid", feature_id)

        # 1. Ligne2.5D (optionnel)
        ligne_text = props.get("Ligne2.5D")
        if ligne_text:
            self._ajouter_ligne_2_5d(element, ligne_text, ogr_pkid)

        # 2 et 3. PrecisionXY et PrecisionZ (obligatoires)
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        # 4. Surface2.5D (optionnel) - Doit venir APRÈS les précisions
        if feature.get("geometry"):
            self._ajouter_surface_2_5d(element, feature["geometry"], ogr_pkid)

        return element

    def mapper_jonction(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_Jonction_Reco avec prise en charge des propriétés optionnelles Aerien et angle"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Jonction_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau avec style multiline
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # ORDRE XSD STRICT : conteneur, DomaineTension, Geometrie?,
        # PrecisionXY?, PrecisionZ?, Statut, TypeJonction, angle?

        # 1. conteneur (hérité de NoeudReseauType - optionnel)
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # 2. DomaineTension (requis)
        self._ajouter_propriete(element, "DomaineTension", props.get("DomaineTension"))

        # 3. Geometrie (optionnel) - SEULEMENT si pas de conteneur
        # Selon XSD: "Les nœuds ne possèdent pas de géométrie (positionnement déduit des Conteneur),
        # sauf pour ceux qui ne possèdent pas de relation avec un Conteneur"
        if feature.get("geometry") and not conteneur_href:
            geom_id = self._obtenir_id_geom_unique(
                "RPD_Jonction_Reco", props.get("ogr_pkid", feature_id)
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        # 4-5. PrecisionXY/Z (optionnels)
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        # 6. Statut (requis)
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        # 7. TypeJonction (requis)
        self._ajouter_propriete(element, "TypeJonction", props.get("TypeJonction"))

        # 8. angle (optionnel)
        angle = props.get("angle")
        if angle is not None:
            self._ajouter_propriete(element, "angle", angle)

        return element

    def mapper_coupe_circuit_a_fusibles(
        self, feature: Dict, feature_id: str
    ) -> ET.Element:
        """Mappe RPD_CoupeCircuitAFusibles_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_CoupeCircuitAFusibles_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau avec style multiline
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Référence conteneur (optionnel selon XSD - NoeudReseauType)
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # Propriété obligatoire : Statut
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element

    def mapper_point_comptage(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_PointDeComptage_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_PointDeComptage_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau avec style multiline
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Référence conteneur
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # Géométrie avec ID unique
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_PointDeComptage_Reco", props.get("ogr_pkid", feature_id)
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        # NumeroPRM (optionnel)
        self._ajouter_propriete(element, "NumeroPRM", props.get("NumeroPRM"))

        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element

    def mapper_point_leve(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_PointLeveOuvrageReseau_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_PointLeveOuvrageReseau_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Géométrie avec ID unique
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_PointLeveOuvrageReseau_Reco", props.get("ogr_pkid", feature_id)
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        # Propriétés
        leve = props.get("Leve")
        if leve:
            self._ajouter_propriete(element, "Leve", leve, props.get("Leve_uom", "m"))

        self._ajouter_propriete(element, "NumeroPoint", props.get("NumeroPoint"))
        self._ajouter_propriete(element, "PrecisionXYnum", props.get("PrecisionXYnum"))
        self._ajouter_propriete(element, "PrecisionZnum", props.get("PrecisionZnum"))
        self._ajouter_propriete(element, "Producteur", props.get("Producteur"))
        self._ajouter_propriete(element, "TypeLeve", props.get("TypeLeve"))

        return element

    def mapper_materiel(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_Materiel_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Materiel_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        self._ajouter_propriete(element, "Fabricant", props.get("Fabricant"))
        self._ajouter_propriete(element, "Modele", props.get("Modele"))
        self._ajouter_propriete(element, "NumeroLot", props.get("NumeroLot"))
        self._ajouter_propriete(element, "NumeroSerie", props.get("NumeroSerie"))

        return element

    def mapper_aerien(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_Aerien_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Aerien_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau avec style multiline
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Géométrie LineString avec ID unique
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_Aerien_Reco", props.get("ogr_pkid", feature_id)
            )
            linestring = self.geo_converter.ligne_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(linestring)

        # ModePose (requis)
        self._ajouter_propriete(element, "ModePose", props.get("ModePose"))

        # PrecisionXY (requis)
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))

        # PrecisionZ (requis)
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        return element

    def mapper_pleine_terre(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_PleineTerre_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_PleineTerre_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau avec style multiline
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # CoupeType (optionnel)
        coupe_type = props.get("CoupeType")
        if coupe_type:
            self._ajouter_propriete(element, "CoupeType", coupe_type)

        # EtatCoupeType (optionnel)
        etat_coupe = props.get("EtatCoupeType")
        if etat_coupe:
            self._ajouter_propriete(element, "EtatCoupeType", etat_coupe)

        # Géométrie LineString avec ID unique
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_PleineTerre_Reco", props.get("ogr_pkid", feature_id)
            )
            linestring = self.geo_converter.ligne_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(linestring)

        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        # ProfondeurMinNonReg (optionnel)
        profondeur = props.get("ProfondeurMinNonReg")
        if profondeur:
            self._ajouter_propriete(
                element,
                "ProfondeurMinNonReg",
                profondeur,
                props.get("ProfondeurMinNonReg_uom", "m"),
            )

        return element

    def mapper_enceinte_cloturee(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_EnceinteCloturee_Reco (conteneur : enceinte clôturée entourant les postes)"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_EnceinteCloturee_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Référence géométrie supplémentaire si présente
        geom_supp = props.get("geometriesupplementaire_href")
        if geom_supp:
            self._ajouter_reference(element, "geometriesupplementaire", geom_supp)

        # Géométrie Point (requis)
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_EnceinteCloturee_Reco", props.get("ogr_pkid", feature_id)
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        # PrecisionXY (requis)
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))

        # PrecisionZ (requis)
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        return element

    def mapper_batiment_technique(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_BatimentTechnique_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_BatimentTechnique_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # Référence géométrie supplémentaire si présente
        geom_supp = props.get("geometriesupplementaire_href")
        if geom_supp:
            self._ajouter_reference(element, "geometriesupplementaire", geom_supp)

        # Géométrie Point (requis)
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_BatimentTechnique_Reco", props.get("ogr_pkid", feature_id)
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        # PrecisionXY (requis)
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))

        # PrecisionZ (requis)
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        return element

    def mapper_poste_electrique(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_PosteElectrique_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_PosteElectrique_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # ORDRE IMPORTANT: conteneur DOIT être AVANT les propriétés spécifiques (NoeudReseauType avant RPD_PosteElectrique_RecoType)
        # conteneur_href (hérité de NoeudReseauType)
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # Categorie (requis, xlink:href)
        self._ajouter_reference(element, "Categorie", props.get("Categorie_href"))

        # Code (requis, string)
        self._ajouter_propriete(element, "Code", props.get("Code"))

        # InformationSupplementaire (requis, string)
        self._ajouter_propriete(
            element, "InformationSupplementaire", props.get("InformationSupplementaire")
        )

        # Statut (requis)
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        # TypePoste (requis, xlink:href)
        self._ajouter_reference(element, "TypePoste", props.get("TypePoste_href"))

        # NOTE: PrecisionXY et PrecisionZ n'existent PAS dans RPD_PosteElectrique_RecoType XSD

        return element

    def mapper_protection_mecanique(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_ProtectionMecanique_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_ProtectionMecanique_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # CoupeType (optionnel)
        coupe_type = props.get("CoupeType")
        if coupe_type:
            self._ajouter_propriete(element, "CoupeType", coupe_type)

        # EtatCoupeType (optionnel)
        etat_coupe = props.get("EtatCoupeType")
        if etat_coupe:
            self._ajouter_propriete(element, "EtatCoupeType", etat_coupe)

        # Geometrie (requis, LineString)
        if feature.get("geometry"):
            geom_id = self._obtenir_id_geom_unique(
                "RPD_ProtectionMecanique_Reco", props.get("ogr_pkid", feature_id)
            )
            linestring = self.geo_converter.ligne_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(linestring)

        # Materiau (requis)
        self._ajouter_propriete(element, "Materiau", props.get("Materiau"))

        # PrecisionXY (requis)
        self._ajouter_propriete(element, "PrecisionXY", props.get("PrecisionXY"))

        # PrecisionZ (requis)
        self._ajouter_propriete(element, "PrecisionZ", props.get("PrecisionZ"))

        # ProfondeurMinNonReg (optionnel)
        profondeur = props.get("ProfondeurMinNonReg")
        if profondeur:
            self._ajouter_propriete(
                element,
                "ProfondeurMinNonReg",
                profondeur,
                props.get("ProfondeurMinNonReg_uom", "m"),
            )

        return element

    def mapper_jeu_barres(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_JeuBarres_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_JeuBarres_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # conteneur_href (optionnel)
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # Statut (requis)
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element

    def mapper_support_modules(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_SupportModules_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_SupportModules_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # conteneur_href (optionnel)
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # NombrePlages (requis)
        self._ajouter_propriete(element, "NombrePlages", props.get("NombrePlages"))

        # Statut (requis)
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element

    def mapper_terre(self, feature: Dict, feature_id: str) -> ET.Element:
        """Mappe RPD_Terre_Reco"""
        props = feature["properties"]

        element = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Terre_Reco")
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # conteneur_href (optionnel)
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # NatureTerre (requis, xlink:href)
        self._ajouter_reference(element, "NatureTerre", props.get("NatureTerre_href"))

        # Resistance (optionnel avec unité)
        resistance = props.get("Resistance")
        if resistance:
            self._ajouter_propriete(
                element, "Resistance", resistance, props.get("Resistance_uom", "Ohm")
            )

        # Statut (requis)
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element

    def mapper_ouvrage_collectif_branchement(
        self, feature: Dict, feature_id: str
    ) -> ET.Element:
        """Mappe RPD_OuvrageCollectifBranchement_Reco"""
        props = feature["properties"]

        element = ET.Element(
            f"{{{NAMESPACE_RECOSTAR}}}RPD_OuvrageCollectifBranchement_Reco"
        )
        element.set(f"{{{NAMESPACE_GML}}}id", feature_id)

        # Référence reseau
        self._ajouter_reference(element, "reseau", "Reseau", multiline_reseau=True)

        # conteneur_href (optionnel)
        conteneur_href = props.get("conteneur_href")
        if conteneur_href:
            self._ajouter_reference(element, "conteneur", conteneur_href)

        # Geometrie (optionnelle, Point)
        if feature.get("geometry") and not conteneur_href:
            geom_id = self._obtenir_id_geom_unique(
                "RPD_OuvrageCollectifBranchement_Reco",
                props.get("ogr_pkid", feature_id),
            )
            point = self.geo_converter.point_vers_gml(feature["geometry"], geom_id)
            geom_elem = ET.SubElement(element, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
            geom_elem.append(point)

        # PrecisionXY (optionnel)
        precision_xy = props.get("PrecisionXY")
        if precision_xy:
            self._ajouter_propriete(element, "PrecisionXY", precision_xy)

        # PrecisionZ (optionnel)
        precision_z = props.get("PrecisionZ")
        if precision_z:
            self._ajouter_propriete(element, "PrecisionZ", precision_z)

        # Statut (requis)
        self._ajouter_propriete(element, "Statut", props.get("Statut"))

        return element


class GenerateurGML:
    """Générateur GML principal avec optimisations de performances"""

    __slots__ = ("mapper", "srs", "metadata")

    def __init__(self, srs: str = DEFAULT_SRS):
        self.mapper = MappeurEntites(srs)
        self.srs = srs
        self.metadata = {}

    def definir_metadonnees(
        self,
        logiciel: str,
        producteur: str,
        responsable: str,
        nom: str,
        srs: str = DEFAULT_SRS,
    ):
        """Configure les métadonnées du GML"""
        self.metadata = {
            "logiciel": logiciel,
            "producteur": producteur,
            "responsable": responsable,
            "nom": nom,
            "srs": srs,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        self.srs = srs
        self.mapper.srs = srs
        self.mapper.geo_converter.srs = srs

    def _creer_membre_metadonnees(self) -> ET.Element:
        """Crée l'élément Metadata"""
        member = ET.Element(f"{{{NAMESPACE_GML}}}featureMember")

        metadata_id = f"id{uuid.uuid4()}"

        metadata = ET.SubElement(member, f"{{{NAMESPACE_RECOSTAR}}}Metadata")
        metadata.set(f"{{{NAMESPACE_GML}}}id", metadata_id)

        date_elem = ET.SubElement(metadata, f"{{{NAMESPACE_RECOSTAR}}}Datecreation")
        date_elem.text = self.metadata.get("date", datetime.now().strftime("%Y-%m-%d"))

        logiciel_elem = ET.SubElement(metadata, f"{{{NAMESPACE_RECOSTAR}}}Logiciel")
        logiciel_elem.text = self.metadata.get("logiciel", "")

        prod_elem = ET.SubElement(metadata, f"{{{NAMESPACE_RECOSTAR}}}Producteur")
        prod_elem.text = self.metadata.get("producteur", "")

        resp_elem = ET.SubElement(metadata, f"{{{NAMESPACE_RECOSTAR}}}Responsable")
        resp_elem.text = self.metadata.get("responsable", "")

        srs_elem = ET.SubElement(metadata, f"{{{NAMESPACE_RECOSTAR}}}SRS")
        srs_elem.text = self.metadata.get("srs", self.srs)

        return member

    def _creer_membre_reseau(self) -> ET.Element:
        """Crée l'élément ReseauUtilite"""
        member = ET.Element(f"{{{NAMESPACE_GML}}}featureMember")

        reseau = ET.SubElement(member, f"{{{NAMESPACE_RECOSTAR}}}ReseauUtilite")
        reseau.set(f"{{{NAMESPACE_GML}}}id", "Reseau")

        mention = ET.SubElement(reseau, f"{{{NAMESPACE_RECOSTAR}}}Mention")
        mention.text = "Récolement informatisé des ouvrages de distribution publique d'électricité, diffusion limitée au Maître d'Ouvrage, à l'Exploitant et leurs Prestataires."

        nom_elem = ET.SubElement(reseau, f"{{{NAMESPACE_RECOSTAR}}}Nom")
        nom_elem.text = self.metadata.get("nom", "")

        resp_elem = ET.SubElement(reseau, f"{{{NAMESPACE_RECOSTAR}}}Responsable")
        resp_elem.text = self.metadata.get("responsable", "")

        theme_elem = ET.SubElement(reseau, f"{{{NAMESPACE_RECOSTAR}}}Theme")
        theme_elem.text = "ELECTRD"

        return member

    def _creer_relation_cable_noeud(self, cable_id: str, noeud_id: str) -> ET.Element:
        """Crée une relation CableElectrique_NoeudReseau"""
        member = ET.Element(f"{{{NAMESPACE_GML}}}featureMember")

        relation_id = f"id{uuid.uuid4()}"

        relation = ET.SubElement(
            member, f"{{{NAMESPACE_RECOSTAR}}}CableElectrique_NoeudReseau"
        )
        relation.set(f"{{{NAMESPACE_GML}}}id", relation_id)

        noeud_elem = ET.SubElement(relation, f"{{{NAMESPACE_RECOSTAR}}}noeudreseau")
        noeud_elem.set(f"{{{NAMESPACE_XLINK}}}href", noeud_id)

        cable_elem = ET.SubElement(relation, f"{{{NAMESPACE_RECOSTAR}}}cableelectrique")
        cable_elem.set(f"{{{NAMESPACE_XLINK}}}href", cable_id)

        return member

    def _creer_relation_cheminement_cable(
        self, cable_id: str, cheminement_id: str
    ) -> ET.Element:
        """Crée une relation Cheminement_Cables"""
        member = ET.Element(f"{{{NAMESPACE_GML}}}featureMember")

        relation_id = f"id{uuid.uuid4()}"

        relation = ET.SubElement(member, f"{{{NAMESPACE_RECOSTAR}}}Cheminement_Cables")
        relation.set(f"{{{NAMESPACE_GML}}}id", relation_id)

        cables_elem = ET.SubElement(relation, f"{{{NAMESPACE_RECOSTAR}}}cables")
        cables_elem.set(f"{{{NAMESPACE_XLINK}}}href", cable_id)

        chemin_elem = ET.SubElement(relation, f"{{{NAMESPACE_RECOSTAR}}}cheminement")
        chemin_elem.set(f"{{{NAMESPACE_XLINK}}}href", cheminement_id)

        return member

    def _creer_relation_ouvrage_materiel(
        self, ouvrage_id: str, materiel_id: str
    ) -> ET.Element:
        """Crée une relation Ouvrage_Materiel"""
        member = ET.Element(f"{{{NAMESPACE_GML}}}featureMember")

        relation_id = f"id{uuid.uuid4()}"

        relation = ET.SubElement(member, f"{{{NAMESPACE_RECOSTAR}}}Ouvrage_Materiel")
        relation.set(f"{{{NAMESPACE_GML}}}id", relation_id)

        ouvrage_elem = ET.SubElement(relation, f"{{{NAMESPACE_RECOSTAR}}}ouvrage")
        ouvrage_elem.set(f"{{{NAMESPACE_XLINK}}}href", ouvrage_id)

        materiel_elem = ET.SubElement(relation, f"{{{NAMESPACE_RECOSTAR}}}materiel")
        materiel_elem.set(f"{{{NAMESPACE_XLINK}}}href", materiel_id)

        return member

    def _analyser_ids_cable(self, cable_href: str) -> List[str]:
        """Analyse les identifiants câble depuis une chaîne séparée par des virgules."""
        return [cid.strip() for cid in cable_href.split(",") if cid.strip()]

    def _extraire_relations_depuis_entites(self, features: List) -> List:
        """Extrait les paires (cable_id, id_entite) depuis une liste d'entités."""
        result = []
        for feat in features:
            props = feat.get("properties", {})
            feat_id = props.get("id")
            cable_href = props.get("cables_href")
            if not (feat_id and cable_href):
                continue
            for cid in self._analyser_ids_cable(cable_href):
                result.append((cid, feat_id))
        return result

    def _extraire_relations_cable(
        self, features_by_type: Dict[str, List], type_names: tuple
    ) -> List:
        """Extrait les relations câble depuis les types donnés via cables_href."""
        result = []
        for type_name in type_names:
            features = features_by_type.get(type_name)
            if features:
                result.extend(self._extraire_relations_depuis_entites(features))
        return result

    def _extraire_relations_ouvrage_materiel(
        self, features_by_type: Dict[str, List]
    ) -> List:
        """Extrait les relations ouvrage-matériel depuis les jonctions."""
        result = []
        jonction_features = features_by_type.get("RPD_Jonction_Reco")
        if not jonction_features:
            return result
        for ouvrage in jonction_features:
            props = ouvrage.get("properties", {})
            ouvrage_id = props.get("id")
            materiel_href = props.get("materiel_href")
            if ouvrage_id and materiel_href:
                result.append((ouvrage_id, materiel_href))
        return result

    def _extraire_relations(self, features_by_type: Dict[str, List]) -> Dict[str, List]:
        """Extrait les relations à partir des références dans les propriétés."""
        chemin_types = (
            "RPD_Aerien_Reco",
            "RPD_Fourreau_Reco",
            "RPD_PleineTerre_Reco",
            "RPD_ProtectionMecanique_Reco",
        )
        noeud_types = (
            "RPD_CoupeCircuitAFusibles_Reco",
            "RPD_JeuBarres_Reco",
            "RPD_Jonction_Reco",
            "RPD_OuvrageCollectifBranchement_Reco",
            "RPD_PointDeComptage_Reco",
            "RPD_PosteElectrique_Reco",
            "RPD_SupportModules_Reco",
            "RPD_Terre_Reco",
        )
        return {
            "cheminement_cable": self._extraire_relations_cable(
                features_by_type, chemin_types
            ),
            "cable_noeud": self._extraire_relations_cable(
                features_by_type, noeud_types
            ),
            "ouvrage_materiel": self._extraire_relations_ouvrage_materiel(
                features_by_type
            ),
        }

    def _extraire_crs_geojson(self, data: Dict) -> Optional[str]:
        """Extrait le CRS depuis la structure GeoJSON.

        Format attendu : {"crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}}
        Retourne le CRS normalisé (ex: "EPSG:2154") ou None si absent/invalide.
        """
        crs_block = data.get("crs")
        if not crs_block or crs_block.get("type") != "name":
            return None

        urn = crs_block.get("properties", {}).get("name", "")
        if not urn:
            return None

        # "urn:ogc:def:crs:EPSG::2154" → "EPSG:2154"
        parts = urn.split(":")
        if len(parts) >= 7 and parts[4]:
            return f"{parts[4]}:{parts[6]}"

        return None

    def charger_fichiers_geojson(
        self, directory: Path
    ) -> Tuple[Dict[str, List], Optional[str]]:
        """Charge tous les fichiers GeoJSON RPD_* et détecte le CRS source.

        Retourne un tuple (features_par_type, crs_detecte).
        Le CRS est extrait du premier fichier contenant une déclaration valide.
        """
        features_by_type = {}
        crs_detecte: Optional[str] = None

        # Recherche optimisée avec glob
        geojson_files = list(directory.glob("RPD_*.geojson"))

        for filepath in geojson_files:
            # Extraction du nom de fichier sans extension
            filename = filepath.stem

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if "features" in data:
                    features_by_type[filename] = data["features"]

                # Détection du CRS sur le premier fichier valide
                if crs_detecte is None:
                    crs_detecte = self._extraire_crs_geojson(data)

            except Exception as e:
                print(f"Erreur lors du chargement de {filepath}: {e}", file=sys.stderr)

        return features_by_type, crs_detecte

    def extraire_materiels_depuis_jonctions(
        self, jonction_features: List[Dict]
    ) -> Tuple[List[Dict], Set[str]]:
        """Extrait les entités RPD_Materiel_Reco depuis les jonctions

        Optimisations appliquées :
        - Utilise set() pour éviter les doublons (recherche O(1))
        - Pré-allocation de la liste résultat
        - Fonctions locales pour réduire les recherches répétées

        Retourne :
            Tuple[List[Dict], Set[str]] : (liste_materiels, ensemble_ids_materiels_créés)
        """
        if not jonction_features:
            return [], set()

        # Utilisation de set pour unicité des IDs (O(1) vs list O(n))
        seen_materiel_ids = set()
        materiels = []

        # Fonction locale pour éviter les recherches répétées
        get_props = lambda feat: feat.get("properties", {})

        # Champs requis pour créer un matériel (frozenset pour recherche O(1))
        required_fields = frozenset(["Fabricant", "Modele", "NumeroLot", "NumeroSerie"])

        for jonction in jonction_features:
            props = get_props(jonction)
            materiel_href = props.get("materiel_href")

            # Vérifier que materiel_href existe
            if not materiel_href:
                continue

            # Éviter les doublons (recherche set O(1))
            if materiel_href in seen_materiel_ids:
                continue

            # Vérifier présence des champs matériel
            has_all_fields = all(props.get(field) for field in required_fields)

            if has_all_fields:
                # Créer feature matériel
                materiel_feature = {
                    "type": "Feature",
                    "properties": {
                        "id": materiel_href,
                        "Fabricant": props["Fabricant"],
                        "Modele": props["Modele"],
                        "NumeroLot": props["NumeroLot"],
                        "NumeroSerie": props["NumeroSerie"],
                    },
                    "geometry": None,
                }

                materiels.append(materiel_feature)
                seen_materiel_ids.add(materiel_href)

        return materiels, seen_materiel_ids

    def _fusionner_materiels(self, features_by_type: Dict[str, List]):
        """Fusionne les matériels extraits des jonctions avec les matériels existants."""
        jonction_features = features_by_type.get("RPD_Jonction_Reco", [])
        materiels_extraits, _ = self.extraire_materiels_depuis_jonctions(
            jonction_features
        )

        existing_materiels = features_by_type.get("RPD_Materiel_Reco", [])

        # Ensemble pour IDs existants (recherche O(1))
        existing_ids = {
            feat.get("properties", {}).get("id")
            for feat in existing_materiels
            if feat.get("properties", {}).get("id")
        }

        for materiel in materiels_extraits:
            mat_id = materiel["properties"]["id"]
            if mat_id not in existing_ids:
                existing_materiels.append(materiel)

        if existing_materiels:
            features_by_type["RPD_Materiel_Reco"] = existing_materiels

    def _ajouter_relations(self, root, features_by_type: Dict[str, List]):
        """Ajoute les relations, métadonnées et réseau à la racine GML."""
        relations = self._extraire_relations(features_by_type)

        for cable_id, noeud_id in relations["cable_noeud"]:
            root.append(self._creer_relation_cable_noeud(cable_id, noeud_id))

        for cable_id, cheminement_id in relations["cheminement_cable"]:
            root.append(
                self._creer_relation_cheminement_cable(cable_id, cheminement_id)
            )

        if self.metadata:
            root.append(self._creer_membre_metadonnees())

        for ouvrage_id, materiel_id in relations["ouvrage_materiel"]:
            root.append(self._creer_relation_ouvrage_materiel(ouvrage_id, materiel_id))

        if self.metadata:
            root.append(self._creer_membre_reseau())

    def _construire_cache_conteneurs(
        self, features_by_type: Dict[str, List]
    ) -> Dict[str, Dict]:
        """Indexe les géométries des conteneurs (Coffret, EnceinteCloturee, Support, BatimentTechnique) par id.

        Permet aux entités sans géométrie de résoudre leur conteneur_href
        vers une géométrie ponctuelle valide.
        """
        # Types de conteneurs possédant une géométrie propre (cohérent avec recostar_to_geojson)
        types_conteneurs = (
            "RPD_Coffret_Reco",
            "RPD_EnceinteCloturee_Reco",
            "RPD_Support_Reco",
            "RPD_BatimentTechnique_Reco",
        )
        cache: Dict[str, Dict] = {}

        for type_conteneur in types_conteneurs:
            for feat in features_by_type.get(type_conteneur, []):
                geom = feat.get("geometry")
                feat_id = feat.get("properties", {}).get("id")
                if feat_id and geom and geom.get("type"):
                    cache[feat_id] = geom

        return cache

    def _enrichir_geometries_depuis_conteneurs(
        self, features_by_type: Dict[str, List], cache_conteneurs: Dict[str, Dict]
    ):
        """Attribue la géométrie du conteneur aux entités sans géométrie propre.

        Concerne les noeuds liés via conteneur_href : PointDeComptage, Jonction,
        PosteElectrique, JeuBarres, SupportModules, Terre, CoupeCircuitAFusibles,
        OuvrageCollectifBranchement.
        """
        types_noeuds = (
            "RPD_CoupeCircuitAFusibles_Reco",
            "RPD_JeuBarres_Reco",
            "RPD_Jonction_Reco",
            "RPD_OuvrageCollectifBranchement_Reco",
            "RPD_PointDeComptage_Reco",
            "RPD_PosteElectrique_Reco",
            "RPD_SupportModules_Reco",
            "RPD_Terre_Reco",
        )

        nb_enrichies = 0
        for type_noeud in types_noeuds:
            for feat in features_by_type.get(type_noeud, []):
                geom = feat.get("geometry")
                if geom and geom.get("type"):
                    continue

                conteneur_href = feat.get("properties", {}).get("conteneur_href")
                if conteneur_href and conteneur_href in cache_conteneurs:
                    feat["geometry"] = cache_conteneurs[conteneur_href]
                    nb_enrichies += 1

        if nb_enrichies > 0:
            print(f"  {nb_enrichies} entite(s) enrichie(s) avec geometrie du conteneur")

    def _ajouter_membres_entites(
        self, root, features_by_type: Dict[str, List], type_mappers: dict
    ):
        """Ajoute les membres entités RPD principales à la racine GML."""
        ordered_types = (
            "RPD_Aerien_Reco",
            "RPD_BatimentTechnique_Reco",
            "RPD_CableElectrique_Reco",
            "RPD_CableTerre_Reco",
            "RPD_Coffret_Reco",
            "RPD_CoupeCircuitAFusibles_Reco",
            "RPD_EnceinteCloturee_Reco",
            "RPD_GeometrieSupplementaire_Reco",
            "RPD_JeuBarres_Reco",
            "RPD_Jonction_Reco",
            "RPD_Materiel_Reco",
            "RPD_OuvrageCollectifBranchement_Reco",
            "RPD_PleineTerre_Reco",
            "RPD_Fourreau_Reco",
            "RPD_PointDeComptage_Reco",
            "RPD_PointLeveOuvrageReseau_Reco",
            "RPD_PosteElectrique_Reco",
            "RPD_ProtectionMecanique_Reco",
            "RPD_Support_Reco",
            "RPD_SupportModules_Reco",
            "RPD_Terre_Reco",
        )

        for feature_type in ordered_types:
            features = features_by_type.get(feature_type)
            if not features:
                continue
            mapper_func = type_mappers.get(feature_type)
            if not mapper_func:
                continue

            for feature in features:
                props = feature.get("properties", {})
                feature_id = props.get("id") or f'id{props.get("fid", "")}'
                member = ET.SubElement(root, f"{{{NAMESPACE_GML}}}featureMember")
                member.append(mapper_func(feature, feature_id))

    def _ecrire_fichier_gml(self, root, output_path: Path):
        """Écrit l'arbre XML dans le fichier GML avec en-tête et commentaire."""
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")

        with open(output_path, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="utf-8" ?>\n')

            tree_bytes = ET.tostring(root, encoding="utf-8")
            tree_str = tree_bytes.decode("utf-8")
            lines = tree_str.split("\n")

            if lines:
                f.write(lines[0].encode("utf-8") + b"\n")
                f.write(b"<!-- GML au format RecoStarElec v1.0. -->\n")
                for line in lines[1:]:
                    f.write(line.encode("utf-8") + b"\n")

        print(f"Fichier GML généré: {output_path}")

    def generer_gml(self, features_by_type: Dict[str, List], output_path: Path):
        """Génère le fichier GML à partir des entités"""

        for prefix, uri in NS_MAP.items():
            ET.register_namespace(prefix, uri)

        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        root.set(
            f"{{{NAMESPACE_XSI}}}schemaLocation",
            f"{NAMESPACE_RECOSTAR} https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/RecoStar-v1.0/RecoStaR/SchemaStarElecRecoStar.xsd",
        )

        # Dispatch O(1) des types vers les fonctions de mappage
        type_mappers = {
            "RPD_Aerien_Reco": self.mapper.mapper_aerien,
            "RPD_CableElectrique_Reco": self.mapper.mapper_cable_electrique,
            "RPD_CableTerre_Reco": self.mapper.mapper_cable_terre,
            "RPD_Coffret_Reco": self.mapper.mapper_coffret,
            "RPD_CoupeCircuitAFusibles_Reco": self.mapper.mapper_coupe_circuit_a_fusibles,
            "RPD_EnceinteCloturee_Reco": self.mapper.mapper_enceinte_cloturee,
            "RPD_Fourreau_Reco": self.mapper.mapper_fourreau,
            "RPD_GeometrieSupplementaire_Reco": self.mapper.mapper_geometrie_supplementaire,
            "RPD_JeuBarres_Reco": self.mapper.mapper_jeu_barres,
            "RPD_Jonction_Reco": self.mapper.mapper_jonction,
            "RPD_OuvrageCollectifBranchement_Reco": self.mapper.mapper_ouvrage_collectif_branchement,
            "RPD_PointDeComptage_Reco": self.mapper.mapper_point_comptage,
            "RPD_PointLeveOuvrageReseau_Reco": self.mapper.mapper_point_leve,
            "RPD_Materiel_Reco": self.mapper.mapper_materiel,
            "RPD_PleineTerre_Reco": self.mapper.mapper_pleine_terre,
            "RPD_Support_Reco": self.mapper.mapper_support,
            "RPD_SupportModules_Reco": self.mapper.mapper_support_modules,
            "RPD_BatimentTechnique_Reco": self.mapper.mapper_batiment_technique,
            "RPD_PosteElectrique_Reco": self.mapper.mapper_poste_electrique,
            "RPD_ProtectionMecanique_Reco": self.mapper.mapper_protection_mecanique,
            "RPD_Terre_Reco": self.mapper.mapper_terre,
        }

        self._fusionner_materiels(features_by_type)

        # Résolution des géométries héritées avant écriture
        cache_conteneurs = self._construire_cache_conteneurs(features_by_type)
        self._enrichir_geometries_depuis_conteneurs(features_by_type, cache_conteneurs)

        self._ajouter_relations(root, features_by_type)
        self._ajouter_membres_entites(root, features_by_type, type_mappers)
        self._ecrire_fichier_gml(root, output_path)


def main():
    """Point d'entrée principal du script"""
    parser = argparse.ArgumentParser(
        description="Convertit des fichiers GeoJSON RPD_* en GML RecoStaR conforme au XSD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "input_dir", type=Path, help="Répertoire contenant les fichiers GeoJSON RPD_*"
    )

    parser.add_argument("output_file", type=Path, help="Fichier GML de sortie")

    parser.add_argument(
        "--logiciel", default="LAZio", help="Logiciel utilisé pour la génération"
    )

    parser.add_argument("--producteur", default="TEST", help="Producteur du récolement")

    parser.add_argument(
        "--responsable", default="TEST", help="Responsable du récolement"
    )

    parser.add_argument("--nom", default="TEST", help="Nom du réseau")

    parser.add_argument(
        "--srs",
        default=None,
        help="Forcer le CRS (ex: EPSG:2154). Si absent, le CRS est détecté depuis les GeoJSON.",
    )

    args = parser.parse_args()

    # Validation du répertoire d'entrée
    if not args.input_dir.exists():
        print(f"Erreur: Le répertoire {args.input_dir} n'existe pas", file=sys.stderr)
        sys.exit(1)

    if not args.input_dir.is_dir():
        print(f"Erreur: {args.input_dir} n'est pas un répertoire", file=sys.stderr)
        sys.exit(1)

    # Chargement des fichiers GeoJSON (avec détection CRS)
    generator = GenerateurGML()
    print(f"Chargement des fichiers GeoJSON depuis {args.input_dir}...")
    features, crs_detecte = generator.charger_fichiers_geojson(args.input_dir)

    if not features:
        print("Aucun fichier GeoJSON RPD_* trouvé", file=sys.stderr)
        sys.exit(1)

    # Résolution du CRS : override CLI > détection GeoJSON > défaut
    if args.srs:
        srs_final = args.srs
        print(f"CRS forcé par l'utilisateur : {srs_final}")
    elif crs_detecte:
        srs_final = crs_detecte
        print(f"CRS détecté depuis les fichiers GeoJSON : {srs_final}")
    else:
        srs_final = DEFAULT_SRS
        print(f"Aucun CRS détecté, utilisation du défaut : {srs_final}")

    # Recréation du générateur avec le CRS résolu
    generator = GenerateurGML(srs_final)
    generator.definir_metadonnees(
        logiciel=args.logiciel,
        producteur=args.producteur,
        responsable=args.responsable,
        nom=args.nom,
        srs=srs_final,
    )

    print(f"Fichiers chargés: {', '.join(features.keys())}")

    # Génération du GML
    print("Génération du fichier GML...")
    generator.generer_gml(features, args.output_file)

    print("Conversion terminée avec succès!")


if __name__ == "__main__":
    main()
