import re

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree as ET  # nosec B405

import geojson_to_recostar as g2r
import pytest
from geojson_to_recostar import (
    DEFAULT_SRS,
    NAMESPACE_GML,
    NAMESPACE_RECOSTAR,
    NAMESPACE_XLINK,
    NS_MAP,
    REQUIRED_RPD_FILES,
    ConvertisseurGeometrie,
    ElementGML,
    RemappeurIds,
)

# ============================================================
# Tests des constantes du module
# ============================================================


class TestConstantesModule:
    """Tests pour les constantes du module geojson_to_recostar."""

    def test_namespace_gml_valide(self):
        """Vérifie que le namespace GML est correct."""
        assert NAMESPACE_GML == "http://www.opengis.net/gml/3.2"

    def test_namespace_recostar_valide(self):
        """Vérifie que le namespace RecoStaR est correct."""
        assert NAMESPACE_RECOSTAR == "http://StaR-Elec.com"

    def test_default_srs(self):
        """Vérifie le SRS par défaut."""
        assert DEFAULT_SRS == "EPSG:2154"

    def test_ns_map_contient_tous_les_prefixes(self):
        """Vérifie que NS_MAP contient gml, RecoStaR, xlink, xsi."""
        assert {"gml", "RecoStaR", "xlink", "xsi"} <= set(NS_MAP.keys())

    def test_required_rpd_files_est_frozenset(self):
        """Vérifie que REQUIRED_RPD_FILES est un frozenset."""
        assert isinstance(REQUIRED_RPD_FILES, frozenset)

    def test_required_rpd_files_non_vide(self):
        """Vérifie que REQUIRED_RPD_FILES contient des éléments."""
        assert len(REQUIRED_RPD_FILES) > 0

    def test_required_rpd_files_contient_module_raccordement(self):
        """RPD_ModuleRaccordement_Reco doit être pris en charge par le pipeline."""
        assert "RPD_ModuleRaccordement_Reco" in REQUIRED_RPD_FILES


# ============================================================
# Tests de ElementGML
# ============================================================


class TestGMLElement:
    """Tests pour la classe ElementGML."""

    def test_creation_basique(self):
        """Vérifie la création d'un élément avec tag seul."""
        elem = ElementGML("monTag")
        assert elem.tag == "monTag"
        assert elem.attrib == {}
        assert elem.text is None
        assert elem.children == []

    def test_creation_avec_attributs(self):
        """Vérifie la création avec attributs."""
        attribs = {"id": "test", "name": "valeur"}
        elem = ElementGML("tag", attrib=attribs)
        assert elem.attrib == attribs

    def test_creation_avec_texte(self):
        """Vérifie la création avec texte."""
        elem = ElementGML("tag", text="contenu")
        assert elem.text == "contenu"

    def test_slots_interdit_attributs_dynamiques(self):
        """Vérifie que __slots__ empêche les attributs dynamiques."""
        elem = ElementGML("tag")
        with pytest.raises(AttributeError):
            elem.attribut_inexistant = "valeur"  # type: ignore[attr-defined]

    def test_children_modifiable(self):
        """Vérifie que la liste children est modifiable."""
        elem = ElementGML("parent")
        enfant = ElementGML("enfant")
        elem.children.append(enfant)
        assert len(elem.children) == 1


# ============================================================
# Tests de ConvertisseurGeometrie
# ============================================================


class TestGeometryConverter:
    """Tests pour la classe ConvertisseurGeometrie."""

    def test_initialisation_srs_defaut(self, geometry_converter):
        """Vérifie le SRS par défaut."""
        assert geometry_converter.srs == DEFAULT_SRS

    def test_initialisation_srs_personnalise(self):
        """Vérifie un SRS personnalisé."""
        conv = ConvertisseurGeometrie("EPSG:4326")
        assert conv.srs == "EPSG:4326"

    def test_format_coord_entier(self, geometry_converter):
        """Vérifie le formatage d'une coordonnée entière."""
        resultat = geometry_converter._formater_coord(42.0)
        assert resultat == "42.0"

    def test_format_coord_decimal(self, geometry_converter):
        """Vérifie le formatage d'une coordonnée décimale."""
        resultat = geometry_converter._formater_coord(3.14159)
        assert "3.14159" in resultat

    def test_coords_to_string_2d(self, geometry_converter):
        """Vérifie la conversion de coordonnées 2D en string."""
        coords = [[1.0, 2.0], [3.0, 4.0]]
        resultat = geometry_converter._coords_vers_chaine(coords)
        assert "1.0" in resultat
        assert "2.0" in resultat
        assert "3.0" in resultat

    def test_point_to_gml_2d(self, geometry_converter, point_2d):
        """Vérifie la conversion d'un Point 2D en GML."""
        elem = geometry_converter.point_vers_gml(point_2d, "pt1")
        assert elem.tag == f"{{{NAMESPACE_GML}}}Point"
        assert elem.get("srsName") == DEFAULT_SRS

    def test_point_to_gml_3d_dimension(self, geometry_converter, point_3d):
        """Vérifie que srsDimension=3 est ajouté pour un Point 3D."""
        elem = geometry_converter.point_vers_gml(point_3d, "pt1")
        assert elem.get("srsDimension") == "3"

    def test_point_to_gml_pos_text(self, geometry_converter, point_3d):
        """Vérifie le contenu de gml:pos pour un Point 3D."""
        elem = geometry_converter.point_vers_gml(point_3d, "pt1")
        pos = elem.find(f"{{{NAMESPACE_GML}}}pos")
        assert pos is not None
        assert "2.35" in pos.text
        assert "48.86" in pos.text
        assert "100.5" in pos.text

    def test_linestring_to_gml(self, geometry_converter, linestring_2d):
        """Vérifie la conversion d'un LineString en GML."""
        elem = geometry_converter.ligne_vers_gml(linestring_2d, "ls1")
        assert elem.tag == f"{{{NAMESPACE_GML}}}LineString"
        pos_list = elem.find(f"{{{NAMESPACE_GML}}}posList")
        assert pos_list is not None

    def test_linestring_3d_dimension(self, geometry_converter, linestring_3d):
        """Vérifie srsDimension=3 pour un LineString 3D."""
        elem = geometry_converter.ligne_vers_gml(linestring_3d, "ls1")
        pos_list = elem.find(f"{{{NAMESPACE_GML}}}posList")
        assert pos_list.get("srsDimension") == "3"

    def test_linestring_2d_dimension(self, geometry_converter, linestring_2d):
        """Vérifie srsDimension=2 pour un LineString 2D."""
        elem = geometry_converter.ligne_vers_gml(linestring_2d, "ls1")
        pos_list = elem.find(f"{{{NAMESPACE_GML}}}posList")
        assert pos_list.get("srsDimension") == "2"

    def test_polygon_to_gml(self, geometry_converter, polygon_2d):
        """Vérifie la conversion d'un Polygon en GML."""
        elem = geometry_converter.polygone_vers_gml(polygon_2d, "poly1")
        assert elem.tag == f"{{{NAMESPACE_GML}}}Polygon"
        exterior = elem.find(f"{{{NAMESPACE_GML}}}exterior")
        assert exterior is not None
        ring = exterior.find(f"{{{NAMESPACE_GML}}}LinearRing")
        assert ring is not None

    def test_multipolygon_to_gml(self, geometry_converter, multipolygon):
        """Vérifie la conversion du premier polygone d'un MultiPolygon."""
        elem = geometry_converter.multipolygone_vers_gml(multipolygon, "mp1")
        assert elem is not None
        assert elem.tag == f"{{{NAMESPACE_GML}}}Polygon"

    def test_multipolygon_vide(self, geometry_converter):
        """Vérifie qu'un MultiPolygon vide retourne None."""
        geom = {"type": "MultiPolygon", "coordinates": []}
        assert geometry_converter.multipolygone_vers_gml(geom, "mp1") is None


# ============================================================
# Tests de MappeurEntites
# ============================================================


