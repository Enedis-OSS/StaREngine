import pytest
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from recostar_to_geojson import (
    GMLNamespaceHelper,
    GeometryParser,
    EntityExtractor,
    GMLConverter,
    NAMESPACE_GML,
    NAMESPACE_RECOSTAR,
    NAMESPACE_XLINK,
    RPD_ENTITY_TYPES,
    RELATION_TYPES,
    GEOMETRY_LIGNE_2_5D,
)

# ============================================================
# Tests des constantes du module
# ============================================================


class TestConstantesModule:
    """Tests pour les constantes du module recostar_to_geojson."""

    def test_namespace_gml_valide(self):
        """Vérifie que le namespace GML est correct."""
        assert NAMESPACE_GML == "http://www.opengis.net/gml/3.2"

    def test_namespace_recostar_valide(self):
        """Vérifie que le namespace RecoStaR est correct."""
        assert NAMESPACE_RECOSTAR == "http://StaR-Elec.com"

    def test_namespace_xlink_valide(self):
        """Vérifie que le namespace XLink est correct."""
        assert NAMESPACE_XLINK == "http://www.w3.org/1999/xlink"

    def test_rpd_entity_types_est_frozenset(self):
        """Vérifie que RPD_ENTITY_TYPES est un frozenset."""
        assert isinstance(RPD_ENTITY_TYPES, frozenset)

    def test_rpd_entity_types_contient_types_principaux(self):
        """Vérifie la présence des types d'entités principaux."""
        types_attendus = {
            "RPD_CableElectrique_Reco",
            "RPD_Coffret_Reco",
            "RPD_Support_Reco",
            "RPD_Jonction_Reco",
            "RPD_Materiel_Reco",
        }
        assert types_attendus <= RPD_ENTITY_TYPES

    def test_relation_types_est_frozenset(self):
        """Vérifie que RELATION_TYPES est un frozenset."""
        assert isinstance(RELATION_TYPES, frozenset)

    def test_relation_types_contient_3_relations(self):
        """Vérifie les 3 types de relations."""
        assert len(RELATION_TYPES) == 3
        assert "CableElectrique_NoeudReseau" in RELATION_TYPES
        assert "Cheminement_Cables" in RELATION_TYPES
        assert "Ouvrage_Materiel" in RELATION_TYPES

    def test_geometry_ligne_2_5d(self):
        """Vérifie la constante géométrie Ligne2.5D."""
        assert GEOMETRY_LIGNE_2_5D == "Ligne2.5D"


# ============================================================
# Tests de AideNamespaceGML
# ============================================================


class TestAideNamespaceGML:
    """Tests pour la classe AideNamespaceGML."""

    def test_tag_gml(self, ns_helper):
        """Vérifie la génération d'un tag GML qualifié via préfixe."""
        result = ns_helper.tag("gml", "Point")
        assert result == f"{{{NAMESPACE_GML}}}Point"

    def test_tag_recostar(self, ns_helper):
        """Vérifie la génération d'un tag RecoStaR qualifié via préfixe."""
        result = ns_helper.tag("RecoStaR", "Coffret")
        assert result == f"{{{NAMESPACE_RECOSTAR}}}Coffret"

    def test_tag_mise_en_cache(self, ns_helper):
        """Vérifie que les appels répétés retournent le même résultat (cache)."""
        r1 = ns_helper.tag("gml", "Polygon")
        r2 = ns_helper.tag("gml", "Polygon")
        assert r1 == r2

    def test_retirer_namespace_avec_namespace(self, ns_helper):
        """Vérifie le retrait du namespace d'un tag."""
        tag = f"{{{NAMESPACE_GML}}}Point"
        assert ns_helper.strip_namespace(tag) == "Point"

    def test_retirer_namespace_sans_namespace(self, ns_helper):
        """Vérifie que retirer_namespace retourne le tag tel quel sans namespace."""
        assert ns_helper.strip_namespace("MonTag") == "MonTag"

    def test_retirer_namespace_recostar(self, ns_helper):
        """Vérifie le retrait du namespace RecoStaR."""
        tag = f"{{{NAMESPACE_RECOSTAR}}}RPD_Coffret_Reco"
        assert ns_helper.strip_namespace(tag) == "RPD_Coffret_Reco"


# ============================================================
# Tests de ParseurGeometrie
# ============================================================


class TestParseurGeometrieParsePoslist:
    """Tests pour la méthode _parser_pos_list."""

    def test_parser_pos_list_3d(self, geometry_parser):
        """Vérifie le parsing d'une posList 3D."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}posList")
        elem.set("srsDimension", "3")
        elem.text = "600000.0 6800000.0 100.0 600010.0 6800010.0 110.0"
        result = geometry_parser._parse_pos_list(elem)
        assert len(result) == 2
        assert result[0] == pytest.approx([600000.0, 6800000.0, 100.0])
        assert result[1] == pytest.approx([600010.0, 6800010.0, 110.0])

    def test_parser_pos_list_2d(self, geometry_parser):
        """Vérifie le parsing d'une posList 2D."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}posList")
        elem.set("srsDimension", "2")
        elem.text = "0.0 0.0 1.0 1.0 2.0 0.0"
        result = geometry_parser._parse_pos_list(elem)
        assert len(result) == 3
        assert result[0] == pytest.approx([0.0, 0.0])
        assert result[1] == pytest.approx([1.0, 1.0])

    def test_parser_pos_list_defaut_3d(self, geometry_parser):
        """Vérifie que la dimension par défaut est 3."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}posList")
        elem.text = "1.0 2.0 3.0 4.0 5.0 6.0"
        result = geometry_parser._parse_pos_list(elem)
        assert len(result) == 2
        assert result[0] == pytest.approx([1.0, 2.0, 3.0])

    def test_parser_pos_list_vide(self, geometry_parser):
        """Vérifie le parsing d'une posList vide."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}posList")
        elem.text = None
        result = geometry_parser._parse_pos_list(elem)
        assert result == []

    def test_parser_pos_list_texte_vide(self, geometry_parser):
        """Vérifie le parsing d'une posList avec texte vide."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}posList")
        elem.text = ""
        result = geometry_parser._parse_pos_list(elem)
        assert result == []


class TestParseurGeometrieParsePos:
    """Tests pour la méthode _parser_pos."""

    def test_parser_pos_3d(self, geometry_parser):
        """Vérifie le parsing d'un pos 3D."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}pos")
        elem.text = "600000.0 6800000.0 100.5"
        result = geometry_parser._parse_pos(elem)
        assert result == pytest.approx([600000.0, 6800000.0, 100.5])

    def test_parser_pos_2d(self, geometry_parser):
        """Vérifie le parsing d'un pos 2D."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}pos")
        elem.text = "600000.0 6800000.0"
        result = geometry_parser._parse_pos(elem)
        assert result == pytest.approx([600000.0, 6800000.0])

    def test_parser_pos_vide(self, geometry_parser):
        """Vérifie le parsing d'un pos vide."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}pos")
        elem.text = None
        result = geometry_parser._parse_pos(elem)
        assert result == []


