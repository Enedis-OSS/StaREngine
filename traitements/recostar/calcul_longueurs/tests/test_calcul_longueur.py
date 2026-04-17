"""Tests du calcul des longueurs geographiques et electriques des cables."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calcul_longueur import (  # type: ignore[import-not-found]
    CORRECTIONS,
    CORRECTIONS_AERIEN,
    ISOLANTS_ISOLES,
    ISOLANTS_NU,
    TYPE_COFFRET,
    TYPE_POSTE,
    TYPE_RAS,
    EntiteReferencee,
    ResultatCorrections,
    analyser_cable,
    calculer_corrections_cable,
    construire_ensemble_cables_aeriens,
    construire_index_entites,
    construire_index_statuts,
    executer_calcul,
    _calculer_centroide,
    _calculer_longueur_3d,
    _corriger_z_nuls,
    _extraire_coordonnees_cable,
    _extraire_ids_cables,
    _extraire_position_entite,
    _obtenir_correction,
    _obtenir_taux_correction_aerien,
)

# --- Tests de _calculer_longueur_3d ---


class TestCalculerLongueur3D:
    """Tests du calcul de longueur 3D."""

    def test_segment_horizontal(self):
        """Segment horizontal (dz=0) : longueur = distance 2D."""
        coords = [[0.0, 0.0, 10.0], [3.0, 4.0, 10.0]]
        assert _calculer_longueur_3d(coords) == pytest.approx(5.0)

    def test_segment_3d(self):
        """Segment 3D avec composante Z."""
        coords = [[0.0, 0.0, 10.0], [1.0, 0.0, 10.0], [1.0, 1.0, 11.0]]
        # Premier segment : 1.0, deuxieme : sqrt(0 + 1 + 1) = sqrt(2)
        attendu = 1.0 + math.sqrt(2.0)
        assert _calculer_longueur_3d(coords) == pytest.approx(attendu)

    def test_segment_2d_sans_z(self):
        """Coordonnees 2D (sans Z) : dz traite comme 0."""
        coords = [[0.0, 0.0], [3.0, 4.0]]
        assert _calculer_longueur_3d(coords) == pytest.approx(5.0)

    def test_segment_mixte_z(self):
        """Un sommet avec Z, l'autre sans : dz traite comme 0."""
        coords = [[0.0, 0.0, 5.0], [3.0, 4.0]]
        assert _calculer_longueur_3d(coords) == pytest.approx(5.0)

    def test_polyligne_multi_segments(self):
        """Polyligne de 4 sommets 3D."""
        coords = [
            [0.0, 0.0, 10.0],
            [3.0, 4.0, 10.0],
            [3.0, 4.0, 22.0],
            [3.0, 4.0, 22.0],
        ]
        # 5.0 + 12.0 + 0.0
        assert _calculer_longueur_3d(coords) == pytest.approx(17.0)

    def test_deux_points_identiques(self):
        """Deux points identiques : longueur nulle."""
        coords = [[5.0, 5.0, 5.0], [5.0, 5.0, 5.0]]
        assert _calculer_longueur_3d(coords) == pytest.approx(0.0)

    def test_z_nul_interpole_debut(self):
        """Z=0.0 en debut : corrige par le Z suivant valide, dz quasi nul."""
        coords = [[0.0, 0.0, 0.0], [3.0, 4.0, 300.0]]
        # Z corrige : [300.0, 300.0] → dz=0 → longueur = 5.0
        assert _calculer_longueur_3d(coords) == pytest.approx(5.0)

    def test_z_nul_milieu_polyligne(self):
        """Z=0.0 au milieu : corrige par propagation du Z precedent."""
        coords = [
            [0.0, 0.0, 10.0],
            [3.0, 4.0, 0.0],
            [6.0, 8.0, 12.0],
        ]
        # Z corrige : [10.0, 10.0, 12.0] → seg0: dz=0 → 5.0, seg1: dz=2 → sqrt(9+16+4)
        attendu = 5.0 + math.sqrt(29.0)
        assert _calculer_longueur_3d(coords) == pytest.approx(attendu)


# --- Tests de _corriger_z_nuls ---


