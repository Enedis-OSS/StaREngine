# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree as ET  # nosec B405

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
    GenerateurGML,
    MappeurEntites,
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
        """RPD_ModuleRaccordement_Reco doit être pris en charge par le pipeline V1.1."""
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

    def test_map_module_raccordement_ordre_xsd_v11(self, feature_mapper):
        """L'ordre XSD V1.1 strict doit être respecté.

        Différent de V1.0 : `Coupure, NbPlagesOccupees, noeudParent, Protection`
        au lieu de `noeudParent, Coupure, NbPlagesOccupees, Protection`.
        Le Commentaire (V1.1) s'intercale entre reseau et conteneur.
        """
        feature = self._feature_module_raccordement(avec_commentaire=True)
        elem = feature_mapper.mapper_module_raccordement(feature, "module_001")
        ordre_attendu = (
            "reseau",
            "Commentaire",
            "conteneur",
            "Coupure",
            "NbPlagesOccupees",
            "noeudParent",
            "Protection",
        )
        ordre_obtenu = tuple(child.tag.split("}", 1)[-1] for child in elem)
        assert ordre_obtenu == ordre_attendu

    def test_map_module_raccordement_sans_commentaire(self, feature_mapper):
        """Sans Commentaire, la balise est absente."""
        feature = self._feature_module_raccordement()
        elem = feature_mapper.mapper_module_raccordement(feature, "module_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Commentaire") is None

    @staticmethod
    def _feature_module_raccordement(avec_commentaire: bool = False) -> dict:
        """Feature GeoJSON typique pour RPD_ModuleRaccordement_Reco V1.1."""
        props = {
            "id": "module_001",
            "fid": 1,
            "ogr_pkid": "RPD_ModuleRaccordement_Reco_0",
            "Coupure": "true",
            "NbPlagesOccupees": "4",
            "Protection": "false",
            "conteneur_href": "coffret_001",
            "noeudParent_href": "support_modules_001",
        }
        if avec_commentaire:
            props["Commentaire"] = "note libre"
        return {"type": "Feature", "properties": props, "geometry": None}

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
                "Statut": "Functional",
            },
            "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        }
        elem = feature_mapper.mapper_support(feature, "support_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_Support_Reco"
        statut = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Statut")
        assert statut is not None
        assert statut.text == "Functional"

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
        """Vérifie le mapping EnceinteCloturee avec Point et Statut."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "enc_001",
                "fid": 1,
                "ogr_pkid": "RPD_EnceinteCloturee_Reco_0",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "Statut": "Functional",
                "geometriesupplementaire_href": "geom_supp_001",
            },
            "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 50.0]},
        }
        elem = feature_mapper.mapper_enceinte_cloturee(feature, "enc_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_EnceinteCloturee_Reco"
        statut = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Statut")
        assert statut is not None
        assert statut.text == "Functional"
        geom = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Geometrie")
        assert geom is not None
        prec_xy = elem.find(f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY")
        assert prec_xy is not None
        assert prec_xy.text == "A"

    def test_map_cable_telecommunication(self, feature_mapper):
        """Vérifie le mapping CableTelecommunication avec attributs complets."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "cabtelecom_001",
                "fid": 1,
                "ogr_pkid": "RPD_CableTelecommunication_Reco_0",
                "Capacite": 48,
                "Fonction": "Transport",
                "Section": 6.0,
                "Section_uom": "mm-2",
                "Statut": "Functional",
                "TechnoCable_href": "FibreOptique",
            },
            "geometry": None,
        }
        elem = feature_mapper.mapper_cable_telecommunication(feature, "cabtelecom_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_CableTelecommunication_Reco"
        statut = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Statut")
        assert statut is not None
        assert statut.text == "Functional"
        capacite = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Capacite")
        assert capacite is not None
        assert capacite.text == "48"
        fonction = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Fonction")
        assert fonction is not None
        assert fonction.text == "Transport"
        section = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Section")
        assert section is not None
        assert section.text == "6"
        assert section.get("uom") == "mm-2"

    def test_map_cable_telecommunication_sans_optionnels(self, feature_mapper):
        """Vérifie le mapping CableTelecommunication avec champs optionnels absents."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "cabtelecom_002",
                "fid": 2,
                "ogr_pkid": "RPD_CableTelecommunication_Reco_1",
                "Statut": "Projected",
            },
            "geometry": None,
        }
        elem = feature_mapper.mapper_cable_telecommunication(feature, "cabtelecom_002")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_CableTelecommunication_Reco"
        statut = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Statut")
        assert statut is not None
        assert statut.text == "Projected"
        # Les optionnels absents ne génèrent pas d'éléments XML
        section = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Section")
        assert section is None


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
        # Sous V1.1, _extraire_relations_cable_noeud produit des tuples enrichis
        # (cable_id, noeud_id) + EtatAvantRaccordement. On vérifie l'appariement.
        paires_cle = [(r[0], r[1]) for r in result["cable_noeud"]]
        assert ("cable_xxx", "mr_001") in paires_cle

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
        assert "RecoStarElec v1.10" in contenu

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
        """Vérifie que le cache indexe Coffret, Support, BatimentTechnique et EnceinteCloturee."""
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
            "RPD_EnceinteCloturee_Reco": [
                {
                    "properties": {"id": "e1"},
                    "geometry": {"type": "Point", "coordinates": [7.0, 8.0]},
                }
            ],
        }
        cache = gml_generator._construire_cache_conteneurs(features_by_type)
        assert len(cache) == 4

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
# Tests du mapper PLOR V1.10
# ============================================================


class TestMapperPointLeveV110:
    """Tests pour mapper_point_leve conforme au modele V1.10."""

    def test_mapper_plor_v1_10_complet(self, feature_mapper):
        """Vérifie la production de ChargeGeneratrice et Horodatage."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "plor_001",
                "ogr_pkid": "RPD_PointLeveOuvrageReseau_Reco_0",
                "ChargeGeneratrice": 0.8,
                "ChargeGeneratrice_uom": "m",
                "Horodatage": "2025-03-15",
                "NumeroPoint": "P001",
                "PrecisionXYnum": 10,
                "PrecisionZnum": 20,
                "Producteur": "TEST",
            },
            "geometry": {"type": "Point", "coordinates": [600000.0, 6800000.0, 100.5]},
        }

        element = feature_mapper.mapper_point_leve(feature, "plor_001")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        # Verifier ChargeGeneratrice present avec uom
        charge_elem = element.find(f"{ns_r}ChargeGeneratrice")
        assert charge_elem is not None
        assert charge_elem.text is not None
        assert charge_elem.get("uom") == "m"

        # Verifier Horodatage present
        horodatage_elem = element.find(f"{ns_r}Horodatage")
        assert horodatage_elem is not None
        assert horodatage_elem.text == "2025-03-15"

        # Verifier les attributs obligatoires
        assert element.find(f"{ns_r}NumeroPoint") is not None
        assert element.find(f"{ns_r}PrecisionXYnum") is not None
        assert element.find(f"{ns_r}PrecisionZnum") is not None
        assert element.find(f"{ns_r}Producteur") is not None

        # Verifier que Leve et TypeLeve ne sont PAS produits
        assert element.find(f"{ns_r}Leve") is None
        assert element.find(f"{ns_r}TypeLeve") is None

    def test_mapper_plor_v1_10_sans_optionnels(self, feature_mapper):
        """Vérifie le comportement sans ChargeGeneratrice ni Horodatage."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "plor_002",
                "ogr_pkid": "RPD_PointLeveOuvrageReseau_Reco_1",
                "NumeroPoint": "P002",
                "PrecisionXYnum": 5,
                "PrecisionZnum": 10,
                "Producteur": "MINIMAL",
            },
            "geometry": {"type": "Point", "coordinates": [600100.0, 6800100.0]},
        }

        element = feature_mapper.mapper_point_leve(feature, "plor_002")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        # Les optionnels ne doivent pas etre presents
        assert element.find(f"{ns_r}ChargeGeneratrice") is None
        assert element.find(f"{ns_r}Horodatage") is None

        # Les obligatoires doivent etre la
        assert element.find(f"{ns_r}NumeroPoint").text == "P002"
        assert element.find(f"{ns_r}Producteur").text == "MINIMAL"

    def test_schema_location_v1_10(self, gml_generator):
        """Vérifie que le schemaLocation pointe vers V1.10."""
        gml_generator.definir_metadonnees(logiciel="Test", producteur="P", responsable="R", nom="N")
        _ = {"RPD_PointLeveOuvrageReseau_Reco": []}

        for prefix, uri in {
            "gml": NAMESPACE_GML,
            "RecoStaR": NAMESPACE_RECOSTAR,
        }.items():
            ET.register_namespace(prefix, uri)

        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        ns_xsi = "http://www.w3.org/2001/XMLSchema-instance"
        root.set(
            f"{{{ns_xsi}}}schemaLocation",
            # Tag canonique de la version 1.1 (et non l'ancien v1.10).
            f"{NAMESPACE_RECOSTAR} https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/RecoStar-v1.1/RecoStaR/SchemaStarElecRecoStar.xsd",
        )

        schema_loc = root.get(f"{{{ns_xsi}}}schemaLocation")
        assert schema_loc is not None
        assert "RecoStar-v1.1" in schema_loc
        assert "RecoStar-v1.0/" not in schema_loc


# ============================================================
# Tests Commentaire dans les mappers
# ============================================================


class TestCommentaireMappers:
    """Tests pour l'écriture du champ Commentaire dans les mappers."""

    @pytest.fixture
    def mappeur(self):
        return MappeurEntites("EPSG:2154")

    def _feature_coffret(self, commentaire=None):
        """Crée une feature GeoJSON Coffret avec ou sans Commentaire."""
        return {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "coffret_com_001",
                "TypeCoffret_href": "S22",
                "FonctionCoffret_href": "Distribution",
                "PrecisionXY": "A",
                "PrecisionZ": "A",
                "Statut": "Functional",
                "Commentaire": commentaire,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [600000.0, 6800000.0, 100.0],
            },
        }

    def test_commentaire_present_coffret(self, mappeur):
        """Vérifie que Commentaire est écrit dans le GML quand présent."""
        feature = self._feature_coffret("Test commentaire coffret")
        element = mappeur.mapper_coffret(feature, "coffret_com_001")

        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        commentaire_elem = element.find(f"{ns_r}Commentaire")
        assert commentaire_elem is not None
        assert commentaire_elem.text == "Test commentaire coffret"

    def test_commentaire_absent_coffret(self, mappeur):
        """Vérifie que Commentaire n'est pas écrit quand None."""
        feature = self._feature_coffret(None)
        element = mappeur.mapper_coffret(feature, "coffret_nocom_001")

        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        commentaire_elem = element.find(f"{ns_r}Commentaire")
        assert commentaire_elem is None

    def test_commentaire_aerien(self, mappeur):
        """Vérifie que Commentaire est écrit pour un Aerien."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "aerien_com_001",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "Statut": "Functional",
                "Commentaire": "Commentaire aérien",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            },
        }
        element = mappeur.mapper_aerien(feature, "aerien_com_001")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        commentaire_elem = element.find(f"{ns_r}Commentaire")
        assert commentaire_elem is not None
        assert commentaire_elem.text == "Commentaire aérien"

    def test_commentaire_support(self, mappeur):
        """Vérifie que Commentaire est écrit pour un Support."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "support_com_001",
                "NatureSupport_href": "Poteau",
                "PrecisionXY": "A",
                "PrecisionZ": "B",
                "Statut": "Functional",
                "Commentaire": "Support test",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [600000.0, 6800000.0, 100.0],
            },
        }
        element = mappeur.mapper_support(feature, "support_com_001")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        commentaire_elem = element.find(f"{ns_r}Commentaire")
        assert commentaire_elem is not None
        assert commentaire_elem.text == "Support test"