class TestFeatureMapper:
    """Tests pour la classe MappeurEntites."""

    def test_initialisation(self, feature_mapper):
        """Vérifie l'initialisation du mapper."""
        assert feature_mapper.srs == DEFAULT_SRS
        assert isinstance(feature_mapper.seen_ids, set)
        assert isinstance(feature_mapper.geom_counter, dict)

    def test_add_property_none_ignore(self, feature_mapper):
        """Vérifie que _ajouter_propriete ignore les valeurs None."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "champ", None)
        assert len(parent) == 0

    def test_add_property_vide_ignore(self, feature_mapper):
        """Vérifie que _ajouter_propriete ignore les chaînes vides."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "champ", "")
        assert len(parent) == 0

    def test_add_property_string(self, feature_mapper):
        """Vérifie l'ajout d'une propriété string."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "nom", "valeur")
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}nom")
        assert enfant is not None
        assert enfant.text == "valeur"

    def test_add_property_bool_true(self, feature_mapper):
        """Vérifie la conversion bool → 'true'."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "actif", True)
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}actif")
        assert enfant is not None
        assert enfant.text == "true"

    def test_add_property_bool_false(self, feature_mapper):
        """Vérifie la conversion bool → 'false'."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "actif", False)
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}actif")
        assert enfant is not None
        assert enfant.text == "false"

    def test_add_property_float_entier(self, feature_mapper):
        """Vérifie que 35.0 devient '35'."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "val", 35.0)
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}val")
        assert enfant is not None
        assert enfant.text == "35"

    def test_add_property_float_decimal(self, feature_mapper):
        """Vérifie que 35.5 reste '35.5'."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "val", 35.5)
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}val")
        assert enfant is not None
        assert enfant.text == "35.5"

    def test_add_property_int(self, feature_mapper):
        """Vérifie la conversion int → string."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "val", 42)
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}val")
        assert enfant is not None
        assert enfant.text == "42"

    def test_add_property_avec_uom(self, feature_mapper):
        """Vérifie l'ajout de l'attribut uom."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_propriete(parent, "section", 150, "mm-2")
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}section")
        assert enfant is not None
        assert enfant.get("uom") == "mm-2"

    def test_add_reference(self, feature_mapper):
        """Vérifie l'ajout d'une référence xlink:href."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_reference(parent, "ref", "id_cible")
        enfant = parent.find(f"{{{NAMESPACE_RECOSTAR}}}ref")
        assert enfant is not None
        assert enfant.get(f"{{{NAMESPACE_XLINK}}}href") == "id_cible"

    def test_add_reference_vide_ignore(self, feature_mapper):
        """Vérifie que _ajouter_reference ignore les href vides."""
        parent = ET.Element("parent")
        feature_mapper._ajouter_reference(parent, "ref", "")
        assert len(parent) == 0

    def test_get_unique_geom_id(self, feature_mapper):
        """Vérifie la génération d'IDs de géométrie uniques."""
        id1 = feature_mapper._obtenir_id_geom_unique("RPD_Coffret_Reco", "coffret_0")
        id2 = feature_mapper._obtenir_id_geom_unique("RPD_Coffret_Reco", "coffret_0")
        assert id1 == "coffret_0.geom0"
        assert id2 == "coffret_0.geom1"

    def test_get_unique_geom_id_types_differents(self, feature_mapper):
        """Vérifie que les compteurs sont indépendants par type."""
        id1 = feature_mapper._obtenir_id_geom_unique("TypeA", "a_0")
        id2 = feature_mapper._obtenir_id_geom_unique("TypeB", "b_0")
        assert id1 == "a_0.geom0"
        assert id2 == "b_0.geom0"


class TestFeatureMapperMappings:
    """Tests pour les méthodes de mapping de MappeurEntites."""

    def test_map_cable_electrique(self, feature_mapper, feature_cable_electrique):
        """Vérifie le mapping CableElectrique."""
        elem = feature_mapper.mapper_cable_electrique(feature_cable_electrique, "cable_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_CableElectrique_Reco"
        assert elem.get(f"{{{NAMESPACE_GML}}}id") == "cable_001"

    def test_map_cable_electrique_domaine_tension(self, feature_mapper, feature_cable_electrique):
        """Vérifie la propriété DomaineTension dans CableElectrique."""
        elem = feature_mapper.mapper_cable_electrique(feature_cable_electrique, "cable_001")
        dt = elem.find(f"{{{NAMESPACE_RECOSTAR}}}DomaineTension")
        assert dt is not None
        assert dt.text == "BT"

    def test_map_coffret(self, feature_mapper, feature_coffret):
        """Vérifie le mapping Coffret avec géométrie Point."""
        elem = feature_mapper.mapper_coffret(feature_coffret, "coffret_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Coffret_Reco"

    def test_map_coffret_geometrie(self, feature_mapper, feature_coffret):
        """Vérifie que le Coffret contient une géométrie."""
        elem = feature_mapper.mapper_coffret(feature_coffret, "coffret_001")
        geom = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        assert geom is not None

    def test_map_materiel(self, feature_mapper, feature_materiel):
        """Vérifie le mapping Materiel."""
        elem = feature_mapper.mapper_materiel(feature_materiel, "materiel_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Materiel_Reco"
        fab = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Fabricant")
        assert fab is not None
        assert fab.text == "Nexans"

    def test_map_materiel_numero_serie(self, feature_mapper, feature_materiel):
        """Vérifie la propriété NumeroSerie du Materiel."""
        elem = feature_mapper.mapper_materiel(feature_materiel, "materiel_001")
        ns = elem.find(f"{{{NAMESPACE_RECOSTAR}}}NumeroSerie")
        assert ns is not None
        assert ns.text == "SN001"

    def test_map_module_raccordement_balise_principale(self, feature_mapper):
        """Vérifie que le mapper produit la bonne balise et l'id."""
        feature = self._feature_module_raccordement()
        elem = feature_mapper.mapper_module_raccordement(feature, "module_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_ModuleRaccordement_Reco"
        assert elem.get(f"{{{NAMESPACE_GML}}}id") == "module_001"

    def test_map_module_raccordement_references(self, feature_mapper):
        """Vérifie la présence et l'href des références conteneur et noeudParent."""
        feature = self._feature_module_raccordement()
        elem = feature_mapper.mapper_module_raccordement(feature, "module_001")

        ns_xlink = f"{{{NAMESPACE_XLINK}}}href"
        cont = elem.find(f"{{{NAMESPACE_RECOSTAR}}}conteneur")
        noeud = elem.find(f"{{{NAMESPACE_RECOSTAR}}}noeudParent")
        reseau = elem.find(f"{{{NAMESPACE_RECOSTAR}}}reseau")

        assert reseau is not None and reseau.get(ns_xlink) == "Reseau"
        assert cont is not None and cont.get(ns_xlink) == "coffret_001"
        assert noeud is not None and noeud.get(ns_xlink) == "support_modules_001"

    def test_map_module_raccordement_proprietes(self, feature_mapper):
        """Vérifie Coupure, NbPlagesOccupees et Protection."""
        feature = self._feature_module_raccordement()
        elem = feature_mapper.mapper_module_raccordement(feature, "module_001")

        coupure = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Coupure")
        nb_plages = elem.find(f"{{{NAMESPACE_RECOSTAR}}}NbPlagesOccupees")
        protection = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Protection")

        assert coupure is not None and coupure.text == "true"
        assert nb_plages is not None and nb_plages.text == "4"
        assert protection is not None and protection.text == "false"

    def test_map_module_raccordement_ordre_xsd(self, feature_mapper):
        """L'ordre XSD strict doit être respecté (sequence Plage → ModuleRaccordement)."""
        feature = self._feature_module_raccordement()
        elem = feature_mapper.mapper_module_raccordement(feature, "module_001")

        ordre_attendu = (
            "reseau",
            "conteneur",
            "noeudParent",
            "Coupure",
            "NbPlagesOccupees",
            "Protection",
        )
        ordre_obtenu = tuple(child.tag.split("}", 1)[-1] for child in elem)
        assert ordre_obtenu == ordre_attendu

    def test_map_module_raccordement_sans_conteneur(self, feature_mapper):
        """Sans conteneur_href, la balise conteneur doit être absente."""
        feature = self._feature_module_raccordement()
        feature["properties"].pop("conteneur_href")
        elem = feature_mapper.mapper_module_raccordement(feature, "module_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}conteneur") is None

    @staticmethod
    def _feature_module_raccordement() -> dict:
        """Feature GeoJSON typique pour RPD_ModuleRaccordement_Reco."""
        return {
            "type": "Feature",
            "properties": {
                "id": "module_001",
                "fid": 1,
                "ogr_pkid": "RPD_ModuleRaccordement_Reco_0",
                "Coupure": "true",
                "NbPlagesOccupees": "4",
                "Protection": "false",
                "conteneur_href": "coffret_001",
                "noeudParent_href": "support_modules_001",
            },
            "geometry": None,
        }

    def test_map_jonction_sans_geometrie(self, feature_mapper):
        """Vérifie le mapping Jonction sans géométrie (conteneur existant)."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "jonc_001",
                "fid": 1,
                "ogr_pkid": "RPD_Jonction_Reco_0",
                "DomaineTension": "BT",
                "TypeJonction": "DERIVATION",
                "conteneur_href": "coffret_001",
            },
            "geometry": None,
        }
        elem = feature_mapper.mapper_jonction(feature, "jonc_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Jonction_Reco"
        geom = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        assert geom is None

    def test_map_aerien(self, feature_mapper):
        """Vérifie le mapping Aerien avec LineString."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "aerien_001",
                "fid": 1,
                "ogr_pkid": "RPD_Aerien_Reco_0",
                "ModePose": "FACADE",
                "PrecisionXY": "A",
                "PrecisionZ": "A",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0]],
            },
        }
        elem = feature_mapper.mapper_aerien(feature, "aerien_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Aerien_Reco"

    def test_map_support(self, feature_mapper):
        """Vérifie le mapping Support avec Point."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "support_001",
                "fid": 1,
                "ogr_pkid": "RPD_Support_Reco_0",
                "NatureSupport_href": "Poteau",
                "Matiere_href": "Beton",
                "PrecisionXY": "A",
                "PrecisionZ": "A",
            },
            "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        }
        elem = feature_mapper.mapper_support(feature, "support_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Support_Reco"

    def test_map_terre(self, feature_mapper):
        """Vérifie le mapping Terre."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "terre_001",
                "fid": 1,
                "ogr_pkid": "RPD_Terre_Reco_0",
                "NatureTerre_href": "Piquet",
                "Statut": "EN_SERVICE",
            },
            "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        }
        elem = feature_mapper.mapper_terre(feature, "terre_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Terre_Reco"

    def test_map_enceinte_cloturee(self, feature_mapper):
        """Vérifie le mapping EnceinteCloturee avec Point, PrecisionXY/Z et geometriesupplementaire."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "enc_001",
                "fid": 1,
                "ogr_pkid": "RPD_EnceinteCloturee_Reco_0",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "geometriesupplementaire_href": "geom_supp_001",
            },
            "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        }
        elem = feature_mapper.mapper_enceinte_cloturee(feature, "enc_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_EnceinteCloturee_Reco"
        geom = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        assert geom is not None
        prec_xy = elem.find(f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY")
        assert prec_xy is not None
        assert prec_xy.text == "A"
        prec_z = elem.find(f"{{{NAMESPACE_RECOSTAR}}}PrecisionZ")
        assert prec_z is not None
        assert prec_z.text == "B"

    def test_map_enceinte_cloturee_sans_geometrie(self, feature_mapper):
        """Vérifie le mapping EnceinteCloturee sans géométrie."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "enc_002",
                "fid": 2,
                "ogr_pkid": "RPD_EnceinteCloturee_Reco_1",
                "PrecisionXY": "C",
                "PrecisionZ": "D",
            },
            "geometry": None,
        }
        elem = feature_mapper.mapper_enceinte_cloturee(feature, "enc_002")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_EnceinteCloturee_Reco"
        geom = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        assert geom is None


