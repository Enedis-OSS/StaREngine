"""Tests unitaires pour le pipeline de controle GML."""

import json
import os
from typing import Any

import pytest

from controle_valeur_xsd import _resoudre_chemin_referentiel
from pipeline_controle_gml import executer_pipeline

# Verification de la disponibilite du referentiel pour les tests valeur_xsd
_CHEMIN_REFERENTIEL = _resoudre_chemin_referentiel(None)
_REFERENTIEL_DISPONIBLE = os.path.isfile(_CHEMIN_REFERENTIEL)


def _creer_geojson(
    features: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cree un dict GeoJSON FeatureCollection minimal."""
    return {"type": "FeatureCollection", "features": features}


def _creer_feature(id_val: str | None) -> dict[str, Any]:
    """Cree une feature GeoJSON minimale."""
    props: dict[str, Any] = {}
    if id_val is not None:
        props["id"] = id_val
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
    }


def _ecrire_geojson(chemin: str, features: list[dict[str, Any]]) -> None:
    """Ecrit un fichier GeoJSON minimal."""
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(_creer_geojson(features), f, ensure_ascii=False, indent=2)


class TestExecuterPipeline:
    """Tests d'integration pour executer_pipeline."""

    def test_repertoire_inexistant(self) -> None:
        """Un repertoire inexistant retourne une erreur."""
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False

    def test_sans_doublon(self, tmp_path: Any) -> None:
        """Donnees sans doublon : pipeline reussi, zero anomalie."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id1"), _creer_feature("id2")],
        )
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0
        assert "controle_unicite_id" in resultat["controles"]
        assert "controle_valeur_xsd" in resultat["controles"]

    def test_avec_doublons(self, tmp_path: Any) -> None:
        """Donnees avec doublons : pipeline reussi, anomalies comptees."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id1"), _creer_feature("id1")],
        )
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 2
        assert "controle_valeur_xsd" in resultat["controles"]

    def test_sortie_dans_repertoire_dedie(self, tmp_path: Any) -> None:
        """Les fichiers de sortie sont generes dans le repertoire de sortie."""
        entree = tmp_path / "entree"
        entree.mkdir()
        sortie = tmp_path / "sortie"

        _ecrire_geojson(
            str(entree / "RPD_A.geojson"),
            [_creer_feature("id1")],
        )
        resultat = executer_pipeline(str(entree), str(sortie))
        assert resultat["succes"] is True
        assert os.path.isdir(str(sortie))

    @pytest.mark.skipif(
        not _REFERENTIEL_DISPONIBLE,
        reason="Referentiel recostar introuvable",
    )
    def test_avec_anomalies_valeur_xsd(self, tmp_path: Any) -> None:
        """Donnees avec valeurs non conformes : anomalies XSD comptees."""
        features = [
            {
                "type": "Feature",
                "properties": {
                    "id": "j1",
                    "DomaineTension": "INVALIDE",
                    "TypeJonction": "Derivation",
                },
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            },
        ]
        with open(
            str(tmp_path / "RPD_Jonction_Reco.geojson"), "w", encoding="utf-8"
        ) as f:
            json.dump({"type": "FeatureCollection", "features": features}, f)

        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        controle_xsd = resultat["controles"]["controle_valeur_xsd"]
        assert controle_xsd["succes"] is True
        assert controle_xsd["nombre_anomalies"] >= 1
        assert resultat["nombre_anomalies_total"] >= 1