class TestParseurGeometrieParseGeometries:
    """Tests pour les méthodes parser_point, parser_ligne, parser_polygone."""

    def test_parser_point(self, geometry_parser, gml_point_elem):
        """Vérifie la conversion d'un élément gml:Point en GeoJSON."""
        result = geometry_parser.parse_point(gml_point_elem)
        assert result is not None
        assert result["type"] == "Point"
        assert result["coordinates"] == pytest.approx([600000.0, 6800000.0, 100.5])

    def test_parser_point_sans_pos(self, geometry_parser):
        """Vérifie que parser_point retourne None sans gml:pos."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}Point")
        result = geometry_parser.parse_point(elem)
        assert result is None

    def test_parser_ligne(self, geometry_parser, gml_linestring_elem):
        """Vérifie la conversion d'un gml:LineString en GeoJSON."""
        _, ls = gml_linestring_elem
        result = geometry_parser.parse_linestring(ls)
        assert result is not None
        assert result["type"] == "LineString"
        assert len(result["coordinates"]) == 2

    def test_parser_ligne_sans_poslist(self, geometry_parser):
        """Vérifie que parser_ligne retourne None sans posList."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}LineString")
        result = geometry_parser.parse_linestring(elem)
        assert result is None

    def test_parser_polygone(self, geometry_parser, gml_polygon_elem):
        """Vérifie la conversion d'un gml:Polygon en GeoJSON."""
        result = geometry_parser.parse_polygon(gml_polygon_elem)
        assert result is not None
        assert result["type"] == "Polygon"
        assert len(result["coordinates"]) == 1
        assert len(result["coordinates"][0]) == 4

    def test_parser_polygone_sans_exterior(self, geometry_parser):
        """Vérifie que parser_polygone retourne None sans exterior."""
        elem = ET.Element(f"{{{NAMESPACE_GML}}}Polygon")
        result = geometry_parser.parse_polygon(elem)
        assert result is None

    def test_parser_geometrie_dispatch_point(self, geometry_parser):
        """Vérifie le dispatch vers parser_point."""
        parent = ET.Element("geom")
        point = ET.SubElement(parent, f"{{{NAMESPACE_GML}}}Point")
        pos = ET.SubElement(point, f"{{{NAMESPACE_GML}}}pos")
        pos.text = "1.0 2.0 3.0"
        result = geometry_parser.parse_geometry(parent)
        assert result is not None
        assert result["type"] == "Point"

    def test_parser_geometrie_dispatch_linestring(self, geometry_parser):
        """Vérifie le dispatch vers parser_ligne."""
        parent = ET.Element("geom")
        ls = ET.SubElement(parent, f"{{{NAMESPACE_GML}}}LineString")
        pos_list = ET.SubElement(ls, f"{{{NAMESPACE_GML}}}posList")
        pos_list.set("srsDimension", "2")
        pos_list.text = "0.0 0.0 1.0 1.0"
        result = geometry_parser.parse_geometry(parent)
        assert result is not None
        assert result["type"] == "LineString"

    def test_parser_geometrie_dispatch_polygon(self, geometry_parser):
        """Vérifie le dispatch vers parser_polygone."""
        parent = ET.Element("geom")
        polygon = ET.SubElement(parent, f"{{{NAMESPACE_GML}}}Polygon")
        exterior = ET.SubElement(polygon, f"{{{NAMESPACE_GML}}}exterior")
        ring = ET.SubElement(exterior, f"{{{NAMESPACE_GML}}}LinearRing")
        pos_list = ET.SubElement(ring, f"{{{NAMESPACE_GML}}}posList")
        pos_list.set("srsDimension", "2")
        pos_list.text = "0.0 0.0 1.0 0.0 1.0 1.0 0.0 0.0"
        result = geometry_parser.parse_geometry(parent)
        assert result is not None
        assert result["type"] == "Polygon"

    def test_parser_geometrie_sans_enfant(self, geometry_parser):
        """Vérifie que parser_geometrie retourne None sans sous-élément."""
        parent = ET.Element("geom")
        result = geometry_parser.parse_geometry(parent)
        assert result is None


# ============================================================
# Tests de ExtracteurEntites
# ============================================================