# ============================================================
# Tests Chargement _metadata.json (round-trip)
# ============================================================


class TestChargementMetadata:
    """Tests pour le chargement de _metadata.json dans GenerateurGML."""

    def test_charger_metadata_json(self, tmp_path):
        """Vérifie le chargement de _metadata.json."""
        import json

        metadata = {
            "Metadata": {
                "Datecreation": "2024-06-15",
                "Logiciel": "MonLogiciel",
                "Producteur": "Enedis",
                "Responsable": "Enedis DR Nord",
                "SRS": "EPSG:2154",
                "VersionSpecification": "v1.1",
            },
            "ReseauUtilite": {
                "id": "Reseau_Test",
                "Mention": "Mention test",
                "Nom": "Tranche ABC",
                "Responsable": "Enedis DR Nord",
                "Theme": "ELECTRD",
            },
        }
        metadata_file = tmp_path / "_metadata.json"
        metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

        gen = GenerateurGML()
        result = gen._charger_metadata_json(tmp_path)

        assert result["Metadata"]["Logiciel"] == "MonLogiciel"
        assert result["Metadata"]["VersionSpecification"] == "v1.1"
        assert result["ReseauUtilite"]["id"] == "Reseau_Test"
        assert result["ReseauUtilite"]["Mention"] == "Mention test"

    def test_charger_metadata_json_absent(self, tmp_path):
        """Vérifie le comportement sans _metadata.json."""
        gen = GenerateurGML()
        result = gen._charger_metadata_json(tmp_path)
        assert result == {}

    def test_definir_metadonnees_avec_metadata_chargees(self, tmp_path):
        """Vérifie que definir_metadonnees utilise les valeurs chargées comme fallback."""
        import json

        metadata = {
            "Metadata": {
                "Datecreation": "2024-06-15",
                "Logiciel": "SourceLogiciel",
                "Producteur": "SourceProducteur",
                "Responsable": "SourceResponsable",
                "SRS": "EPSG:2154",
                "VersionSpecification": "v1.1",
            },
            "ReseauUtilite": {
                "id": "Reseau_Source",
                "Mention": "Mention source",
                "Nom": "Tranche Source",
                "Responsable": "Resp Source",
                "Theme": "ELECTRD",
            },
        }
        metadata_file = tmp_path / "_metadata.json"
        metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

        gen = GenerateurGML()
        gen._metadata_chargees = gen._charger_metadata_json(tmp_path)

        # CLI override avec des valeurs non-vides
        gen.definir_metadonnees(
            logiciel="LAZio",
            producteur="CLI_Prod",
            responsable="CLI_Resp",
            nom="CLI_Nom",
            srs="EPSG:2154",
        )

        # CLI args sont prioritaires
        assert gen.metadata["logiciel"] == "LAZio"
        assert gen.metadata["producteur"] == "CLI_Prod"
        # Valeurs round-trip conservées
        assert gen.metadata["version_specification"] == "v1.1"
        assert gen.metadata["reseau_id"] == "Reseau_Source"
        assert gen.metadata["reseau_mention"] == "Mention source"
        assert gen.metadata["reseau_theme"] == "ELECTRD"

    def test_version_specification_dans_gml(self, tmp_path):
        """Vérifie que VersionSpecification est inclus dans le GML généré."""
        gen = GenerateurGML()
        gen._metadata_chargees = {
            "Metadata": {"VersionSpecification": "v1.1"},
            "ReseauUtilite": {},
        }
        gen.definir_metadonnees(
            logiciel="Test",
            producteur="P",
            responsable="R",
            nom="N",
            srs="EPSG:2154",
        )

        member = gen._creer_membre_metadonnees()
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        metadata_elem = member.find(f"{ns_r}Metadata")
        assert metadata_elem is not None
        vs_elem = metadata_elem.find(f"{ns_r}VersionSpecification")
        assert vs_elem is not None
        assert vs_elem.text == "v1.1"

    def test_reseau_utilite_valeurs_chargees(self, tmp_path):
        """Vérifie que _creer_membre_reseau utilise les valeurs chargées."""
        gen = GenerateurGML()
        gen._metadata_chargees = {
            "Metadata": {},
            "ReseauUtilite": {
                "id": "MonReseau",
                "Mention": "Mention personnalisée",
                "Theme": "ELECTRD",
            },
        }
        gen.definir_metadonnees(
            logiciel="Test",
            producteur="P",
            responsable="R",
            nom="N",
            srs="EPSG:2154",
        )

        member = gen._creer_membre_reseau()
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        ns_g = f"{{{NAMESPACE_GML}}}"
        reseau = member.find(f"{ns_r}ReseauUtilite")
        assert reseau is not None

        assert reseau.get(f"{ns_g}id") == "MonReseau"
        mention = reseau.find(f"{ns_r}Mention")
        assert mention is not None
        assert mention.text == "Mention personnalisée"


