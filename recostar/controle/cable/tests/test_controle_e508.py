"""
Tests du controle E508 : cables HTB situes dans l'emprise DR.

Couvre :
  - le filtrage des cables au chargement (Statut et DomaineTension)
  - la detection d'un cable HTB dans l'emprise et la conformite hors emprise
  - la reprojection du point representatif avant le test de containment
  - la construction du GeoJSON d'ecarts (priorite information)
  - l'exclusion metier de certains numeros d'affaire (12345678, prefixe OSR)
  - l'execution CLI complete (numero d'affaire manquant, repertoire invalide,
    fichier source absent, cas nominaux) avec mock du referentiel DR
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any
from unittest.mock import patch

from controle_e508 import (
    DOMAINE_TENSION_CONTROLE,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    STATUT_CONTROLE,
    TYPE_ANOMALIE,
    charger_cables_htb,
    construire_geojson_ecarts,
    detecter_cables_dans_emprise,
    executer_controle_cli,
)
from utils_emprise_dr import creer_transformateur
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Emprise carree de test, en coordonnees Lambert 93 plausibles
_EMPRISE_TEST: list[dict[str, Any]] = [
    {
        "code": "8A",
        "coordonnees": [
            [
                [600000.0, 6600000.0],
                [700000.0, 6600000.0],
                [700000.0, 6700000.0],
                [600000.0, 6700000.0],
                [600000.0, 6600000.0],
            ]
        ],
        "bbox": (600000.0, 6600000.0, 700000.0, 6700000.0),
    }
]

# Traces de cable : le premier a son centroide dans l'emprise, le second dehors
TRACE_DANS_EMPRISE: list[list[float]] = [[650000.0, 6650000.0], [650100.0, 6650000.0]]
TRACE_HORS_EMPRISE: list[list[float]] = [[100000.0, 6200000.0], [100100.0, 6200000.0]]

_NUMERO_AFFAIRE: str = "RAC-CVL-25-007998"


def _feature_cable(
    identifiant: str,
    coordonnees: list[list[float]] | None = None,
    statut: str = STATUT_CONTROLE,
    domaine_tension: str = DOMAINE_TENSION_CONTROLE,
    geometrie: dict[str, Any] | None = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON d'un cable electrique, dans l'emprise par defaut."""
    proprietes: dict[str, Any] = {
        "id": identifiant,
        "Statut": statut,
        "DomaineTension": domaine_tension,
    }
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": geometrie or {"type": "LineString", "coordinates": coordonnees or TRACE_DANS_EMPRISE},
    }


def _ecrire_cables(repertoire: Any, features: list[dict[str, Any]]) -> None:
    """Ecrit le fichier source des cables electriques dans le repertoire."""
    ecrire_collection(str(repertoire / FICHIER_CABLE_ELECTRIQUE), features)


def _executer(repertoire: Any, numero_affaire: str = _NUMERO_AFFAIRE) -> dict[str, Any]:
    """Execute le controle avec le referentiel DR mocke par l'emprise de test."""
    with patch("controle_e508.resoudre_emprises_affaire", return_value=(_EMPRISE_TEST, "8A", None)):
        return executer_controle_cli(str(repertoire), numero_affaire)


# --------------------------------------------------------------------------- #
# Chargement
# --------------------------------------------------------------------------- #


class TestChargerCablesHtb:
    """Tests du filtrage applique au chargement des cables."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        source = charger_cables_htb(str(tmp_path))
        assert source.fichier_absent is True
        assert source.cables == []

    def test_cable_htb_en_service_retenu(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        source = charger_cables_htb(str(tmp_path))
        assert source.fichier_absent is False
        assert len(source.cables) == 1

    def test_statut_hors_perimetre_ecarte(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1", statut="InService")])
        assert charger_cables_htb(str(tmp_path)).cables == []

    def test_domaine_tension_hors_perimetre_ecarte(self, tmp_path: Any) -> None:
        _ecrire_cables(
            tmp_path,
            [_feature_cable("c1", domaine_tension="HTA"), _feature_cable("c2", domaine_tension="BT")],
        )
        assert charger_cables_htb(str(tmp_path)).cables == []

    def test_proprietes_absentes_ecartees(self, tmp_path: Any) -> None:
        feature = {"type": "Feature", "properties": None, "geometry": None}
        _ecrire_cables(tmp_path, [feature])
        assert charger_cables_htb(str(tmp_path)).cables == []

    def test_crs_propage(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1")],
            "EPSG:2154",
        )
        source = charger_cables_htb(str(tmp_path))
        assert source.crs is not None
        assert source.nom_crs == "urn:ogc:def:crs:EPSG::2154"


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterCablesDansEmprise:
    """Tests de la detection des cables HTB situes dans l'emprise DR."""

    def test_cable_dans_emprise_signale(self) -> None:
        anomalies, nb = detecter_cables_dans_emprise([_feature_cable("c1")], _EMPRISE_TEST, None)
        assert nb == 1
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable"] == "c1"

    def test_cable_hors_emprise_conforme(self) -> None:
        cable = _feature_cable("c1", coordonnees=TRACE_HORS_EMPRISE)
        anomalies, nb = detecter_cables_dans_emprise([cable], _EMPRISE_TEST, None)
        assert nb == 1
        assert anomalies == []

    def test_geometrie_absente_non_analysee(self) -> None:
        cable = _feature_cable("c1", geometrie={"type": "LineString", "coordinates": []})
        cable_sans_geometrie = {"type": "Feature", "properties": {"id": "c2"}, "geometry": None}
        anomalies, nb = detecter_cables_dans_emprise([cable, cable_sans_geometrie], _EMPRISE_TEST, None)
        assert nb == 0
        assert anomalies == []

    def test_aucune_emprise_aucune_anomalie(self) -> None:
        anomalies, nb = detecter_cables_dans_emprise([_feature_cable("c1")], [], None)
        assert nb == 1
        assert anomalies == []

    def test_reprojection_appliquee(self) -> None:
        # Coordonnees WGS84 d'un point situe dans l'emprise Lambert 93 de test
        cable = _feature_cable("c1", coordonnees=[[2.3426, 46.9483], [2.3427, 46.9483]])
        transformateur = creer_transformateur("EPSG:4326")
        anomalies, nb = detecter_cables_dans_emprise([cable], _EMPRISE_TEST, transformateur)
        assert nb == 1
        assert len(anomalies) == 1

    def test_type_geometrie_reporte(self) -> None:
        anomalies, _ = detecter_cables_dans_emprise([_feature_cable("c1")], _EMPRISE_TEST, None)
        assert anomalies[0]["type_geometrie"] == "LineString"