# ============================================================
# Tests de GenerateurGML
# ============================================================


class TestGMLGenerator:
    """Tests pour la classe GenerateurGML."""

    def test_initialisation(self, gml_generator):
        """Vérifie l'initialisation du générateur."""
        assert gml_generator.srs == DEFAULT_SRS
        assert gml_generator.metadata == {}

    def test_set_metadata(self, gml_generator):
        """Vérifie la configuration des métadonnées."""
        gml_generator.definir_metadonnees("Lazio", "Producteur", "Responsable", "Nom")
        assert gml_generator.metadata["logiciel"] == "Lazio"
        assert gml_generator.metadata["producteur"] == "Producteur"
        assert "date" in gml_generator.metadata

    def test_set_metadata_met_a_jour_srs(self, gml_generator):
        """Vérifie que definir_metadonnees propage le SRS."""
        gml_generator.definir_metadonnees("L", "P", "R", "N", srs="EPSG:4326")
        assert gml_generator.srs == "EPSG:4326"
        assert gml_generator.mapper.srs == "EPSG:4326"
        assert gml_generator.mapper.geo_converter.srs == "EPSG:4326"


class TestGMLGeneratorRelations:
    """Tests pour l'extraction des relations."""

    def test_parse_cable_ids_simple(self, gml_generator):
        """Vérifie le parsing d'un ID unique."""
        result = gml_generator._analyser_ids_cable("cable_001")
        assert result == ["cable_001"]

    def test_parse_cable_ids_multiples(self, gml_generator):
        """Vérifie le parsing d'IDs séparés par des virgules."""
        result = gml_generator._analyser_ids_cable("c1, c2, c3")
        assert result == ["c1", "c2", "c3"]

    def test_parse_cable_ids_avec_espaces(self, gml_generator):
        """Vérifie le strip des espaces."""
        result = gml_generator._analyser_ids_cable("  c1 , c2  ")
        assert result == ["c1", "c2"]

    def test_parse_cable_ids_virgule_vide(self, gml_generator):
        """Vérifie que les entrées vides sont ignorées."""
        result = gml_generator._analyser_ids_cable("c1,,c2,")
        assert result == ["c1", "c2"]

    def test_extract_relations_from_features(self, gml_generator):
        """Vérifie l'extraction des relations câble depuis des features."""
        features = [
            {"properties": {"id": "aerien_001", "cables_href": "cable_001,cable_002"}},
            {"properties": {"id": "aerien_002", "cables_href": "cable_003"}},
        ]
        result = gml_generator._extraire_relations_depuis_entites(features)
        assert ("cable_001", "aerien_001") in result
        assert ("cable_002", "aerien_001") in result
        assert ("cable_003", "aerien_002") in result

    def test_extract_relations_from_features_sans_cables(self, gml_generator):
        """Vérifie l'extraction avec des features sans câbles."""
        features = [
            {"properties": {"id": "aerien_001"}},
            {"properties": {"id": "aerien_002", "cables_href": None}},
        ]
        result = gml_generator._extraire_relations_depuis_entites(features)
        assert result == []

    def test_extract_ouvrage_materiel_relations(self, gml_generator):
        """Vérifie l'extraction des relations ouvrage-matériel."""
        features_by_type = {
            "RPD_Jonction_Reco": [
                {"properties": {"id": "jonc_001", "materiel_href": "mat_001"}},
                {"properties": {"id": "jonc_002", "materiel_href": "mat_002"}},
            ]
        }
        result = gml_generator._extraire_relations_ouvrage_materiel(features_by_type)
        assert ("jonc_001", "mat_001") in result
        assert ("jonc_002", "mat_002") in result

    def test_extract_ouvrage_materiel_sans_jonctions(self, gml_generator):
        """Vérifie le résultat sans jonctions."""
        result = gml_generator._extraire_relations_ouvrage_materiel({})
        assert result == []

    def test_extract_relations_complet(self, gml_generator):
        """Vérifie l'extraction complète des 3 types de relations."""
        features_by_type = {
            "RPD_Aerien_Reco": [
                {"properties": {"id": "a1", "cables_href": "c1"}},
            ],
            "RPD_Jonction_Reco": [
                {
                    "properties": {
                        "id": "j1",
                        "cables_href": "c1",
                        "materiel_href": "m1",
                    }
                },
            ],
        }
        result = gml_generator._extraire_relations(features_by_type)
        assert "cheminement_cable" in result
        assert "cable_noeud" in result
        assert "ouvrage_materiel" in result

    def test_extract_relations_module_raccordement_cable_noeud(self, gml_generator):
        """RPD_ModuleRaccordement_Reco doit alimenter les relations cable_noeud."""
        features_by_type = {
            "RPD_ModuleRaccordement_Reco": [
                {"properties": {"id": "mr_001", "cables_href": "cable_xxx"}},
            ],
        }
        result = gml_generator._extraire_relations(features_by_type)
        assert ("cable_xxx", "mr_001") in result["cable_noeud"]

    def test_create_cable_noeud_relation(self, gml_generator):
        """Vérifie la création d'une relation cable-noeud."""
        member = gml_generator._creer_relation_cable_noeud("cable_001", "noeud_001")
        assert member.tag == f"{{{NAMESPACE_GML}}}featureMember"
        relation = member.find(f"{{{NAMESPACE_RECOSTAR}}}CableElectrique_NoeudReseau")
        assert relation is not None

    def test_create_cheminement_cable_relation(self, gml_generator):
        """Vérifie la création d'une relation cheminement-câble."""
        member = gml_generator._creer_relation_cheminement_cable("cable_001", "chemin_001")
        assert member.tag == f"{{{NAMESPACE_GML}}}featureMember"
        relation = member.find(f"{{{NAMESPACE_RECOSTAR}}}Cheminement_Cables")
        assert relation is not None

    def test_create_ouvrage_materiel_relation(self, gml_generator):
        """Vérifie la création d'une relation ouvrage-matériel."""
        member = gml_generator._creer_relation_ouvrage_materiel("ouvr_001", "mat_001")
        assert member.tag == f"{{{NAMESPACE_GML}}}featureMember"
        relation = member.find(f"{{{NAMESPACE_RECOSTAR}}}Ouvrage_Materiel")
        assert relation is not None