class TestCorrigerZNuls:
    """Tests de la correction des valeurs Z nulles par propagation."""

    def test_aucun_z_nul(self):
        """Aucun Z a corriger : les valeurs restent identiques."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0], [2.0, 2.0, 30.0]]
        assert _corriger_z_nuls(coords) == [10.0, 20.0, 30.0]

    def test_z_nul_debut(self):
        """Z=0.0 en debut : corrige par le premier Z valide suivant."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 15.0], [2.0, 2.0, 20.0]]
        assert _corriger_z_nuls(coords) == [15.0, 15.0, 20.0]

    def test_z_nul_fin(self):
        """Z=0.0 en fin : corrige par le dernier Z valide precedent."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0], [2.0, 2.0, 0.0]]
        assert _corriger_z_nuls(coords) == [10.0, 20.0, 20.0]

    def test_z_nul_milieu(self):
        """Z=0.0 au milieu : corrige par propagation avant (Z precedent)."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 0.0], [2.0, 2.0, 30.0]]
        assert _corriger_z_nuls(coords) == [10.0, 10.0, 30.0]

    def test_tous_z_nuls(self):
        """Tous les Z a 0.0 : aucun Z valide, tout reste a 0.0."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]
        assert _corriger_z_nuls(coords) == [0.0, 0.0]

    def test_plusieurs_z_nuls_consecutifs(self):
        """Plusieurs Z=0.0 consecutifs : propages par le Z precedent valide."""
        coords = [
            [0.0, 0.0, 10.0],
            [1.0, 1.0, 0.0],
            [2.0, 2.0, 0.0],
            [3.0, 3.0, 25.0],
        ]
        assert _corriger_z_nuls(coords) == [10.0, 10.0, 10.0, 25.0]

    def test_sans_composante_z(self):
        """Coordonnees 2D sans Z : traites comme Z=0.0."""
        coords = [[0.0, 0.0], [1.0, 1.0, 10.0]]
        assert _corriger_z_nuls(coords) == [10.0, 10.0]


class TestCalculerCentroide:
    """Tests du calcul de centroide."""

    def test_carre(self):
        """Centroide d'un carre unitaire."""
        anneau = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
        centroide = _calculer_centroide(anneau)
        assert centroide[0] == pytest.approx(0.4)
        assert centroide[1] == pytest.approx(0.4)

    def test_anneau_vide(self):
        """Anneau vide : retourne [0, 0]."""
        assert _calculer_centroide([]) == [0.0, 0.0]


# --- Tests de _extraire_coordonnees_cable ---


class TestExtraireCoordonnesCable:
    """Tests de l'extraction des coordonnees de cable."""

    def test_linestring(self):
        """LineString : retourne une liste contenant une seule polyligne."""
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}
        resultat = _extraire_coordonnees_cable(geom)
        assert resultat == [[[0.0, 0.0], [1.0, 1.0]]]

    def test_multilinestring(self):
        """MultiLineString : retourne une liste de polylignes separees."""
        geom = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0], [1.0, 1.0]],
                [[5.0, 5.0], [6.0, 6.0]],
            ],
        }
        resultat = _extraire_coordonnees_cable(geom)
        assert resultat is not None
        assert len(resultat) == 2
        assert resultat[0] == [[0.0, 0.0], [1.0, 1.0]]
        assert resultat[1] == [[5.0, 5.0], [6.0, 6.0]]

    def test_type_non_supporte(self):
        """Type non supporte (Point) : retourne None."""
        geom = {"type": "Point", "coordinates": [0.0, 0.0]}
        assert _extraire_coordonnees_cable(geom) is None

    def test_linestring_un_seul_sommet(self):
        """LineString avec un seul sommet : retourne None."""
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0]]}
        assert _extraire_coordonnees_cable(geom) is None

    def test_multilinestring_vide(self):
        """MultiLineString vide : retourne None."""
        geom = {"type": "MultiLineString", "coordinates": []}
        assert _extraire_coordonnees_cable(geom) is None


# --- Tests de _extraire_position_entite ---


class TestExtrairePositionEntite:
    """Tests de l'extraction de position."""

    def test_point(self):
        """Feature Point : retourne les coordonnees directement."""
        feature = {"geometry": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}}
        assert _extraire_position_entite(feature) == [1.0, 2.0, 3.0]

    def test_polygone(self):
        """Feature Polygon : retourne le centroide."""
        feature = {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]]],
            }
        }
        pos = _extraire_position_entite(feature)
        assert pos is not None
        assert pos[0] == pytest.approx(1.0)
        assert pos[1] == pytest.approx(1.0)

    def test_geometrie_absente(self):
        """Feature sans geometrie : retourne None."""
        assert _extraire_position_entite({"geometry": None}) is None

    def test_type_non_supporte(self):
        """Geometrie de type non supporte : retourne None."""
        feature = {"geometry": {"type": "MultiPoint", "coordinates": [[1.0, 2.0]]}}
        assert _extraire_position_entite(feature) is None


# --- Tests de _extraire_ids_cables ---


class TestExtraireIdsCables:
    """Tests de l'extraction des IDs de cables."""

    def test_cables_href_simple(self):
        """Un seul cable dans cables_href."""
        feature = {"properties": {"cables_href": "cable_1"}}
        assert _extraire_ids_cables(feature) == {"cable_1"}

    def test_cables_href_multiple(self):
        """Plusieurs cables separes par des virgules."""
        feature = {"properties": {"cables_href": "cable_1, cable_2, cable_3"}}
        assert _extraire_ids_cables(feature) == {"cable_1", "cable_2", "cable_3"}

    def test_cables_href_absent(self):
        """Pas de cables_href : ensemble vide."""
        feature = {"properties": {}}
        assert _extraire_ids_cables(feature) == set()

    def test_cables_href_vide(self):
        """cables_href vide : ensemble vide."""
        feature = {"properties": {"cables_href": "  "}}
        assert _extraire_ids_cables(feature) == set()

    def test_cables_href_non_string(self):
        """cables_href non-string : ensemble vide."""
        feature = {"properties": {"cables_href": 42}}
        assert _extraire_ids_cables(feature) == set()