# --------------------------------------------------------------------------- #
# Sortie GeoJSON
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de la construction du fichier d'ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "id_cable": "c1",
            "type_geometrie": "LineString",
            "geometrie": {"type": "LineString", "coordinates": TRACE_DANS_EMPRISE},
        }

    def test_sans_anomalie_collection_vide(self) -> None:
        resultat = construire_geojson_ecarts([], "8A")
        assert resultat["type"] == "FeatureCollection"
        assert resultat["features"] == []

    def test_proprietes_anomalie(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()], "8A")
        proprietes = resultat["features"][0]["properties"]
        assert proprietes["type_anomalie"] == TYPE_ANOMALIE
        assert proprietes["id_cable"] == "c1"
        assert proprietes["domaine_tension"] == DOMAINE_TENSION_CONTROLE
        assert proprietes["codes_dr"] == "8A"
        assert proprietes["priorite"] == PRIORITE_ANOMALIE

    def test_geometrie_du_cable_conservee(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()], "8A")
        assert resultat["features"][0]["geometry"]["coordinates"] == TRACE_DANS_EMPRISE

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], "8A", crs)["crs"] == crs

    def test_crs_absent_non_ajoute(self) -> None:
        assert "crs" not in construire_geojson_ecarts([], "8A")


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Tests de l'orchestration CLI du controle."""

    def test_numero_affaire_absent_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path), None)
        assert resultat["succes"] is False
        assert "numero_affaire" in resultat["erreur"]

    def test_affaire_exclue_court_circuite_sans_traitement(self, tmp_path: Any) -> None:
        # Numero exclu -> succes immediat, 0 anomalie, controle_ignore=True.
        # Aucun mock du referentiel : l'exclusion doit preceder tout chargement.
        resultat = executer_controle_cli(str(tmp_path), "OSR-CVL-25-007998")
        assert resultat["succes"] is True
        assert resultat["controle_ignore"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_affaire_exclue_numero_exact(self, tmp_path: Any) -> None:
        """Le numero 12345678 n'est pas resolvable : il exclut le controle."""
        resultat = executer_controle_cli(str(tmp_path), "12345678")
        assert resultat["succes"] is True
        assert resultat["controle_ignore"] is True

    def test_affaire_exclue_aucun_fichier_ecrit(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        executer_controle_cli(str(tmp_path), "12345678")
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_repertoire_introuvable_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path / "absent"), _NUMERO_AFFAIRE)
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_erreur_referentiel_remontee(self, tmp_path: Any) -> None:
        with patch(
            "controle_e508.resoudre_emprises_affaire",
            return_value=([], "", "Trigramme 'XYZ' introuvable dans reference_dr.json"),
        ):
            resultat = executer_controle_cli(str(tmp_path), "RAC-XYZ-25-001234")
        assert resultat["succes"] is False
        assert "XYZ" in resultat["erreur"]

    def test_fichier_cable_absent_non_bloquant(self, tmp_path: Any) -> None:
        resultat = _executer(tmp_path)
        assert resultat["succes"] is True
        assert resultat["fichier_cable_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_avec_anomalie(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        resultat = _executer(tmp_path)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_cables_htb"] == 1
        assert resultat["nombre_cables_analyses"] == 1
        assert resultat["codes_dr"] == "8A"
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_nominal_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1", coordonnees=TRACE_HORS_EMPRISE)])
        resultat = _executer(tmp_path)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        resultat = _executer(tmp_path)
        assert os.path.isfile(resultat["sortie"])
        assert os.path.basename(resultat["sortie"]) == FICHIER_SORTIE

    def test_rapport_contient_champs_obligatoires(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        resultat = _executer(tmp_path)
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_cables_htb",
            "nombre_cables_analyses",
            "numero_affaire",
            "codes_dr",
            "fichier_cable_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"

    def test_sortie_dans_repertoire_dedie(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        destination = tmp_path / "sortie"
        with patch(
            "controle_e508.resoudre_emprises_affaire",
            return_value=(_EMPRISE_TEST, "8A", None),
        ):
            resultat = executer_controle_cli(str(tmp_path), _NUMERO_AFFAIRE, str(destination))
        assert os.path.isfile(str(destination / FICHIER_SORTIE))
        assert resultat["succes"] is True

    def test_comportement_identique_v10_v11(self, tmp_path: Any) -> None:
        # La V1.1 ajoute des champs sans impact sur le perimetre du controle
        repertoire_v11 = tmp_path / "v11"
        repertoire_v11.mkdir()
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        _ecrire_cables(repertoire_v11, [_feature_cable("c1", proprietes_extra={"Commentaire": "V1.1"})])
        resultat_v10 = _executer(tmp_path)
        resultat_v11 = _executer(repertoire_v11)
        assert resultat_v10["nombre_anomalies"] == resultat_v11["nombre_anomalies"] == 1