class TestGMLGeneratorMateriels:
    """Tests pour l'extraction et fusion des matériels."""

    def test_extract_materiels_from_jonctions(self, gml_generator):
        """Vérifie l'extraction des matériels depuis les jonctions."""
        jonctions = [
            {
                "properties": {
                    "id": "jonc_001",
                    "materiel_href": "mat_001",
                    "Fabricant": "Nexans",
                    "Modele": "ModelX",
                    "NumeroLot": "LOT01",
                    "NumeroSerie": "SN01",
                }
            }
        ]
        materiels, ids = gml_generator.extraire_materiels_depuis_jonctions(jonctions)
        assert len(materiels) == 1
        assert "mat_001" in ids
        assert materiels[0]["properties"]["Fabricant"] == "Nexans"

    def test_extract_materiels_sans_materiel_href(self, gml_generator):
        """Vérifie l'absence d'extraction sans materiel_href."""
        jonctions = [{"properties": {"id": "jonc_001", "Fabricant": "Nexans"}}]
        materiels, _ = gml_generator.extraire_materiels_depuis_jonctions(jonctions)
        assert len(materiels) == 0

    def test_extract_materiels_doublons_ignores(self, gml_generator):
        """Vérifie que les doublons de materiel_href sont ignorés."""
        jonctions = [
            {
                "properties": {
                    "id": "j1",
                    "materiel_href": "m1",
                    "Fabricant": "F",
                    "Modele": "M",
                    "NumeroLot": "L",
                    "NumeroSerie": "S",
                }
            },
            {
                "properties": {
                    "id": "j2",
                    "materiel_href": "m1",
                    "Fabricant": "F2",
                    "Modele": "M2",
                    "NumeroLot": "L2",
                    "NumeroSerie": "S2",
                }
            },
        ]
        materiels, _ = gml_generator.extraire_materiels_depuis_jonctions(jonctions)
        assert len(materiels) == 1

    def test_extract_materiels_champs_manquants(self, gml_generator):
        """Vérifie l'absence d'extraction si un champ requis est manquant."""
        jonctions = [
            {
                "properties": {
                    "id": "j1",
                    "materiel_href": "m1",
                    "Fabricant": "F",
                    # Modele, NumeroLot, NumeroSerie manquants
                }
            }
        ]
        materiels, _ = gml_generator.extraire_materiels_depuis_jonctions(jonctions)
        assert len(materiels) == 0

    def test_extract_materiels_liste_vide(self, gml_generator):
        """Vérifie le comportement avec une liste vide."""
        materiels, ids = gml_generator.extraire_materiels_depuis_jonctions([])
        assert materiels == []
        assert ids == set()

    def test_merge_materiels(self, gml_generator):
        """Vérifie la fusion des matériels extraits avec les existants."""
        features_by_type = {
            "RPD_Jonction_Reco": [
                {
                    "properties": {
                        "id": "j1",
                        "materiel_href": "m1",
                        "Fabricant": "F",
                        "Modele": "M",
                        "NumeroLot": "L",
                        "NumeroSerie": "S",
                    }
                }
            ],
            "RPD_Materiel_Reco": [],
        }
        gml_generator._fusionner_materiels(features_by_type)
        assert len(features_by_type["RPD_Materiel_Reco"]) == 1

    def test_merge_materiels_pas_de_doublon(self, gml_generator):
        """Vérifie que la fusion ne crée pas de doublons."""
        features_by_type = {
            "RPD_Jonction_Reco": [
                {
                    "properties": {
                        "id": "j1",
                        "materiel_href": "m1",
                        "Fabricant": "F",
                        "Modele": "M",
                        "NumeroLot": "L",
                        "NumeroSerie": "S",
                    }
                }
            ],
            "RPD_Materiel_Reco": [{"properties": {"id": "m1", "Fabricant": "Existe"}, "geometry": None}],
        }
        gml_generator._fusionner_materiels(features_by_type)
        assert len(features_by_type["RPD_Materiel_Reco"]) == 1


class TestGMLGeneratorXMLOutput:
    """Tests pour la génération de membres XML."""

    def test_create_metadata_member(self, gml_generator):
        """Vérifie la création du membre Metadata."""
        gml_generator.definir_metadonnees("Lazio", "Prod", "Resp", "Nom")
        member = gml_generator._creer_membre_metadonnees()
        assert member.tag == f"{{{NAMESPACE_GML}}}featureMember"
        metadata = member.find(f"{{{NAMESPACE_RECOSTAR}}}Metadata")
        assert metadata is not None

    def test_create_metadata_contient_logiciel(self, gml_generator):
        """Vérifie que Metadata contient le logiciel."""
        gml_generator.definir_metadonnees("Lazio", "Prod", "Resp", "Nom")
        member = gml_generator._creer_membre_metadonnees()
        metadata = member.find(f"{{{NAMESPACE_RECOSTAR}}}Metadata")
        logiciel = metadata.find(f"{{{NAMESPACE_RECOSTAR}}}Logiciel")
        assert logiciel is not None
        assert logiciel.text == "Lazio"

    def test_create_reseau_member(self, gml_generator):
        """Vérifie la création du membre ReseauUtilite."""
        gml_generator.definir_metadonnees("L", "P", "R", "N")
        member = gml_generator._creer_membre_reseau()
        assert member.tag == f"{{{NAMESPACE_GML}}}featureMember"
        reseau = member.find(f"{{{NAMESPACE_RECOSTAR}}}ReseauUtilite")
        assert reseau is not None

    def test_write_gml_file(self, gml_generator, tmp_path):
        """Vérifie l'écriture d'un fichier GML."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        output = tmp_path / "test.gml"
        gml_generator._ecrire_fichier_gml(root, output)
        assert output.exists()
        contenu = output.read_text(encoding="utf-8")
        assert '<?xml version="1.0"' in contenu
        assert "RecoStarElec v1.0" in contenu

    def test_generate_gml_fichier_cree(self, gml_generator, tmp_path):
        """Vérifie que generer_gml crée un fichier."""
        output = tmp_path / "output.gml"
        features = {"RPD_Coffret_Reco": []}
        gml_generator.generer_gml(features, output)
        assert output.exists()


# ============================================================
# Tests de la détection CRS
# ============================================================


class TestDetectionCRS:
    """Tests pour la détection automatique du CRS depuis les fichiers GeoJSON."""

    def test_extraction_crs_urn_standard(self, gml_generator):
        """Vérifie l'extraction d'un CRS au format URN OGC standard."""
        data = {
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::2154"},
            }
        }
        assert gml_generator._extraire_crs_geojson(data) == "EPSG:2154"

    def test_extraction_crs_epsg_4326(self, gml_generator):
        """Vérifie l'extraction du CRS EPSG:4326."""
        data = {
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
            }
        }
        assert gml_generator._extraire_crs_geojson(data) == "EPSG:4326"

    def test_extraction_crs_absent(self, gml_generator):
        """Vérifie le retour None si aucun CRS n'est déclaré."""
        assert gml_generator._extraire_crs_geojson({}) is None

    def test_extraction_crs_type_invalide(self, gml_generator):
        """Vérifie le retour None si le type CRS n'est pas 'name'."""
        data = {"crs": {"type": "link", "properties": {"href": "http://example.com"}}}
        assert gml_generator._extraire_crs_geojson(data) is None

    def test_extraction_crs_name_vide(self, gml_generator):
        """Vérifie le retour None si le champ name est vide."""
        data = {"crs": {"type": "name", "properties": {"name": ""}}}
        assert gml_generator._extraire_crs_geojson(data) is None

    def test_extraction_crs_urn_malformee(self, gml_generator):
        """Vérifie le retour None pour une URN trop courte."""
        data = {"crs": {"type": "name", "properties": {"name": "EPSG:2154"}}}
        assert gml_generator._extraire_crs_geojson(data) is None

    def test_charger_geojson_detecte_crs(self, gml_generator, tmp_path):
        """Vérifie que charger_fichiers_geojson retourne le CRS détecté."""
        import json

        geojson_data = {
            "type": "FeatureCollection",
            "name": "RPD_Coffret_Reco",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
            },
            "features": [
                {
                    "type": "Feature",
                    "properties": {"id": "c1"},
                    "geometry": {"type": "Point", "coordinates": [2.35, 48.86]},
                }
            ],
        }
        fichier = tmp_path / "RPD_Coffret_Reco.geojson"
        fichier.write_text(json.dumps(geojson_data), encoding="utf-8")

        features, crs = gml_generator.charger_fichiers_geojson(tmp_path)
        assert crs == "EPSG:4326"
        assert "RPD_Coffret_Reco" in features

    def test_charger_geojson_sans_crs(self, gml_generator, tmp_path):
        """Vérifie le retour None si aucun fichier ne déclare de CRS."""
        import json

        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"id": "c1"},
                    "geometry": {"type": "Point", "coordinates": [2.35, 48.86]},
                }
            ],
        }
        fichier = tmp_path / "RPD_Coffret_Reco.geojson"
        fichier.write_text(json.dumps(geojson_data), encoding="utf-8")

        features, crs = gml_generator.charger_fichiers_geojson(tmp_path)
        assert crs is None
        assert "RPD_Coffret_Reco" in features