# --- Tests de _obtenir_correction ---


class TestObtenirCorrection:
    """Tests du calcul de correction par type et domaine."""

    def test_hta_ras(self):
        """HTA + remontee aero-souterraine : 11 m."""
        assert _obtenir_correction(TYPE_RAS, "HTA") == pytest.approx(11.0)

    def test_hta_poste(self):
        """HTA + poste : 5 m."""
        assert _obtenir_correction(TYPE_POSTE, "HTA") == pytest.approx(5.0)

    def test_bt_ras(self):
        """BT + remontee aero-souterraine : 11 m."""
        assert _obtenir_correction(TYPE_RAS, "BT") == pytest.approx(11.0)

    def test_bt_poste(self):
        """BT + poste : 3 m."""
        assert _obtenir_correction(TYPE_POSTE, "BT") == pytest.approx(3.0)

    def test_bt_coffret(self):
        """BT + coffret : 1 m."""
        assert _obtenir_correction(TYPE_COFFRET, "BT") == pytest.approx(1.0)

    def test_hta_coffret_pas_de_correction(self):
        """HTA + coffret : pas de correction definie."""
        assert _obtenir_correction(TYPE_COFFRET, "HTA") == pytest.approx(0.0)

    def test_domaine_inconnu(self):
        """Domaine de tension inconnu : pas de correction."""
        assert _obtenir_correction(TYPE_RAS, "HTB") == pytest.approx(0.0)


# --- Tests de calculer_corrections_cable ---


class TestCalculerCorrectionsCable:
    """Tests du calcul des corrections aux extremites."""

    def test_ras_au_depart_hta(self):
        """RAS proche du depart d'un cable HTA : correction depart = 11 m."""
        entites = [EntiteReferencee([0.0, 0.0], TYPE_RAS)]
        resultat = calculer_corrections_cable(
            [0.0, 0.0], [100.0, 100.0], entites, "HTA"
        )
        assert resultat.correction_depart == pytest.approx(11.0)
        assert resultat.correction_arrivee == pytest.approx(0.0)
        assert resultat.type_entite_depart == TYPE_RAS
        assert resultat.type_entite_arrivee == ""

    def test_poste_a_arrivee_hta(self):
        """Poste proche de l'arrivee d'un cable HTA : correction arrivee = 5 m."""
        entites = [EntiteReferencee([100.0, 100.0], TYPE_POSTE)]
        resultat = calculer_corrections_cable(
            [0.0, 0.0], [100.0, 100.0], entites, "HTA"
        )
        assert resultat.correction_depart == pytest.approx(0.0)
        assert resultat.correction_arrivee == pytest.approx(5.0)
        assert resultat.type_entite_depart == ""
        assert resultat.type_entite_arrivee == TYPE_POSTE

    def test_ras_et_poste_hta(self):
        """RAS au depart et poste a l'arrivee d'un cable HTA."""
        entites = [
            EntiteReferencee([0.0, 0.0], TYPE_RAS),
            EntiteReferencee([100.0, 100.0], TYPE_POSTE),
        ]
        resultat = calculer_corrections_cable(
            [0.0, 0.0], [100.0, 100.0], entites, "HTA"
        )
        assert resultat.correction_depart == pytest.approx(11.0)
        assert resultat.correction_arrivee == pytest.approx(5.0)
        assert resultat.type_entite_depart == TYPE_RAS
        assert resultat.type_entite_arrivee == TYPE_POSTE

    def test_coffret_bt(self):
        """Coffret proche de l'arrivee d'un cable BT : correction = 1 m."""
        entites = [EntiteReferencee([50.0, 50.0], TYPE_COFFRET)]
        resultat = calculer_corrections_cable([0.0, 0.0], [50.0, 50.0], entites, "BT")
        assert resultat.correction_depart == pytest.approx(0.0)
        assert resultat.correction_arrivee == pytest.approx(1.0)
        assert resultat.type_entite_arrivee == TYPE_COFFRET

    def test_aucune_entite(self):
        """Aucune entite connectee : pas de correction."""
        resultat = calculer_corrections_cable([0.0, 0.0], [100.0, 100.0], [], "HTA")
        assert resultat.correction_depart == pytest.approx(0.0)
        assert resultat.correction_arrivee == pytest.approx(0.0)
        assert resultat.type_entite_depart == ""
        assert resultat.type_entite_arrivee == ""

    def test_deux_entites_meme_extremite_max_retenu(self):
        """Deux entites a la meme extremite : la correction maximale est retenue."""
        entites = [
            EntiteReferencee([100.0, 100.0], TYPE_RAS),
            EntiteReferencee([100.1, 100.1], TYPE_POSTE),
        ]
        resultat = calculer_corrections_cable([0.0, 0.0], [100.0, 100.0], entites, "BT")
        # Les deux entites sont proches de l'arrivee, RAS (11) > poste (3)
        assert resultat.correction_arrivee == pytest.approx(11.0)
        assert resultat.type_entite_arrivee == TYPE_RAS