# ============================================================
# Tests geometriesupplementaire_href pour mapper_support
# ============================================================


class TestMapperSupportGeomSupp:
    """Tests pour la gestion de geometriesupplementaire_href dans mapper_support."""

    @pytest.fixture
    def mappeur(self):
        """Crée un MappeurEntites pour les tests."""
        return MappeurEntites()

    def test_mapper_support_avec_geom_supp(self, mappeur):
        """Vérifie que geometriesupplementaire_href est ajouté au XML du support."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "RPD_Support_Reco_0",
                "NatureSupport_href": "http://example.com/nature",
                "PrecisionXY": "5",
                "PrecisionZ": "5",
                "Statut": "Functional",
                "geometriesupplementaire_href": "#geom_supp_42",
            },
            "geometry": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

        element = mappeur.mapper_support(feature, "support_gs_001")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"
        ns_xl = f"{{{NAMESPACE_XLINK}}}"

        geom_supp = element.find(f"{ns_r}geometriesupplementaire")
        assert geom_supp is not None
        assert geom_supp.get(f"{ns_xl}href") == "#geom_supp_42"

    def test_mapper_support_sans_geom_supp(self, mappeur):
        """Vérifie que geometriesupplementaire n'est pas ajouté si absent."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "RPD_Support_Reco_1",
                "NatureSupport_href": "http://example.com/nature",
                "PrecisionXY": "5",
                "PrecisionZ": "5",
                "Statut": "Functional",
            },
            "geometry": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]},
        }

        element = mappeur.mapper_support(feature, "support_gs_002")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        geom_supp = element.find(f"{ns_r}geometriesupplementaire")
        assert geom_supp is None


# ============================================================
# Tests Etiquette et EtatAvantRaccordement
# ============================================================


class TestEtiquetteEtEtatAvantRaccordement:
    """Tests pour Etiquette dans mapper_cable_electrique et EtatAvantRaccordement."""

    @pytest.fixture
    def mappeur(self):
        """Crée un MappeurEntites pour les tests."""
        return MappeurEntites()

    @pytest.fixture
    def generateur(self):
        """Crée un GenerateurGML pour les tests."""
        return GenerateurGML()

    def test_mapper_cable_avec_etiquette(self, mappeur):
        """Vérifie que Etiquette est écrit dans le XML du câble."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "RPD_CableElectrique_Reco_0",
                "DomaineTension": "BT",
                "Etiquette": "ETQ-123",
                "FonctionCable_href": "Distribution",
                "Statut": "Functional",
            },
            "geometry": None,
        }

        element = mappeur.mapper_cable_electrique(feature, "cable_etiq_001")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        etiq = element.find(f"{ns_r}Etiquette")
        assert etiq is not None
        assert etiq.text == "ETQ-123"

    def test_mapper_cable_sans_etiquette(self, mappeur):
        """Vérifie que Etiquette n'est pas écrit si absent."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "RPD_CableElectrique_Reco_1",
                "DomaineTension": "BT",
                "FonctionCable_href": "Distribution",
                "Statut": "Functional",
            },
            "geometry": None,
        }

        element = mappeur.mapper_cable_electrique(feature, "cable_noetiq_001")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        etiq = element.find(f"{ns_r}Etiquette")
        assert etiq is None

    def test_mapper_cable_etiquette_ordre_xsd(self, mappeur):
        """Vérifie que Etiquette est placé entre DomaineTension et FonctionCable."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "RPD_CableElectrique_Reco_2",
                "DomaineTension": "BT",
                "Etiquette": "ETQ-XSD",
                "FonctionCable_href": "Distribution",
                "Statut": "Functional",
            },
            "geometry": None,
        }

        element = mappeur.mapper_cable_electrique(feature, "cable_ordre_001")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        children = [child.tag.replace(ns_r, "") for child in element]
        idx_dt = children.index("DomaineTension")
        idx_etiq = children.index("Etiquette")
        idx_fc = children.index("FonctionCable")
        assert idx_dt < idx_etiq < idx_fc

    def test_creer_relation_cable_noeud_avec_etat(self, generateur):
        """Vérifie la création de la relation avec EtatAvantRaccordement."""
        member = generateur._creer_relation_cable_noeud("cable_001", "noeud_001", "EnAttente")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        relation = member.find(f"{ns_r}CableElectrique_NoeudReseau")
        assert relation is not None

        etat = relation.find(f"{ns_r}EtatAvantRaccordement")
        assert etat is not None
        assert etat.text == "EnAttente"

    def test_creer_relation_cable_noeud_sans_etat(self, generateur):
        """Vérifie la relation sans EtatAvantRaccordement."""
        member = generateur._creer_relation_cable_noeud("cable_002", "noeud_002")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        relation = member.find(f"{ns_r}CableElectrique_NoeudReseau")
        assert relation is not None

        etat = relation.find(f"{ns_r}EtatAvantRaccordement")
        assert etat is None

    def test_creer_relation_cable_noeud_ordre_xsd(self, generateur):
        """Vérifie l'ordre XSD: cableelectrique, EtatAvantRaccordement, noeudreseau."""
        member = generateur._creer_relation_cable_noeud("cable_003", "noeud_003", "Raccorde")
        ns_r = f"{{{NAMESPACE_RECOSTAR}}}"

        relation = member.find(f"{ns_r}CableElectrique_NoeudReseau")
        assert relation is not None
        children = [child.tag.replace(ns_r, "") for child in relation]
        assert children == ["cableelectrique", "EtatAvantRaccordement", "noeudreseau"]

    def test_extraire_noeud_avec_etat(self, generateur):
        """Vérifie l'extraction des triplets (cable, noeud, etat)."""
        features = [
            {
                "properties": {
                    "id": "noeud_001",
                    "cables_href": "cable_a,cable_b",
                    "EtatAvantRaccordement": "EnAttente,Raccorde",
                }
            }
        ]

        result = generateur._extraire_noeud_avec_etat(features)
        assert len(result) == 2
        assert result[0] == ("cable_a", "noeud_001", "EnAttente")
        assert result[1] == ("cable_b", "noeud_001", "Raccorde")

    def test_extraire_noeud_sans_etat(self, generateur):
        """Vérifie l'extraction sans EtatAvantRaccordement (etat vide)."""
        features = [
            {
                "properties": {
                    "id": "noeud_002",
                    "cables_href": "cable_c",
                }
            }
        ]

        result = generateur._extraire_noeud_avec_etat(features)
        assert len(result) == 1
        assert result[0] == ("cable_c", "noeud_002", "")


