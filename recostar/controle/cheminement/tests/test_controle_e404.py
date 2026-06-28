"""
Tests du controle E404 : profondeur manquante aux points de charge generatrice.

Couvre la regle du controle :
    Tout cheminement souterrain superpose a un point de charge generatrice
    doit posseder le champ ProfondeurMinNonReg renseigne. Si le point est
    a la limite entre deux cheminements, au moins un doit etre conforme.
"""

import json
import os
from typing import Any

from controle_e404 import (
    CHAMP_CHARGE_GENERATRICE_V11,
    CHAMP_TYPE_LEVE,
    FICHIER_SORTIE,
    FICHIER_SOURCE,
    FICHIERS_CHEMINEMENT_SOUTERRAIN,
    JETON_AUTO,
    PRIORITE_ANOMALIE,
    TYPE_ANOMALIE,
    VERSION_DEFAUT,
    EntiteCheminement,
    EntitePoint,
    _est_charge_generatrice_v10,
    _est_charge_generatrice_v11,
    charger_cheminements_souterrains,
    charger_points_charge,
    construire_geojson_ecarts,
    detecter_anomalies,
    detecter_version_depuis_features,
    executer_controle_cli,
    resoudre_version,
)
from shapely.geometry import LineString, Point
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# ---------------------------------------------------------------------------
# Helpers de construction des features de test
# ---------------------------------------------------------------------------


def _feature_point_v10(
    identifiant: str,
    coords: list[float],
    type_leve: str = "ChargeGeneratrice",
) -> dict[str, Any]:
    """Feature GeoJSON Point de leve version 1.0."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, CHAMP_TYPE_LEVE: type_leve},
        "geometry": {"type": "Point", "coordinates": coords},
    }


def _feature_point_v11(
    identifiant: str,
    coords: list[float],
    charge_generatrice: float | None = 1.0,
) -> dict[str, Any]:
    """Feature GeoJSON Point de leve version 1.1."""
    return {
        "type": "Feature",
        "properties": {
            "id": identifiant,
            CHAMP_CHARGE_GENERATRICE_V11: charge_generatrice,
        },
        "geometry": {"type": "Point", "coordinates": coords},
    }


def _feature_point_simple(identifiant: str, coords: list[float]) -> dict[str, Any]:
    """Feature GeoJSON Point sans champ de version (ni TypeLeve ni ChargeGeneratrice)."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "Point", "coordinates": coords},
    }