# --- Tests de analyser_cable ---


class TestAnalyserCable:
    """Tests de l'analyse d'un cable individuel."""

    def test_cable_hta_avec_ras_au_depart(self, cable_hta_3d):
        """Cable HTA avec RAS au depart : correction depart = 11 m."""
        index = {
            "cable_hta_1": [EntiteReferencee([100.0, 200.0, 10.0], TYPE_RAS)],
        }
        resultat = analyser_cable(cable_hta_3d, index)

        assert resultat is not None
        assert resultat["id"] == "cable_hta_1"
        assert resultat["domaine_tension"] == "HTA"
        assert resultat["hierarchie_bt"] == ""
        assert resultat["longueur_geographique"] > 0
        assert resultat["correction_depart"] == pytest.approx(11.0)
        assert resultat["correction_arrivee"] == pytest.approx(0.0)
        assert resultat["type_entite_depart"] == TYPE_RAS
        assert resultat["type_entite_arrivee"] == ""
        assert resultat["correction_aerien"] == pytest.approx(0.0)
        assert resultat["taux_aerien"] == pytest.approx(0.0)

    def test_cable_longueur_geo_arrondie_une_decimale(self):
        """La longueur geographique est arrondie a une decimale."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c_ceil", "DomaineTension": "BT"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0, 0.0], [3.0, 4.0, 0.0]],
            },
        }
        resultat = analyser_cable(cable, {})
        assert resultat is not None
        # longueur 3D = 5.0, round(5.0, 1) = 5.0
        assert resultat["longueur_geographique"] == pytest.approx(5.0)
        assert resultat["longueur_electrique"] == 5
        assert isinstance(resultat["longueur_geographique"], float)

    def test_cable_longueur_geo_non_entiere(self):
        """Longueur geographique non entiere arrondie a une decimale."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c_ceil2", "DomaineTension": "HTA"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
            },
        }
        resultat = analyser_cable(cable, {})
        assert resultat is not None
        # longueur 3D = sqrt(2) ≈ 1.414, round(_, 1) = 1.4
        assert resultat["longueur_geographique"] == pytest.approx(1.4)

    def test_cable_sans_id(self):
        """Cable sans identifiant : retourne None."""
        cable = {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [1.0, 1.0]],
            },
        }
        assert analyser_cable(cable, {}) is None

    def test_cable_geometry_point(self):
        """Cable avec geometrie Point (invalide) : retourne None."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c1"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        }
        assert analyser_cable(cable, {}) is None

    def test_cable_multilinestring(self):
        """Cable MultiLineString : sous-lignes calculees separement puis sommees."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_multi",
                "DomaineTension": "BT",
                "HierarchieBT": "",
                "Isolant": "",
            },
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [
                    [[0.0, 0.0, 10.0], [3.0, 0.0, 10.0]],
                    [[10.0, 10.0, 10.0], [10.0, 14.0, 10.0]],
                ],
            },
        }
        resultat = analyser_cable(cable, {})
        assert resultat is not None
        # 3.0 + 4.0 = 7.0 (pas de segment fantome entre les deux sous-lignes)
        assert resultat["longueur_geographique"] == pytest.approx(7.0)

    def test_cable_un_seul_point(self):
        """Cable avec un seul sommet : retourne None."""
        cable = {
            "type": "Feature",
            "properties": {"id": "c1"},
            "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0]]},
        }
        assert analyser_cable(cable, {}) is None

    def test_cable_sans_entites(self, cable_bt_3d):
        """Cable BT sans entites connectees : longueur electrique = longueur geo."""
        resultat = analyser_cable(cable_bt_3d, {})
        assert resultat is not None
        assert resultat["correction_depart"] == pytest.approx(0.0)
        assert resultat["correction_arrivee"] == pytest.approx(0.0)
        assert resultat["type_entite_depart"] == ""
        assert resultat["type_entite_arrivee"] == ""

    def test_cable_2d(self, cable_2d):
        """Cable 2D : longueur calculee sans composante Z."""
        resultat = analyser_cable(cable_2d, {})
        assert resultat is not None
        attendu = round(math.hypot(3.0, 4.0), 1)
        assert resultat["longueur_geographique"] == pytest.approx(attendu)

    def test_cable_bt_avec_hierarchie(self):
        """Cable BT avec HierarchieBT : le champ est restitue."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_bt_h",
                "DomaineTension": "BT",
                "HierarchieBT": "BT_400V",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [10.0, 0.0]],
            },
        }
        resultat = analyser_cable(cable, {})
        assert resultat is not None
        assert resultat["hierarchie_bt"] == "BT_400V"

    def test_cable_statut_avec_alias(self):
        """Cable avec Statut connu : le champ statut contient l'alias."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_statut",
                "DomaineTension": "BT",
                "Statut": "Functional",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [10.0, 0.0]],
            },
        }
        index_statuts = {"Functional": "En service", "Projected": "En projet"}
        resultat = analyser_cable(cable, {}, index_statuts=index_statuts)
        assert resultat is not None
        assert resultat["statut"] == "En service"

    def test_cable_statut_sans_alias(self):
        """Cable avec Statut inconnu du referentiel : valeur brute conservee."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_statut2",
                "DomaineTension": "BT",
                "Statut": "InconnuXYZ",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [10.0, 0.0]],
            },
        }
        resultat = analyser_cable(cable, {}, index_statuts={})
        assert resultat is not None
        assert resultat["statut"] == "InconnuXYZ"

    def test_cable_sans_statut(self, cable_bt_3d):
        """Cable sans attribut Statut : le champ statut est vide."""
        resultat = analyser_cable(cable_bt_3d, {})
        assert resultat is not None
        assert resultat["statut"] == ""


# --- Tests de construire_index_statuts ---


class TestConstruireIndexStatuts:
    """Tests de la construction de l'index des alias de statuts."""

    def test_referentiel_existant(self):
        """Le referentiel par defaut est charge et contient les statuts attendus."""
        index = construire_index_statuts()
        # Le referentiel doit contenir au minimum ces valeurs
        assert "Functional" in index
        assert index["Functional"] == "En service"
        assert "UnderCommissionning" in index
        assert "Decommissioned" in index

    def test_referentiel_inexistant(self, tmp_path):
        """Referentiel inexistant : retourne un dict vide."""
        chemin = str(tmp_path / "inexistant.json")
        index = construire_index_statuts(chemin)
        assert index == {}

    def test_referentiel_sans_cable(self, tmp_path):
        """Referentiel sans objet Cable : retourne un dict vide."""
        chemin = tmp_path / "ref.json"
        chemin.write_text('{"objets": {}}', encoding="utf-8")
        index = construire_index_statuts(str(chemin))
        assert index == {}