# ============================================================
# Tests de l'héritage de géométrie via conteneur
# ============================================================


class TestHeritageGeometrieConteneur:
    """Tests pour l'enrichissement des entités sans géométrie via conteneur_href."""

    def test_cache_conteneurs_coffret(self, gml_generator):
        """Vérifie que le cache indexe les géométries des Coffret."""
        features_by_type = {
            "RPD_Coffret_Reco": [
                {
                    "properties": {"id": "coffret_001"},
                    "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 100.0]},
                }
            ],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        assert "coffret_001" in cache
        assert cache["coffret_001"]["type"] == "Point"

    def test_cache_conteneurs_types_multiples(self, gml_generator):
        """Vérifie que le cache indexe Coffret, Support et BatimentTechnique."""
        features_by_type = {
            "RPD_Coffret_Reco": [
                {
                    "properties": {"id": "c1"},
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                }
            ],
            "RPD_Support_Reco": [
                {
                    "properties": {"id": "s1"},
                    "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
                }
            ],
            "RPD_BatimentTechnique_Reco": [
                {
                    "properties": {"id": "b1"},
                    "geometry": {"type": "Point", "coordinates": [5.0, 6.0]},
                }
            ],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        assert len(cache) == 3

    def test_cache_conteneurs_inclut_enceinte_cloturee(self, gml_generator):
        """Vérifie que le cache indexe aussi EnceinteCloturee comme conteneur."""
        features_by_type = {
            "RPD_Coffret_Reco": [
                {
                    "properties": {"id": "c1"},
                    "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                }
            ],
            "RPD_EnceinteCloturee_Reco": [
                {
                    "properties": {"id": "e1"},
                    "geometry": {"type": "Point", "coordinates": [7.0, 8.0]},
                }
            ],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        assert len(cache) == 2
        assert "e1" in cache
        assert cache["e1"]["type"] == "Point"

    def test_cache_conteneurs_ignore_sans_geometrie(self, gml_generator):
        """Vérifie que les conteneurs sans géométrie ne sont pas indexés."""
        features_by_type = {
            "RPD_Coffret_Reco": [{"properties": {"id": "c1"}, "geometry": None}],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        assert len(cache) == 0

    def test_enrichir_point_comptage(self, gml_generator):
        """Vérifie l'enrichissement d'un PointDeComptage sans géométrie."""
        geom_conteneur = {"type": "Point", "coordinates": [2.0, 48.0, 100.0]}
        features_by_type = {
            "RPD_Coffret_Reco": [{"properties": {"id": "coffret_001"}, "geometry": geom_conteneur}],
            "RPD_PointDeComptage_Reco": [
                {
                    "properties": {"id": "pdc_001", "conteneur_href": "coffret_001"},
                    "geometry": None,
                }
            ],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        gml_generator._enrichir_geometries_depuis_conteneurs(features_by_type, cache)

        pdc = features_by_type["RPD_PointDeComptage_Reco"][0]
        assert pdc["geometry"] is not None
        assert pdc["geometry"]["type"] == "Point"
        assert pdc["geometry"]["coordinates"] == [2.0, 48.0, 100.0]

    def test_enrichir_jonction_sans_conteneur(self, gml_generator):
        """Vérifie qu'une entité sans conteneur_href reste inchangée."""
        features_by_type = {
            "RPD_Jonction_Reco": [{"properties": {"id": "j1"}, "geometry": None}],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        gml_generator._enrichir_geometries_depuis_conteneurs(features_by_type, cache)

        assert features_by_type["RPD_Jonction_Reco"][0]["geometry"] is None

    def test_enrichir_preserve_geometrie_existante(self, gml_generator):
        """Vérifie qu'une entité avec géométrie propre n'est pas écrasée."""
        geom_propre = {"type": "Point", "coordinates": [1.0, 1.0]}
        geom_conteneur = {"type": "Point", "coordinates": [9.0, 9.0]}
        features_by_type = {
            "RPD_Coffret_Reco": [{"properties": {"id": "c1"}, "geometry": geom_conteneur}],
            "RPD_Jonction_Reco": [
                {
                    "properties": {"id": "j1", "conteneur_href": "c1"},
                    "geometry": geom_propre,
                }
            ],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        gml_generator._enrichir_geometries_depuis_conteneurs(features_by_type, cache)

        assert features_by_type["RPD_Jonction_Reco"][0]["geometry"] == geom_propre

    def test_enrichir_tous_types_noeuds(self, gml_generator):
        """Vérifie l'enrichissement pour tous les types de noeuds supportés."""
        geom = {"type": "Point", "coordinates": [2.0, 48.0]}
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
        features_by_type = {
            "RPD_Coffret_Reco": [{"properties": {"id": "c1"}, "geometry": geom}],
        }
        for t in types_noeuds:
            features_by_type[t] = [
                {
                    "properties": {"id": f"{t}_1", "conteneur_href": "c1"},
                    "geometry": None,
                }
            ]

        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        gml_generator._enrichir_geometries_depuis_conteneurs(features_by_type, cache)

        for t in types_noeuds:
            assert features_by_type[t][0]["geometry"] == geom, f"{t} non enrichi"

    def test_enrichir_conteneur_inconnu(self, gml_generator):
        """Vérifie qu'un conteneur_href inexistant ne provoque pas d'erreur."""
        features_by_type = {
            "RPD_PointDeComptage_Reco": [
                {
                    "properties": {"id": "pdc_1", "conteneur_href": "inexistant"},
                    "geometry": None,
                }
            ],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        gml_generator._enrichir_geometries_depuis_conteneurs(features_by_type, cache)

        assert features_by_type["RPD_PointDeComptage_Reco"][0]["geometry"] is None


# ============================================================
# Tests complémentaires des mappers et du CLI
# ============================================================


class TestFeatureMapperMappingsComplements:
    """Tests complémentaires pour les méthodes mapper_* peu couvertes."""

    @staticmethod
    def _feature(properties, geometry=None):
        """Crée une Feature GeoJSON de test."""
        return {"type": "Feature", "properties": properties, "geometry": geometry}

    @staticmethod
    def _href(elem, name):
        """Retourne l'attribut xlink:href d'un enfant RecoStaR."""
        child = elem.find(f"{{{NAMESPACE_RECOSTAR}}}{name}")
        assert child is not None
        return child.get(f"{{{NAMESPACE_XLINK}}}href")

    @staticmethod
    def _text(elem, name):
        """Retourne le texte d'un enfant RecoStaR."""
        child = elem.find(f"{{{NAMESPACE_RECOSTAR}}}{name}")
        assert child is not None
        return child.text

    def test_map_cable_terre_complet(self, feature_mapper):
        """Vérifie le mapping complet de RPD_CableTerre_Reco."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_CableTerre_Reco_0",
                "noeudreseau_href": "terre_001",
                "Commentaire": "terre principale",
                "FonctionCable_href": "MALT",
                "Materiau": "Cuivre",
                "NatureCableTerre_href": "Nu",
                "Section": 25.0,
                "Section_uom": "mm-2",
                "Statut": "EN_SERVICE",
            }
        )
        elem = feature_mapper.mapper_cable_terre(feature, "ct_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_CableTerre_Reco"
        assert self._href(elem, "noeudReseau") == "terre_001"
        assert self._href(elem, "FonctionCable") == "MALT"
        assert self._text(elem, "Materiau") == "Cuivre"
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Section").get("uom") == "mm-2"

    def test_map_fourreau_complet(self, feature_mapper):
        """Vérifie le mapping Fourreau avec mesures et géométrie LineString."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_Fourreau_Reco_0",
                "CoupeType": "T1",
                "DiametreDuFourreau": 63,
                "DiametreDuFourreau_uom": "mm",
                "EtatCoupeType": "BON",
                "Materiau": "PEHD",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "ProfondeurMinNonReg": 0.8,
                "ProfondeurMinNonReg_uom": "m",
            },
            {"type": "LineString", "coordinates": [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]]},
        )
        elem = feature_mapper.mapper_fourreau(feature, "fourreau_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Fourreau_Reco"
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}LineString") is not None
        assert self._text(elem, "Materiau") == "PEHD"
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}ProfondeurMinNonReg").get("uom") == "m"

    def test_map_geometrie_supplementaire_ligne_et_surface(self, feature_mapper):
        """Vérifie Ligne2.5D et Surface2.5D dans GeometrieSupplementaire."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_GeometrieSupplementaire_Reco_0",
                "Ligne2.5D": "LINESTRING (0 0 1, 1 1 2)",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
            },
            {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            },
        )
        elem = feature_mapper.mapper_geometrie_supplementaire(feature, "geom_001")
        ligne = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Ligne2.5D/{{{NAMESPACE_GML}}}LineString")
        surface = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Surface2.5D/{{{NAMESPACE_GML}}}Polygon")
        assert ligne is not None
        assert ligne.find(f"{{{NAMESPACE_GML}}}posList").text == "0 0 1  1 1 2"
        assert surface is not None
        assert self._text(elem, "PrecisionXY") == "A"

    def test_ajouter_ligne_2_5d_ignore_coordonnees_invalides(self, feature_mapper):
        """Vérifie qu'une Ligne2.5D invalide n'ajoute pas d'élément."""
        elem = ET.Element("parent")
        feature_mapper._ajouter_ligne_2_5d(elem, "1 2", "geom")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Ligne2.5D") is None

    def test_map_jonction_avec_geometrie_et_angle(self, feature_mapper):
        """Vérifie le mapping Jonction avec géométrie propre et angle."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_Jonction_Reco_0",
                "DomaineTension": "BT",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "Statut": "EN_SERVICE",
                "TypeJonction": "DERIVATION",
                "angle": 45,
            },
            {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        )
        elem = feature_mapper.mapper_jonction(feature, "jonc_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}Point") is not None
        assert self._text(elem, "angle") == "45"

    def test_map_coupe_circuit_a_fusibles_conteneur(self, feature_mapper):
        """Vérifie le mapping CoupeCircuitAFusibles avec conteneur."""
        feature = self._feature({"conteneur_href": "coffret_001", "Statut": "EN_SERVICE"})
        elem = feature_mapper.mapper_coupe_circuit_a_fusibles(feature, "ccf_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_CoupeCircuitAFusibles_Reco"
        assert self._href(elem, "conteneur") == "coffret_001"
        assert self._text(elem, "Statut") == "EN_SERVICE"

    def test_map_point_comptage_avec_geometrie(self, feature_mapper):
        """Vérifie le mapping PointDeComptage avec NumeroPRM et géométrie."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_PointDeComptage_Reco_0",
                "conteneur_href": "coffret_001",
                "NumeroPRM": "12345678901234",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "Statut": "EN_SERVICE",
            },
            {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        )
        elem = feature_mapper.mapper_point_comptage(feature, "pc_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}Point") is not None
        assert self._text(elem, "NumeroPRM") == "12345678901234"

    def test_map_point_leve_complet(self, feature_mapper):
        """Vérifie le mapping PointLeve avec mesure Leve et précisions numériques."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_PointLeveOuvrageReseau_Reco_0",
                "Leve": 120.5,
                "Leve_uom": "m",
                "NumeroPoint": "P001",
                "PrecisionXYnum": 2,
                "PrecisionZnum": 3,
                "Producteur": "Prod",
                "TypeLeve": "GPS",
            },
            {"type": "Point", "coordinates": [2.0, 48.0, 120.5]},
        )
        elem = feature_mapper.mapper_point_leve(feature, "pl_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}Point") is not None
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Leve").get("uom") == "m"
        assert self._text(elem, "NumeroPoint") == "P001"

    def test_map_pleine_terre_complet(self, feature_mapper):
        """Vérifie le mapping PleineTerre avec LineString et profondeur."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_PleineTerre_Reco_0",
                "CoupeType": "CT",
                "EtatCoupeType": "OK",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "ProfondeurMinNonReg": 0.7,
                "ProfondeurMinNonReg_uom": "m",
            },
            {"type": "LineString", "coordinates": [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]]},
        )
        elem = feature_mapper.mapper_pleine_terre(feature, "pt_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}LineString") is not None
        assert self._text(elem, "EtatCoupeType") == "OK"

    def test_map_batiment_technique_complet(self, feature_mapper):
        """Vérifie le mapping BatimentTechnique."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_BatimentTechnique_Reco_0",
                "geometriesupplementaire_href": "gs_1",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
            },
            {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        )
        elem = feature_mapper.mapper_batiment_technique(feature, "bat_001")
        assert self._href(elem, "geometriesupplementaire") == "gs_1"
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}Point") is not None

    def test_map_poste_electrique_complet(self, feature_mapper):
        """Vérifie le mapping PosteElectrique avec propriétés et références."""
        feature = self._feature(
            {
                "conteneur_href": "bat_001",
                "Categorie_href": "HTA_BT",
                "Code": "P001",
                "InformationSupplementaire": "info",
                "Statut": "EN_SERVICE",
                "TypePoste_href": "CABINE",
            }
        )
        elem = feature_mapper.mapper_poste_electrique(feature, "poste_001")
        assert self._href(elem, "conteneur") == "bat_001"
        assert self._href(elem, "Categorie") == "HTA_BT"
        assert self._text(elem, "Code") == "P001"

    def test_map_protection_mecanique_complet(self, feature_mapper):
        """Vérifie le mapping ProtectionMecanique."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_ProtectionMecanique_Reco_0",
                "CoupeType": "CT",
                "EtatCoupeType": "OK",
                "Materiau": "Béton",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "ProfondeurMinNonReg": 1.1,
                "ProfondeurMinNonReg_uom": "m",
            },
            {"type": "LineString", "coordinates": [[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]]},
        )
        elem = feature_mapper.mapper_protection_mecanique(feature, "pm_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}LineString") is not None
        assert self._text(elem, "Materiau") == "Béton"

    def test_map_jeu_barres_et_support_modules(self, feature_mapper):
        """Vérifie les mappings JeuBarres et SupportModules."""
        jeu = feature_mapper.mapper_jeu_barres(
            self._feature({"conteneur_href": "coffret_001", "Statut": "EN_SERVICE"}),
            "jb_001",
        )
        support_modules = feature_mapper.mapper_support_modules(
            self._feature(
                {
                    "conteneur_href": "coffret_001",
                    "NombrePlages": 8,
                    "Statut": "EN_SERVICE",
                }
            ),
            "sm_001",
        )
        assert self._href(jeu, "conteneur") == "coffret_001"
        assert self._text(jeu, "Statut") == "EN_SERVICE"
        assert self._text(support_modules, "NombrePlages") == "8"

    def test_map_ouvrage_collectif_branchement_avec_geometrie(self, feature_mapper):
        """Vérifie le mapping OuvrageCollectifBranchement avec géométrie propre."""
        feature = self._feature(
            {
                "ogr_pkid": "RPD_OuvrageCollectifBranchement_Reco_0",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "Statut": "EN_SERVICE",
            },
            {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        )
        elem = feature_mapper.mapper_ouvrage_collectif_branchement(feature, "ocb_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie/{{{NAMESPACE_GML}}}Point") is not None
        assert self._text(elem, "Statut") == "EN_SERVICE"


class TestGeoJSONToRecostarCLI:
    """Tests de la fonction main() du module geojson_to_recostar."""

    def test_main_repertoire_inexistant_quitte_en_erreur(self, monkeypatch, tmp_path, capsys):
        """Vérifie l'erreur si le répertoire d'entrée n'existe pas."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "geojson_to_recostar.py",
                str(tmp_path / "absent"),
                str(tmp_path / "out.gml"),
            ],
        )
        with pytest.raises(SystemExit) as exc:
            g2r.main()
        assert exc.value.code == 1
        assert "n'existe pas" in capsys.readouterr().err

    def test_main_entree_pas_un_repertoire(self, monkeypatch, tmp_path, capsys):
        """Vérifie l'erreur si l'entrée n'est pas un répertoire."""
        entree = tmp_path / "input.geojson"
        entree.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "sys.argv",
            ["geojson_to_recostar.py", str(entree), str(tmp_path / "out.gml")],
        )
        with pytest.raises(SystemExit) as exc:
            g2r.main()
        assert exc.value.code == 1
        assert "n'est pas un répertoire" in capsys.readouterr().err

    def test_main_aucun_geojson_quitte_en_erreur(self, monkeypatch, tmp_path, capsys):
        """Vérifie l'erreur si aucun fichier RPD_* n'est chargé."""

        class FauxGenerateur:
            def __init__(self, srs=None):
                self.srs = srs

            def charger_fichiers_geojson(self, input_dir):
                return {}, None

        monkeypatch.setattr(g2r, "GenerateurGML", FauxGenerateur)
        monkeypatch.setattr(
            "sys.argv",
            ["geojson_to_recostar.py", str(tmp_path), str(tmp_path / "out.gml")],
        )
        with pytest.raises(SystemExit) as exc:
            g2r.main()
        assert exc.value.code == 1
        assert "Aucun fichier GeoJSON" in capsys.readouterr().err

    def test_main_succes_crs_force(self, monkeypatch, tmp_path, capsys):
        """Vérifie un succès complet avec CRS forcé par l'utilisateur."""
        appels = []

        class FauxGenerateur:
            def __init__(self, srs=None):
                self.srs = srs
                appels.append(("init", srs))

            def charger_fichiers_geojson(self, input_dir):
                return {"RPD_Coffret_Reco": [{"properties": {"id": "c1"}}]}, "EPSG:4326"

            def definir_metadonnees(self, **kwargs):
                appels.append(("metadata", kwargs))

            def generer_gml(self, features, output_file, remplacer_ids=False):
                appels.append(("generer", features, output_file))
                output_file.write_text("<gml/>", encoding="utf-8")

        monkeypatch.setattr(g2r, "GenerateurGML", FauxGenerateur)
        output = tmp_path / "out.gml"
        monkeypatch.setattr(
            "sys.argv",
            [
                "geojson_to_recostar.py",
                str(tmp_path),
                str(output),
                "--srs",
                "EPSG:3949",
                "--logiciel",
                "L",
                "--producteur",
                "P",
                "--responsable",
                "R",
                "--nom",
                "N",
            ],
        )
        g2r.main()
        assert output.exists()
        assert ("init", "EPSG:3949") in appels
        assert "CRS forcé" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "crs_detecte,message",
        [("EPSG:4326", "CRS détecté"), (None, "Aucun CRS détecté")],
    )
    def test_main_succes_resolution_crs_detecte_ou_defaut(self, monkeypatch, tmp_path, capsys, crs_detecte, message):
        """Vérifie la résolution CRS détecté puis défaut."""

        class FauxGenerateur:
            def __init__(self, srs=None):
                self.srs = srs

            def charger_fichiers_geojson(self, input_dir):
                return {"RPD_Coffret_Reco": [{"properties": {"id": "c1"}}]}, crs_detecte

            def definir_metadonnees(self, **kwargs):
                self.metadata = kwargs

            def generer_gml(self, features, output_file, remplacer_ids=False):
                output_file.write_text("<gml/>", encoding="utf-8")

        monkeypatch.setattr(g2r, "GenerateurGML", FauxGenerateur)
        output = tmp_path / "out.gml"
        monkeypatch.setattr("sys.argv", ["geojson_to_recostar.py", str(tmp_path), str(output)])
        g2r.main()
        assert output.exists()
        assert message in capsys.readouterr().out

    def test_main_avec_option_id_passe_remplacer_ids(self, monkeypatch, tmp_path):
        """Vérifie que --id propage remplacer_ids=True à generer_gml."""
        appels = []

        class FauxGenerateur:
            def __init__(self, srs=None):
                self.srs = srs

            def charger_fichiers_geojson(self, input_dir):
                return {"RPD_Coffret_Reco": [{"properties": {"id": "c1"}}]}, None

            def definir_metadonnees(self, **kwargs):
                pass

            def generer_gml(self, features, output_file, remplacer_ids=False):
                appels.append(remplacer_ids)
                output_file.write_text("<gml/>", encoding="utf-8")

        monkeypatch.setattr(g2r, "GenerateurGML", FauxGenerateur)
        output = tmp_path / "out.gml"
        monkeypatch.setattr(
            "sys.argv",
            ["geojson_to_recostar.py", str(tmp_path), str(output), "--id"],
        )
        g2r.main()
        assert appels == [True]