def _feature_cheminement(
    identifiant: str,
    coords: list[list[float]],
    profondeur: float | None = None,
    fichier: str = "RPD_Fourreau_Reco.geojson",
) -> dict[str, Any]:
    """Feature GeoJSON LineString de cheminement souterrain."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "ProfondeurMinNonReg": profondeur},
        "geometry": {"type": "LineString", "coordinates": coords},
    }


def _entite_point(
    id_entite: str = "id-p1",
    x: float = 5.0,
    y: float = 0.0,
) -> EntitePoint:
    """Construit une EntitePoint Shapely pour les tests unitaires de detection."""
    return EntitePoint(
        id_entite=id_entite,
        geometrie=Point(x, y),
        coordonnees=[x, y],
    )


def _entite_cheminement(
    id_entite: str = "id-c1",
    fichier: str = "RPD_Fourreau_Reco.geojson",
    coords: list[tuple] | None = None,
    profondeur_renseignee: bool = False,
) -> EntiteCheminement:
    """Construit une EntiteCheminement Shapely pour les tests unitaires de detection."""
    if coords is None:
        coords = [(0.0, 0.0), (10.0, 0.0)]
    return EntiteCheminement(
        id_entite=id_entite,
        fichier=fichier,
        geometrie=LineString(coords),
        profondeur_renseignee=profondeur_renseignee,
    )


# ---------------------------------------------------------------------------
# TestDetecterVersionDepuisFeatures
# ---------------------------------------------------------------------------


class TestDetecterVersionDepuisFeatures:
    """Tests de la detection de version depuis les proprietes GeoJSON."""

    def test_version_10_detectee_si_type_leve_present(self):
        features = [_feature_point_v10("id-p1", [0.0, 0.0])]
        assert detecter_version_depuis_features(features) == "1.0"

    def test_retourne_none_si_type_leve_absent(self):
        features = [_feature_point_v11("id-p1", [0.0, 0.0])]
        assert detecter_version_depuis_features(features) is None

    def test_retourne_none_si_collection_vide(self):
        assert detecter_version_depuis_features([]) is None

    def test_version_10_si_au_moins_une_feature_avec_type_leve(self):
        features = [
            _feature_point_simple("id-p1", [0.0, 0.0]),
            _feature_point_v10("id-p2", [1.0, 0.0]),
        ]
        assert detecter_version_depuis_features(features) == "1.0"


# ---------------------------------------------------------------------------
# TestResoudreVersion
# ---------------------------------------------------------------------------


class TestResoudreVersion:
    """Tests de la resolution de la version effective."""

    def test_auto_retourne_10_si_type_leve_detecte(self):
        features = [_feature_point_v10("id-p1", [0.0, 0.0])]
        assert resoudre_version(JETON_AUTO, features) == "1.0"

    def test_auto_retourne_version_defaut_si_non_detecte(self):
        features = [_feature_point_simple("id-p1", [0.0, 0.0])]
        assert resoudre_version(JETON_AUTO, features) == VERSION_DEFAUT

    def test_explicite_ignore_le_contenu(self):
        features = [_feature_point_v10("id-p1", [0.0, 0.0])]
        assert resoudre_version("1.1", features) == "1.1"

    def test_auto_collection_vide_retourne_version_defaut(self):
        assert resoudre_version(JETON_AUTO, []) == VERSION_DEFAUT


# ---------------------------------------------------------------------------
# TestEstChargeGeneratrice
# ---------------------------------------------------------------------------


class TestEstChargeGeneratrice:
    """Tests des predicats de detection des charges generatrices par version."""

    def test_v10_type_leve_charge_generatrice_retourne_vrai(self):
        props = {CHAMP_TYPE_LEVE: "ChargeGeneratrice"}
        assert _est_charge_generatrice_v10(props) is True

    def test_v10_autre_type_leve_retourne_faux(self):
        props = {CHAMP_TYPE_LEVE: "NouvelPoint"}
        assert _est_charge_generatrice_v10(props) is False

    def test_v10_champ_absent_retourne_faux(self):
        assert _est_charge_generatrice_v10({}) is False

    def test_v11_charge_generatrice_non_nulle_retourne_vrai(self):
        props = {CHAMP_CHARGE_GENERATRICE_V11: 1.83}
        assert _est_charge_generatrice_v11(props) is True

    def test_v11_charge_generatrice_nulle_retourne_faux(self):
        props = {CHAMP_CHARGE_GENERATRICE_V11: None}
        assert _est_charge_generatrice_v11(props) is False

    def test_v11_champ_absent_retourne_faux(self):
        assert _est_charge_generatrice_v11({}) is False

    def test_v11_valeur_zero_est_renseignee(self):
        props = {CHAMP_CHARGE_GENERATRICE_V11: 0.0}
        assert _est_charge_generatrice_v11(props) is True


# ---------------------------------------------------------------------------
# TestChargerPointsCharge
# ---------------------------------------------------------------------------


class TestChargerPointsCharge:
    """Tests du chargement et filtrage des points de charge generatrice."""

    def test_v10_filtre_sur_type_leve(self):
        features = [
            _feature_point_v10("id-cg", [1.0, 2.0]),
            _feature_point_v10("id-autre", [3.0, 4.0], type_leve="NouvelPoint"),
        ]
        points = charger_points_charge(features, "1.0")
        assert len(points) == 1
        assert points[0].id_entite == "id-cg"

    def test_v11_filtre_sur_charge_generatrice(self):
        features = [
            _feature_point_v11("id-cg", [1.0, 2.0], charge_generatrice=3.5),
            _feature_point_simple("id-autre", [3.0, 4.0]),
        ]
        points = charger_points_charge(features, "1.1")
        assert len(points) == 1
        assert points[0].id_entite == "id-cg"

    def test_feature_non_point_ignoree(self):
        feature_ligne = {
            "type": "Feature",
            "properties": {"id": "id-ligne", CHAMP_TYPE_LEVE: "ChargeGeneratrice"},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0]]},
        }
        assert charger_points_charge([feature_ligne], "1.0") == []

    def test_feature_sans_geometrie_ignoree(self):
        feature = {
            "type": "Feature",
            "properties": {"id": "id-p", CHAMP_TYPE_LEVE: "ChargeGeneratrice"},
            "geometry": None,
        }
        assert charger_points_charge([feature], "1.0") == []

    def test_coordonnees_2d_extraites(self):
        features = [_feature_point_v10("id-p", [100.0, 200.0, 50.0])]
        points = charger_points_charge(features, "1.0")
        assert points[0].coordonnees == [100.0, 200.0]

    def test_collection_vide_retourne_liste_vide(self):
        assert charger_points_charge([], "1.0") == []

    def test_geometrie_shapely_en_2d(self):
        features = [_feature_point_v10("id-p", [5.0, 3.0, 100.0])]
        points = charger_points_charge(features, "1.0")
        assert points[0].geometrie.has_z is False


# ---------------------------------------------------------------------------
# TestChargerCheminementsSouterrains
# ---------------------------------------------------------------------------


class TestChargerCheminementsSouterrains:
    """Tests du chargement des cheminements souterrains depuis le repertoire."""

    def test_fichiers_absents_signales(self, tmp_path):
        _, fichiers_absents, _ = charger_cheminements_souterrains(str(tmp_path))
        assert set(fichiers_absents) == set(FICHIERS_CHEMINEMENT_SOUTERRAIN)

    def test_cheminement_charge_depuis_fourreau(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        ecrire_collection(
            str(chemin),
            [_feature_cheminement("id-f1", [[0.0, 0.0], [10.0, 0.0]])],
        )
        cheminements, _, _ = charger_cheminements_souterrains(str(tmp_path))
        assert any(c.id_entite == "id-f1" for c in cheminements)

    def test_profondeur_renseignee_detectee(self, tmp_path):
        chemin = tmp_path / "RPD_PleineTerre_Reco.geojson"
        ecrire_collection(
            str(chemin),
            [_feature_cheminement("id-pt1", [[0.0, 0.0], [5.0, 0.0]], profondeur=1.3)],
        )
        cheminements, _, _ = charger_cheminements_souterrains(str(tmp_path))
        assert cheminements[0].profondeur_renseignee is True

    def test_profondeur_absente_detectee(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        ecrire_collection(
            str(chemin),
            [_feature_cheminement("id-f1", [[0.0, 0.0], [5.0, 0.0]], profondeur=None)],
        )
        cheminements, _, _ = charger_cheminements_souterrains(str(tmp_path))
        assert cheminements[0].profondeur_renseignee is False

    def test_crs_propage(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        ecrire_collection_avec_crs(
            str(chemin),
            [_feature_cheminement("id-f1", [[0.0, 0.0], [5.0, 0.0]])],
            "EPSG:2154",
        )
        _, _, crs = charger_cheminements_souterrains(str(tmp_path))
        assert crs is not None
        assert "2154" in crs["properties"]["name"]

    def test_cheminements_des_trois_fichiers_fusionnes(self, tmp_path):
        for nom in FICHIERS_CHEMINEMENT_SOUTERRAIN:
            ecrire_collection(
                str(tmp_path / nom),
                [_feature_cheminement(f"id-{nom}", [[0.0, 0.0], [1.0, 0.0]])],
            )
        cheminements, absents, _ = charger_cheminements_souterrains(str(tmp_path))
        assert len(cheminements) == 3
        assert absents == []

    def test_feature_non_lineaire_ignoree(self, tmp_path):
        chemin = tmp_path / "RPD_Fourreau_Reco.geojson"
        feature_point = {
            "type": "Feature",
            "properties": {"id": "id-pt"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        }
        ecrire_collection(str(chemin), [feature_point])
        cheminements, _, _ = charger_cheminements_souterrains(str(tmp_path))
        assert cheminements == []


# ---------------------------------------------------------------------------
# TestDetecterAnomalies
# ---------------------------------------------------------------------------


class TestDetecterAnomalies:
    """Tests de la detection spatiale des anomalies de profondeur."""

    def test_liste_vide_si_aucun_point(self):
        cheminement = _entite_cheminement()
        assert detecter_anomalies([], [cheminement]) == []

    def test_liste_vide_si_aucun_cheminement(self):
        point = _entite_point()
        assert detecter_anomalies([point], []) == []

    def test_point_sur_cheminement_sans_profondeur_est_anomalie(self):
        point = _entite_point(x=5.0, y=0.0)
        chemin = _entite_cheminement(coords=[(0.0, 0.0), (10.0, 0.0)], profondeur_renseignee=False)
        anomalies = detecter_anomalies([point], [chemin])
        assert len(anomalies) == 1
        assert anomalies[0]["id_point"] == "id-p1"

    def test_point_sur_cheminement_avec_profondeur_est_conforme(self):
        point = _entite_point(x=5.0, y=0.0)
        chemin = _entite_cheminement(coords=[(0.0, 0.0), (10.0, 0.0)], profondeur_renseignee=True)
        assert detecter_anomalies([point], [chemin]) == []

    def test_point_hors_cheminement_ignore(self):
        point = _entite_point(x=5.0, y=2.0)  # 2m du cheminement > EPSILON
        chemin = _entite_cheminement(coords=[(0.0, 0.0), (10.0, 0.0)])
        assert detecter_anomalies([point], [chemin]) == []

    def test_limite_deux_cheminements_un_avec_profondeur_est_conforme(self):
        # Point au raccordement de deux cheminements — un seul a la profondeur
        ligne_a = LineString([(0.0, 0.0), (5.0, 0.0)])
        ligne_b = LineString([(5.0, 0.0), (10.0, 0.0)])
        chemin_a = EntiteCheminement("id-a", "RPD_Fourreau_Reco.geojson", ligne_a, True)
        chemin_b = EntiteCheminement("id-b", "RPD_PleineTerre_Reco.geojson", ligne_b, False)
        point = EntitePoint("id-p", Point(5.0, 0.0), [5.0, 0.0])
        assert detecter_anomalies([point], [chemin_a, chemin_b]) == []

    def test_limite_deux_cheminements_aucun_avec_profondeur_est_anomalie(self):
        ligne_a = LineString([(0.0, 0.0), (5.0, 0.0)])
        ligne_b = LineString([(5.0, 0.0), (10.0, 0.0)])
        chemin_a = EntiteCheminement("id-a", "RPD_Fourreau_Reco.geojson", ligne_a, False)
        chemin_b = EntiteCheminement("id-b", "RPD_PleineTerre_Reco.geojson", ligne_b, False)
        point = EntitePoint("id-p", Point(5.0, 0.0), [5.0, 0.0])
        anomalies = detecter_anomalies([point], [chemin_a, chemin_b])
        assert len(anomalies) == 1
        assert len(anomalies[0]["cheminements_touches"]) == 2

    def test_anomalie_inclut_details_cheminement_touche(self):
        point = _entite_point(x=5.0, y=0.0)
        chemin = _entite_cheminement(
            id_entite="id-c-attend",
            fichier="RPD_Fourreau_Reco.geojson",
            coords=[(0.0, 0.0), (10.0, 0.0)],
            profondeur_renseignee=False,
        )
        anomalie = detecter_anomalies([point], [chemin])[0]
        touches = anomalie["cheminements_touches"]
        assert len(touches) == 1
        assert touches[0]["id_cheminement"] == "id-c-attend"
        assert touches[0]["fichier"] == "RPD_Fourreau_Reco.geojson"

    def test_plusieurs_points_en_anomalie(self):
        chemin = _entite_cheminement(coords=[(0.0, 0.0), (20.0, 0.0)])
        point_a = _entite_point("id-pa", 5.0, 0.0)
        point_b = _entite_point("id-pb", 15.0, 0.0)
        anomalies = detecter_anomalies([point_a, point_b], [chemin])
        assert len(anomalies) == 2

    def test_seuls_points_sans_profondeur_signales(self):
        chemin_avec = _entite_cheminement("id-c-avec", profondeur_renseignee=True)
        chemin_sans = _entite_cheminement(
            "id-c-sans",
            coords=[(20.0, 0.0), (30.0, 0.0)],
            profondeur_renseignee=False,
        )
        point_ok = _entite_point("id-p-ok", x=5.0)
        point_ko = _entite_point("id-p-ko", x=25.0)
        anomalies = detecter_anomalies([point_ok, point_ko], [chemin_avec, chemin_sans])
        assert len(anomalies) == 1
        assert anomalies[0]["id_point"] == "id-p-ko"

    def test_anomalie_inclut_coordonnees_du_point(self):
        point = _entite_point(x=7.0, y=0.0)
        chemin = _entite_cheminement()
        anomalie = detecter_anomalies([point], [chemin])[0]
        assert anomalie["coordonnees"] == [7.0, 0.0]


# ---------------------------------------------------------------------------
# TestConstruireGeojsonEcarts
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    """Tests de la construction du FeatureCollection GeoJSON de sortie."""

    def test_collection_vide(self):
        resultat = construire_geojson_ecarts([], "1.0")
        assert resultat["type"] == "FeatureCollection"
        assert resultat["features"] == []

    def test_crs_absent_si_none(self):
        assert "crs" not in construire_geojson_ecarts([], "1.0")

    def test_crs_propage(self):
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], "1.0", crs)["crs"] == crs

    def test_proprietes_feature(self):
        anomalie = {
            "id_point": "id-p1",
            "coordonnees": [1.0, 2.0],
            "cheminements_touches": [{"id_cheminement": "id-c1", "fichier": "RPD_Fourreau_Reco.geojson"}],
        }
        feature = construire_geojson_ecarts([anomalie], "1.1")["features"][0]
        props = feature["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["version"] == "1.1"
        assert props["id_point"] == "id-p1"
        assert props["nb_cheminements_touches"] == 1

    def test_ids_cheminements_en_csv(self):
        anomalie = {
            "id_point": "id-p",
            "coordonnees": [0.0, 0.0],
            "cheminements_touches": [
                {"id_cheminement": "id-c1", "fichier": "RPD_Fourreau_Reco.geojson"},
                {"id_cheminement": "id-c2", "fichier": "RPD_PleineTerre_Reco.geojson"},
            ],
        }
        props = construire_geojson_ecarts([anomalie], "1.0")["features"][0]["properties"]
        assert props["ids_cheminements_touches"] == "id-c1,id-c2"
        assert props["fichiers_cheminements_touches"] == ("RPD_Fourreau_Reco.geojson,RPD_PleineTerre_Reco.geojson")

    def test_geometrie_point_aux_coordonnees_du_point(self):
        anomalie = {
            "id_point": "id-p",
            "coordonnees": [3.0, 7.0],
            "cheminements_touches": [],
        }
        geom = construire_geojson_ecarts([anomalie], "1.0")["features"][0]["geometry"]
        assert geom["type"] == "Point"
        assert geom["coordinates"] == [3.0, 7.0]

    def test_id_point_none_reste_none(self):
        anomalie = {
            "id_point": None,
            "coordonnees": [0.0, 0.0],
            "cheminements_touches": [],
        }
        props = construire_geojson_ecarts([anomalie], "1.0")["features"][0]["properties"]
        assert props["id_point"] is None


# ---------------------------------------------------------------------------
# TestCli
# ---------------------------------------------------------------------------


class TestCli:
    """Tests de l'orchestration CLI (executer_controle_cli)."""

    def _ecrire_source_v10(self, tmp_path, features_points):
        """Ecrit RPD_PointLeveOuvrageReseau_Reco.geojson en format V1.0."""
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), features_points)

    def _ecrire_source_v11(self, tmp_path, features_points):
        """Ecrit RPD_PointLeveOuvrageReseau_Reco.geojson en format V1.1."""
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), features_points)

    def test_repertoire_inexistant(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path / "inexistant"))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_fichier_source_absent(self, tmp_path):
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert FICHIER_SOURCE in resultat["erreur"]

    def test_version_10_auto_detectee(self, tmp_path):
        self._ecrire_source_v10(
            tmp_path,
            [_feature_point_v10("id-p1", [5.0, 0.0])],
        )
        resultat = executer_controle_cli(str(tmp_path), version=JETON_AUTO)
        assert resultat["succes"] is True
        assert resultat["version_detectee"] == "1.0"

    def test_version_11_auto_detectee(self, tmp_path):
        self._ecrire_source_v11(
            tmp_path,
            [_feature_point_v11("id-p1", [5.0, 0.0])],
        )
        resultat = executer_controle_cli(str(tmp_path), version=JETON_AUTO)
        assert resultat["succes"] is True
        assert resultat["version_detectee"] == "1.1"

    def test_version_explicite(self, tmp_path):
        # V1.0 data with explicit 1.1 → no ChargeGeneratrice detected
        self._ecrire_source_v10(
            tmp_path,
            [_feature_point_v10("id-p1", [5.0, 0.0])],
        )
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["version_detectee"] == "1.1"
        assert resultat["nombre_points_charge_analyses"] == 0

    def test_succes_sans_anomalie(self, tmp_path):
        self._ecrire_source_v10(
            tmp_path,
            [_feature_point_v10("id-p1", [5.0, 0.0])],
        )
        # Fourreau avec profondeur, passe par le point
        ecrire_collection(
            str(tmp_path / "RPD_Fourreau_Reco.geojson"),
            [_feature_cheminement("id-f1", [[0.0, 0.0], [10.0, 0.0]], profondeur=1.3)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_anomalie_detectee(self, tmp_path):
        self._ecrire_source_v10(
            tmp_path,
            [_feature_point_v10("id-p1", [5.0, 0.0])],
        )
        ecrire_collection(
            str(tmp_path / "RPD_Fourreau_Reco.geojson"),
            [_feature_cheminement("id-f1", [[0.0, 0.0], [10.0, 0.0]], profondeur=None)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_fichier_sortie_cree(self, tmp_path):
        self._ecrire_source_v10(tmp_path, [])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(tmp_path / FICHIER_SORTIE)

    def test_sortie_personnalisee(self, tmp_path):
        self._ecrire_source_v10(tmp_path, [])
        dossier_sortie = tmp_path / "sortie"
        dossier_sortie.mkdir()
        executer_controle_cli(str(tmp_path), str(dossier_sortie))
        assert os.path.isfile(dossier_sortie / FICHIER_SORTIE)

    def test_fichiers_cheminement_absents_rapportes(self, tmp_path):
        self._ecrire_source_v10(tmp_path, [])
        resultat = executer_controle_cli(str(tmp_path))
        assert set(resultat["fichiers_cheminement_absents"]) == set(FICHIERS_CHEMINEMENT_SOUTERRAIN)

    def test_compteurs_dans_rapport(self, tmp_path):
        self._ecrire_source_v10(
            tmp_path,
            [_feature_point_v10("id-p1", [5.0, 0.0])],
        )
        ecrire_collection(
            str(tmp_path / "RPD_Fourreau_Reco.geojson"),
            [_feature_cheminement("id-f1", [[0.0, 0.0], [10.0, 0.0]])],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_points_charge_analyses"] == 1
        assert resultat["nombre_cheminements_analyses"] == 1
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_geojson_sortie_valide(self, tmp_path):
        self._ecrire_source_v10(
            tmp_path,
            [_feature_point_v10("id-p1", [5.0, 0.0])],
        )
        ecrire_collection(
            str(tmp_path / "RPD_Fourreau_Reco.geojson"),
            [_feature_cheminement("id-f1", [[0.0, 0.0], [10.0, 0.0]], profondeur=None)],
        )
        executer_controle_cli(str(tmp_path))
        with open(tmp_path / FICHIER_SORTIE, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1
        assert contenu["features"][0]["properties"]["type_anomalie"] == TYPE_ANOMALIE