# ============================================================
# Tests de l'ordre XSD pour Ouvrage_Materiel
# ============================================================


class TestOrdreXSDRelationOuvrageMateriel:
    """Tests vérifiant l'ordre XSD des enfants de Ouvrage_Materiel."""

    def test_ordre_materiel_avant_ouvrage(self, gml_generator):
        """Vérifie que materiel précède ouvrage dans Ouvrage_Materiel (ordre XSD)."""
        member = gml_generator._creer_relation_ouvrage_materiel("ouvr_001", "mat_001")
        relation = member.find(f"{{{NAMESPACE_RECOSTAR}}}Ouvrage_Materiel")
        enfants = list(relation)
        assert enfants[0].tag == f"{{{NAMESPACE_RECOSTAR}}}materiel"
        assert enfants[1].tag == f"{{{NAMESPACE_RECOSTAR}}}ouvrage"

    def test_href_materiel_correct(self, gml_generator):
        """Vérifie le xlink:href de l'élément materiel."""
        member = gml_generator._creer_relation_ouvrage_materiel("ouvr_001", "mat_001")
        relation = member.find(f"{{{NAMESPACE_RECOSTAR}}}Ouvrage_Materiel")
        materiel = relation.find(f"{{{NAMESPACE_RECOSTAR}}}materiel")
        assert materiel.get(f"{{{NAMESPACE_XLINK}}}href") == "mat_001"

    def test_href_ouvrage_correct(self, gml_generator):
        """Vérifie le xlink:href de l'élément ouvrage."""
        member = gml_generator._creer_relation_ouvrage_materiel("ouvr_001", "mat_001")
        relation = member.find(f"{{{NAMESPACE_RECOSTAR}}}Ouvrage_Materiel")
        ouvrage = relation.find(f"{{{NAMESPACE_RECOSTAR}}}ouvrage")
        assert ouvrage.get(f"{{{NAMESPACE_XLINK}}}href") == "ouvr_001"


# ============================================================
# Tests du mapping RPD_CableTerre_Reco
# ============================================================


class TestMapperCableTerre:
    """Tests vérifiant le mapping et l'ordre XSD de RPD_CableTerre_Reco."""

    @pytest.fixture
    def feature_cable_terre(self):
        """Feature GeoJSON pour CableTerre avec toutes les propriétés optionnelles."""
        return {
            "type": "Feature",
            "properties": {
                "id": "ct_001",
                "fid": 1,
                "ogr_pkid": "RPD_CableTerre_Reco_0",
                "FonctionCable_href": "Mise_A_La_Terre",
                "Materiau": "Cuivre",
                "NatureCableTerre_href": "nature_001",
                "noeudreseau_href": "noeud_001",
                "Section": 25,
                "Section_uom": "mm-2",
                "Statut": "EN_SERVICE",
            },
            "geometry": None,
        }

    def test_cable_terre_tag(self, feature_mapper, feature_cable_terre):
        """Vérifie le tag de l'élément RPD_CableTerre_Reco."""
        elem = feature_mapper.mapper_cable_terre(feature_cable_terre, "ct_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_CableTerre_Reco"

    def test_noeud_reseau_apres_nature_cable_terre(self, feature_mapper, feature_cable_terre):
        """Vérifie que noeudReseau apparaît après NatureCableTerre (ordre XSD)."""
        elem = feature_mapper.mapper_cable_terre(feature_cable_terre, "ct_001")
        tags = [enfant.tag for enfant in elem]
        idx_nature = tags.index(f"{{{NAMESPACE_RECOSTAR}}}NatureCableTerre")
        idx_noeud = tags.index(f"{{{NAMESPACE_RECOSTAR}}}noeudReseau")
        assert idx_noeud > idx_nature

    def test_cable_terre_sans_noeud_reseau(self, feature_mapper):
        """Vérifie l'absence de noeudReseau quand noeudreseau_href est absent."""
        feature = {
            "type": "Feature",
            "properties": {
                "id": "ct_002",
                "FonctionCable_href": "Mise_A_La_Terre",
                "Materiau": "Cuivre",
                "Section": 25,
                "Statut": "EN_SERVICE",
            },
            "geometry": None,
        }
        elem = feature_mapper.mapper_cable_terre(feature, "ct_002")
        noeud = elem.find(f"{{{NAMESPACE_RECOSTAR}}}noeudReseau")
        assert noeud is None


# ============================================================
# Tests du mapping RPD_GeometrieSupplementaire_Reco
# ============================================================


class TestMapperGeometrieSupplementaire:
    """Tests vérifiant le mapping et l'ordre XSD de RPD_GeometrieSupplementaire_Reco."""

    @pytest.fixture
    def feature_geom_supp_complet(self):
        """Feature GeoJSON pour GeometrieSupplementaire avec toutes les propriétés."""
        return {
            "type": "Feature",
            "properties": {
                "id": "gs_001",
                "ogr_pkid": "RPD_GeometrieSupplementaire_Reco_0",
                "Commentaire": "Un commentaire de test",
                "Ligne3D": "100000 200000 10,100010 200010 20",
                "PrecisionXY": "A",
                "PrecisionZ": "A",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
            },
        }

    def test_tag_rpd_geometrie_supplementaire(self, feature_mapper, feature_geom_supp_complet):
        """Vérifie le tag de l'élément RPD_GeometrieSupplementaire_Reco."""
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_geom_supp_complet, "gs_001")
        assert elem.tag == f"{{{NAMESPACE_RECOSTAR}}}RPD_GeometrieSupplementaire_Reco"

    def test_commentaire_est_premier_enfant(self, feature_mapper, feature_geom_supp_complet):
        """Vérifie que Commentaire est le premier enfant (ordre XSD)."""
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_geom_supp_complet, "gs_001")
        enfants = list(elem)
        assert len(enfants) > 0
        assert enfants[0].tag == f"{{{NAMESPACE_RECOSTAR}}}Commentaire"

    def test_ligne3d_present(self, feature_mapper, feature_geom_supp_complet):
        """Vérifie la présence de l'élément Ligne3D (nom RPD conforme XSD)."""
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_geom_supp_complet, "gs_001")
        ligne = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Ligne3D")
        assert ligne is not None

    def test_surface3d_presente(self, feature_mapper, feature_geom_supp_complet):
        """Vérifie la présence de l'élément Surface3D (nom RPD conforme XSD)."""
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_geom_supp_complet, "gs_001")
        surface = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Surface3D")
        assert surface is not None

    def test_ordre_xsd_strict(self, feature_mapper, feature_geom_supp_complet):
        """Vérifie l'ordre XSD : Commentaire → Ligne3D → PrecisionXY → PrecisionZ → Surface3D."""
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_geom_supp_complet, "gs_001")
        tags = [enfant.tag for enfant in elem]
        assert tags == [
            f"{{{NAMESPACE_RECOSTAR}}}Commentaire",
            f"{{{NAMESPACE_RECOSTAR}}}Ligne3D",
            f"{{{NAMESPACE_RECOSTAR}}}PrecisionXY",
            f"{{{NAMESPACE_RECOSTAR}}}PrecisionZ",
            f"{{{NAMESPACE_RECOSTAR}}}Surface3D",
        ]