class TestExtracteurEntitesHelpers:
    """Tests pour les méthodes utilitaires de ExtracteurEntites."""

    def test_obtenir_fid_auto_increment(self, entity_extractor):
        """Vérifie l'auto-incrémentation par type (commence à 1)."""
        fid1 = entity_extractor._get_fid("RPD_Coffret_Reco")
        fid2 = entity_extractor._get_fid("RPD_Coffret_Reco")
        assert fid1 == 1
        assert fid2 == 2

    def test_obtenir_fid_types_independants(self, entity_extractor):
        """Vérifie que les compteurs sont indépendants par type."""
        fid_coffret = entity_extractor._get_fid("RPD_Coffret_Reco")
        fid_support = entity_extractor._get_fid("RPD_Support_Reco")
        assert fid_coffret == 1
        assert fid_support == 1

    def test_obtenir_texte_present(self, entity_extractor):
        """Vérifie la récupération de texte d'un sous-élément existant."""
        parent = ET.Element("parent")
        child = ET.SubElement(parent, f"{{{NAMESPACE_RECOSTAR}}}Nom")
        child.text = "valeur"
        result = entity_extractor._get_text(parent, "Nom")
        assert result == "valeur"

    def test_obtenir_texte_absent(self, entity_extractor):
        """Vérifie le retour None pour un sous-élément absent."""
        parent = ET.Element("parent")
        result = entity_extractor._get_text(parent, "Inexistant")
        assert result is None

    def test_obtenir_texte_sans_texte(self, entity_extractor):
        """Vérifie le retour None pour un sous-élément sans texte."""
        parent = ET.Element("parent")
        ET.SubElement(parent, f"{{{NAMESPACE_RECOSTAR}}}Vide")
        result = entity_extractor._get_text(parent, "Vide")
        assert result is None

    def test_obtenir_href_present(self, entity_extractor):
        """Vérifie la récupération d'un attribut xlink:href."""
        parent = ET.Element("parent")
        child = ET.SubElement(parent, f"{{{NAMESPACE_RECOSTAR}}}Ref")
        child.set(f"{{{NAMESPACE_XLINK}}}href", "cible_001")
        result = entity_extractor._get_href(parent, "Ref")
        assert result == "cible_001"

    def test_obtenir_href_absent(self, entity_extractor):
        """Vérifie le retour None pour un href absent."""
        parent = ET.Element("parent")
        result = entity_extractor._get_href(parent, "RefInexistante")
        assert result is None

    def test_obtenir_mesure_valeur_et_uom(self, entity_extractor):
        """Vérifie la récupération d'une mesure avec valeur et unité."""
        parent = ET.Element("parent")
        child = ET.SubElement(parent, f"{{{NAMESPACE_RECOSTAR}}}Section")
        child.text = "150.0"
        child.set("uom", "mm-2")
        value, uom = entity_extractor._get_measure(parent, "Section")
        assert value == pytest.approx(150.0)
        assert uom == "mm-2"

    def test_obtenir_mesure_absent(self, entity_extractor):
        """Vérifie le retour (None, None) pour une mesure absente."""
        parent = ET.Element("parent")
        value, uom = entity_extractor._get_measure(parent, "Inexistant")
        assert value is None
        assert uom is None

    def test_obtenir_mesure_sans_uom(self, entity_extractor):
        """Vérifie la récupération d'une mesure sans unité."""
        parent = ET.Element("parent")
        child = ET.SubElement(parent, f"{{{NAMESPACE_RECOSTAR}}}Valeur")
        child.text = "42.0"
        value, uom = entity_extractor._get_measure(parent, "Valeur")
        assert value == pytest.approx(42.0)
        assert uom is None