# --- Tests de construire_index_entites ---


class TestConstruireIndexEntites:
    """Tests de la construction de l'index des entites."""

    def test_index_jonctions_ras(
        self, dossier_projet, jonction_ras_depart, ecrire_geojson
    ):
        """Les jonctions RAS sont indexees."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(recolement, "RPD_Jonction_Reco.geojson", [jonction_ras_depart])

        index = construire_index_entites(str(recolement))
        assert "cable_hta_1" in index
        assert index["cable_hta_1"][0].type_entite == TYPE_RAS

    def test_jonctions_derivation_ignorees(
        self, dossier_projet, jonction_derivation, ecrire_geojson
    ):
        """Les jonctions de type Derivation ne sont pas indexees."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(recolement, "RPD_Jonction_Reco.geojson", [jonction_derivation])

        index = construire_index_entites(str(recolement))
        assert "cable_hta_1" not in index

    def test_index_postes(self, dossier_projet, poste_hta, ecrire_geojson):
        """Les postes sont indexes avec leur centroide."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(recolement, "RPD_PosteElectrique_Reco.geojson", [poste_hta])

        index = construire_index_entites(str(recolement))
        assert "cable_hta_1" in index
        assert index["cable_hta_1"][0].type_entite == TYPE_POSTE

    def test_index_noeuds_coffrets(
        self, dossier_projet, noeud_coffret_bt, ecrire_geojson
    ):
        """Les noeuds de coffrets avec conteneur_href sont indexes."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(
            recolement, "RPD_CoupeCircuitAFusibles_Reco.geojson", [noeud_coffret_bt]
        )

        index = construire_index_entites(str(recolement))
        assert "cable_bt_1" in index
        assert index["cable_bt_1"][0].type_entite == TYPE_COFFRET

    def test_noeuds_sans_conteneur_ignores(
        self, dossier_projet, noeud_sans_conteneur, ecrire_geojson
    ):
        """Les noeuds sans conteneur_href ne sont pas indexes."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(
            recolement,
            "RPD_CoupeCircuitAFusibles_Reco.geojson",
            [noeud_sans_conteneur],
        )

        index = construire_index_entites(str(recolement))
        assert "cable_bt_1" not in index

    def test_fichiers_absents(self, dossier_projet):
        """Fichiers GeoJSON absents : index vide sans erreur."""
        recolement = dossier_projet / "recolement"
        index = construire_index_entites(str(recolement))
        assert index == {}


# --- Tests d'integration de executer_calcul ---


class TestExecuterCalcul:
    """Tests d'integration du calcul complet."""

    def test_fichier_cables_absent(self, dossier_projet):
        """Retourne une erreur si le fichier cables est absent."""
        resultat = executer_calcul(str(dossier_projet))
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_cable_hta_ras_et_poste(
        self,
        dossier_projet,
        cable_hta_3d,
        jonction_ras_depart,
        poste_hta,
        ecrire_geojson,
    ):
        """Cable HTA avec RAS au depart et poste a l'arrivee."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(recolement, "RPD_CableElectrique_Reco.geojson", [cable_hta_3d])
        ecrire_geojson(recolement, "RPD_Jonction_Reco.geojson", [jonction_ras_depart])
        ecrire_geojson(recolement, "RPD_PosteElectrique_Reco.geojson", [poste_hta])

        resultat = executer_calcul(str(dossier_projet))
        assert resultat["succes"] is True
        assert len(resultat["resultats"]) == 1

        cable_res = resultat["resultats"][0]
        assert cable_res["correction_depart"] == pytest.approx(11.0)
        assert cable_res["correction_arrivee"] == pytest.approx(5.0)
        assert cable_res["type_entite_depart"] == "remontee_aero_souterraine"
        assert cable_res["type_entite_arrivee"] == "poste"
        assert isinstance(cable_res["longueur_geographique"], float)
        assert isinstance(cable_res["longueur_electrique"], int)

    def test_cable_bt_ras_et_coffret(
        self,
        dossier_projet,
        cable_bt_3d,
        jonction_ras_bt,
        noeud_coffret_bt,
        ecrire_geojson,
    ):
        """Cable BT avec RAS au depart et coffret a l'arrivee."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(recolement, "RPD_CableElectrique_Reco.geojson", [cable_bt_3d])
        ecrire_geojson(recolement, "RPD_Jonction_Reco.geojson", [jonction_ras_bt])
        ecrire_geojson(
            recolement,
            "RPD_CoupeCircuitAFusibles_Reco.geojson",
            [noeud_coffret_bt],
        )

        resultat = executer_calcul(str(dossier_projet))
        assert resultat["succes"] is True

        cable_res = resultat["resultats"][0]
        assert cable_res["correction_depart"] == pytest.approx(11.0)
        assert cable_res["correction_arrivee"] == pytest.approx(1.0)
        assert cable_res["type_entite_depart"] == "remontee_aero_souterraine"
        assert cable_res["type_entite_arrivee"] == "coffret"

    def test_cable_sans_entites_liees(
        self, dossier_projet, cable_bt_3d, ecrire_geojson
    ):
        """Cable sans entites connectees : longueur electrique = longueur geo."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(recolement, "RPD_CableElectrique_Reco.geojson", [cable_bt_3d])

        resultat = executer_calcul(str(dossier_projet))
        assert resultat["succes"] is True

        cable_res = resultat["resultats"][0]
        assert cable_res["type_entite_depart"] == ""
        assert cable_res["type_entite_arrivee"] == ""

    def test_cable_bt_poste(
        self, dossier_projet, cable_bt_3d, poste_bt, ecrire_geojson
    ):
        """Cable BT avec poste a l'arrivee : correction = 3 m."""
        recolement = dossier_projet / "recolement"
        ecrire_geojson(recolement, "RPD_CableElectrique_Reco.geojson", [cable_bt_3d])
        ecrire_geojson(recolement, "RPD_PosteElectrique_Reco.geojson", [poste_bt])

        resultat = executer_calcul(str(dossier_projet))
        cable_res = resultat["resultats"][0]
        assert cable_res["correction_arrivee"] == pytest.approx(3.0)
        assert cable_res["type_entite_arrivee"] == "poste"


