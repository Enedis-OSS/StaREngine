import os
import sys
import pytest
from xml.etree import ElementTree as ET

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# Fixtures pour geojson_to_recostar
# ============================================================


@pytest.fixture
def geometry_converter():
    """Instance de ConvertisseurGeometrie avec SRS par défaut."""
    from geojson_to_recostar import ConvertisseurGeometrie

    return ConvertisseurGeometrie()


@pytest.fixture
def feature_mapper():
    """Instance de MappeurEntites avec SRS par défaut."""
    from geojson_to_recostar import MappeurEntites

    return MappeurEntites()


@pytest.fixture
def gml_generator():
    """Instance de GenerateurGML avec SRS par défaut."""
    from geojson_to_recostar import GenerateurGML

    return GenerateurGML()


@pytest.fixture
def point_2d():
    """Géométrie GeoJSON Point 2D."""
    return {"type": "Point", "coordinates": [2.35, 48.86]}


@pytest.fixture
def point_3d():
    """Géométrie GeoJSON Point 3D."""
    return {"type": "Point", "coordinates": [2.35, 48.86, 100.5]}


@pytest.fixture
def linestring_2d():
    """Géométrie GeoJSON LineString 2D."""
    return {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]}


@pytest.fixture
def linestring_3d():
    """Géométrie GeoJSON LineString 3D."""
    return {
        "type": "LineString",
        "coordinates": [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0], [2.0, 0.0, 15.0]],
    }


@pytest.fixture
def polygon_2d():
    """Géométrie GeoJSON Polygon 2D."""
    return {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
    }


@pytest.fixture
def multipolygon():
    """Géométrie GeoJSON MultiPolygon."""
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
            [[[2.0, 2.0], [3.0, 2.0], [3.0, 3.0], [2.0, 2.0]]],
        ],
    }


@pytest.fixture
def feature_cable_electrique():
    """Feature GeoJSON pour CableElectrique."""
    return {
        "type": "Feature",
        "properties": {
            "id": "cable_001",
            "fid": 1,
            "ogr_pkid": "RPD_CableElectrique_Reco_0",
            "DomaineTension": "BT",
            "FonctionCable_href": "Distribution",
            "Section": 150,
            "Section_uom": "mm-2",
            "Statut": "EN_SERVICE",
        },
        "geometry": None,
    }


@pytest.fixture
def feature_coffret():
    """Feature GeoJSON pour Coffret."""
    return {
        "type": "Feature",
        "properties": {
            "id": "coffret_001",
            "fid": 1,
            "ogr_pkid": "RPD_Coffret_Reco_0",
            "FonctionCoffret": "Distribution",
            "PrecisionXY": "A",
            "PrecisionZ": "A",
        },
        "geometry": {"type": "Point", "coordinates": [2.35, 48.86, 100.0]},
    }


@pytest.fixture
def feature_materiel():
    """Feature GeoJSON pour Materiel."""
    return {
        "type": "Feature",
        "properties": {
            "id": "materiel_001",
            "Fabricant": "Nexans",
            "Modele": "ModelX",
            "NumeroLot": "LOT001",
            "NumeroSerie": "SN001",
        },
        "geometry": None,
    }


# ============================================================
# Fixtures pour recostar_to_geojson
# ============================================================

NAMESPACE_GML = "http://www.opengis.net/gml/3.2"
NAMESPACE_RECOSTAR = "http://StaR-Elec.com"
NAMESPACE_XLINK = "http://www.w3.org/1999/xlink"


@pytest.fixture
def ns_helper():
    """Instance de GMLNamespaceHelper."""
    from recostar_to_geojson import GMLNamespaceHelper

    return GMLNamespaceHelper()


@pytest.fixture
def geometry_parser(ns_helper):
    """Instance de GeometryParser."""
    from recostar_to_geojson import GeometryParser

    return GeometryParser(ns_helper)


@pytest.fixture
def entity_extractor(ns_helper):
    """Instance d'EntityExtractor."""
    from recostar_to_geojson import EntityExtractor

    return EntityExtractor(ns_helper)


@pytest.fixture
def gml_converter():
    """Instance de GMLConverter."""
    from recostar_to_geojson import GMLConverter

    return GMLConverter()


@pytest.fixture
def gml_point_elem():
    """Élément XML gml:Point 3D."""
    point = ET.Element(f"{{{NAMESPACE_GML}}}Point")
    point.set("srsName", "EPSG:2154")
    pos = ET.SubElement(point, f"{{{NAMESPACE_GML}}}pos")
    pos.text = "600000.0 6800000.0 100.5"
    return point


@pytest.fixture
def gml_linestring_elem():
    """Élément XML gml:LineString 3D."""
    ls = ET.Element(f"{{{NAMESPACE_GML}}}LineString")
    ls.set("srsName", "EPSG:2154")
    pos_list = ET.SubElement(ls, f"{{{NAMESPACE_GML}}}posList")
    pos_list.set("srsDimension", "3")
    pos_list.text = "600000.0 6800000.0 100.0 600010.0 6800010.0 110.0"
    return pos_list, ls


@pytest.fixture
def gml_polygon_elem():
    """Élément XML gml:Polygon 2D."""
    polygon = ET.Element(f"{{{NAMESPACE_GML}}}Polygon")
    exterior = ET.SubElement(polygon, f"{{{NAMESPACE_GML}}}exterior")
    ring = ET.SubElement(exterior, f"{{{NAMESPACE_GML}}}LinearRing")
    pos_list = ET.SubElement(ring, f"{{{NAMESPACE_GML}}}posList")
    pos_list.set("srsDimension", "2")
    pos_list.text = "0.0 0.0 1.0 0.0 1.0 1.0 0.0 0.0"
    return polygon