class TestExtracteurEntitesExtraction:
    """Tests pour les méthodes d'extraction d'entités de ExtracteurEntites."""

    def _creer_element_coffret(self, gml_id="coffret_001"):
        """Crée un élément XML Coffret pour les tests."""
        coffret = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Coffret_Reco")
        coffret.set(f"{{{NAMESPACE_GML}}}id", gml_id)
        # TypeCoffret
        tc = ET.SubElement(coffret, f"{{{NAMESPACE_RECOSTAR}}}TypeCoffret")
        tc.set(f"{{{NAMESPACE_XLINK}}}href", "S22")
        # FonctionCoffret
        fc = ET.SubElement(coffret, f"{{{NAMESPACE_RECOSTAR}}}FonctionCoffret")
        fc.set(f"{{{NAMESPACE_XLINK}}}href", "Distribution")
        # Géométrie
        geom = ET.SubElement(coffret, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        point = ET.SubElement(geom, f"{{{NAMESPACE_GML}}}Point")
        pos = ET.SubElement(point, f"{{{NAMESPACE_GML}}}pos")
        pos.text = "600000.0 6800000.0 100.0"
        # PrecisionXY, PrecisionZ
        pxy = ET.SubElement(coffret, f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY")
        pxy.text = "A"
        pz = ET.SubElement(coffret, f"{{{NAMESPACE_RECOSTAR}}}PrecisionZ")
        pz.text = "A"
        return coffret

    def _creer_element_support(self, gml_id="support_001"):
        """Crée un élément XML Support pour les tests."""
        support = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Support_Reco")
        support.set(f"{{{NAMESPACE_GML}}}id", gml_id)
        nature = ET.SubElement(support, f"{{{NAMESPACE_RECOSTAR}}}NatureSupport")
        nature.set(f"{{{NAMESPACE_XLINK}}}href", "Poteau")
        matiere = ET.SubElement(support, f"{{{NAMESPACE_RECOSTAR}}}Matiere")
        matiere.set(f"{{{NAMESPACE_XLINK}}}href", "Beton")
        geom = ET.SubElement(support, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        point = ET.SubElement(geom, f"{{{NAMESPACE_GML}}}Point")
        pos = ET.SubElement(point, f"{{{NAMESPACE_GML}}}pos")
        pos.text = "600010.0 6800010.0 110.0"
        pxy = ET.SubElement(support, f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY")
        pxy.text = "A"
        pz = ET.SubElement(support, f"{{{NAMESPACE_RECOSTAR}}}PrecisionZ")
        pz.text = "B"
        return support

    def _creer_element_materiel(self, gml_id="materiel_001"):
        """Crée un élément XML Materiel pour les tests."""
        mat = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Materiel_Reco")
        mat.set(f"{{{NAMESPACE_GML}}}id", gml_id)
        fab = ET.SubElement(mat, f"{{{NAMESPACE_RECOSTAR}}}Fabricant")
        fab.text = "Nexans"
        modele = ET.SubElement(mat, f"{{{NAMESPACE_RECOSTAR}}}Modele")
        modele.text = "ModelX"
        lot = ET.SubElement(mat, f"{{{NAMESPACE_RECOSTAR}}}NumeroLot")
        lot.text = "LOT001"
        serie = ET.SubElement(mat, f"{{{NAMESPACE_RECOSTAR}}}NumeroSerie")
        serie.text = "SN001"
        return mat

    def _creer_element_cable(self, gml_id="cable_001"):
        """Crée un élément XML CableElectrique pour les tests."""
        cable = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_CableElectrique_Reco")
        cable.set(f"{{{NAMESPACE_GML}}}id", gml_id)
        dt = ET.SubElement(cable, f"{{{NAMESPACE_RECOSTAR}}}DomaineTension")
        dt.text = "BT"
        fc = ET.SubElement(cable, f"{{{NAMESPACE_RECOSTAR}}}FonctionCable")
        fc.set(f"{{{NAMESPACE_XLINK}}}href", "Distribution")
        return cable

    def _creer_element_jonction(self, gml_id="jonction_001", conteneur_href=None):
        """Crée un élément XML Jonction pour les tests."""
        jonc = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Jonction_Reco")
        jonc.set(f"{{{NAMESPACE_GML}}}id", gml_id)
        dt = ET.SubElement(jonc, f"{{{NAMESPACE_RECOSTAR}}}DomaineTension")
        dt.text = "BT"
        tj = ET.SubElement(jonc, f"{{{NAMESPACE_RECOSTAR}}}TypeJonction")
        tj.text = "DERIVATION"
        if conteneur_href:
            cont = ET.SubElement(jonc, f"{{{NAMESPACE_RECOSTAR}}}conteneur")
            cont.set(f"{{{NAMESPACE_XLINK}}}href", conteneur_href)
        pxy = ET.SubElement(jonc, f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY")
        pxy.text = "A"
        pz = ET.SubElement(jonc, f"{{{NAMESPACE_RECOSTAR}}}PrecisionZ")
        pz.text = "A"
        return jonc

    def _creer_element_aerien(self, gml_id="aerien_001"):
        """Crée un élément XML Aerien pour les tests."""
        aerien = ET.Element(f"{{{NAMESPACE_RECOSTAR}}}RPD_Aerien_Reco")
        aerien.set(f"{{{NAMESPACE_GML}}}id", gml_id)
        mode = ET.SubElement(aerien, f"{{{NAMESPACE_RECOSTAR}}}ModePose")
        mode.text = "FACADE"
        geom = ET.SubElement(aerien, f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        ls = ET.SubElement(geom, f"{{{NAMESPACE_GML}}}LineString")
        pos_list = ET.SubElement(ls, f"{{{NAMESPACE_GML}}}posList")
        pos_list.set("srsDimension", "3")
        pos_list.text = "600000.0 6800000.0 100.0 600010.0 6800010.0 110.0"
        pxy = ET.SubElement(aerien, f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY")
        pxy.text = "A"
        pz = ET.SubElement(aerien, f"{{{NAMESPACE_RECOSTAR}}}PrecisionZ")
        pz.text = "A"
        return aerien

    def test_extraire_coffret_proprietes(self, entity_extractor):
        """Vérifie l'extraction des propriétés d'un Coffret."""
        elem = self._creer_element_coffret()
        feature = entity_extractor.extract_coffret(elem)
        props = feature["properties"]
        assert props["id"] == "coffret_001"
        assert props["TypeCoffret_href"] == "S22"
        assert props["FonctionCoffret_href"] == "Distribution"
        assert props["PrecisionXY"] == "A"

    def test_extraire_coffret_geometrie(self, entity_extractor):
        """Vérifie que le Coffret a une géométrie Point."""
        elem = self._creer_element_coffret()
        feature = entity_extractor.extract_coffret(elem)
        geom = feature["geometry"]
        assert geom is not None
        assert geom["type"] == "Point"
        assert geom["coordinates"] == pytest.approx([600000.0, 6800000.0, 100.0])

    def test_extraire_coffret_stocke_geometrie_conteneur(self, entity_extractor):
        """Vérifie que la géométrie du Coffret est stockée pour héritage."""
        elem = self._creer_element_coffret("coffret_cache")
        entity_extractor.extract_coffret(elem)
        assert "coffret_cache" in entity_extractor.conteneur_geometries

    def test_extraire_coffret_fid_auto_increment(self, entity_extractor):
        """Vérifie l'auto-incrémentation du fid (commence à 1)."""
        elem1 = self._creer_element_coffret("c1")
        elem2 = self._creer_element_coffret("c2")
        f1 = entity_extractor.extract_coffret(elem1)
        f2 = entity_extractor.extract_coffret(elem2)
        assert f1["properties"]["fid"] == 1
        assert f2["properties"]["fid"] == 2

    def test_extraire_support_proprietes(self, entity_extractor):
        """Vérifie l'extraction des propriétés d'un Support."""
        elem = self._creer_element_support()
        feature = entity_extractor.extract_support(elem)
        props = feature["properties"]
        assert props["id"] == "support_001"
        assert props["NatureSupport_href"] == "Poteau"
        assert props["Matiere_href"] == "Beton"

    def test_extraire_support_stocke_geometrie(self, entity_extractor):
        """Vérifie le stockage de la géométrie du Support."""
        elem = self._creer_element_support("sup_cache")
        entity_extractor.extract_support(elem)
        assert "sup_cache" in entity_extractor.conteneur_geometries

    def test_extraire_enceinte_cloturee_proprietes(self, entity_extractor):
        """Vérifie l'extraction complète de RPD_EnceinteCloturee_Reco."""
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        ns_g = f"{{{NAMESPACE_GML}}}"
        elem = ET.Element(f"{ns_r}RPD_EnceinteCloturee_Reco")
        elem.set(f"{ns_g}id", "enc_001")
        geom = ET.SubElement(elem, f"{ns_r}Geometrie")
        point = ET.SubElement(geom, f"{ns_g}Point")
        pos = ET.SubElement(point, f"{ns_g}pos")
        pos.text = "600000.0 6800000.0 100.0"
        ET.SubElement(elem, f"{ns_r}PrecisionXY").text = "A"
        ET.SubElement(elem, f"{ns_r}PrecisionZ").text = "B"
        feature = entity_extractor.extract_enceinte_cloturee(elem)
        props = feature["properties"]
        assert props["id"] == "enc_001"
        assert props["PrecisionXY"] == "A"
        assert props["PrecisionZ"] == "B"
        assert feature["geometry"]["type"] == "Point"

    def test_extraire_enceinte_cloturee_stocke_geometrie_conteneur(
        self, entity_extractor
    ):
        """Vérifie que la géométrie est stockée dans conteneur_geometries."""
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        ns_g = f"{{{NAMESPACE_GML}}}"
        elem = ET.Element(f"{ns_r}RPD_EnceinteCloturee_Reco")
        elem.set(f"{ns_g}id", "enc_geom_001")
        geom = ET.SubElement(elem, f"{ns_r}Geometrie")
        point = ET.SubElement(geom, f"{ns_g}Point")
        pos = ET.SubElement(point, f"{ns_g}pos")
        pos.text = "600000.0 6800000.0 100.0"
        ET.SubElement(elem, f"{ns_r}PrecisionXY").text = "A"
        ET.SubElement(elem, f"{ns_r}PrecisionZ").text = "A"
        entity_extractor.extract_enceinte_cloturee(elem)
        assert "enc_geom_001" in entity_extractor.conteneur_geometries

    def test_extraire_enceinte_cloturee_sans_geometrie(self, entity_extractor):
        """Vérifie l'extraction sans géométrie (pas de stockage conteneur)."""
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        ns_g = f"{{{NAMESPACE_GML}}}"
        elem = ET.Element(f"{ns_r}RPD_EnceinteCloturee_Reco")
        elem.set(f"{ns_g}id", "enc_no_geom")
        ET.SubElement(elem, f"{ns_r}PrecisionXY").text = "C"
        ET.SubElement(elem, f"{ns_r}PrecisionZ").text = "D"
        feature = entity_extractor.extract_enceinte_cloturee(elem)
        assert feature["geometry"] is None
        assert "enc_no_geom" not in entity_extractor.conteneur_geometries

    def test_extraire_materiel_proprietes(self, entity_extractor):
        """Vérifie l'extraction des propriétés d'un Materiel."""
        elem = self._creer_element_materiel()
        feature = entity_extractor.extract_materiel(elem)
        props = feature["properties"]
        assert props["Fabricant"] == "Nexans"
        assert props["Modele"] == "ModelX"
        assert props["NumeroLot"] == "LOT001"
        assert props["NumeroSerie"] == "SN001"

    def test_extraire_materiel_sans_geometrie(self, entity_extractor):
        """Vérifie que le Materiel n'a pas de géométrie."""
        elem = self._creer_element_materiel()
        feature = entity_extractor.extract_materiel(elem)
        assert feature["geometry"] is None

    def test_extraire_cable_electrique_sans_relation(self, entity_extractor):
        """Vérifie l'extraction d'un câble sans relation cheminement."""
        elem = self._creer_element_cable()
        feature = entity_extractor.extract_cable_electrique(elem)
        props = feature["properties"]
        assert props["id"] == "cable_001"
        assert props["DomaineTension"] == "BT"
        assert feature["geometry"] is None

    def test_extraire_cable_electrique_avec_geometrie_heritee(self, entity_extractor):
        """Vérifie l'héritage géométrique câble → cheminement unique (LineString)."""
        # Simuler le cache cheminement
        geom_linestring = {
            "type": "LineString",
            "coordinates": [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0]],
        }
        entity_extractor.cheminement_geometries["aerien_001"] = geom_linestring
        # Simuler la relation câble → cheminements (liste)
        entity_extractor.relations["cable_cheminement"]["cable_001"] = ["aerien_001"]
        elem = self._creer_element_cable()
        feature = entity_extractor.extract_cable_electrique(elem)
        assert feature["geometry"] is not None
        assert feature["geometry"]["type"] == "LineString"

    def test_extraire_cable_electrique_multi_cheminements(self, entity_extractor):
        """Vérifie l'assemblage MultiLineString avec plusieurs cheminements."""
        geom_1 = {
            "type": "LineString",
            "coordinates": [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0]],
        }
        geom_2 = {
            "type": "LineString",
            "coordinates": [[1.0, 1.0, 20.0], [2.0, 2.0, 30.0]],
        }
        entity_extractor.cheminement_geometries["fourreau_001"] = geom_1
        entity_extractor.cheminement_geometries["pleine_terre_001"] = geom_2
        entity_extractor.relations["cable_cheminement"]["cable_001"] = [
            "fourreau_001",
            "pleine_terre_001",
        ]
        elem = self._creer_element_cable()
        feature = entity_extractor.extract_cable_electrique(elem)
        assert feature["geometry"] is not None
        assert feature["geometry"]["type"] == "MultiLineString"
        assert len(feature["geometry"]["coordinates"]) == 2

    def test_extraire_jonction_sans_geometrie_propre(self, entity_extractor):
        """Vérifie que la Jonction hérite la géométrie du conteneur."""
        geom_point = {"type": "Point", "coordinates": [600000.0, 6800000.0, 100.0]}
        entity_extractor.conteneur_geometries["coffret_001"] = geom_point
        elem = self._creer_element_jonction("jonc_001", "coffret_001")
        feature = entity_extractor.extract_jonction(elem)
        assert feature["geometry"] is not None
        assert feature["geometry"]["type"] == "Point"
        assert feature["properties"]["conteneur_href"] == "coffret_001"

    def test_extraire_aerien_proprietes(self, entity_extractor):
        """Vérifie l'extraction des propriétés d'un Aerien."""
        elem = self._creer_element_aerien()
        feature = entity_extractor.extract_aerien(elem)
        props = feature["properties"]
        assert props["ModePose"] == "FACADE"
        assert feature["geometry"]["type"] == "LineString"

    def test_extraire_aerien_stocke_geometrie_cheminement(self, entity_extractor):
        """Vérifie le stockage de la géométrie Aerien."""
        elem = self._creer_element_aerien("aer_cache")
        entity_extractor.extract_aerien(elem)
        assert "aer_cache" in entity_extractor.cheminement_geometries

    def test_extract_ogr_pkid(self, entity_extractor):
        """Vérifie la génération de ogr_pkid."""
        elem = self._creer_element_coffret("coffret_test")
        feature = entity_extractor.extract_coffret(elem)
        assert "ogr_pkid" in feature["properties"]
        assert feature["properties"]["ogr_pkid"].startswith("RPD_Coffret_Reco_")


# ============================================================
# Tests de _assembler_geometries_cheminements
# ============================================================


class TestAssemblerGeometriesCheminements:
    """Tests pour la méthode _assembler_geometries_cheminements."""

    def test_aucun_cheminement_retourne_none(self, entity_extractor):
        """Vérifie le retour None sans relation câble-cheminement."""
        result = entity_extractor._assembler_geometries_cheminements("cable_inconnu")
        assert result is None

    def test_cable_id_none_retourne_none(self, entity_extractor):
        """Vérifie le retour None avec un cable_id None."""
        result = entity_extractor._assembler_geometries_cheminements(None)
        assert result is None

    def test_un_cheminement_retourne_linestring(self, entity_extractor):
        """Vérifie le retour LineString avec un seul cheminement."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0]]
        entity_extractor.cheminement_geometries["chem_001"] = {
            "type": "LineString",
            "coordinates": coords,
        }
        entity_extractor.relations["cable_cheminement"]["cable_001"] = ["chem_001"]
        result = entity_extractor._assembler_geometries_cheminements("cable_001")
        assert result is not None
        assert result["type"] == "LineString"
        assert result["coordinates"] == coords

    def test_plusieurs_cheminements_retourne_multilinestring(self, entity_extractor):
        """Vérifie le retour MultiLineString avec plusieurs cheminements."""
        coords_1 = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0]]
        coords_2 = [[1.0, 1.0, 20.0], [2.0, 2.0, 30.0]]
        coords_3 = [[2.0, 2.0, 30.0], [3.0, 3.0, 40.0]]
        entity_extractor.cheminement_geometries["chem_001"] = {
            "type": "LineString",
            "coordinates": coords_1,
        }
        entity_extractor.cheminement_geometries["chem_002"] = {
            "type": "LineString",
            "coordinates": coords_2,
        }
        entity_extractor.cheminement_geometries["chem_003"] = {
            "type": "LineString",
            "coordinates": coords_3,
        }
        entity_extractor.relations["cable_cheminement"]["cable_001"] = [
            "chem_001",
            "chem_002",
            "chem_003",
        ]
        result = entity_extractor._assembler_geometries_cheminements("cable_001")
        assert result["type"] == "MultiLineString"
        assert len(result["coordinates"]) == 3
        assert result["coordinates"][0] == coords_1
        assert result["coordinates"][2] == coords_3

    def test_cheminements_sans_geometrie_ignores(self, entity_extractor):
        """Vérifie que les cheminements sans géométrie en cache sont ignorés."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0]]
        entity_extractor.cheminement_geometries["chem_001"] = {
            "type": "LineString",
            "coordinates": coords,
        }
        # chem_002 n'a pas de géométrie en cache
        entity_extractor.relations["cable_cheminement"]["cable_001"] = [
            "chem_001",
            "chem_002",
        ]
        result = entity_extractor._assembler_geometries_cheminements("cable_001")
        assert result is not None
        assert result["type"] == "LineString"
        assert result["coordinates"] == coords

    def test_tous_cheminements_sans_geometrie_retourne_none(self, entity_extractor):
        """Vérifie le retour None si aucun cheminement n'a de géométrie."""
        entity_extractor.relations["cable_cheminement"]["cable_001"] = [
            "chem_001",
            "chem_002",
        ]
        result = entity_extractor._assembler_geometries_cheminements("cable_001")
        assert result is None


# ============================================================
# Tests de ConvertisseurGML
# ============================================================


class TestConvertisseurGMLRelations:
    """Tests pour l'extraction des relations dans ConvertisseurGML."""

    def _creer_arbre_relations(self):
        """Crée un arbre XML avec des relations pour les tests."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        # Relation CableElectrique_NoeudReseau
        member1 = ET.SubElement(root, f"{{{NAMESPACE_GML}}}featureMember")
        rel1 = ET.SubElement(
            member1, f"{{{NAMESPACE_RECOSTAR}}}CableElectrique_NoeudReseau"
        )
        cable_ref = ET.SubElement(rel1, f"{{{NAMESPACE_RECOSTAR}}}cableelectrique")
        cable_ref.set(f"{{{NAMESPACE_XLINK}}}href", "cable_001")
        noeud_ref = ET.SubElement(rel1, f"{{{NAMESPACE_RECOSTAR}}}noeudreseau")
        noeud_ref.set(f"{{{NAMESPACE_XLINK}}}href", "jonc_001")
        # Relation Cheminement_Cables
        member2 = ET.SubElement(root, f"{{{NAMESPACE_GML}}}featureMember")
        rel2 = ET.SubElement(member2, f"{{{NAMESPACE_RECOSTAR}}}Cheminement_Cables")
        chem_ref = ET.SubElement(rel2, f"{{{NAMESPACE_RECOSTAR}}}cheminement")
        chem_ref.set(f"{{{NAMESPACE_XLINK}}}href", "aerien_001")
        cable_ref2 = ET.SubElement(rel2, f"{{{NAMESPACE_RECOSTAR}}}cables")
        cable_ref2.set(f"{{{NAMESPACE_XLINK}}}href", "cable_001")
        # Relation Ouvrage_Materiel
        member3 = ET.SubElement(root, f"{{{NAMESPACE_GML}}}featureMember")
        rel3 = ET.SubElement(member3, f"{{{NAMESPACE_RECOSTAR}}}Ouvrage_Materiel")
        ouvr_ref = ET.SubElement(rel3, f"{{{NAMESPACE_RECOSTAR}}}ouvrage")
        ouvr_ref.set(f"{{{NAMESPACE_XLINK}}}href", "jonc_001")
        mat_ref = ET.SubElement(rel3, f"{{{NAMESPACE_RECOSTAR}}}materiel")
        mat_ref.set(f"{{{NAMESPACE_XLINK}}}href", "mat_001")
        return root

    def test_extraire_relations_cable_noeud(self, gml_converter):
        """Vérifie l'extraction des relations câble-noeud."""
        root = self._creer_arbre_relations()
        gml_converter._extract_relations(root)
        rels = gml_converter.extractor.relations
        assert "cable_001" in rels["cable_noeud"]["jonc_001"]

    def test_extraire_relations_cheminement_cable(self, gml_converter):
        """Vérifie l'extraction des relations cheminement-câble."""
        root = self._creer_arbre_relations()
        gml_converter._extract_relations(root)
        rels = gml_converter.extractor.relations
        assert "cable_001" in rels["cheminement_cable"]["aerien_001"]

    def test_extraire_relations_cable_cheminement_inverse(self, gml_converter):
        """Vérifie la relation inverse câble → cheminements (liste)."""
        root = self._creer_arbre_relations()
        gml_converter._extract_relations(root)
        rels = gml_converter.extractor.relations
        assert "aerien_001" in rels["cable_cheminement"]["cable_001"]

    def test_extraire_relations_ouvrage_materiel(self, gml_converter):
        """Vérifie l'extraction des relations ouvrage-matériel."""
        root = self._creer_arbre_relations()
        gml_converter._extract_relations(root)
        rels = gml_converter.extractor.relations
        assert rels["ouvrage_materiel"]["jonc_001"] == "mat_001"


class TestConvertisseurGMLInjectionMateriels:
    """Tests pour l'injection des propriétés matériel dans les jonctions."""

    def test_injection_materiel_dans_jonction(self, gml_converter):
        """Vérifie l'injection des propriétés matériel dans une jonction."""
        features = {
            "RPD_Jonction_Reco": [
                {
                    "properties": {
                        "id": "jonc_001",
                        "materiel_href": "mat_001",
                    }
                }
            ],
            "RPD_Materiel_Reco": [
                {
                    "properties": {
                        "id": "mat_001",
                        "Fabricant": "Nexans",
                        "Modele": "ModelX",
                        "NumeroLot": "LOT001",
                        "NumeroSerie": "SN001",
                    }
                }
            ],
        }
        gml_converter._inject_materiel_properties_into_jonctions(features)
        jonction = features["RPD_Jonction_Reco"][0]
        assert jonction["properties"]["Fabricant"] == "Nexans"
        assert jonction["properties"]["Modele"] == "ModelX"

    def test_injection_sans_materiel_correspondant(self, gml_converter):
        """Vérifie que l'injection ne plante pas sans matériel correspondant."""
        features = {
            "RPD_Jonction_Reco": [
                {
                    "properties": {
                        "id": "jonc_001",
                        "materiel_href": "mat_inexistant",
                    }
                }
            ],
            "RPD_Materiel_Reco": [],
        }
        gml_converter._inject_materiel_properties_into_jonctions(features)
        jonction = features["RPD_Jonction_Reco"][0]
        assert "Fabricant" not in jonction["properties"]

    def test_injection_sans_materiel_href(self, gml_converter):
        """Vérifie que l'injection ignore les jonctions sans materiel_href."""
        features = {
            "RPD_Jonction_Reco": [{"properties": {"id": "jonc_001"}}],
            "RPD_Materiel_Reco": [
                {
                    "properties": {
                        "id": "mat_001",
                        "Fabricant": "F",
                        "Modele": "M",
                        "NumeroLot": "L",
                        "NumeroSerie": "S",
                    }
                }
            ],
        }
        gml_converter._inject_materiel_properties_into_jonctions(features)
        jonction = features["RPD_Jonction_Reco"][0]
        assert "Fabricant" not in jonction["properties"]

    def test_injection_sans_jonctions(self, gml_converter):
        """Vérifie le comportement sans jonctions."""
        features = {
            "RPD_Materiel_Reco": [{"properties": {"id": "mat_001", "Fabricant": "F"}}],
        }
        # Ne doit pas lever d'exception
        gml_converter._inject_materiel_properties_into_jonctions(features)


class TestConvertisseurGMLEcritureGeoJSON:
    """Tests pour l'écriture des fichiers GeoJSON par ConvertisseurGML."""

    def test_ecrire_fichiers_geojson(self, gml_converter, tmp_path):
        """Vérifie l'écriture de fichiers GeoJSON."""
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {"id": "c1", "fid": 0},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [600000.0, 6800000.0, 100.0],
                    },
                }
            ]
        }
        gml_converter._write_geojson_files(features, tmp_path)
        fichier = tmp_path / "RPD_Coffret_Reco.geojson"
        assert fichier.exists()
        contenu = json.loads(fichier.read_text(encoding="utf-8"))
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1

    def test_write_geojson_type_vide_ignore(self, gml_converter, tmp_path):
        """Vérifie que les types sans features ne créent pas de fichier."""
        features = {"RPD_Coffret_Reco": []}
        gml_converter._write_geojson_files(features, tmp_path)
        fichier = tmp_path / "RPD_Coffret_Reco.geojson"
        assert not fichier.exists()

    def test_write_geojson_crs_metadata(self, gml_converter, tmp_path):
        """Vérifie la présence de la metadata CRS dans le GeoJSON."""
        features = {
            "RPD_Support_Reco": [
                {
                    "type": "Feature",
                    "properties": {"id": "s1", "fid": 0},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [600000.0, 6800000.0],
                    },
                }
            ]
        }
        gml_converter._write_geojson_files(features, tmp_path)
        fichier = tmp_path / "RPD_Support_Reco.geojson"
        contenu = json.loads(fichier.read_text(encoding="utf-8"))
        assert "crs" in contenu
        assert "properties" in contenu["crs"]

    def test_write_geojson_multiple_types(self, gml_converter, tmp_path):
        """Vérifie l'écriture de plusieurs types d'entités."""
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {"id": "c1", "fid": 0},
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                }
            ],
            "RPD_Support_Reco": [
                {
                    "type": "Feature",
                    "properties": {"id": "s1", "fid": 0},
                    "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
                }
            ],
        }
        gml_converter._write_geojson_files(features, tmp_path)
        assert (tmp_path / "RPD_Coffret_Reco.geojson").exists()
        assert (tmp_path / "RPD_Support_Reco.geojson").exists()