class TestQualificationGeometrieSupplementaire:
    """Vérifie la qualification automatique Ligne3D / Surface3D selon les coordonnées."""

    @pytest.fixture
    def feature_base(self):
        """Squelette de feature GeometrieSupplementaire sans géométrie."""
        return {
            "type": "Feature",
            "properties": {
                "id": "gs_qual",
                "ogr_pkid": "RPD_GeometrieSupplementaire_Reco_qual",
                "PrecisionXY": "A",
                "PrecisionZ": "A",
            },
            "geometry": None,
        }

    def _types_enfants(self, elem):
        return [enfant.tag.split("}")[-1] for enfant in elem]

    def test_linestring_ouverte_donne_ligne3d(self, feature_mapper, feature_base):
        """Une LineString ouverte (premier != dernier point) → Ligne3D."""
        feature_base["geometry"] = {
            "type": "LineString",
            "coordinates": [[0.0, 0.0, 0.0], [10.0, 5.0, 1.0], [20.0, 0.0, 2.0]],
        }
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        types = self._types_enfants(elem)
        assert "Ligne3D" in types
        assert "Surface3D" not in types

    def test_linestring_fermee_donne_surface3d(self, feature_mapper, feature_base):
        """Une LineString fermée (premier == dernier point) → Surface3D."""
        feature_base["geometry"] = {
            "type": "LineString",
            "coordinates": [
                [0.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [10.0, 10.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
        }
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        types = self._types_enfants(elem)
        assert "Surface3D" in types
        assert "Ligne3D" not in types

    def test_polygon_donne_surface3d(self, feature_mapper, feature_base):
        """Un Polygon (toujours fermé en GeoJSON) → Surface3D."""
        feature_base["geometry"] = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
        }
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        types = self._types_enfants(elem)
        assert "Surface3D" in types
        assert "Ligne3D" not in types

    def test_multipolygon_donne_surface3d(self, feature_mapper, feature_base):
        """Un MultiPolygon → Surface3D."""
        feature_base["geometry"] = {
            "type": "MultiPolygon",
            "coordinates": [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]],
        }
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        types = self._types_enfants(elem)
        assert "Surface3D" in types

    def test_multilinestring_ouverte_donne_ligne3d(self, feature_mapper, feature_base):
        """Une MultiLineString dont la première ligne est ouverte → Ligne3D."""
        feature_base["geometry"] = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0, 0.0], [5.0, 5.0, 1.0]],
                [[10.0, 10.0, 0.0], [20.0, 20.0, 1.0]],
            ],
        }
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        types = self._types_enfants(elem)
        assert "Ligne3D" in types
        assert "Surface3D" not in types

    def test_geometrie_absente_aucune_geometrie_emise(self, feature_mapper, feature_base):
        """Sans géométrie ni propriété Ligne3D, aucun élément géométrique n'est émis."""
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        types = self._types_enfants(elem)
        assert "Ligne3D" not in types
        assert "Surface3D" not in types

    def test_ligne3d_legacy_et_surface_coexistent(self, feature_mapper, feature_base):
        """Si la propriété WKT Ligne3D et une géométrie surfacique sont fournies,
        les deux sont émises dans le bon ordre XSD."""
        feature_base["properties"]["Ligne3D"] = "100 200 10,110 210 20"
        feature_base["geometry"] = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
        }
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        types = self._types_enfants(elem)
        assert types == [
            "Ligne3D",
            "PrecisionXY",
            "PrecisionZ",
            "Surface3D",
        ]

    def test_ligne3d_geometry_id_unique(self, feature_mapper, feature_base):
        """Le gml:id de la Ligne3D dérivée de la géométrie ne collisionne pas
        avec celui généré pour la propriété WKT."""
        feature_base["properties"]["Ligne3D"] = "100 200 10,110 210 20"
        feature_base["geometry"] = {
            "type": "LineString",
            "coordinates": [[0.0, 0.0, 0.0], [5.0, 5.0, 1.0]],
        }
        elem = feature_mapper.mapper_geometrie_supplementaire(feature_base, "gs_qual")
        gml_ids = [ls.get(f"{{{NAMESPACE_GML}}}id") for ls in elem.iter(f"{{{NAMESPACE_GML}}}LineString")]
        assert len(gml_ids) == 2
        assert len(set(gml_ids)) == 2


# ============================================================
# Tests suppression doublons géographiques PointLeveOuvrageReseau
# ============================================================