# --- Tests de _obtenir_taux_correction_aerien ---


class TestObtenirTauxCorrectionAerien:
    """Tests du calcul du taux de correction aerienne."""

    def test_bt_nu(self):
        """BT + isolant Nu : taux = 4 %."""
        assert _obtenir_taux_correction_aerien("BT", "Nu") == pytest.approx(0.04)

    def test_bt_reticulee(self):
        """BT + isolant Reticulee : taux = 5 %."""
        assert _obtenir_taux_correction_aerien("BT", "Reticulee") == pytest.approx(0.05)

    def test_bt_thermodurcissable(self):
        """BT + isolant Thermodurcissable : taux = 5 %."""
        assert _obtenir_taux_correction_aerien(
            "BT", "Thermodurcissable"
        ) == pytest.approx(0.05)

    def test_hta_nu(self):
        """HTA + isolant Nu : taux = 3 %."""
        assert _obtenir_taux_correction_aerien("HTA", "Nu") == pytest.approx(0.03)

    def test_hta_reticulee(self):
        """HTA + isolant Reticulee : taux = 5 %."""
        assert _obtenir_taux_correction_aerien("HTA", "Reticulee") == pytest.approx(
            0.05
        )

    def test_hta_thermodurcissable(self):
        """HTA + isolant Thermodurcissable : taux = 5 %."""
        assert _obtenir_taux_correction_aerien(
            "HTA", "Thermodurcissable"
        ) == pytest.approx(0.05)

    def test_domaine_inconnu(self):
        """Domaine de tension inconnu : taux = 0."""
        assert _obtenir_taux_correction_aerien("HTB", "Nu") == pytest.approx(0.0)

    def test_isolant_inconnu(self):
        """Isolant non reconnu : taux = 0."""
        assert _obtenir_taux_correction_aerien("BT", "Autre") == pytest.approx(0.0)

    def test_isolant_vide(self):
        """Isolant vide : taux = 0."""
        assert _obtenir_taux_correction_aerien("HTA", "") == pytest.approx(0.0)


