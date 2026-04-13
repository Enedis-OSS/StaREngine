import pytest
from xml.etree import ElementTree as ET

from geojson_to_recostar import (
    ElementGML,
    ConvertisseurGeometrie,
    MappeurEntites,
    GenerateurGML,
    NAMESPACE_GML,
    NAMESPACE_RECOSTAR,
    NAMESPACE_XLINK,
    DEFAULT_SRS,
    NS_MAP,
    REQUIRED_RPD_FILES,
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
        elem = feature_mapper.mapper_cable_electrique(
            feature_cable_electrique, "cable_001"
        )
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_CableElectrique_Reco"
        assert elem.get(f"{{{NAMESPACE_GML}}}id") == "cable_001"

    def test_map_cable_electrique_domaine_tension(
        self, feature_mapper, feature_cable_electrique
    ):
        """Vérifie la propriété DomaineTension dans CableElectrique."""
        elem = feature_mapper.mapper_cable_electrique(
            feature_cable_electrique, "cable_001"
        )
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

    def test_create_cable_noeud_relation(self, gml_generator):
        """Vérifie la création d'une relation cable-noeud."""
        member = gml_generator._creer_relation_cable_noeud("cable_001", "noeud_001")
        assert member.tag == f"{{{NAMESPACE_GML}}}featureMember"
        relation = member.find(f"{{{NAMESPACE_RECOSTAR}}}CableElectrique_NoeudReseau")
        assert relation is not None

    def test_create_cheminement_cable_relation(self, gml_generator):
        """Vérifie la création d'une relation cheminement-câble."""
        member = gml_generator._creer_relation_cheminement_cable(
            "cable_001", "chemin_001"
        )
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
            "RPD_Materiel_Reco": [
                {"properties": {"id": "m1", "Fabricant": "Existe"}, "geometry": None}
            ],
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
            "RPD_Coffret_Reco": [
                {"properties": {"id": "coffret_001"}, "geometry": geom_conteneur}
            ],
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
            "RPD_Coffret_Reco": [
                {"properties": {"id": "c1"}, "geometry": geom_conteneur}
            ],
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
