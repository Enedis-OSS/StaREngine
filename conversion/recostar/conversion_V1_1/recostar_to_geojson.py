#!/usr/bin/env python3
"""
Convertit un fichier GML RecoStaR vers plusieurs fichiers GeoJSON (un par type d'entité).
Opération inverse de geojson_to_gml.py.

Entrée : Fichier GML RecoStaR unique
Sortie : Dossier contenant RPD_*.geojson (un fichier par type)

Fonctionnalités :
- Héritage de géométries : les nœuds héritent des conteneurs, les câbles des cheminements
- Extraction des relations (cable-noeud, cheminement-cable, ouvrage-materiel)
- Traitement en 4 passes pour gérer les dépendances

"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import defusedxml.ElementTree as DefusedET  # type: ignore
from functools import lru_cache
from itertools import islice

# Namespaces GML/RecoStaR
NAMESPACE_GML = "http://www.opengis.net/gml/3.2"
NAMESPACE_RECOSTAR = "http://StaR-Elec.com"
NAMESPACE_XLINK = "http://www.w3.org/1999/xlink"
NAMESPACE_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# URLs de schéma pour détection de version
SCHEMA_URL_V1_0 = "https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/RecoStar-v1.0/RecoStaR/SchemaStarElecRecoStar.xsd"
SCHEMA_URL_V1_10 = "https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/RecoStar-v1.1/RecoStaR/SchemaStarElecRecoStar.xsd"

# Versions supportées
VERSION_V1_0 = "V1.0"
VERSION_V1_10 = "V1.10"

# Constants for geometry types
GEOMETRY_LIGNE_2_5D = "Ligne2.5D"

# Types d'entités RPD supportés (frozenset (par expérience cela améliore vraiment les performances) pour lookups O(1))
RPD_ENTITY_TYPES = frozenset(
    [
        "RPD_Aerien_Reco",
        "RPD_CableElectrique_Reco",
        "RPD_CableTelecommunication_Reco",
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
        "RPD_Materiel_Reco",
        "RPD_PleineTerre_Reco",
        "RPD_Support_Reco",
        "RPD_SupportModules_Reco",
        "RPD_BatimentTechnique_Reco",
        "RPD_PosteElectrique_Reco",
        "RPD_ProtectionMecanique_Reco",
        "RPD_Terre_Reco",
    ]
)

# Types de relations RecoStaR
RELATION_TYPES = frozenset(
    ["CableElectrique_NoeudReseau", "Cheminement_Cables", "Ouvrage_Materiel"]
)


class GMLNamespaceHelper:
    """Utilitaire pour gérer les namespaces GML/RecoStaR avec cache"""

    __slots__ = ("ns_map",)

    def __init__(self):
        self.ns_map = {
            "gml": NAMESPACE_GML,
            "RecoStaR": NAMESPACE_RECOSTAR,
            "xlink": NAMESPACE_XLINK,
        }

    @lru_cache(maxsize=64)
    def tag(self, namespace: str, element: str) -> str:
        """Génère un tag qualifié : {http://namespace}element (résultat en cache)"""
        return f"{{{self.ns_map[namespace]}}}{element}"

    def strip_namespace(self, tag: str) -> str:
        """Enlève le namespace d'un tag : {http://...}Element → Element"""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag


class GeometryParser:
    """Parse les géométries GML (Point, LineString, Polygon) vers GeoJSON"""

    __slots__ = ("ns_helper",)

    def __init__(self, ns_helper: GMLNamespaceHelper):
        self.ns_helper = ns_helper

    def _parse_pos_list(self, pos_list_elem: ET.Element) -> List[List[float]]:
        """Parse gml:posList en liste de coordonnées GeoJSON

        Exemple : "x1 y1 z1 x2 y2 z2" → [[x1, y1, z1], [x2, y2, z2]]
        """
        text = pos_list_elem.text
        if not text:
            return []

        coords_flat = text.split()

        # Dimension 2D ou 3D (défaut 3)
        dim_attr = pos_list_elem.get("srsDimension")
        dim = int(dim_attr) if dim_attr else 3

        num_coords = len(coords_flat)
        result = []

        # Découper en points selon la dimension
        for i in range(0, num_coords, dim):
            point = [float(coords_flat[j]) for j in range(i, min(i + dim, num_coords))]
            result.append(point)

        return result

    def _parse_pos(self, pos_elem: ET.Element) -> List[float]:
        """Parse gml:pos en coordonnées : "x y z" → [x, y, z]"""
        text = pos_elem.text
        if not text:
            return []
        return list(map(float, text.split()))

    def parse_point(self, point_elem: ET.Element) -> Optional[Dict]:
        """gml:Point → GeoJSON Point"""
        pos_elem = point_elem.find(self.ns_helper.tag("gml", "pos"))
        if pos_elem is not None:
            coords = self._parse_pos(pos_elem)
            return {"type": "Point", "coordinates": coords}
        return None

    def parse_linestring(self, linestring_elem: ET.Element) -> Optional[Dict]:
        """gml:LineString → GeoJSON LineString"""
        pos_list_elem = linestring_elem.find(self.ns_helper.tag("gml", "posList"))
        if pos_list_elem is not None:
            coords = self._parse_pos_list(pos_list_elem)
            return {"type": "LineString", "coordinates": coords}
        return None

    def parse_polygon(self, polygon_elem: ET.Element) -> Optional[Dict]:
        """gml:Polygon → GeoJSON Polygon"""
        exterior_elem = polygon_elem.find(self.ns_helper.tag("gml", "exterior"))
        if exterior_elem is None:
            return None

        linear_ring = exterior_elem.find(self.ns_helper.tag("gml", "LinearRing"))
        if linear_ring is None:
            return None

        pos_list_elem = linear_ring.find(self.ns_helper.tag("gml", "posList"))
        if pos_list_elem is not None:
            coords = self._parse_pos_list(pos_list_elem)
            return {
                "type": "Polygon",
                "coordinates": [coords],  # Exterior ring uniquement
            }
        return None

    def parse_geometry(self, geom_elem: ET.Element) -> Optional[Dict]:
        """Parse n'importe quelle géométrie GML enfant"""
        for child in geom_elem:
            tag = self.ns_helper.strip_namespace(child.tag)

            if tag == "Point":
                return self.parse_point(child)
            elif tag == "LineString":
                return self.parse_linestring(child)
            elif tag == "Polygon":
                return self.parse_polygon(child)

        return None


class EntityExtractor:
    """Extrait les entités RPD_* du GML avec gestion de l'héritage de géométries

    Caches :
    - conteneur_geometries : Géométries des Coffret/Support/BatimentTechnique
    - cheminement_geometries : Géométries des Fourreau/PleineTerre/ProtectionMecanique

    Les nœuds sans géométrie (Jonction, PosteElectrique...) héritent des conteneurs.
    Les câbles sans géométrie héritent des cheminements.
    """

    __slots__ = (
        "ns_helper",
        "geom_parser",
        "relations",
        "counter",
        "conteneur_geometries",
        "cheminement_geometries",
        "schema_version",
    )

    def __init__(self, ns_helper: GMLNamespaceHelper):
        self.ns_helper = ns_helper
        self.geom_parser = GeometryParser(ns_helper)
        self.relations = {
            "cable_noeud": {},  # noeud_id → [cable_ids]
            "cable_noeud_etat": {},  # "noeud_id_cable_id" → EtatAvantRaccordement
            "cheminement_cable": {},  # cheminement_id → cable_id
            "cable_cheminement": {},  # cable_id → [cheminement_ids] (mapping 1-to-N)
            "ouvrage_materiel": {},  # ouvrage_id → materiel_id
        }
        self.counter = {}  # Compteur par type pour générer fid
        self.conteneur_geometries = {}  # Cache : conteneur_id → geometry
        self.cheminement_geometries = {}  # Cache : cheminement_id → geometry
        self.schema_version = VERSION_V1_10  # Version par défaut

    def _get_text(self, elem: ET.Element, child_name: str) -> Optional[str]:
        """Récupère le texte d'un élément enfant (balise simple)"""
        child = elem.find(self.ns_helper.tag("RecoStaR", child_name))
        if child is not None and child.text:
            return child.text.strip()
        return None

    def _get_href(self, elem: ET.Element, child_name: str) -> Optional[str]:
        """Récupère l'attribut xlink:href d'un élément enfant (référence)"""
        child = elem.find(self.ns_helper.tag("RecoStaR", child_name))
        if child is not None:
            return child.get(self.ns_helper.tag("xlink", "href"))
        return None

    def _get_measure(
        self, elem: ET.Element, child_name: str
    ) -> Tuple[Optional[float], Optional[str]]:
        """Récupère une mesure avec son unité (uom) : (valeur, unité)"""
        child = elem.find(self.ns_helper.tag("RecoStaR", child_name))
        if child is not None:
            value = float(child.text) if child.text else None
            uom = child.get("uom")
            return value, uom
        return None, None

    def _get_fid(self, entity_type: str) -> int:
        """Génère un fid auto-incrémenté unique par type d'entité"""
        if entity_type not in self.counter:
            self.counter[entity_type] = 0
        self.counter[entity_type] += 1
        return self.counter[entity_type]

    def _peupler_cables_href(self, properties: Dict, noeud_id: Optional[str]):
        """Ajoute cables_href et EtatAvantRaccordement aux propriétés d'un nœud.

        Factorise la logique commune à tous les extracteurs de NoeudReseau.
        """
        if not noeud_id:
            return
        cables = self.relations.get("cable_noeud", {}).get(noeud_id, [])
        if not cables:
            return
        properties["cables_href"] = ",".join(cables)

        # EtatAvantRaccordement par câble (ordre correspondant à cables_href)
        cable_noeud_etat = self.relations.get("cable_noeud_etat", {})
        etats = [cable_noeud_etat.get(f"{noeud_id}_{cid}", "") for cid in cables]
        if any(etats):
            properties["EtatAvantRaccordement"] = ",".join(etats)

    def _assembler_geometries_cheminements(
        self, cable_id: Optional[str]
    ) -> Optional[Dict]:
        """Assemble les géométries de tous les cheminements liés à un câble.

        - 0 cheminement avec géométrie → None
        - 1 cheminement avec géométrie → LineString
        - N cheminements avec géométrie → MultiLineString
        """
        if not cable_id or cable_id not in self.relations["cable_cheminement"]:
            return None

        cheminement_ids = self.relations["cable_cheminement"][cable_id]
        geom_cache = self.cheminement_geometries

        # Collecter les coordonnées de chaque cheminement ayant une géométrie
        all_coords = [
            geom_cache[cid]["coordinates"]
            for cid in cheminement_ids
            if cid in geom_cache
        ]

        if not all_coords:
            return None
        if len(all_coords) == 1:
            return {"type": "LineString", "coordinates": all_coords[0]}
        return {"type": "MultiLineString", "coordinates": all_coords}

    def extract_cable_electrique(self, elem: ET.Element) -> Dict:
        """RPD_CableElectrique_Reco → GeoJSON feature

        La géométrie est héritée du cheminement lié via la relation Cheminement_Cables.
        """
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_CableElectrique_Reco"),
            "ogr_pkid": f"RPD_CableElectrique_Reco_{self.counter['RPD_CableElectrique_Reco'] - 1}",
            "id": gml_id,
            "DomaineTension": self._get_text(elem, "DomaineTension"),
            "Etiquette": self._get_text(elem, "Etiquette"),
            "FonctionCable_href": self._get_href(elem, "FonctionCable"),
            "HierarchieBT": self._get_text(elem, "HierarchieBT"),
            "Isolant": self._get_text(elem, "Isolant"),
            "Materiau": self._get_text(elem, "Materiau"),
            "Statut": self._get_text(elem, "Statut"),
            "Commentaire": self._get_text(elem, "Commentaire"),
        }

        nb_cond = self._get_text(elem, "NombreConducteurs")
        if nb_cond:
            properties["NombreConducteurs"] = int(nb_cond)

        section, section_uom = self._get_measure(elem, "Section")
        if section is not None:
            properties["Section"] = section
            properties["Section_uom"] = section_uom

        section_n, section_n_uom = self._get_measure(elem, "SectionNeutre")
        if section_n is not None:
            properties["SectionNeutre"] = section_n
            properties["SectionNeutre_uom"] = section_n_uom

        # Héritage de géométrie : assembler les géométries de tous les cheminements liés
        geometry = self._assembler_geometries_cheminements(gml_id)

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_cable_terre(self, elem: ET.Element) -> Dict:
        """Extrait RPD_CableTerre_Reco - NOUVEAU"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_CableTerre_Reco"),
            "ogr_pkid": f"RPD_CableTerre_Reco_{self.counter['RPD_CableTerre_Reco'] - 1}",
            "id": gml_id,
            "FonctionCable_href": self._get_href(elem, "FonctionCable"),
            "Materiau": self._get_text(elem, "Materiau"),
            "NatureCableTerre_href": self._get_href(elem, "NatureCableTerre"),
            "noeudreseau_href": self._get_href(elem, "noeudReseau"),
            "Statut": self._get_text(elem, "Statut"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "TypePose": self._get_text(elem, "TypePose"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # Section avec UOM
        section, section_uom = self._get_measure(elem, "Section")
        if section is not None:
            properties["Section"] = section
            properties["Section_uom"] = section_uom

        # Héritage de géométrie : assembler les géométries de tous les cheminements liés
        geometry = self._assembler_geometries_cheminements(gml_id)

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_cable_telecommunication(self, elem: ET.Element) -> Dict:
        """Extrait RPD_CableTelecommunication_Reco

        La géométrie est héritée du cheminement lié via la relation Cheminement_Cables.
        """
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_CableTelecommunication_Reco"),
            "ogr_pkid": f"RPD_CableTelecommunication_Reco_{self.counter['RPD_CableTelecommunication_Reco'] - 1}",
            "id": gml_id,
            "Fonction": self._get_text(elem, "Fonction"),
            "Statut": self._get_text(elem, "Statut"),
            "TechnoCable_href": self._get_href(elem, "TechnoCable"),
            "Commentaire": self._get_text(elem, "Commentaire"),
        }

        # Capacite (optionnel, entier)
        capacite = self._get_text(elem, "Capacite")
        if capacite is not None:
            properties["Capacite"] = int(capacite)

        # Section avec UOM (optionnel)
        section, section_uom = self._get_measure(elem, "Section")
        if section is not None:
            properties["Section"] = section
            properties["Section_uom"] = section_uom

        # Héritage de géométrie : assembler les géométries de tous les cheminements liés
        geometry = self._assembler_geometries_cheminements(gml_id)

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_coffret(self, elem: ET.Element) -> Dict:
        """Extrait RPD_Coffret_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        # Statut : lecture GML ou valeur par défaut si V1.0
        statut = self._get_text(elem, "Statut")
        if statut is None and self.schema_version == VERSION_V1_0:
            statut = "UnderCommissionning"

        properties = {
            "fid": self._get_fid("RPD_Coffret_Reco"),
            "ogr_pkid": f"RPD_Coffret_Reco_{self.counter['RPD_Coffret_Reco'] - 1}",
            "id": gml_id,
            "TypeCoffret_href": self._get_href(elem, "TypeCoffret"),
            "FonctionCoffret_href": self._get_href(elem, "FonctionCoffret"),
            "ImplantationArmoire_href": self._get_href(elem, "ImplantationArmoire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
            "Statut": statut,
            "Commentaire": self._get_text(elem, "Commentaire"),
            "geometriesupplementaire_href": self._get_href(
                elem, "geometriesupplementaire"
            ),
        }

        # Géométrie Point
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker la géométrie pour héritage par les nœuds
        if geometry and gml_id:
            self.conteneur_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_coupe_circuit_a_fusibles(self, elem: ET.Element) -> Dict:
        """Extrait RPD_CoupeCircuitAFusibles_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_CoupeCircuitAFusibles_Reco"),
            "ogr_pkid": f"RPD_CoupeCircuitAFusibles_Reco_{self.counter['RPD_CoupeCircuitAFusibles_Reco'] - 1}",
            "id": gml_id,
            "Statut": self._get_text(elem, "Statut"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # conteneur_href
        conteneur = self._get_href(elem, "conteneur")
        if conteneur:
            properties["conteneur_href"] = conteneur

        # cables_href et EtatAvantRaccordement depuis les relations
        self._peupler_cables_href(properties, gml_id)

        # Géométrie Point (optionnelle si conteneur présent)
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)
        elif conteneur and conteneur in self.conteneur_geometries:
            # Hériter de la géométrie du conteneur si pas de géométrie propre
            geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_fourreau(self, elem: ET.Element) -> Dict:
        """Extrait RPD_Fourreau_Reco et stocke la géométrie pour héritage par les câbles"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_Fourreau_Reco"),
            "ogr_pkid": f"RPD_Fourreau_Reco_line_{self.counter['RPD_Fourreau_Reco'] - 1}",
            "id": gml_id,
            "Materiau": self._get_text(elem, "Materiau"),
            "CoupeType": self._get_text(elem, "CoupeType"),
            "EtatCoupeType": self._get_text(elem, "EtatCoupeType"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # DiametreDuFourreau avec UOM
        diametre, diametre_uom = self._get_measure(elem, "DiametreDuFourreau")
        if diametre is not None:
            properties["DiametreDuFourreau"] = diametre
            properties["DiametreDuFourreau_uom"] = diametre_uom

        # ProfondeurMinNonReg avec UOM
        profondeur, profondeur_uom = self._get_measure(elem, "ProfondeurMinNonReg")
        if profondeur is not None:
            properties["ProfondeurMinNonReg"] = profondeur
            properties["ProfondeurMinNonReg_uom"] = profondeur_uom

        # Référence câbles depuis les relations
        if gml_id in self.relations["cheminement_cable"]:
            properties["cables_href"] = self.relations["cheminement_cable"][gml_id]

        # Géométrie LineString
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker la géométrie pour héritage par les câbles
        if geometry and gml_id:
            self.cheminement_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def _extract_ligne_2_5d(self, ligne_elem: ET.Element) -> str | None:
        """Extrait le texte posList depuis un élément Ligne2.5D (MultiCurve ou LineString)."""
        multicurve = ligne_elem.find(self.ns_helper.tag("gml", "MultiCurve"))
        if multicurve is not None:
            return self._extract_poslist_from_multicurve(multicurve)
        # Ancien format (rétrocompatibilité) : LineString direct
        return self._extract_poslist_from_linestring(ligne_elem)

    def _extract_poslist_from_multicurve(self, multicurve: ET.Element) -> str | None:
        """Extrait le posList depuis MultiCurve > curveMember > LineString."""
        curve_member = multicurve.find(self.ns_helper.tag("gml", "curveMember"))
        if curve_member is None:
            return None
        return self._extract_poslist_from_linestring(curve_member)

    def _extract_poslist_from_linestring(self, parent: ET.Element) -> str | None:
        """Extrait le posList depuis un élément contenant un LineString."""
        linestring = parent.find(self.ns_helper.tag("gml", "LineString"))
        if linestring is None:
            return None
        pos_list = linestring.find(self.ns_helper.tag("gml", "posList"))
        if pos_list is not None and pos_list.text:
            return pos_list.text.strip()
        return None

    def extract_geometrie_supplementaire(self, elem: ET.Element) -> Dict:
        """RPD_GeometrieSupplementaire_Reco → GeoJSON feature

        Ligne2.5D : Stocké comme texte dans properties (coordonnées 3D)
        Surface2.5D : Stocké comme MultiPolygon dans geometry

        Structure XML Ligne2.5D : MultiCurve > curveMember > LineString > posList
        """
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_GeometrieSupplementaire_Reco"),
            "ogr_pkid": f"RPD_Coffret_Reco_geomsupp_{self.counter['RPD_GeometrieSupplementaire_Reco']}",
            "id": gml_id,
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # Ligne2.5D : Extraction depuis MultiCurve > curveMember > LineString > posList
        ligne_elem = elem.find(self.ns_helper.tag("RecoStaR", GEOMETRY_LIGNE_2_5D))
        if ligne_elem is not None:
            ligne_text = self._extract_ligne_2_5d(ligne_elem)
            if ligne_text:
                properties[GEOMETRY_LIGNE_2_5D] = ligne_text

        # Surface2.5D : Extraction comme MultiPolygon dans geometry
        surface_elem = elem.find(self.ns_helper.tag("RecoStaR", "Surface2.5D"))
        geometry = None
        if surface_elem is not None:
            polygon = self.geom_parser.parse_geometry(surface_elem)
            if polygon:
                # Convertir en MultiPolygon pour cohérence avec format d'origine
                geometry = {
                    "type": "MultiPolygon",
                    "coordinates": [polygon["coordinates"]],
                }

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_jonction(self, elem: ET.Element) -> Dict:
        """Extrait RPD_Jonction_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_Jonction_Reco"),
            "ogr_pkid": f"RPD_Jonction_Reco_{self.counter['RPD_Jonction_Reco'] - 1}",
            "id": gml_id,
            "DomaineTension": self._get_text(elem, "DomaineTension"),
            "TypeJonction": self._get_text(elem, "TypeJonction"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
            "Statut": self._get_text(elem, "Statut"),
            "Commentaire": self._get_text(elem, "Commentaire"),
        }

        # Propriétés optionnelles
        # Note: Fabricant, Modele, NumeroLot, NumeroSerie sont extraits depuis
        # l'entité RPD_Materiel_Reco liée (voir injection plus bas)

        angle = self._get_text(elem, "angle")
        if angle:
            properties["angle"] = angle

        # Références depuis les relations
        self._peupler_cables_href(properties, gml_id)

        if gml_id in self.relations["ouvrage_materiel"]:
            properties["materiel_href"] = self.relations["ouvrage_materiel"][gml_id]

        # conteneur_href
        conteneur = self._get_href(elem, "conteneur")
        if conteneur:
            properties["conteneur_href"] = conteneur

        # Géométrie Point
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)
        elif conteneur and conteneur in self.conteneur_geometries:
            # Hériter de la géométrie du conteneur si pas de géométrie propre
            geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_support(self, elem: ET.Element) -> Dict:
        """Extrait RPD_Support_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        # Statut : lecture GML ou valeur par défaut si V1.0
        statut = self._get_text(elem, "Statut")
        if statut is None and self.schema_version == VERSION_V1_0:
            statut = "UnderCommissionning"

        properties = {
            "fid": self._get_fid("RPD_Support_Reco"),
            "ogr_pkid": f"RPD_Support_Reco_{self.counter['RPD_Support_Reco'] - 1}",
            "id": gml_id,
            "NatureSupport_href": self._get_href(elem, "NatureSupport"),
            "Matiere_href": self._get_href(elem, "Matiere"),
            "Classe_href": self._get_href(elem, "Classe"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
            "Statut": statut,
            "Commentaire": self._get_text(elem, "Commentaire"),
            "geometriesupplementaire_href": self._get_href(
                elem, "geometriesupplementaire"
            ),
        }

        # Effort avec UOM (optionnel)
        effort, effort_uom = self._get_measure(elem, "Effort")
        if effort is not None:
            properties["Effort"] = effort
            properties["Effort_uom"] = effort_uom

        # HauteurPoteau avec UOM (optionnel)
        hauteur, hauteur_uom = self._get_measure(elem, "HauteurPoteau")
        if hauteur is not None:
            properties["HauteurPoteau"] = hauteur
            properties["HauteurPoteau_uom"] = hauteur_uom

        # Géométrie Point
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker la géométrie pour héritage par les nœuds
        if geometry and gml_id:
            self.conteneur_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_point_comptage(self, elem: ET.Element) -> Dict:
        """Extrait RPD_PointDeComptage_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_PointDeComptage_Reco"),
            "ogr_pkid": f"RPD_PointDeComptage_Reco_{self.counter['RPD_PointDeComptage_Reco'] - 1}",
            "id": gml_id,
            "Statut": self._get_text(elem, "Statut"),
            "conteneur_href": self._get_href(elem, "conteneur"),
            "NumeroPRM": self._get_text(elem, "NumeroPRM"),  # AJOUT
            "Commentaire": self._get_text(elem, "Commentaire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # cables_href et EtatAvantRaccordement depuis les relations
        self._peupler_cables_href(properties, gml_id)

        # Géométrie Point (héritée du conteneur si absente)
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)
        elif properties.get("conteneur_href"):
            conteneur = properties["conteneur_href"]
            if conteneur in self.conteneur_geometries:
                geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def _extraire_proprietes_plor_communes(self, elem: ET.Element) -> Dict[str, object]:
        """Extrait les propriétés communes à tous les PointLeveOuvrageReseau (V1.0 et V1.10).

        Attributs communs : NumeroPoint, PrecisionXYnum, PrecisionZnum, Producteur.
        """
        properties: Dict[str, object] = {
            "NumeroPoint": self._get_text(elem, "NumeroPoint"),
            "Producteur": self._get_text(elem, "Producteur"),
        }

        precision_xy = self._get_text(elem, "PrecisionXYnum")
        if precision_xy:
            properties["PrecisionXYnum"] = int(precision_xy)

        precision_z = self._get_text(elem, "PrecisionZnum")
        if precision_z:
            properties["PrecisionZnum"] = int(precision_z)

        return properties

    def _extraire_proprietes_plor_v1_10(self, elem: ET.Element, properties: Dict):
        """Extrait les attributs V1.10 spécifiques : ChargeGeneratrice, Horodatage."""
        charge, charge_uom = self._get_measure(elem, "ChargeGeneratrice")
        if charge is not None:
            properties["ChargeGeneratrice"] = charge
            properties["ChargeGeneratrice_uom"] = charge_uom

        horodatage = self._get_text(elem, "Horodatage")
        if horodatage:
            properties["Horodatage"] = horodatage

    def _convertir_leve_v1_0_vers_v1_10(self, elem: ET.Element, properties: Dict):
        """Convertit les attributs Leve/TypeLeve V1.0 vers ChargeGeneratrice V1.10.

        Règle métier : si TypeLeve == "ChargeGeneratrice", la valeur de Leve
        alimente l'attribut ChargeGeneratrice du modèle V1.10.
        Les attributs Leve et TypeLeve ne sont jamais conservés dans la sortie.
        """
        type_leve = self._get_text(elem, "TypeLeve")
        if type_leve != "ChargeGeneratrice":
            return

        leve_elem = elem.find(self.ns_helper.tag("RecoStaR", "Leve"))
        if leve_elem is None or not leve_elem.text:
            return

        try:
            properties["ChargeGeneratrice"] = float(leve_elem.text)
        except ValueError:
            return
        properties["ChargeGeneratrice_uom"] = leve_elem.get("uom", "m")

    def extract_point_leve(self, elem: ET.Element) -> Dict:
        """Extrait RPD_PointLeveOuvrageReseau_Reco selon la version du schéma.

        V1.0 : lit Leve/TypeLeve et normalise vers V1.10 (suppression de ces attributs).
        V1.10 : lit ChargeGeneratrice/Horodatage directement.
        Produit toujours un GeoJSON conforme au modèle V1.10.
        """
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))
        fid = self._get_fid("RPD_PointLeveOuvrageReseau_Reco")

        properties = {
            "fid": fid,
            "ogr_pkid": f"RPD_PointLeveOuvrageReseau_Reco_{fid - 1}",
            "id": gml_id,
        }

        # Propriétés communes V1.0 et V1.10
        properties.update(self._extraire_proprietes_plor_communes(elem))

        if self.schema_version == VERSION_V1_0:
            # V1.0 → V1.10 : transformer Leve/TypeLeve en ChargeGeneratrice si applicable
            self._convertir_leve_v1_0_vers_v1_10(elem, properties)
        else:
            # V1.10 : extraction des nouveaux attributs
            self._extraire_proprietes_plor_v1_10(elem, properties)

        # Géométrie Point
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_materiel(self, elem: ET.Element) -> Dict:
        """Extrait RPD_Materiel_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_Materiel_Reco"),
            "ogr_pkid": f"RPD_Materiel_Reco_{self.counter['RPD_Materiel_Reco'] - 1}",
            "id": gml_id,
            "Fabricant": self._get_text(elem, "Fabricant"),
            "Modele": self._get_text(elem, "Modele"),
            "NumeroLot": self._get_text(elem, "NumeroLot"),
            "NumeroSerie": self._get_text(elem, "NumeroSerie"),
        }

        return {
            "type": "Feature",
            "properties": properties,
            "geometry": None,  # Pas de géométrie pour matériel
        }

    def extract_pleine_terre(self, elem: ET.Element) -> Dict:
        """Extrait RPD_PleineTerre_Reco et stocke la géométrie pour héritage par les câbles"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_PleineTerre_Reco"),
            "ogr_pkid": f"RPD_PleineTerre_Reco_virt_{self.counter['RPD_PleineTerre_Reco'] - 1}",
            "id": gml_id,
            "CoupeType": self._get_text(elem, "CoupeType"),  # AJOUT
            "EtatCoupeType": self._get_text(elem, "EtatCoupeType"),  # AJOUT
            "Commentaire": self._get_text(elem, "Commentaire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # ProfondeurMinNonReg avec UOM - AJOUT
        profondeur, profondeur_uom = self._get_measure(elem, "ProfondeurMinNonReg")
        if profondeur is not None:
            properties["ProfondeurMinNonReg"] = profondeur
            properties["ProfondeurMinNonReg_uom"] = profondeur_uom

        # Référence câbles depuis les relations
        if gml_id in self.relations["cheminement_cable"]:
            properties["cables_href"] = self.relations["cheminement_cable"][gml_id]

        # Géométrie LineString
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker la géométrie pour héritage par les câbles
        if geometry and gml_id:
            self.cheminement_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_batiment_technique(self, elem: ET.Element) -> Dict:
        """Extrait RPD_BatimentTechnique_Reco - NOUVEAU"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        # Statut : lecture GML ou valeur par défaut si V1.0
        statut = self._get_text(elem, "Statut")
        if statut is None and self.schema_version == VERSION_V1_0:
            statut = "UnderCommissionning"

        properties = {
            "fid": self._get_fid("RPD_BatimentTechnique_Reco"),
            "ogr_pkid": f"RPD_BatimentTechnique_Reco_{self.counter['RPD_BatimentTechnique_Reco'] - 1}",
            "id": gml_id,
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
            "Statut": statut,
            "Commentaire": self._get_text(elem, "Commentaire"),
            "geometriesupplementaire_href": self._get_href(
                elem, "geometriesupplementaire"
            ),
        }

        # Géométrie Point
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker pour héritage par nœuds
        if geometry and gml_id:
            self.conteneur_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_enceinte_cloturee(self, elem: ET.Element) -> Dict:
        """Extrait RPD_EnceinteCloturee_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        # Statut : lecture GML ou valeur par défaut si V1.0
        statut = self._get_text(elem, "Statut")
        if statut is None and self.schema_version == VERSION_V1_0:
            statut = "UnderCommissionning"

        properties = {
            "fid": self._get_fid("RPD_EnceinteCloturee_Reco"),
            "ogr_pkid": f"RPD_EnceinteCloturee_Reco_{self.counter['RPD_EnceinteCloturee_Reco'] - 1}",
            "id": gml_id,
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
            "Statut": statut,
            "Commentaire": self._get_text(elem, "Commentaire"),
            "geometriesupplementaire_href": self._get_href(
                elem, "geometriesupplementaire"
            ),
        }

        # Géométrie Point
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker pour héritage par nœuds
        if geometry and gml_id:
            self.conteneur_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_poste_electrique(self, elem: ET.Element) -> Dict:
        """Extrait RPD_PosteElectrique_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_PosteElectrique_Reco"),
            "ogr_pkid": f"RPD_PosteElectrique_Reco_{self.counter['RPD_PosteElectrique_Reco'] - 1}",
            "id": gml_id,
            "Categorie_href": self._get_href(elem, "Categorie"),
            "Code": self._get_text(elem, "Code"),
            "conteneur_href": self._get_href(elem, "conteneur"),
            "InformationSupplementaire": self._get_text(
                elem, "InformationSupplementaire"
            ),
            "Statut": self._get_text(elem, "Statut"),
            "TypePoste_href": self._get_href(elem, "TypePoste"),
            "Commentaire": self._get_text(elem, "Commentaire"),
        }
        # NOTE: PrecisionXY et PrecisionZ n'existent PAS dans RPD_PosteElectrique_RecoType XSD

        # cables_href et EtatAvantRaccordement depuis les relations
        self._peupler_cables_href(properties, gml_id)

        # Géométrie héritée du conteneur (PosteElectrique n'a pas de géométrie propre dans XSD)
        geometry = None
        conteneur = properties.get("conteneur_href")
        if conteneur and conteneur in self.conteneur_geometries:
            geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_aerien(self, elem: ET.Element) -> Dict:
        """Extrait RPD_Aerien_Reco et stocke la géométrie pour héritage par les câbles"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_Aerien_Reco"),
            "ogr_pkid": f"RPD_Aerien_Reco_virt_{self.counter['RPD_Aerien_Reco'] - 1}",
            "id": gml_id,
            "ModePose": self._get_text(elem, "ModePose"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # Référence câbles depuis les relations
        if gml_id in self.relations["cheminement_cable"]:
            properties["cables_href"] = self.relations["cheminement_cable"][gml_id]

        # Géométrie LineString
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker la géométrie pour héritage par les câbles
        if geometry and gml_id:
            self.cheminement_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_protection_mecanique(self, elem: ET.Element) -> Dict:
        """Extrait RPD_ProtectionMecanique_Reco - NOUVEAU"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_ProtectionMecanique_Reco"),
            "ogr_pkid": f"RPD_ProtectionMecanique_Reco_{self.counter['RPD_ProtectionMecanique_Reco'] - 1}",
            "id": gml_id,
            "CoupeType": self._get_text(elem, "CoupeType"),
            "EtatCoupeType": self._get_text(elem, "EtatCoupeType"),
            "Materiau": self._get_text(elem, "Materiau"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
        }

        # ProfondeurMinNonReg avec UOM
        profondeur, profondeur_uom = self._get_measure(elem, "ProfondeurMinNonReg")
        if profondeur is not None:
            properties["ProfondeurMinNonReg"] = profondeur
            properties["ProfondeurMinNonReg_uom"] = profondeur_uom

        # Référence câbles depuis les relations
        if gml_id in self.relations["cheminement_cable"]:
            properties["cables_href"] = self.relations["cheminement_cable"][gml_id]

        # Géométrie LineString
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)

        # Stocker la géométrie pour héritage
        if geometry and gml_id:
            self.cheminement_geometries[gml_id] = geometry

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_jeu_barres(self, elem: ET.Element) -> Dict:
        """Extrait RPD_JeuBarres_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_JeuBarres_Reco"),
            "ogr_pkid": f"RPD_JeuBarres_Reco_{self.counter['RPD_JeuBarres_Reco'] - 1}",
            "id": gml_id,
            "conteneur_href": self._get_href(elem, "conteneur"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "Statut": self._get_text(elem, "Statut"),
        }

        # cables_href et EtatAvantRaccordement depuis les relations
        self._peupler_cables_href(properties, gml_id)

        # Géométrie héritée du conteneur
        geometry = None
        conteneur = properties.get("conteneur_href")
        if conteneur and conteneur in self.conteneur_geometries:
            geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_support_modules(self, elem: ET.Element) -> Dict:
        """Extrait RPD_SupportModules_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_SupportModules_Reco"),
            "ogr_pkid": f"RPD_SupportModules_Reco_{self.counter['RPD_SupportModules_Reco'] - 1}",
            "id": gml_id,
            "conteneur_href": self._get_href(elem, "conteneur"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "Statut": self._get_text(elem, "Statut"),
        }

        # cables_href et EtatAvantRaccordement depuis les relations
        self._peupler_cables_href(properties, gml_id)

        # Géométrie héritée du conteneur
        geometry = None
        conteneur = properties.get("conteneur_href")
        if conteneur and conteneur in self.conteneur_geometries:
            geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_terre(self, elem: ET.Element) -> Dict:
        """Extrait RPD_Terre_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_Terre_Reco"),
            "ogr_pkid": f"RPD_Terre_Reco_{self.counter['RPD_Terre_Reco'] - 1}",
            "id": gml_id,
            "conteneur_href": self._get_href(elem, "conteneur"),
            "NatureTerre_href": self._get_href(elem, "NatureTerre"),
            "Resistance": self._get_text(elem, "Resistance"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "Statut": self._get_text(elem, "Statut"),
        }

        # cables_href et EtatAvantRaccordement depuis les relations
        self._peupler_cables_href(properties, gml_id)

        # Géométrie héritée du conteneur
        geometry = None
        conteneur = properties.get("conteneur_href")
        if conteneur and conteneur in self.conteneur_geometries:
            geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def extract_ouvrage_collectif_branchement(self, elem: ET.Element) -> Dict:
        """Extrait RPD_OuvrageCollectifBranchement_Reco"""
        gml_id = elem.get(self.ns_helper.tag("gml", "id"))

        properties = {
            "fid": self._get_fid("RPD_OuvrageCollectifBranchement_Reco"),
            "ogr_pkid": f"RPD_OuvrageCollectifBranchement_Reco_{self.counter['RPD_OuvrageCollectifBranchement_Reco'] - 1}",
            "id": gml_id,
            "conteneur_href": self._get_href(elem, "conteneur"),
            "Commentaire": self._get_text(elem, "Commentaire"),
            "PrecisionXY": self._get_text(elem, "PrecisionXY"),
            "PrecisionZ": self._get_text(elem, "PrecisionZ"),
            "Statut": self._get_text(elem, "Statut"),
        }

        # cables_href et EtatAvantRaccordement depuis les relations
        self._peupler_cables_href(properties, gml_id)

        # Géométrie Point (optionnelle si conteneur présent)
        geom_elem = elem.find(self.ns_helper.tag("RecoStaR", "Geometrie"))
        geometry = None
        if geom_elem is not None:
            geometry = self.geom_parser.parse_geometry(geom_elem)
        elif properties.get("conteneur_href"):
            # Hériter du conteneur si pas de géométrie propre
            conteneur = properties["conteneur_href"]
            if conteneur in self.conteneur_geometries:
                geometry = self.conteneur_geometries[conteneur]

        return {"type": "Feature", "properties": properties, "geometry": geometry}


class GMLConverter:
    """Convertisseur GML vers GeoJSON avec optimisations"""

    __slots__ = ("ns_helper", "extractor", "srs", "metadata_info")

    def __init__(self):
        self.ns_helper = GMLNamespaceHelper()
        self.extractor = EntityExtractor(self.ns_helper)
        self.srs = "EPSG:2154"
        self.metadata_info: Dict = {}

    def _detecter_version_schema(self, root: ET.Element) -> str:
        """Détecte la version du schéma RecoStaR depuis xsi:schemaLocation.

        Analyse l'attribut xsi:schemaLocation de l'élément racine pour
        déterminer si les données sont en V1.0 ou V1.10.
        Retourne VERSION_V1_10 par défaut si non détectable.
        """
        schema_location = root.get(f"{{{NAMESPACE_XSI}}}schemaLocation", "")

        if SCHEMA_URL_V1_0 in schema_location:
            return VERSION_V1_0
        if SCHEMA_URL_V1_10 in schema_location:
            return VERSION_V1_10

        # Fallback : recherche partielle dans l'URL
        if "RecoStar-v1.0" in schema_location:
            return VERSION_V1_0
        if "RecoStar-v1.1" in schema_location:
            return VERSION_V1_10

        return VERSION_V1_10

    def _extraire_metadonnees_completes(self, root: ET.Element) -> Dict:
        """Extrait les métadonnées et informations réseau du GML.

        Récupère les éléments Metadata et ReseauUtilite pour conservation
        dans le fichier _metadata.json (round-trip GML→GeoJSON→GML).
        """
        info: Dict = {}
        tag = self.ns_helper.tag

        # Extraction de l'élément Metadata
        metadata_elem = root.find(f".//{tag('RecoStaR', 'Metadata')}")
        if metadata_elem is not None:
            info["Metadata"] = self._extraire_champs_metadata(metadata_elem)

        # Extraction de l'élément ReseauUtilite
        reseau_elem = root.find(f".//{tag('RecoStaR', 'ReseauUtilite')}")
        if reseau_elem is not None:
            info["ReseauUtilite"] = self._extraire_champs_reseau(reseau_elem)

        return info

    def _extraire_champs_metadata(self, elem: ET.Element) -> Dict:
        """Extrait les 6 champs de l'élément Metadata."""
        tag = self.ns_helper.tag
        champs = (
            "Datecreation",
            "Logiciel",
            "Producteur",
            "Responsable",
            "SRS",
            "VersionSpecification",
        )
        resultat = {}
        for champ in champs:
            sub = elem.find(tag("RecoStaR", champ))
            if sub is not None and sub.text:
                resultat[champ] = sub.text.strip()
        return resultat

    def _extraire_champs_reseau(self, elem: ET.Element) -> Dict:
        """Extrait les champs de l'élément ReseauUtilite."""
        tag = self.ns_helper.tag
        resultat = {}

        # Récupérer le gml:id
        gml_id = elem.get(tag("gml", "id"))
        if gml_id:
            resultat["id"] = gml_id

        champs = ("Mention", "Nom", "Responsable", "Theme")
        for champ in champs:
            sub = elem.find(tag("RecoStaR", champ))
            if sub is not None and sub.text:
                resultat[champ] = sub.text.strip()
        return resultat

    def _store_cable_noeud(self, child: ET.Element, get_href):
        """Enregistre une relation CableElectrique_NoeudReseau."""
        cable_id = get_href(child, "cableelectrique")
        noeud_id = get_href(child, "noeudreseau")
        if not (cable_id and noeud_id):
            return
        if noeud_id not in self.extractor.relations["cable_noeud"]:
            self.extractor.relations["cable_noeud"][noeud_id] = []
        self.extractor.relations["cable_noeud"][noeud_id].append(cable_id)

        # EtatAvantRaccordement (optionnel, V1.1)
        etat = self.extractor._get_text(child, "EtatAvantRaccordement")
        if etat:
            self.extractor.relations["cable_noeud_etat"][
                f"{noeud_id}_{cable_id}"
            ] = etat

    def _store_cheminement_cable(self, child: ET.Element, get_href):
        """Enregistre une relation Cheminement_Cables (1 câble → N cheminements)."""
        cable_id = get_href(child, "cables")
        chemin_id = get_href(child, "cheminement")
        if not (cable_id and chemin_id):
            return
        self.extractor.relations["cheminement_cable"][chemin_id] = cable_id
        # Mapping 1-to-N : un câble peut traverser plusieurs cheminements
        if cable_id not in self.extractor.relations["cable_cheminement"]:
            self.extractor.relations["cable_cheminement"][cable_id] = []
        self.extractor.relations["cable_cheminement"][cable_id].append(chemin_id)

    def _store_ouvrage_materiel(self, child: ET.Element, get_href):
        """Enregistre une relation Ouvrage_Materiel."""
        ouvrage_id = get_href(child, "ouvrage")
        materiel_id = get_href(child, "materiel")
        if ouvrage_id and materiel_id:
            self.extractor.relations["ouvrage_materiel"][ouvrage_id] = materiel_id

    def _extract_relations(self, root: ET.Element):
        """Extrait toutes les relations en premier passage avec mapping inverse"""
        get_href = self.extractor._get_href
        strip_ns = self.ns_helper.strip_namespace

        relation_handlers = {
            "CableElectrique_NoeudReseau": self._store_cable_noeud,
            "Cheminement_Cables": self._store_cheminement_cable,
            "Ouvrage_Materiel": self._store_ouvrage_materiel,
        }

        for member in root.findall(self.ns_helper.tag("gml", "featureMember")):
            for child in member:
                handler = relation_handlers.get(strip_ns(child.tag))
                if handler:
                    handler(child, get_href)

    def _collecter_ids_cables_terre(
        self, features_by_type: Dict[str, List[Dict]]
    ) -> set:
        """Collecte les identifiants des câbles de terre pour filtrage ultérieur."""
        return {
            feat.get("properties", {}).get("id")
            for feat in features_by_type.get("RPD_CableTerre_Reco", [])
            if feat.get("properties", {}).get("id")
        }

    def _regrouper_noeuds_par_conteneur(
        self,
        features_by_type: Dict[str, List[Dict]],
        noeud_types: Tuple[str, ...],
    ) -> Dict[str, List[Tuple[str, Dict]]]:
        """Regroupe les nœuds par conteneur_href.

        Retourne un dictionnaire {conteneur_id: [(type_entite, properties)]}.
        """
        conteneur_noeuds: Dict[str, List[Tuple[str, Dict]]] = {}
        for type_entite in noeud_types:
            for feat in features_by_type.get(type_entite, []):
                props = feat.get("properties", {})
                conteneur = props.get("conteneur_href")
                if conteneur:
                    conteneur_noeuds.setdefault(conteneur, []).append(
                        (type_entite, props)
                    )
        return conteneur_noeuds

    def _collecter_cables_electriques_du_groupe(
        self, noeuds: List[Tuple[str, Dict]], cable_terre_ids: set
    ) -> set:
        """Collecte les cables_href non-terre d'un groupe de nœuds."""
        cables: set = set()
        for _, props in noeuds:
            href = props.get("cables_href")
            if href:
                cables.update(
                    cid_strip
                    for cid in href.split(",")
                    if (cid_strip := cid.strip()) and cid_strip not in cable_terre_ids
                )
        return cables

    def _nettoyer_cables_noeud_terre(self, props: Dict, cable_terre_ids: set) -> bool:
        """Retire les câbles non-terre d'un nœud Terre. Retourne True si nettoyé."""
        href = props.get("cables_href")
        if not href:
            return False
        cables_restants = [
            cid.strip() for cid in href.split(",") if cid.strip() in cable_terre_ids
        ]
        if cables_restants:
            props["cables_href"] = ",".join(cables_restants)
        else:
            props.pop("cables_href", None)
        return True

    def _appliquer_propagation_conteneur(
        self,
        noeuds: List[Tuple[str, Dict]],
        cable_terre_ids: set,
    ) -> Tuple[int, int]:
        """Applique la propagation des câbles pour un conteneur donné.

        Retourne (nb_propagations, nb_nettoyages_terre).
        """
        cables_electriques = self._collecter_cables_electriques_du_groupe(
            noeuds, cable_terre_ids
        )
        if not cables_electriques:
            return 0, 0

        cables_str = ",".join(sorted(cables_electriques))
        propagation_count = 0
        nettoyage_terre_count = 0

        for type_entite, props in noeuds:
            if type_entite == "RPD_Terre_Reco":
                if self._nettoyer_cables_noeud_terre(props, cable_terre_ids):
                    nettoyage_terre_count += 1
            elif props.get("cables_href") != cables_str:
                props["cables_href"] = cables_str
                propagation_count += 1

        return propagation_count, nettoyage_terre_count

    def _propager_cables_dans_conteneurs(self, features_by_type: Dict[str, List[Dict]]):
        """Propage les liens cables_href aux nœuds partageant le même conteneur.

        Règle métier : tous les nœuds d'un conteneur (coffret, support, bâtiment
        technique) doivent porter les mêmes liens câbles électriques, SAUF les
        nœuds RPD_Terre_Reco qui ne peuvent être liés qu'à un câble de terre.
        """
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

        cable_terre_ids = self._collecter_ids_cables_terre(features_by_type)
        conteneur_noeuds = self._regrouper_noeuds_par_conteneur(
            features_by_type, noeud_types
        )

        propagation_count = 0
        nettoyage_terre_count = 0

        for noeuds in conteneur_noeuds.values():
            prop, nett = self._appliquer_propagation_conteneur(noeuds, cable_terre_ids)
            propagation_count += prop
            nettoyage_terre_count += nett

        if propagation_count > 0:
            print(
                f"  [OK] {propagation_count} noeud(s) enrichi(s) avec câbles du conteneur"
            )
        if nettoyage_terre_count > 0:
            print(
                f"  [OK] {nettoyage_terre_count} noeud(s) Terre nettoyé(s) (câbles électriques retirés)"
            )

    def _inject_materiel_properties_into_jonctions(
        self, features_by_type: Dict[str, List[Dict]]
    ):
        """Injecte les propriétés matériel dans les jonctions depuis les entités RPD_Materiel_Reco

        Symétrique avec extract_materiels_from_jonctions dans geojson_to_gml.

        Optimisations appliquées :
        - Utilise dict() pour lookup O(1) des matériels par ID
        - Pré-allocation et fonctions locales pour réduire les appels
        - frozenset pour les champs requis
        """
        materiels = features_by_type.get("RPD_Materiel_Reco", [])
        jonctions = features_by_type.get("RPD_Jonction_Reco", [])

        if not materiels or not jonctions:
            return

        # Construire un dictionnaire de lookup : {materiel_id: properties}
        # Optimisation : évite les itérations répétées sur la liste des matériels
        materiel_lookup = {}
        get_props = lambda feat: feat.get("properties", {})
        required_fields = frozenset(["Fabricant", "Modele", "NumeroLot", "NumeroSerie"])

        for materiel_feat in materiels:
            props = get_props(materiel_feat)
            materiel_id = props.get("id")
            if materiel_id:
                # Extraire uniquement les propriétés nécessaires
                materiel_props = {
                    field: props.get(field)
                    for field in required_fields
                    if props.get(field) is not None
                }
                if materiel_props:  # Seulement si au moins une propriété existe
                    materiel_lookup[materiel_id] = materiel_props

        # Injecter les propriétés matériel dans chaque jonction
        injection_count = 0
        for jonction_feat in jonctions:
            props = get_props(jonction_feat)
            materiel_href = props.get("materiel_href")

            if materiel_href and materiel_href in materiel_lookup:
                # Injecter les propriétés du matériel
                props.update(materiel_lookup[materiel_href])
                injection_count += 1

        if injection_count > 0:
            print(
                f"  [OK] {injection_count} jonction(s) enrichie(s) avec propriétés matériel"
            )

    def _extract_features_by_pass(
        self,
        root: ET.Element,
        extractors: dict,
        features_by_type: dict,
        target_types: frozenset,
        exclude_types: frozenset = frozenset(),
    ):
        """Extrait les features des types ciblés depuis les featureMembers."""
        strip_ns = self.ns_helper.strip_namespace
        gml_id_tag = self.ns_helper.tag("gml", "id")

        for member in root.findall(self.ns_helper.tag("gml", "featureMember")):
            for child in member:
                tag = strip_ns(child.tag)
                if (
                    tag in exclude_types
                    or tag not in target_types
                    or tag not in extractors
                ):
                    continue
                try:
                    features_by_type[tag].append(extractors[tag](child))
                except Exception as e:
                    gml_id = child.get(gml_id_tag, "unknown")
                    print(
                        f"Erreur lors de l'extraction de {tag} (id: {gml_id}): {e}",
                        file=sys.stderr,
                    )

    def _generer_geom_supp_v1_0(self, features_by_type: Dict[str, List[Dict]]):
        """Génère automatiquement les GeometrieSupplementaire pour les supports V1.0.

        Règle métier : en V1.0, les supports n'ont pas de geometriesupplementaire.
        On crée un rectangle 60×20 cm centré sur le point du support,
        puis on associe le support à cette géométrie via geometriesupplementaire_href.
        """
        if self.extractor.schema_version != VERSION_V1_0:
            return

        supports = features_by_type.get("RPD_Support_Reco", [])
        if not supports:
            return

        geom_supp_list = features_by_type.setdefault(
            "RPD_GeometrieSupplementaire_Reco", []
        )

        # Dimensions du rectangle : 60 cm × 20 cm (en mètres)
        demi_longueur = 0.30
        demi_largeur = 0.10

        creation_count = 0
        for support in supports:
            props = support.get("properties", {})
            geom = support.get("geometry")

            # Ne créer que si pas déjà de lien et géométrie existante
            if props.get("geometriesupplementaire_href") or not geom:
                continue

            coords = geom.get("coordinates", [])
            if len(coords) < 2:
                continue

            x, y = coords[0], coords[1]
            z = coords[2] if len(coords) > 2 else 0.0

            # Construction du rectangle 60×20 cm centré sur le point
            polygon_coords = [
                [x - demi_longueur, y - demi_largeur, z],
                [x + demi_longueur, y - demi_largeur, z],
                [x + demi_longueur, y + demi_largeur, z],
                [x - demi_longueur, y + demi_largeur, z],
                [x - demi_longueur, y - demi_largeur, z],
            ]

            support_id = props.get("id", props.get("ogr_pkid", ""))
            geom_supp_id = f"geomsupp_support_{support_id}"

            # Créer la feature GeometrieSupplementaire
            fid = self.extractor._get_fid("RPD_GeometrieSupplementaire_Reco")
            geom_supp_feature = {
                "type": "Feature",
                "properties": {
                    "fid": fid,
                    "ogr_pkid": f"RPD_Support_Reco_geomsupp_{fid}",
                    "id": geom_supp_id,
                    "PrecisionXY": props.get("PrecisionXY"),
                    "PrecisionZ": props.get("PrecisionZ"),
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[polygon_coords]],
                },
            }
            geom_supp_list.append(geom_supp_feature)

            # Associer le support à la géométrie supplémentaire
            props["geometriesupplementaire_href"] = geom_supp_id
            creation_count += 1

        if creation_count > 0:
            print(
                f"  [OK] {creation_count} geometrie(s) supplementaire(s) "
                f"creee(s) pour les supports (V1.0)"
            )

    def _supprimer_doublons_geographiques_plor(
        self, features_by_type: Dict[str, List[Dict]]
    ):
        """Supprime les doublons géographiques des RPD_PointLeveOuvrageReseau_Reco.

        Deux entités sont considérées en doublon si elles ont des coordonnées
        strictement identiques. Seule la première occurrence est conservée.
        Les entités sans géométrie sont toujours conservées.
        """
        type_cible = "RPD_PointLeveOuvrageReseau_Reco"
        features = features_by_type.get(type_cible)
        if not features:
            return

        coordonnees_vues: set = set()
        features_uniques: List[Dict] = []

        for feature in features:
            geometry = feature.get("geometry")
            if geometry is None:
                features_uniques.append(feature)
                continue

            coords = geometry.get("coordinates")
            if coords is None:
                features_uniques.append(feature)
                continue

            cle_coords = tuple(coords)
            if cle_coords not in coordonnees_vues:
                coordonnees_vues.add(cle_coords)
                features_uniques.append(feature)

        nb_doublons = len(features) - len(features_uniques)
        if nb_doublons > 0:
            features_by_type[type_cible] = features_uniques
            print(
                f"  [OK] {nb_doublons} doublon(s) geographique(s) "
                f"supprime(s) pour {type_cible}"
            )

    def _write_geojson_files(self, features_by_type: dict, output_dir: Path):
        """Écrit les fichiers GeoJSON par type d'entité et le fichier _metadata.json."""
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Écriture des fichiers GeoJSON dans {output_dir}...")

        for entity_type, features in features_by_type.items():
            if not features:
                continue

            geojson_data = {
                "type": "FeatureCollection",
                "name": entity_type,
                "crs": {
                    "type": "name",
                    "properties": {
                        "name": f'urn:ogc:def:crs:{self.srs.replace(":", "::")}'
                    },
                },
                "features": features,
            }

            output_file = output_dir / f"{entity_type}.geojson"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(geojson_data, f, indent=2, ensure_ascii=False)

            print(f"  [OK] {entity_type}.geojson ({len(features)} features)")

        # Écriture du fichier _metadata.json (métadonnées + réseau)
        if self.metadata_info:
            metadata_file = output_dir / "_metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.metadata_info, f, indent=2, ensure_ascii=False)
            print("  [OK] _metadata.json")

    def convert_gml_to_geojson(self, gml_path: Path, output_dir: Path):
        """Convertit un GML en plusieurs fichiers GeoJSON par type"""

        print(f"Lecture du fichier GML: {gml_path}")
        try:
            tree = DefusedET.parse(gml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Erreur lors du parsing XML: {e}", file=sys.stderr)
            return

        if root is None:
            print("Erreur: document XML vide", file=sys.stderr)
            return

        # Détection de la version du schéma depuis xsi:schemaLocation
        schema_version = self._detecter_version_schema(root)
        self.extractor.schema_version = schema_version
        print(f"Version du schema detectee : {schema_version}")

        # Extraire le SRS si disponible
        metadata_elem = root.find(f".//{self.ns_helper.tag('RecoStaR', 'Metadata')}")
        if metadata_elem is not None:
            srs_elem = metadata_elem.find(self.ns_helper.tag("RecoStaR", "SRS"))
            if srs_elem is not None and srs_elem.text:
                self.srs = srs_elem.text.strip()

        # Extraction complète des métadonnées et informations réseau
        self.metadata_info = self._extraire_metadonnees_completes(root)

        print("Extraction des relations...")
        self._extract_relations(root)

        extractors = {
            "RPD_Aerien_Reco": self.extractor.extract_aerien,
            "RPD_CableElectrique_Reco": self.extractor.extract_cable_electrique,
            "RPD_CableTelecommunication_Reco": self.extractor.extract_cable_telecommunication,
            "RPD_CableTerre_Reco": self.extractor.extract_cable_terre,
            "RPD_Coffret_Reco": self.extractor.extract_coffret,
            "RPD_CoupeCircuitAFusibles_Reco": self.extractor.extract_coupe_circuit_a_fusibles,
            "RPD_EnceinteCloturee_Reco": self.extractor.extract_enceinte_cloturee,
            "RPD_Fourreau_Reco": self.extractor.extract_fourreau,
            "RPD_GeometrieSupplementaire_Reco": self.extractor.extract_geometrie_supplementaire,
            "RPD_JeuBarres_Reco": self.extractor.extract_jeu_barres,
            "RPD_Jonction_Reco": self.extractor.extract_jonction,
            "RPD_OuvrageCollectifBranchement_Reco": self.extractor.extract_ouvrage_collectif_branchement,
            "RPD_PointDeComptage_Reco": self.extractor.extract_point_comptage,
            "RPD_PointLeveOuvrageReseau_Reco": self.extractor.extract_point_leve,
            "RPD_Materiel_Reco": self.extractor.extract_materiel,
            "RPD_PleineTerre_Reco": self.extractor.extract_pleine_terre,
            "RPD_Support_Reco": self.extractor.extract_support,
            "RPD_SupportModules_Reco": self.extractor.extract_support_modules,
            "RPD_BatimentTechnique_Reco": self.extractor.extract_batiment_technique,
            "RPD_PosteElectrique_Reco": self.extractor.extract_poste_electrique,
            "RPD_ProtectionMecanique_Reco": self.extractor.extract_protection_mecanique,
            "RPD_Terre_Reco": self.extractor.extract_terre,
        }

        features_by_type = {entity_type: [] for entity_type in extractors}
        all_types = frozenset(extractors)

        conteneur_types = frozenset(
            {
                "RPD_Coffret_Reco",
                "RPD_EnceinteCloturee_Reco",
                "RPD_Support_Reco",
                "RPD_BatimentTechnique_Reco",
            }
        )
        cheminement_types = frozenset(
            {
                "RPD_Aerien_Reco",
                "RPD_Fourreau_Reco",
                "RPD_PleineTerre_Reco",
                "RPD_ProtectionMecanique_Reco",
            }
        )

        # Passes ordonnées pour remplir les caches de géométries
        print("Extraction des conteneurs...")
        self._extract_features_by_pass(
            root, extractors, features_by_type, conteneur_types
        )

        print("Extraction des cheminements...")
        self._extract_features_by_pass(
            root, extractors, features_by_type, cheminement_types
        )

        print("Extraction des autres entités...")
        already_processed = conteneur_types | cheminement_types
        self._extract_features_by_pass(
            root, extractors, features_by_type, all_types, already_processed
        )

        print("Propagation des câbles électriques dans les conteneurs...")
        self._propager_cables_dans_conteneurs(features_by_type)

        print("Injection des propriétés matériel dans les jonctions...")
        self._inject_materiel_properties_into_jonctions(features_by_type)

        print("Génération des géométries supplémentaires pour supports (V1.0)...")
        self._generer_geom_supp_v1_0(features_by_type)

        print("Suppression des doublons géographiques (PointLeveOuvrageReseau)...")
        self._supprimer_doublons_geographiques_plor(features_by_type)

        self._write_geojson_files(features_by_type, output_dir)
        print("Conversion terminée avec succès!")


# Alias français pour compatibilité avec les tests et la convention de nommage
AideNamespaceGML = GMLNamespaceHelper
ParseurGeometrie = GeometryParser
ExtracteurEntites = EntityExtractor
ConvertisseurGML = GMLConverter


def main():
    """Point d'entrée principal du script"""
    parser = argparse.ArgumentParser(
        description="Convertit un fichier GML RecoStaR en fichiers GeoJSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python gml_to_geojson.py input.gml output_dir/
  python gml_to_geojson.py recolement.gml geojson_output/
        """,
    )

    parser.add_argument("input_gml", type=Path, help="Fichier GML RecoStaR en entrée")

    parser.add_argument(
        "output_dir", type=Path, help="Répertoire de sortie pour les fichiers GeoJSON"
    )

    args = parser.parse_args()

    # Validation du fichier d'entrée
    if not args.input_gml.exists():
        print(f"Erreur: Le fichier {args.input_gml} n'existe pas", file=sys.stderr)
        sys.exit(1)

    if not args.input_gml.is_file():
        print(f"Erreur: {args.input_gml} n'est pas un fichier", file=sys.stderr)
        sys.exit(1)

    # Conversion
    converter = GMLConverter()
    converter.convert_gml_to_geojson(args.input_gml, args.output_dir)


if __name__ == "__main__":
    main()