# --- Tests de construire_ensemble_cables_aeriens ---


class TestConstruireEnsembleCablesAeriens:
    """Tests de la construction de l'ensemble des cables aeriens."""

    def test_fichier_absent(self, dossier_projet):
        """Fichier Aerien absent : ensemble vide sans erreur."""
        recolement = dossier_projet / "recolement"
        assert construire_ensemble_cables_aeriens(str(recolement)) == set()

    def test_aerien_avec_cables(self, dossier_projet, ecrire_geojson):
        """Cheminements aeriens indexent correctement les cables."""
        recolement = dossier_projet / "recolement"
        aeriens = [
            {
                "type": "Feature",
                "properties": {"id": "aer_1", "cables_href": "cable_a"},
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            },
            {
                "type": "Feature",
                "properties": {"id": "aer_2", "cables_href": "cable_b, cable_c"},
                "geometry": {"type": "LineString", "coordinates": [[2, 2], [3, 3]]},
            },
        ]
        ecrire_geojson(recolement, "RPD_Aerien_Reco.geojson", aeriens)

        resultat = construire_ensemble_cables_aeriens(str(recolement))
        assert resultat == {"cable_a", "cable_b", "cable_c"}


# --- Tests de analyser_cable avec correction aerienne ---


class TestAnalyserCableAerien:
    """Tests de l'analyse d'un cable avec correction aerienne."""

    def test_cable_bt_aerien_reticulee(self):
        """Cable BT aerien avec isolant Reticulee : correction aerienne = 5 %."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_aer_bt",
                "DomaineTension": "BT",
                "Isolant": "Reticulee",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [100.0, 0.0]],
            },
        }
        cables_aeriens = {"c_aer_bt"}

        resultat = analyser_cable(cable, {}, cables_aeriens)
        assert resultat is not None
        assert resultat["taux_aerien"] == pytest.approx(0.05)
        assert resultat["correction_aerien"] == pytest.approx(5.0)
        # Attendu : ceil(100 + 5) soit 105
        assert resultat["longueur_electrique"] == 105

    def test_cable_hta_aerien_nu(self):
        """Cable HTA aerien avec isolant Nu : correction aerienne = 3 %."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_aer_hta",
                "DomaineTension": "HTA",
                "Isolant": "Nu",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [200.0, 0.0]],
            },
        }
        cables_aeriens = {"c_aer_hta"}

        resultat = analyser_cable(cable, {}, cables_aeriens)
        assert resultat is not None
        assert resultat["taux_aerien"] == pytest.approx(0.03)
        assert resultat["correction_aerien"] == pytest.approx(6.0)
        # Attendu : ceil(200 + 6) soit 206
        assert resultat["longueur_electrique"] == 206

    def test_cable_bt_aerien_nu(self):
        """Cable BT aerien avec isolant Nu : correction aerienne = 4 %."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_aer_bt_nu",
                "DomaineTension": "BT",
                "Isolant": "Nu",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [50.0, 0.0]],
            },
        }
        cables_aeriens = {"c_aer_bt_nu"}

        resultat = analyser_cable(cable, {}, cables_aeriens)
        assert resultat is not None
        assert resultat["taux_aerien"] == pytest.approx(0.04)
        assert resultat["correction_aerien"] == pytest.approx(2.0)
        # Attendu : ceil(50 + 2) soit 52
        assert resultat["longueur_electrique"] == 52

    def test_cable_hta_aerien_thermodurcissable(self):
        """Cable HTA aerien avec isolant Thermodurcissable : correction = 5 %."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_aer_hta_td",
                "DomaineTension": "HTA",
                "Isolant": "Thermodurcissable",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [100.0, 0.0]],
            },
        }
        cables_aeriens = {"c_aer_hta_td"}

        resultat = analyser_cable(cable, {}, cables_aeriens)
        assert resultat is not None
        assert resultat["taux_aerien"] == pytest.approx(0.05)
        assert resultat["correction_aerien"] == pytest.approx(5.0)
        assert resultat["longueur_electrique"] == 105

    def test_cable_non_aerien_pas_de_correction(self):
        """Cable non aerien : aucune correction aerienne appliquee."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_non_aer",
                "DomaineTension": "BT",
                "Isolant": "Reticulee",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [100.0, 0.0]],
            },
        }
        # Cable absent de l'ensemble aerien
        cables_aeriens = {"autre_cable"}

        resultat = analyser_cable(cable, {}, cables_aeriens)
        assert resultat is not None
        assert resultat["taux_aerien"] == pytest.approx(0.0)
        assert resultat["correction_aerien"] == pytest.approx(0.0)
        assert resultat["longueur_electrique"] == 100

    def test_cable_aerien_sans_corrections_extremites(self):
        """Cable aerien : les corrections aux extremites ne sont pas appliquees."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_cumul",
                "DomaineTension": "HTA",
                "Isolant": "Nu",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [100.0, 0.0]],
            },
        }
        index = {
            "c_cumul": [
                EntiteReferencee([0.0, 0.0], TYPE_RAS),
                EntiteReferencee([100.0, 0.0], TYPE_POSTE),
            ],
        }
        cables_aeriens = {"c_cumul"}

        resultat = analyser_cable(cable, index, cables_aeriens)
        assert resultat is not None
        # Cable aerien : pas de correction aux extremites
        assert resultat["correction_depart"] == pytest.approx(0.0)
        assert resultat["correction_arrivee"] == pytest.approx(0.0)
        assert resultat["type_entite_depart"] == ""
        assert resultat["type_entite_arrivee"] == ""
        # Correction aerienne seule : 100 * 0.03 = 3
        assert resultat["correction_aerien"] == pytest.approx(3.0)
        # Attendu : ceil(100 + 3) soit 103
        assert resultat["longueur_electrique"] == 103

    def test_cable_aerien_sans_cables_aeriens_none(self):
        """Cable analyse sans ensemble aerien (None) : pas de correction."""
        cable = {
            "type": "Feature",
            "properties": {
                "id": "c_none",
                "DomaineTension": "BT",
                "Isolant": "Nu",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [10.0, 0.0]],
            },
        }
        resultat = analyser_cable(cable, {}, None)
        assert resultat is not None
        assert resultat["correction_aerien"] == pytest.approx(0.0)


