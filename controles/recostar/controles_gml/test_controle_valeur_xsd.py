"""Tests unitaires pour le controle de conformite des valeurs XSD."""

import json
import os
from typing import Any

import pytest

from controle_valeur_xsd import (
    FICHIER_ECARTS_AGREGE,
    FICHIER_RAPPORT_JSON,
    PREFIXE_ECARTS_GEOJSON,
    _detecter_ecarts_feature,
    _indexer_valeurs_autorisees,
    construire_geojson_ecarts,
    construire_rapport_json,
    controler_fichier,
    executer_controle_cli,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def referentiel_minimal() -> dict[str, Any]:
    """Referentiel de test couvrant DomaineTension et TypeJonction."""
    return {
        "version": "V1.1-test",
        "objets": {
            "Câble": {
                "section": "12.1",
                "types": {
                    "DomaineTensionValue": {
                        "categorie": "Enumeration",
                        "section": "12.1.1",
                        "valeurs": [
                            {"valeur": "BT", "alias": "Basse Tension"},
                            {"valeur": "HTA", "alias": "Haute Tension A"},
                        ],
                    },
                    "ConditionOfFacilityValueReco": {
                        "categorie": "Enumeration",
                        "section": "12.1.5",
                        "valeurs": [
                            {"valeur": "Functional", "alias": ""},
                            {"valeur": "UnderCommissionning", "alias": ""},
                        ],
                    },
                },
            },
            "Nœuds": {
                "section": "12.4",
                "types": {
                    "TypeJonctionValueReco": {
                        "categorie": "Enumeration",
                        "section": "12.4.1",
                        "valeurs": [
                            {"valeur": "Derivation", "alias": ""},
                            {"valeur": "RemonteeAeroSouterraine", "alias": ""},
                        ],
                    }
                },
            },
        },
    }


@pytest.fixture
def index_valeurs(referentiel_minimal: dict[str, Any]) -> dict[str, set[str]]:
    """Index precalcule pour les tests."""
    return _indexer_valeurs_autorisees(referentiel_minimal)


# ---------------------------------------------------------------------------
# Helpers d'ecriture
# ---------------------------------------------------------------------------
def _ecrire_geojson(
    chemin: str,
    features: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> None:
    """Ecrit un GeoJSON minimal."""
    collection: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        collection["crs"] = crs
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


def _ecrire_referentiel(chemin: str, referentiel: dict[str, Any]) -> None:
    """Ecrit le referentiel sur disque."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(referentiel, fichier, ensure_ascii=False)


def _feature(
    identifiant: str,
    proprietes_extra: dict[str, Any],
    geometrie: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fabrique une feature GeoJSON avec les proprietes fournies."""
    props = {"id": identifiant, **proprietes_extra}
    return {
        "type": "Feature",
        "properties": props,
        "geometry": geometrie or {"type": "Point", "coordinates": [0.0, 0.0]},
    }


# ---------------------------------------------------------------------------
# TestIndexerValeursAutorisees
# ---------------------------------------------------------------------------
class TestIndexerValeursAutorisees:
    """Tests pour la construction de l'index id_type -> set de valeurs."""

    def test_index_contient_tous_les_types(
        self, referentiel_minimal: dict[str, Any]
    ) -> None:
        index = _indexer_valeurs_autorisees(referentiel_minimal)
        assert "DomaineTensionValue" in index
        assert "TypeJonctionValueReco" in index
        assert "ConditionOfFacilityValueReco" in index

    def test_valeurs_sont_des_sets(self, referentiel_minimal: dict[str, Any]) -> None:
        index = _indexer_valeurs_autorisees(referentiel_minimal)
        assert isinstance(index["DomaineTensionValue"], set)
        assert index["DomaineTensionValue"] == {"BT", "HTA"}

    def test_referentiel_vide(self) -> None:
        """Un referentiel sans types retourne un index vide."""
        assert _indexer_valeurs_autorisees({"objets": {}}) == {}


# ---------------------------------------------------------------------------
# TestDetecterEcartsFeature
# ---------------------------------------------------------------------------
class TestDetecterEcartsFeature:
    """Tests pour la detection des ecarts sur une feature."""

    def test_aucun_ecart_si_valeur_conforme(
        self, index_valeurs: dict[str, set[str]]
    ) -> None:
        feature = _feature("j1", {"DomaineTension": "HTA"})
        champs = {"DomaineTension": "DomaineTensionValue"}
        assert _detecter_ecarts_feature(feature, champs, index_valeurs) == []

    def test_ecart_detecte_sur_valeur_non_autorisee(
        self, index_valeurs: dict[str, set[str]]
    ) -> None:
        feature = _feature("j1", {"DomaineTension": "HTZ"})
        champs = {"DomaineTension": "DomaineTensionValue"}
        ecarts = _detecter_ecarts_feature(feature, champs, index_valeurs)
        assert len(ecarts) == 1
        assert ecarts[0]["champ"] == "DomaineTension"
        assert ecarts[0]["valeur"] == "HTZ"

    def test_valeur_vide_ignoree(self, index_valeurs: dict[str, set[str]]) -> None:
        """None ou chaine vide ne doit pas generer d'ecart (autre controle)."""
        feature = _feature("j1", {"DomaineTension": None})
        champs = {"DomaineTension": "DomaineTensionValue"}
        assert _detecter_ecarts_feature(feature, champs, index_valeurs) == []

    def test_type_absent_du_referentiel_ignore(
        self, index_valeurs: dict[str, set[str]]
    ) -> None:
        """Un champ mappe vers un type inconnu est silencieusement ignore."""
        feature = _feature("j1", {"Foo": "Bar"})
        champs = {"Foo": "TypeInconnu"}
        assert _detecter_ecarts_feature(feature, champs, index_valeurs) == []


# ---------------------------------------------------------------------------
# TestControlerFichier
# ---------------------------------------------------------------------------
class TestControlerFichier:
    """Tests pour le controle d'un fichier GeoJSON complet."""

    def test_jonction_bt_et_tension_inconnue(
        self, index_valeurs: dict[str, set[str]]
    ) -> None:
        features = [
            _feature("j1", {"DomaineTension": "BT", "TypeJonction": "Derivation"}),
            _feature("j2", {"DomaineTension": "HTZ", "TypeJonction": "FooBar"}),
        ]
        collection = {
            "type": "FeatureCollection",
            "features": features,
            "crs": {"x": 1},
        }
        resultat = controler_fichier(
            "RPD_Jonction_Reco.geojson", collection, index_valeurs
        )

        assert resultat["nombre_features"] == 2
        assert len(resultat["features_ecarts"]) == 1
        assert resultat["features_ecarts"][0]["properties"]["id_entite"] == "j2"
        assert resultat["crs"] == {"x": 1}

    def test_fichier_non_mappe_ne_produit_aucun_ecart(
        self, index_valeurs: dict[str, set[str]]
    ) -> None:
        collection = {
            "type": "FeatureCollection",
            "features": [_feature("m1", {"DomaineTension": "HTZ"})],
        }
        resultat = controler_fichier(
            "RPD_Materiel_Reco.geojson", collection, index_valeurs
        )
        assert resultat["features_ecarts"] == []
        assert resultat["anomalies"] == []


# ---------------------------------------------------------------------------
# TestConstruireGeojsonEcarts
# ---------------------------------------------------------------------------
class TestConstruireGeojsonEcarts:
    """Tests pour la construction du GeoJSON de sortie."""

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3943"}}
        resultat = construire_geojson_ecarts([], crs)
        assert resultat["crs"] == crs

    def test_sans_crs(self) -> None:
        resultat = construire_geojson_ecarts([], None)
        assert "crs" not in resultat


# ---------------------------------------------------------------------------
# TestConstruireRapportJson
# ---------------------------------------------------------------------------
class TestConstruireRapportJson:
    """Tests pour l'agregation du rapport JSON."""

    def test_rapport_agrege_correctement(self) -> None:
        resultats = {
            "RPD_Jonction_Reco.geojson": {
                "features_ecarts": [{}],
                "anomalies": [{"fichier": "RPD_Jonction_Reco.geojson"}],
                "nombre_features": 3,
                "crs": None,
            },
            "RPD_CableElectrique_Reco.geojson": {
                "features_ecarts": [],
                "anomalies": [],
                "nombre_features": 5,
                "crs": None,
            },
        }
        rapport = construire_rapport_json(resultats)
        assert rapport["nombre_fichiers_analyses"] == 2
        assert rapport["nombre_features_total"] == 8
        assert rapport["nombre_anomalies"] == 1
        assert rapport["bloquant"] is True


# ---------------------------------------------------------------------------
# TestExecuterControleCli
# ---------------------------------------------------------------------------
class TestExecuterControleCli:
    """Tests d'integration du pipeline CLI."""

    def _preparer_environnement(
        self,
        tmp_path: Any,
        referentiel: dict[str, Any],
    ) -> tuple[str, str]:
        """Prepare un repertoire d'entree et ecrit le referentiel."""
        entree = tmp_path / "entree"
        entree.mkdir()
        chemin_ref = tmp_path / "referentiel.json"
        _ecrire_referentiel(str(chemin_ref), referentiel)
        return str(entree), str(chemin_ref)

    def test_pipeline_genere_rapport_et_ecarts(
        self, tmp_path: Any, referentiel_minimal: dict[str, Any]
    ) -> None:
        entree, chemin_ref = self._preparer_environnement(tmp_path, referentiel_minimal)

        crs = {"type": "name", "properties": {"name": "EPSG:3943"}}
        _ecrire_geojson(
            os.path.join(entree, "RPD_Jonction_Reco.geojson"),
            [
                _feature("j1", {"DomaineTension": "HTA", "TypeJonction": "Derivation"}),
                _feature("j2", {"DomaineTension": "HTZ", "TypeJonction": "Derivation"}),
            ],
            crs,
        )

        resultat = executer_controle_cli(entree, None, chemin_ref)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1

        chemin_rapport = os.path.join(entree, FICHIER_RAPPORT_JSON)
        with open(chemin_rapport, "r", encoding="utf-8") as fichier:
            rapport = json.load(fichier)
        assert rapport["bloquant"] is True

        chemin_ecarts = os.path.join(
            entree, f"{PREFIXE_ECARTS_GEOJSON}RPD_Jonction_Reco.geojson"
        )
        with open(chemin_ecarts, "r", encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert ecarts["crs"] == crs
        assert len(ecarts["features"]) == 1
        assert ecarts["features"][0]["properties"]["id_entite"] == "j2"

    def test_fichier_agrege_toujours_ecrit(
        self, tmp_path: Any, referentiel_minimal: dict[str, Any]
    ) -> None:
        """Le fichier agrege est ecrit meme avec zero anomalie."""
        entree, chemin_ref = self._preparer_environnement(tmp_path, referentiel_minimal)
        _ecrire_geojson(
            os.path.join(entree, "RPD_Jonction_Reco.geojson"),
            [_feature("j1", {"DomaineTension": "BT", "TypeJonction": "Derivation"})],
        )

        resultat = executer_controle_cli(entree, None, chemin_ref)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

        chemin_agrege = os.path.join(entree, FICHIER_ECARTS_AGREGE)
        assert os.path.isfile(chemin_agrege)
        with open(chemin_agrege, "r", encoding="utf-8") as fichier:
            agrege = json.load(fichier)
        assert agrege["type"] == "FeatureCollection"
        assert len(agrege["features"]) == 0

    def test_fichier_agrege_avec_anomalies(
        self, tmp_path: Any, referentiel_minimal: dict[str, Any]
    ) -> None:
        """Le fichier agrege contient toutes les anomalies de tous les fichiers."""
        entree, chemin_ref = self._preparer_environnement(tmp_path, referentiel_minimal)
        _ecrire_geojson(
            os.path.join(entree, "RPD_Jonction_Reco.geojson"),
            [
                _feature("j1", {"DomaineTension": "HTZ"}),
                _feature("j2", {"DomaineTension": "HTZ"}),
            ],
        )
        _ecrire_geojson(
            os.path.join(entree, "RPD_CableElectrique_Reco.geojson"),
            [_feature("c1", {"DomaineTension": "INVALIDE"})],
        )

        resultat = executer_controle_cli(entree, None, chemin_ref)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 3

        chemin_agrege = os.path.join(entree, FICHIER_ECARTS_AGREGE)
        with open(chemin_agrege, "r", encoding="utf-8") as fichier:
            agrege = json.load(fichier)
        assert len(agrege["features"]) == 3

    def test_repertoire_entree_inexistant(
        self, tmp_path: Any, referentiel_minimal: dict[str, Any]
    ) -> None:
        _, chemin_ref = self._preparer_environnement(tmp_path, referentiel_minimal)
        resultat = executer_controle_cli(str(tmp_path / "absent"), None, chemin_ref)
        assert resultat["succes"] is False

    def test_repertoire_sans_geojson(
        self, tmp_path: Any, referentiel_minimal: dict[str, Any]
    ) -> None:
        entree, chemin_ref = self._preparer_environnement(tmp_path, referentiel_minimal)
        resultat = executer_controle_cli(entree, None, chemin_ref)
        assert resultat["succes"] is False

    def test_sortie_separee(
        self, tmp_path: Any, referentiel_minimal: dict[str, Any]
    ) -> None:
        entree, chemin_ref = self._preparer_environnement(tmp_path, referentiel_minimal)
        sortie = tmp_path / "sortie"

        _ecrire_geojson(
            os.path.join(entree, "RPD_Jonction_Reco.geojson"),
            [_feature("j1", {"DomaineTension": "HTZ"})],
            {"type": "name"},
        )

        resultat = executer_controle_cli(entree, str(sortie), chemin_ref)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(str(sortie), FICHIER_RAPPORT_JSON))
        assert os.path.isfile(
            os.path.join(
                str(sortie), f"{PREFIXE_ECARTS_GEOJSON}RPD_Jonction_Reco.geojson"
            )
        )