# ============================================================
# Tests du remappage d'identifiants GML
# ============================================================


class TestRemappeurIds:
    """Tests unitaires de la classe RemappeurIds."""

    _UUID_RE = re.compile(r"^id[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def _elem_avec_gml_id(self, old_id: str) -> ET.Element:
        """Crée un élément XML minimal portant un gml:id."""
        elem = ET.Element("elem")
        elem.set(f"{{{NAMESPACE_GML}}}id", old_id)
        return elem

    def test_remanier_remplace_gml_id(self):
        """Vérifie que remanier remplace bien le gml:id."""
        root = self._elem_avec_gml_id("ancien_id")
        RemappeurIds().remanier(root)
        assert root.get(f"{{{NAMESPACE_GML}}}id") != "ancien_id"

    def test_remanier_format_uuid(self):
        """Vérifie que le nouvel id respecte le format id{uuid4}."""
        root = self._elem_avec_gml_id("ancien_id")
        RemappeurIds().remanier(root)
        nouvel_id = root.get(f"{{{NAMESPACE_GML}}}id") or ""
        assert self._UUID_RE.match(nouvel_id)

    def test_remanier_unicite_ids(self):
        """Vérifie que 5 éléments distincts reçoivent 5 UUIDs distincts."""
        root = ET.Element("root")
        for i in range(5):
            enfant = ET.SubElement(root, "elem")
            enfant.set(f"{{{NAMESPACE_GML}}}id", f"id_original_{i}")
        RemappeurIds().remanier(root)
        ids = [e.get(f"{{{NAMESPACE_GML}}}id") for e in root]
        assert len(set(ids)) == 5

    def test_remanier_href_sans_diese(self):
        """Vérifie la mise à jour d'un href direct (sans #)."""
        root = ET.Element("root")
        source = ET.SubElement(root, "source")
        source.set(f"{{{NAMESPACE_GML}}}id", "cible")
        ref = ET.SubElement(root, "ref")
        ref.set(f"{{{NAMESPACE_XLINK}}}href", "cible")
        RemappeurIds().remanier(root)
        nouvel_id = source.get(f"{{{NAMESPACE_GML}}}id")
        assert ref.get(f"{{{NAMESPACE_XLINK}}}href") == nouvel_id

    def test_remanier_href_avec_diese(self):
        """Vérifie la mise à jour d'un href avec préfixe #."""
        root = ET.Element("root")
        source = ET.SubElement(root, "source")
        source.set(f"{{{NAMESPACE_GML}}}id", "cible")
        ref = ET.SubElement(root, "ref")
        ref.set(f"{{{NAMESPACE_XLINK}}}href", "#cible")
        RemappeurIds().remanier(root)
        nouvel_id = source.get(f"{{{NAMESPACE_GML}}}id")
        assert ref.get(f"{{{NAMESPACE_XLINK}}}href") == f"#{nouvel_id}"

    def test_remanier_preserves_hrefs_externes(self):
        """Vérifie que les hrefs vers des ressources inconnues sont préservés."""
        root = ET.Element("root")
        ref = ET.SubElement(root, "ref")
        ref.set(f"{{{NAMESPACE_XLINK}}}href", "https://example.com/ressource")
        RemappeurIds().remanier(root)
        assert ref.get(f"{{{NAMESPACE_XLINK}}}href") == "https://example.com/ressource"

    def test_remanier_coherence_id_et_href(self):
        """Vérifie la cohérence entre gml:id renommé et href direct."""
        root = ET.Element("root")
        source = ET.SubElement(root, "source")
        source.set(f"{{{NAMESPACE_GML}}}id", "cible_originale")
        ref = ET.SubElement(root, "ref")
        ref.set(f"{{{NAMESPACE_XLINK}}}href", "cible_originale")
        RemappeurIds().remanier(root)
        assert source.get(f"{{{NAMESPACE_GML}}}id") == ref.get(f"{{{NAMESPACE_XLINK}}}href")

    def test_remanier_coherence_id_et_href_diese(self):
        """Vérifie la cohérence entre gml:id renommé et href avec #."""
        root = ET.Element("root")
        source = ET.SubElement(root, "source")
        source.set(f"{{{NAMESPACE_GML}}}id", "cible_originale")
        ref = ET.SubElement(root, "ref")
        ref.set(f"{{{NAMESPACE_XLINK}}}href", "#cible_originale")
        RemappeurIds().remanier(root)
        nouvel_id = source.get(f"{{{NAMESPACE_GML}}}id")
        assert ref.get(f"{{{NAMESPACE_XLINK}}}href") == f"#{nouvel_id}"

    def test_remanier_meme_id_partage_meme_uuid(self):
        """Vérifie que deux hrefs vers le même id partagent le même UUID."""
        root = ET.Element("root")
        source = ET.SubElement(root, "source")
        source.set(f"{{{NAMESPACE_GML}}}id", "cible")
        ref1 = ET.SubElement(root, "ref1")
        ref1.set(f"{{{NAMESPACE_XLINK}}}href", "cible")
        ref2 = ET.SubElement(root, "ref2")
        ref2.set(f"{{{NAMESPACE_XLINK}}}href", "cible")
        RemappeurIds().remanier(root)
        assert ref1.get(f"{{{NAMESPACE_XLINK}}}href") == ref2.get(f"{{{NAMESPACE_XLINK}}}href")

    def test_generer_gml_sans_remplacer_ids_preserve_id(self, gml_generator, tmp_path):
        """Vérifie que l'id original est présent dans la sortie sans le flag."""
        gml_generator.definir_metadonnees("L", "P", "R", "N")
        output = tmp_path / "out.gml"
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "coffret_test_001",
                        "fid": 1,
                        "ogr_pkid": "RPD_Coffret_Reco_0",
                        "FonctionCoffret": "Distribution",
                        "PrecisionXY": "A",
                        "PrecisionZ": "A",
                    },
                    "geometry": {"type": "Point", "coordinates": [2.35, 48.86, 100.0]},
                }
            ]
        }
        gml_generator.generer_gml(features, output)
        assert "coffret_test_001" in output.read_text(encoding="utf-8")

    def test_generer_gml_avec_remplacer_ids_supprime_ancien_id(self, gml_generator, tmp_path):
        """Vérifie que l'id original est absent de la sortie avec le flag."""
        gml_generator.definir_metadonnees("L", "P", "R", "N")
        output = tmp_path / "out.gml"
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "coffret_test_002",
                        "fid": 1,
                        "ogr_pkid": "RPD_Coffret_Reco_0",
                        "FonctionCoffret": "Distribution",
                        "PrecisionXY": "A",
                        "PrecisionZ": "A",
                    },
                    "geometry": {"type": "Point", "coordinates": [2.35, 48.86, 100.0]},
                }
            ]
        }
        gml_generator.generer_gml(features, output, remplacer_ids=True)
        assert "coffret_test_002" not in output.read_text(encoding="utf-8")

    def test_generer_gml_avec_remplacer_ids_format_uuid(self, gml_generator, tmp_path):
        """Vérifie que les ids de la sortie respectent le format id{uuid4} avec le flag."""
        gml_generator.definir_metadonnees("L", "P", "R", "N")
        output = tmp_path / "out.gml"
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "coffret_test_003",
                        "fid": 1,
                        "ogr_pkid": "RPD_Coffret_Reco_0",
                        "FonctionCoffret": "Distribution",
                        "PrecisionXY": "A",
                        "PrecisionZ": "A",
                    },
                    "geometry": {"type": "Point", "coordinates": [2.35, 48.86, 100.0]},
                }
            ]
        }
        gml_generator.generer_gml(features, output, remplacer_ids=True)
        contenu = output.read_text(encoding="utf-8")
        ids_trouves = re.findall(
            r'gml:id="(id[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
            contenu,
        )
        assert len(ids_trouves) > 0