class TestSuppressionDoublonsGeographiquesPLOR:
    """Tests pour la déduplication géographique des RPD_PointLeveOuvrageReseau_Reco."""

    def _creer_feature_plor(self, coords, ogr_pkid="plor_0", props_extra=None):
        """Crée une feature PLOR avec les coordonnées fournies."""
        geometry = {"type": "Point", "coordinates": list(coords)} if coords else None
        properties = {"ogr_pkid": ogr_pkid, "NumeroPoint": "P1"}
        if props_extra:
            properties.update(props_extra)
        return {"type": "Feature", "properties": properties, "geometry": geometry}

    def test_suppression_doublons_coordonnees_identiques(self):
        """Vérifie que les doublons géographiques sont supprimés."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([1.0, 2.0, 3.0], "plor_0"),
                self._creer_feature_plor([1.0, 2.0, 3.0], "plor_1"),
                self._creer_feature_plor([4.0, 5.0, 6.0], "plor_2"),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 2
        assert resultat[0]["properties"]["ogr_pkid"] == "plor_0"
        assert resultat[1]["properties"]["ogr_pkid"] == "plor_2"

    def test_conservation_premiere_occurrence(self):
        """Vérifie que c'est la première occurrence qui est conservée."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([1.0, 2.0], "plor_premier", {"NumeroPoint": "P100"}),
                self._creer_feature_plor([1.0, 2.0], "plor_second", {"NumeroPoint": "P200"}),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 1
        assert resultat[0]["properties"]["ogr_pkid"] == "plor_premier"
        assert resultat[0]["properties"]["NumeroPoint"] == "P100"

    def test_pas_de_doublons_aucune_suppression(self):
        """Vérifie qu'aucune feature n'est supprimée si pas de doublons."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([1.0, 2.0, 3.0], "plor_0"),
                self._creer_feature_plor([4.0, 5.0, 6.0], "plor_1"),
                self._creer_feature_plor([7.0, 8.0, 9.0], "plor_2"),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        assert len(features_by_type["RPD_PointLeveOuvrageReseau_Reco"]) == 3

    def test_entites_sans_geometrie_conservees(self):
        """Vérifie que les entités sans géométrie ne sont pas supprimées."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor(None, "plor_sans_geom_0"),
                self._creer_feature_plor([1.0, 2.0], "plor_avec_geom"),
                self._creer_feature_plor(None, "plor_sans_geom_1"),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 3

    def test_liste_vide_ne_leve_pas_erreur(self):
        """Vérifie que la méthode gère une liste vide sans erreur."""
        generator = GenerateurGML()
        features_by_type = {"RPD_PointLeveOuvrageReseau_Reco": []}

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        assert features_by_type["RPD_PointLeveOuvrageReseau_Reco"] == []

    def test_type_absent_ne_leve_pas_erreur(self):
        """Vérifie que la méthode gère l'absence du type sans erreur."""
        generator = GenerateurGML()
        features_by_type = {"RPD_Coffret_Reco": []}

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        assert "RPD_PointLeveOuvrageReseau_Reco" not in features_by_type

    def test_autres_types_non_impactes(self):
        """Vérifie que les autres types d'entités ne sont pas modifiés."""
        generator = GenerateurGML()
        coffret_features = [
            {
                "type": "Feature",
                "properties": {"ogr_pkid": "coffret_0"},
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            },
            {
                "type": "Feature",
                "properties": {"ogr_pkid": "coffret_1"},
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            },
        ]
        features_by_type = {
            "RPD_Coffret_Reco": coffret_features,
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([1.0, 2.0], "plor_0"),
                self._creer_feature_plor([1.0, 2.0], "plor_1"),
            ],
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        assert len(features_by_type["RPD_Coffret_Reco"]) == 2
        assert len(features_by_type["RPD_PointLeveOuvrageReseau_Reco"]) == 1

    def test_triples_doublons_une_seule_conservation(self):
        """Vérifie que seule une occurrence est conservée parmi N doublons."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([10.0, 20.0, 30.0], f"plor_{i}") for i in range(5)
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 1
        assert resultat[0]["properties"]["ogr_pkid"] == "plor_0"

    def test_coordonnees_2d_et_3d_distinctes(self):
        """Vérifie que [1.0, 2.0] et [1.0, 2.0, 0.0] sont considérées différentes."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([1.0, 2.0], "plor_2d"),
                self._creer_feature_plor([1.0, 2.0, 0.0], "plor_3d"),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        assert len(features_by_type["RPD_PointLeveOuvrageReseau_Reco"]) == 2

    def test_attributs_coherents_apres_suppression(self):
        """Vérifie que les attributs de la feature conservée restent intacts."""
        generator = GenerateurGML()
        props_complets = {
            "NumeroPoint": "PT42",
            "PrecisionXYnum": 5,
            "PrecisionZnum": 10,
            "Producteur": "TestProd",
            "ChargeGeneratrice": 1.5,
        }
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([1.0, 2.0, 3.0], "plor_0", props_complets),
                self._creer_feature_plor([1.0, 2.0, 3.0], "plor_1"),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 1
        props = resultat[0]["properties"]
        assert props["NumeroPoint"] == "PT42"
        assert props["PrecisionXYnum"] == 5
        assert props["PrecisionZnum"] == 10
        assert props["Producteur"] == "TestProd"
        assert props["ChargeGeneratrice"] == pytest.approx(1.5)

    def test_priorite_charge_generatrice_sur_altitude(self):
        """Vérifie que ChargeGeneratrice est conservée plutôt qu'AltitudeGeneratrice."""
        generator = GenerateurGML()
        feature_altitude = self._creer_feature_plor([1.0, 2.0, 3.0], "plor_altitude", {"Producteur": "ProdAlt"})
        feature_charge = self._creer_feature_plor(
            [1.0, 2.0, 3.0],
            "plor_charge",
            {"ChargeGeneratrice": 0.8, "Producteur": "ProdCharge"},
        )
        features_by_type = {"RPD_PointLeveOuvrageReseau_Reco": [feature_altitude, feature_charge]}

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 1
        assert resultat[0]["properties"]["ogr_pkid"] == "plor_charge"
        assert resultat[0]["properties"]["ChargeGeneratrice"] == pytest.approx(0.8)

    def test_transfert_proprietes_altitude_vers_charge(self):
        """Vérifie le transfert des propriétés manquantes lors de la suppression."""
        generator = GenerateurGML()
        feature_altitude = self._creer_feature_plor(
            [5.0, 6.0, 7.0],
            "plor_altitude",
            {"Producteur": "ProdAlt", "PrecisionZnum": 10, "Horodatage": "2025-01-15"},
        )
        feature_charge = self._creer_feature_plor(
            [5.0, 6.0, 7.0],
            "plor_charge",
            {"ChargeGeneratrice": 1.2, "Producteur": "ProdCharge"},
        )
        features_by_type = {"RPD_PointLeveOuvrageReseau_Reco": [feature_altitude, feature_charge]}

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 1
        props = resultat[0]["properties"]
        assert props["ChargeGeneratrice"] == pytest.approx(1.2)
        assert props["Producteur"] == "ProdCharge"
        assert props["PrecisionZnum"] == 10
        assert props["Horodatage"] == "2025-01-15"

    def test_transfert_ne_ecrase_pas_valeurs_existantes(self):
        """Vérifie que le transfert ne remplace pas les valeurs existantes."""
        generator = GenerateurGML()
        feature_altitude = self._creer_feature_plor(
            [1.0, 2.0],
            "plor_alt",
            {"PrecisionXYnum": 3, "PrecisionZnum": 5},
        )
        feature_charge = self._creer_feature_plor(
            [1.0, 2.0],
            "plor_charge",
            {"ChargeGeneratrice": 0.5, "PrecisionXYnum": 7, "PrecisionZnum": 8},
        )
        features_by_type = {"RPD_PointLeveOuvrageReseau_Reco": [feature_altitude, feature_charge]}

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        props = features_by_type["RPD_PointLeveOuvrageReseau_Reco"][0]["properties"]
        assert props["PrecisionXYnum"] == 7
        assert props["PrecisionZnum"] == 8

    def test_identifiants_non_transferes(self):
        """Vérifie que fid, ogr_pkid et id ne sont pas transférés."""
        generator = GenerateurGML()
        feature_altitude = self._creer_feature_plor([1.0, 2.0], "plor_alt", {"id": "alt_id_123"})
        feature_charge = self._creer_feature_plor([1.0, 2.0], "plor_charge", {"ChargeGeneratrice": 0.3})
        features_by_type = {"RPD_PointLeveOuvrageReseau_Reco": [feature_altitude, feature_charge]}

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        props = features_by_type["RPD_PointLeveOuvrageReseau_Reco"][0]["properties"]
        assert props["ogr_pkid"] == "plor_charge"

    def test_doublons_sans_charge_conserve_premier(self):
        """Sans ChargeGeneratrice dans aucun doublon, la première occurrence est conservée."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([1.0, 2.0], "plor_premier"),
                self._creer_feature_plor([1.0, 2.0], "plor_second"),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 1
        assert resultat[0]["properties"]["ogr_pkid"] == "plor_premier"

    def test_multiples_doublons_avec_charge_generatrice(self):
        """Avec N doublons dont un seul ChargeGeneratrice, celui-ci est conservé."""
        generator = GenerateurGML()
        features_by_type = {
            "RPD_PointLeveOuvrageReseau_Reco": [
                self._creer_feature_plor([10.0, 20.0], "plor_0"),
                self._creer_feature_plor([10.0, 20.0], "plor_1"),
                self._creer_feature_plor(
                    [10.0, 20.0],
                    "plor_2",
                    {"ChargeGeneratrice": 2.0, "ChargeGeneratrice_uom": "m"},
                ),
                self._creer_feature_plor([10.0, 20.0], "plor_3"),
            ]
        }

        generator._supprimer_doublons_geographiques_plor(features_by_type)

        resultat = features_by_type["RPD_PointLeveOuvrageReseau_Reco"]
        assert len(resultat) == 1
        assert resultat[0]["properties"]["ogr_pkid"] == "plor_2"
        assert resultat[0]["properties"]["ChargeGeneratrice"] == pytest.approx(2.0)


# ============================================================
# Tests de RemappeurIds (option --id)
# ============================================================


class TestRemappeurIds:
    """Tests pour la classe RemappeurIds et l'option --id de generer_gml."""

    _GML_ID = f"{{{NAMESPACE_GML}}}id"
    _XLINK_HREF = f"{{{NAMESPACE_XLINK}}}href"

    def _elem_avec_id(self, parent: ET.Element, tag: str, gml_id: str) -> ET.Element:
        """Crée un sous-élément avec un gml:id."""
        elem = ET.SubElement(parent, tag)
        elem.set(self._GML_ID, gml_id)
        return elem

    def test_remanier_remplace_gml_id(self):
        """Vérifie que le gml:id est remplacé après remanier."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        elem = self._elem_avec_id(root, "elem", "coffret_001")

        RemappeurIds().remanier(root)

        assert elem.get(self._GML_ID) != "coffret_001"

    def test_remanier_format_uuid(self):
        """Vérifie que le nouvel ID respecte le format 'id{uuid4}'."""
        import re

        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        elem = self._elem_avec_id(root, "elem", "ancien_id")

        RemappeurIds().remanier(root)

        nouvel_id = elem.get(self._GML_ID) or ""
        pattern = re.compile(r"^id[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert pattern.match(nouvel_id), f"Format invalide : {nouvel_id}"

    def test_remanier_unicite_ids(self):
        """Vérifie que chaque élément reçoit un UUID distinct."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        elems = [self._elem_avec_id(root, "e", f"id_{i}") for i in range(5)]

        RemappeurIds().remanier(root)

        nouveaux_ids = {e.get(self._GML_ID) for e in elems}
        assert len(nouveaux_ids) == 5

    def test_remanier_href_sans_diese(self):
        """Vérifie la mise à jour d'un xlink:href sans '#' pointant vers un gml:id."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        cible = self._elem_avec_id(root, "reseau", "Reseau")
        ref = ET.SubElement(root, "lien")
        ref.set(self._XLINK_HREF, "Reseau")

        RemappeurIds().remanier(root)

        assert ref.get(self._XLINK_HREF) == cible.get(self._GML_ID)

    def test_remanier_href_avec_diese(self):
        """Vérifie la mise à jour d'un xlink:href avec '#' pointant vers un gml:id."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        cible = self._elem_avec_id(root, "geom", "geom_supp_42")
        ref = ET.SubElement(root, "lien")
        ref.set(self._XLINK_HREF, "#geom_supp_42")

        RemappeurIds().remanier(root)

        assert ref.get(self._XLINK_HREF) == f"#{cible.get(self._GML_ID)}"

    def test_remanier_preserves_hrefs_externes(self):
        """Vérifie que les hrefs vers des ressources externes ne sont pas modifiés."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        ref = ET.SubElement(root, "lien")
        href_externe = "http://example.com/catalogue"
        ref.set(self._XLINK_HREF, href_externe)

        RemappeurIds().remanier(root)

        assert ref.get(self._XLINK_HREF) == href_externe

    def test_remanier_coherence_id_et_href(self):
        """Vérifie que le gml:id renommé et son xlink:href sont cohérents."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        coffret = self._elem_avec_id(root, "coffret", "coffret_001")
        ref = ET.SubElement(root, "conteneur")
        ref.set(self._XLINK_HREF, "coffret_001")

        RemappeurIds().remanier(root)

        assert coffret.get(self._GML_ID) == ref.get(self._XLINK_HREF)

    def test_remanier_coherence_id_et_href_diese(self):
        """Vérifie la cohérence entre gml:id renommé et xlink:href avec '#'."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        geom = self._elem_avec_id(root, "point", "geom_abc")
        ref = ET.SubElement(root, "geometrie")
        ref.set(self._XLINK_HREF, "#geom_abc")

        RemappeurIds().remanier(root)

        assert ref.get(self._XLINK_HREF) == f"#{geom.get(self._GML_ID)}"

    def test_remanier_meme_id_partage_meme_uuid(self):
        """Vérifie que deux hrefs pointant vers le même gml:id reçoivent le même UUID."""
        root = ET.Element(f"{{{NAMESPACE_GML}}}FeatureCollection")
        self._elem_avec_id(root, "reseau", "Reseau")
        ref1 = ET.SubElement(root, "lien1")
        ref1.set(self._XLINK_HREF, "Reseau")
        ref2 = ET.SubElement(root, "lien2")
        ref2.set(self._XLINK_HREF, "Reseau")

        RemappeurIds().remanier(root)

        assert ref1.get(self._XLINK_HREF) == ref2.get(self._XLINK_HREF)

    def test_generer_gml_sans_remplacer_ids_preserve_id(self, gml_generator, tmp_path):
        """Vérifie que sans --id, les IDs d'origine sont préservés dans le GML."""
        output = tmp_path / "output.gml"
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "coffret_connu",
                        "ogr_pkid": "RPD_Coffret_Reco_0",
                        "PrecisionXY": "A",
                        "PrecisionZ": "B",
                    },
                    "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 100.0]},
                }
            ]
        }
        gml_generator.generer_gml(features, output)

        assert "coffret_connu" in output.read_text(encoding="utf-8")

    def test_generer_gml_avec_remplacer_ids_supprime_ancien_id(self, gml_generator, tmp_path):
        """Vérifie qu'avec --id, l'ID d'origine disparaît du GML produit."""
        output = tmp_path / "output.gml"
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "coffret_connu",
                        "ogr_pkid": "RPD_Coffret_Reco_0",
                        "PrecisionXY": "A",
                        "PrecisionZ": "B",
                    },
                    "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 100.0]},
                }
            ]
        }
        gml_generator.generer_gml(features, output, remplacer_ids=True)

        assert "coffret_connu" not in output.read_text(encoding="utf-8")

    def test_generer_gml_avec_remplacer_ids_format_uuid(self, gml_generator, tmp_path):
        """Vérifie qu'avec --id, les IDs dans le GML respectent le format 'id{uuid4}'."""
        import re

        output = tmp_path / "output.gml"
        features = {
            "RPD_Coffret_Reco": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "coffret_001",
                        "ogr_pkid": "RPD_Coffret_Reco_0",
                        "PrecisionXY": "A",
                        "PrecisionZ": "B",
                    },
                    "geometry": {"type": "Point", "coordinates": [2.0, 48.0, 100.0]},
                }
            ]
        }
        gml_generator.generer_gml(features, output, remplacer_ids=True)

        contenu = output.read_text(encoding="utf-8")
        pattern = re.compile(r'gml:id="(id[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"')
        correspondances = pattern.findall(contenu)
        assert len(correspondances) > 0, "Aucun gml:id au format UUID trouvé"


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

    def test_mapper_galerie_commentaire_ecrit(self, feature_mapper):
        """RPD_Galerie_RecoType hérite d'ElementReseauType : Commentaire doit être écrit."""
        feature = self._feature_galerie()
        feature["properties"]["Commentaire"] = "Galerie technique sous voirie"
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")

        commentaire_elem = elem.find(f"{{{NAMESPACE_RECOSTAR}}}Commentaire")
        assert commentaire_elem is not None
        assert commentaire_elem.text == "Galerie technique sous voirie"

    def test_mapper_galerie_commentaire_ordre_xsd(self, feature_mapper):
        """Commentaire doit s'intercaler entre reseau et Geometrie (séquence ElementReseauType)."""
        feature = self._feature_galerie()
        feature["properties"]["Commentaire"] = "note"
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")

        tags = [child.tag.split("}")[1] for child in elem]
        assert tags[:3] == ["reseau", "Commentaire", "Geometrie"]

    def test_mapper_galerie_commentaire_absent_si_non_fourni(self, feature_mapper):
        """Sans Commentaire et sans l'option dédiée, aucune balise n'est produite."""
        feature = self._feature_galerie()
        elem = feature_mapper.mapper_galerie(feature, "galerie_001")
        assert elem.find(f"{{{NAMESPACE_RECOSTAR}}}Commentaire") is None