class TestConvertisseurGMLConversionComplete:
    """Tests d'intégration pour la conversion GML vers GeoJSON."""

    def _creer_gml_minimal(self, tmp_path, contenu_xml=None):
        """Crée un fichier GML minimal pour les tests."""
        if contenu_xml is None:
            contenu_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<gml:FeatureCollection
    xmlns:gml="{NAMESPACE_GML}"
    xmlns:RecoStaR="{NAMESPACE_RECOSTAR}"
    xmlns:xlink="{NAMESPACE_XLINK}">
    <gml:featureMember>
        <RecoStaR:Metadata gml:id="metadata_001">
            <RecoStaR:SRS>EPSG:2154</RecoStaR:SRS>
        </RecoStaR:Metadata>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_Coffret_Reco gml:id="coffret_001">
            <RecoStaR:Geometrie>
                <gml:Point srsName="EPSG:2154">
                    <gml:pos>600000.0 6800000.0 100.0</gml:pos>
                </gml:Point>
            </RecoStaR:Geometrie>
            <RecoStaR:PrecisionXY>A</RecoStaR:PrecisionXY>
            <RecoStaR:PrecisionZ>A</RecoStaR:PrecisionZ>
        </RecoStaR:RPD_Coffret_Reco>
    </gml:featureMember>
