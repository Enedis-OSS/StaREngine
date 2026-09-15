"""
Tests unitaires du pipeline de controle de projection.

Couvre les cas nominaux et les cas limites :
- execution complete du pipeline sur un repertoire valide
- resilience en cas d'echec d'un controle
- calcul du nombre total d'anomalies
- gestion des repertoires invalides
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from recostar.controle.projection.pipeline_controle_projection import (
    NOMS_CONTROLES,
    executer_pipeline,
)
from recostar.controle.projection.tests.utils_tests import (
    construire_feature,
    ecrire_collection_avec_crs,
    ecrire_metadata,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _resultat_succes(nb_anomalies: int = 0) -> dict[str, Any]:
    """Construit un resultat de controle reussi."""
    return {
        "succes": True,
        "nombre_anomalies": nb_anomalies,
        "sortie": "ecarts_e5105_projection_differente.geojson",
    }


def _resultat_echec(erreur: str = "Erreur") -> dict[str, Any]:
    """Construit un resultat de controle en echec."""
    return {"succes": False, "erreur": erreur}


# --------------------------------------------------------------------------- #
# Tests du pipeline
# --------------------------------------------------------------------------- #


class TestPipeline:
    """Tests de l'orchestration du pipeline de projection."""

    def test_repertoire_inexistant_retourne_erreur(self) -> None:
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    @patch("recostar.controle.projection.pipeline_controle_projection.executer_controle_projection_differente")
    def test_controle_e5105_execute(self, mock_e5105: Any, tmp_path: Any) -> None:
        mock_e5105.return_value = _resultat_succes(0)
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert mock_e5105.called

    @patch("recostar.controle.projection.pipeline_controle_projection.executer_controle_projection_differente")
    def test_nombre_anomalies_total_cumule(self, mock_e5105: Any, tmp_path: Any) -> None:
        mock_e5105.return_value = _resultat_succes(5)
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["nombre_anomalies_total"] == 5

    @patch("recostar.controle.projection.pipeline_controle_projection.executer_controle_projection_differente")
    def test_echec_controle_non_comptabilise(self, mock_e5105: Any, tmp_path: Any) -> None:
        mock_e5105.return_value = _resultat_echec("Metadata manquante")
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0

    @patch("recostar.controle.projection.pipeline_controle_projection.executer_controle_projection_differente")
    def test_resultats_indexe_par_nom_controle(self, mock_e5105: Any, tmp_path: Any) -> None:
        mock_e5105.return_value = _resultat_succes(3)
        resultat = executer_pipeline(str(tmp_path))
        assert "E-5105" in resultat["controles"]

    def test_noms_controles_couvrent_les_trois_codes(self) -> None:
        assert set(NOMS_CONTROLES) >= {"E-2200", "E-5105", "E-9302"}

    @patch("recostar.controle.projection.pipeline_controle_projection.executer_controle_projection_differente")
    def test_repertoire_sortie_distinct(self, mock_e5105: Any, tmp_path: Any) -> None:
        dossier_sortie = str(tmp_path / "sortie")
        mock_e5105.return_value = _resultat_succes(0)
        resultat = executer_pipeline(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        # Verifie que le dossier de sortie a ete cree
        assert os.path.isdir(dossier_sortie)

    def test_execution_reelle_sans_anomalie(self, tmp_path: Any) -> None:
        """Integration complete sans mock."""
        ecrire_metadata(str(tmp_path / "_metadata.json"), "EPSG:3947")
        features = [construire_feature("e1", "Point", [0.0, 0.0, 0.0])]
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:3947")
        resultat = executer_pipeline(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies_total"] == 0
        assert resultat["controles"]["E-5105"]["succes"] is True