# ============================================================
# Tests de mapper_galerie
# ============================================================


class TestMapperGalerie:
    """Tests pour MappeurEntites.mapper_galerie (RPD_Galerie_Reco)."""

    def _feature_galerie(self, avec_profondeur: bool = False, avec_geometrie: bool = True) -> dict:
        """Crée une feature GeoJSON Galerie pour les tests."""
        props = {
            "id": "galerie_001",
            "fid": 1,
            "ogr_pkid": "RPD_Galerie_Reco_line_0",
            "Hauteur": 2.5,
            "Hauteur_uom": "m",
            "Largeur": 1.2,
            "Largeur_uom": "m",
            "PrecisionXY": "A",
            "PrecisionZ": "B",
        }
        if avec_profondeur:
            props["ProfondeurMinNonReg"] = 0.8
            props["ProfondeurMinNonReg_uom"] = "m"
        geometry = (
            {
                "type": "LineString",
                "coordinates": [
                    [600000.0, 6800000.0, 100.0],
                    [600020.0, 6800020.0, 101.0],
                ],
            }
            if avec_geometrie
            else None
        )
        return {"type": "Feature", "properties": props, "geometry": geometry}

    def test_required_rpd_files_contient_galerie(self):
        """RPD_Galerie_Reco doit figurer dans REQUIRED_RPD_FILES."""
        assert "RPD_Galerie_Reco" in REQUIRED_RPD_FILES

    def test_mapper_galerie_tag_element(self, feature_mapper):
        """Vérifie le tag de l'élément racine."""
        feature = self._feature_galerie()
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Galerie_Reco"

    def test_mapper_galerie_gml_id(self, feature_mapper):
        """Vérifie que gml:id est correctement positionné."""
        feature = self._feature_galerie()
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        assert elem.get(f"{{{NAMESPACE_GML}}}id") == "galerie_001"

    def test_mapper_galerie_geometrie_presente(self, feature_mapper):
        """Vérifie la présence de la balise Geometrie avec un LineString."""
        feature = self._feature_galerie()
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        geom_elem = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        assert geom_elem is not None
        ls = geom_elem.find(f"{{{NAMESPACE_GML}}}LineString")
        assert ls is not None

    def test_mapper_galerie_geometrie_absente_si_none(self, feature_mapper):
        """Vérifie qu'aucune balise Geometrie n'est produite si geometry=None."""
        feature = self._feature_galerie(avec_geometrie=False)
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        geom_elem = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        assert geom_elem is None

    def test_mapper_galerie_hauteur_avec_uom(self, feature_mapper):
        """Vérifie la présence et l'unité de la balise Hauteur."""
        feature = self._feature_galerie()
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        hauteur_elem = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Hauteur")
        assert hauteur_elem is not None
        assert hauteur_elem.get("uom") == "m"
        assert hauteur_elem.text == "2.5"

    def test_mapper_galerie_largeur_avec_uom(self, feature_mapper):
        """Vérifie la présence et l'unité de la balise Largeur."""
        feature = self._feature_galerie()
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        largeur_elem = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Largeur")
        assert largeur_elem is not None
        assert largeur_elem.get("uom") == "m"
        assert largeur_elem.text == "1.2"

    def test_mapper_galerie_precision_presentes(self, feature_mapper):
        """Vérifie la présence de PrecisionXY et PrecisionZ."""
        feature = self._feature_galerie()
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY") is not None
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}PrecisionZ") is not None

    def test_mapper_galerie_profondeur_presente_si_fournie(self, feature_mapper):
        """Vérifie que ProfondeurMinNonReg apparaît avec son uom quand fournie."""
        feature = self._feature_galerie(avec_profondeur=True)
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        prof_elem = elem.find(f"{{{NAMESPACE_RECOSTAR}}}ProfondeurMinNonReg")
        assert prof_elem is not None
        assert prof_elem.get("uom") == "m"

    def test_mapper_galerie_profondeur_absente_si_none(self, feature_mapper):
        """Vérifie l'absence de ProfondeurMinNonReg quand non renseignée."""
        feature = self._feature_galerie(avec_profondeur=False)
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}ProfondeurMinNonReg") is None

    def test_mapper_galerie_dans_type_mappers(self, gml_generator):
        """Vérifie que la méthode mapper_galerie est disponible sur le mapper."""
        assert hasattr(gml_generator.mapper, "mapper_galerie")
        assert callable(gml_generator.mapper.mapper_galerie)