</gml:FeatureCollection>"""
        fichier_gml = tmp_path / "input.gml"
        fichier_gml.write_text(contenu_xml, encoding="utf-8")
        return fichier_gml

    def test_conversion_gml_fichier_cree(self, gml_converter, tmp_path):
        """Vérifie que la conversion crée au moins un fichier GeoJSON."""
        fichier_gml = self._creer_gml_minimal(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        gml_converter.convert_gml_to_geojson(fichier_gml, output_dir)
        fichiers_geojson = list(output_dir.glob("*.geojson"))
        assert len(fichiers_geojson) >= 1

    def test_conversion_gml_coffret_extrait(self, gml_converter, tmp_path):
        """Vérifie que le Coffret est correctement extrait."""
        fichier_gml = self._creer_gml_minimal(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        gml_converter.convert_gml_to_geojson(fichier_gml, output_dir)
        fichier_coffret = output_dir / "RPD_Coffret_Reco.geojson"
        assert fichier_coffret.exists()
        contenu = json.loads(fichier_coffret.read_text(encoding="utf-8"))
        assert len(contenu["features"]) == 1
        feature = contenu["features"][0]
        assert feature["properties"]["id"] == "coffret_001"
        assert feature["geometry"]["type"] == "Point"

    def test_conversion_gml_avec_relations(self, gml_converter, tmp_path):
        """Vérifie la conversion avec des relations câble-noeud."""
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<gml:FeatureCollection
    xmlns:gml="{NAMESPACE_GML}"
    xmlns:RecoStaR="{NAMESPACE_RECOSTAR}"
    xmlns:xlink="{NAMESPACE_XLINK}">
    <gml:featureMember>
        <RecoStaR:Metadata gml:id="metadata_001">
            <RecoStaR:SRS>EPSG:2154</RecoStaR:SRS>
        </RecoStaR:Metadata>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:CableElectrique_NoeudReseau>
            <RecoStaR:cableelectrique xlink:href="cable_001"/>
            <RecoStaR:noeudreseau xlink:href="jonc_001"/>
        </RecoStaR:CableElectrique_NoeudReseau>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:Cheminement_Cables>
            <RecoStaR:cheminement xlink:href="aerien_001"/>
            <RecoStaR:cables xlink:href="cable_001"/>
        </RecoStaR:Cheminement_Cables>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_Aerien_Reco gml:id="aerien_001">
            <RecoStaR:ModePose>FACADE</RecoStaR:ModePose>
            <RecoStaR:Geometrie>
                <gml:LineString srsName="EPSG:2154">
                    <gml:posList srsDimension="3">600000.0 6800000.0 100.0 600010.0 6800010.0 110.0</gml:posList>
                </gml:LineString>
            </RecoStaR:Geometrie>
            <RecoStaR:PrecisionXY>A</RecoStaR:PrecisionXY>
            <RecoStaR:PrecisionZ>A</RecoStaR:PrecisionZ>
        </RecoStaR:RPD_Aerien_Reco>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_CableElectrique_Reco gml:id="cable_001">
            <RecoStaR:DomaineTension>BT</RecoStaR:DomaineTension>
        </RecoStaR:RPD_CableElectrique_Reco>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_Coffret_Reco gml:id="coffret_001">
            <RecoStaR:Geometrie>
                <gml:Point srsName="EPSG:2154">
                    <gml:pos>600000.0 6800000.0 100.0</gml:pos>
                </gml:Point>
            </RecoStaR:Geometrie>
            <RecoStaR:PrecisionXY>A</RecoStaR:PrecisionXY>
            <RecoStaR:PrecisionZ>A</RecoStaR:PrecisionZ>
        </RecoStaR:RPD_Coffret_Reco>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_Jonction_Reco gml:id="jonc_001">
            <RecoStaR:DomaineTension>BT</RecoStaR:DomaineTension>
            <RecoStaR:TypeJonction>DERIVATION</RecoStaR:TypeJonction>
            <RecoStaR:conteneur xlink:href="coffret_001"/>
            <RecoStaR:PrecisionXY>A</RecoStaR:PrecisionXY>
            <RecoStaR:PrecisionZ>A</RecoStaR:PrecisionZ>
        </RecoStaR:RPD_Jonction_Reco>
    </gml:featureMember>
</gml:FeatureCollection>"""
        fichier_gml = self._creer_gml_minimal(tmp_path, xml)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        gml_converter.convert_gml_to_geojson(fichier_gml, output_dir)
        # Le câble doit hériter la géométrie du cheminement (aérien)
        fichier_cable = output_dir / "RPD_CableElectrique_Reco.geojson"
        assert fichier_cable.exists()
        contenu = json.loads(fichier_cable.read_text(encoding="utf-8"))
        cable = contenu["features"][0]
        assert cable["geometry"] is not None
        assert cable["geometry"]["type"] == "LineString"

    def test_conversion_gml_cable_multi_cheminements(self, gml_converter, tmp_path):
        """Vérifie qu'un câble lié à plusieurs cheminements produit un MultiLineString."""
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<gml:FeatureCollection
    xmlns:gml="{NAMESPACE_GML}"
    xmlns:RecoStaR="{NAMESPACE_RECOSTAR}"
    xmlns:xlink="{NAMESPACE_XLINK}">
    <gml:featureMember>
        <RecoStaR:Metadata gml:id="metadata_001">
            <RecoStaR:SRS>EPSG:2154</RecoStaR:SRS>
        </RecoStaR:Metadata>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:Cheminement_Cables>
            <RecoStaR:cheminement xlink:href="fourreau_001"/>
            <RecoStaR:cables xlink:href="cable_001"/>
        </RecoStaR:Cheminement_Cables>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:Cheminement_Cables>
            <RecoStaR:cheminement xlink:href="pleine_terre_001"/>
            <RecoStaR:cables xlink:href="cable_001"/>
        </RecoStaR:Cheminement_Cables>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_Fourreau_Reco gml:id="fourreau_001">
            <RecoStaR:Geometrie>
                <gml:LineString srsName="EPSG:2154">
                    <gml:posList srsDimension="3">600000.0 6800000.0 100.0 600010.0 6800010.0 110.0</gml:posList>
                </gml:LineString>
            </RecoStaR:Geometrie>
            <RecoStaR:PrecisionXY>A</RecoStaR:PrecisionXY>
            <RecoStaR:PrecisionZ>A</RecoStaR:PrecisionZ>
        </RecoStaR:RPD_Fourreau_Reco>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_PleineTerre_Reco gml:id="pleine_terre_001">
            <RecoStaR:Geometrie>
                <gml:LineString srsName="EPSG:2154">
                    <gml:posList srsDimension="3">600010.0 6800010.0 110.0 600020.0 6800020.0 120.0</gml:posList>
                </gml:LineString>
            </RecoStaR:Geometrie>
            <RecoStaR:PrecisionXY>A</RecoStaR:PrecisionXY>
            <RecoStaR:PrecisionZ>A</RecoStaR:PrecisionZ>
        </RecoStaR:RPD_PleineTerre_Reco>
    </gml:featureMember>
    <gml:featureMember>
        <RecoStaR:RPD_CableElectrique_Reco gml:id="cable_001">
            <RecoStaR:DomaineTension>BT</RecoStaR:DomaineTension>
        </RecoStaR:RPD_CableElectrique_Reco>
    </gml:featureMember>
</gml:FeatureCollection>"""
        fichier_gml = self._creer_gml_minimal(tmp_path, xml)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        gml_converter.convert_gml_to_geojson(fichier_gml, output_dir)
        fichier_cable = output_dir / "RPD_CableElectrique_Reco.geojson"
        assert fichier_cable.exists()
        contenu = json.loads(fichier_cable.read_text(encoding="utf-8"))
        cable = contenu["features"][0]
        assert cable["geometry"] is not None
        assert cable["geometry"]["type"] == "MultiLineString"
        assert len(cable["geometry"]["coordinates"]) == 2