# --- Tests d'integration avec cables aeriens ---


class TestExecuterCalculAerien:
    """Tests d'integration du calcul complet avec cheminements aeriens."""

    def test_cable_aerien_bt_reticulee(self, dossier_projet, ecrire_geojson):
        """Integration : cable BT aerien avec isolant Reticulee reçoit +5 %."""
        recolement = dossier_projet / "recolement"

        cable = {
            "type": "Feature",
            "properties": {
                "id": "cable_aer_integ",
                "DomaineTension": "BT",
                "Isolant": "Reticulee",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [100.0, 0.0]],
            },
        }
        aerien = {
            "type": "Feature",
            "properties": {"id": "aer_1", "cables_href": "cable_aer_integ"},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [100, 0]]},
        }

        ecrire_geojson(recolement, "RPD_CableElectrique_Reco.geojson", [cable])
        ecrire_geojson(recolement, "RPD_Aerien_Reco.geojson", [aerien])

        resultat = executer_calcul(str(dossier_projet))
        assert resultat["succes"] is True

        cable_res = resultat["resultats"][0]
        assert cable_res["taux_aerien"] == pytest.approx(0.05)
        assert cable_res["correction_aerien"] == pytest.approx(5.0)
        assert cable_res["longueur_electrique"] == 105

    def test_cable_non_aerien_pas_de_correction(self, dossier_projet, ecrire_geojson):
        """Integration : cable non aerien ne reçoit pas de correction aerienne."""
        recolement = dossier_projet / "recolement"

        cable = {
            "type": "Feature",
            "properties": {
                "id": "cable_sol",
                "DomaineTension": "BT",
                "Isolant": "Reticulee",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [100.0, 0.0]],
            },
        }
        # Aerien reference un autre cable
        aerien = {
            "type": "Feature",
            "properties": {"id": "aer_1", "cables_href": "autre_cable"},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [100, 0]]},
        }

        ecrire_geojson(recolement, "RPD_CableElectrique_Reco.geojson", [cable])
        ecrire_geojson(recolement, "RPD_Aerien_Reco.geojson", [aerien])

        resultat = executer_calcul(str(dossier_projet))
        cable_res = resultat["resultats"][0]
        assert cable_res["correction_aerien"] == pytest.approx(0.0)
        assert cable_res["longueur_electrique"] == 100

    def test_sans_fichier_aerien(self, dossier_projet, ecrire_geojson):
        """Integration : absence du fichier Aerien ne provoque pas d'erreur."""
        recolement = dossier_projet / "recolement"

        cable = {
            "type": "Feature",
            "properties": {
                "id": "cable_ok",
                "DomaineTension": "BT",
                "Isolant": "Nu",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [100.0, 0.0]],
            },
        }
        ecrire_geojson(recolement, "RPD_CableElectrique_Reco.geojson", [cable])

        resultat = executer_calcul(str(dossier_projet))
        assert resultat["succes"] is True
        assert resultat["resultats"][0]["correction_aerien"] == pytest.approx(0.0)