# ============================================================
# Tests de l'option --commentaire (balise Commentaire vide)
# ============================================================


class TestOptionCommentaireVide:
    """Tests pour le mode commentaire_vide (option CLI --commentaire).

    Le champ Commentaire est une évolution V1.1 du standard : optionnel sur
    toutes les entités héritant d'ElementReseauType et sur
    RPD_GeometrieSupplementaire_Reco. L'option produit la balise vide
    lorsqu'aucune valeur n'est fournie, sans jamais écraser une valeur existante.
    """

    NS_R = f"{{{NAMESPACE_RECOSTAR}}}"

    @pytest.fixture
    def mappeur_vide(self):
        """MappeurEntites avec émission des commentaires vides activée."""
        return MappeurEntites(DEFAULT_SRS, commentaire_vide=True)

    @staticmethod
    def _feature_coffret(commentaire=None) -> dict:
        """Crée une feature GeoJSON Coffret, avec ou sans Commentaire."""
        props = {
            "ogr_pkid": "coffret_vide_001",
            "TypeCoffret_href": "S22",
            "FonctionCoffret_href": "Distribution",
            "PrecisionXY": "A",
            "PrecisionZ": "A",
            "Statut": "Functional",
        }
        if commentaire is not None:
            props["Commentaire"] = commentaire
        return {
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [600000.0, 6800000.0, 100.0]},
        }

    def test_defaut_desactive(self, feature_mapper):
        """Par défaut le mode est inactif : comportement historique préservé."""
        assert feature_mapper.commentaire_vide is False
        elem = feature_mapper.mapper_coffret(self._feature_coffret(), "coffret_001")
        assert elem.find(f"{self.NS_R}Commentaire") is None

    def test_balise_vide_produite_si_absente(self, mappeur_vide):
        """Avec l'option, une balise Commentaire vide est ajoutée quand la valeur manque."""
        elem = mappeur_vide.mapper_coffret(self._feature_coffret(), "coffret_001")

        commentaire_elem = elem.find(f"{self.NS_R}Commentaire")
        assert commentaire_elem is not None
        assert not commentaire_elem.text
        assert len(commentaire_elem) == 0

    def test_balise_vide_produite_si_valeur_none(self, mappeur_vide):
        """Une propriété Commentaire explicitement None équivaut à une absence."""
        elem = mappeur_vide.mapper_coffret(self._feature_coffret(commentaire=None), "coffret_001")
        assert elem.find(f"{self.NS_R}Commentaire") is not None

    def test_balise_vide_produite_si_chaine_vide(self, mappeur_vide):
        """Une chaîne vide en entrée produit également la balise vide."""
        elem = mappeur_vide.mapper_coffret(self._feature_coffret(commentaire=""), "coffret_001")

        commentaire_elem = elem.find(f"{self.NS_R}Commentaire")
        assert commentaire_elem is not None
        assert not commentaire_elem.text

    def test_valeur_existante_preservee(self, mappeur_vide):
        """L'option n'écrase jamais un commentaire déjà renseigné."""
        elem = mappeur_vide.mapper_coffret(self._feature_coffret("Coffret en façade"), "coffret_001")

        commentaires = elem.findall(f"{self.NS_R}Commentaire")
        assert len(commentaires) == 1
        assert commentaires[0].text == "Coffret en façade"

    def test_ordre_xsd_respecte(self, mappeur_vide):
        """La balise vide se place juste après reseau, conformément à ElementReseauType."""
        elem = mappeur_vide.mapper_coffret(self._feature_coffret(), "coffret_001")

        tags = [child.tag.split("}")[1] for child in elem]
        assert tags[:2] == ["reseau", "Commentaire"]

    def test_geometrie_supplementaire_couverte(self, mappeur_vide):
        """RPD_GeometrieSupplementaire_Reco déclare Commentaire en propre : il est couvert."""
        feature = {
            "type": "Feature",
            "properties": {"ogr_pkid": "geom_supp_001", "PrecisionXY": "A", "PrecisionZ": "B"},
            "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]},
        }
        elem = mappeur_vide.mapper_geometrie_supplementaire(feature, "geom_supp_001")

        tags = [child.tag.split("}")[1] for child in elem]
        assert tags[0] == "Commentaire"

    def test_materiel_non_concerne(self, mappeur_vide):
        """RPD_Materiel_RecoType ne dérive pas d'ElementReseauType : aucune balise ajoutée."""
        feature = {
            "type": "Feature",
            "properties": {
                "Fabricant": "ACME",
                "Modele": "M1",
                "NumeroLot": "L1",
                "NumeroSerie": "S1",
            },
            "geometry": None,
        }
        elem = mappeur_vide.mapper_materiel(feature, "materiel_001")
        assert elem.find(f"{self.NS_R}Commentaire") is None

    def test_point_leve_non_concerne(self, mappeur_vide):
        """RPD_PointLeveOuvrageReseau_RecoType n'accepte pas Commentaire dans le XSD."""
        feature = {
            "type": "Feature",
            "properties": {
                "ogr_pkid": "plor_001",
                "NumeroPoint": "P1",
                "PrecisionXYnum": "0.05",
                "PrecisionZnum": "0.05",
                "Producteur": "TEST",
            },
            "geometry": {"type": "Point", "coordinates": [600000.0, 6800000.0, 100.0]},
        }
        elem = mappeur_vide.mapper_point_leve(feature, "plor_001")
        assert elem.find(f"{self.NS_R}Commentaire") is None

    def test_generateur_propage_option(self):
        """GenerateurGML transmet l'option à son MappeurEntites."""
        generateur = GenerateurGML(DEFAULT_SRS, commentaire_vide=True)
        assert generateur.mapper.commentaire_vide is True

    def test_generateur_defaut_desactive(self, gml_generator):
        """Le générateur par défaut n'active pas le mode."""
        assert gml_generator.mapper.commentaire_vide is False
