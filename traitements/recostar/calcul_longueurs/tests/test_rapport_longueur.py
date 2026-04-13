"""Tests de la generation du rapport PDF des longueurs de cables."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rapport_longueur import (  # type: ignore[import-not-found]
    LABELS_TYPE_ENTITE,
    _charger_resultats_longueurs,
    _formater_type_entite,
    generer_rapport_longueur,
)

# --- Fixtures ---


@pytest.fixture
def dossier_projet(tmp_path):
    """Cree un dossier projet temporaire avec la structure rapport/."""
    dossier_rapport = tmp_path / "rapport"
    dossier_rapport.mkdir()
    return tmp_path


@pytest.fixture
def resultats_longueurs():
    """Resultats de longueurs de cables pour les tests."""
    return [
        {
            "id": "cable_1",
            "domaine_tension": "HTA",
            "hierarchie_bt": "",
            "longueur_geographique": 150,
            "longueur_electrique": 166,
            "correction_depart": 11.0,
            "correction_arrivee": 5.0,
            "type_entite_depart": "remontee_aero_souterraine",
            "type_entite_arrivee": "poste",
            "correction_aerien": 0.0,
            "taux_aerien": 0.0,
        },
        {
            "id": "cable_2",
            "domaine_tension": "BT",
            "hierarchie_bt": "BT_400V",
            "longueur_geographique": 80,
            "longueur_electrique": 96,
            "correction_depart": 11.0,
            "correction_arrivee": 1.0,
            "type_entite_depart": "remontee_aero_souterraine",
            "type_entite_arrivee": "coffret",
            "correction_aerien": 4.0,
            "taux_aerien": 0.05,
        },
    ]


# --- Tests de _formater_type_entite ---


class TestFormaterTypeEntite:
    """Tests du formatage des types d'entites."""

    def test_ras(self):
        """Remontee aero-souterraine formatee en RAS."""
        assert _formater_type_entite("remontee_aero_souterraine") == "RAS"

    def test_poste(self):
        """Poste formate en Poste."""
        assert _formater_type_entite("poste") == "Poste"

    def test_coffret(self):
        """Coffret formate en Coffret."""
        assert _formater_type_entite("coffret") == "Coffret"

    def test_vide(self):
        """Chaine vide retourne un tiret."""
        assert _formater_type_entite("") == "-"

    def test_inconnu(self):
        """Type inconnu retourne tel quel."""
        assert _formater_type_entite("autre_type") == "autre_type"


# --- Tests de _charger_resultats_longueurs ---


class TestChargerResultatsLongueurs:
    """Tests du chargement des resultats depuis le fichier JSON."""

    def test_fichier_absent(self, dossier_projet):
        """Fichier JSON absent : retourne liste vide."""
        assert _charger_resultats_longueurs(str(dossier_projet)) == []

    def test_fichier_succes_false(self, dossier_projet):
        """Fichier JSON avec succes=false : retourne liste vide."""
        chemin_json = dossier_projet / "rapport" / "resultats_longueurs.json"
        chemin_json.write_text(
            json.dumps({"succes": False, "erreur": "test"}),
            encoding="utf-8",
        )
        assert _charger_resultats_longueurs(str(dossier_projet)) == []

    def test_fichier_valide(self, dossier_projet, resultats_longueurs):
        """Fichier JSON valide : retourne les resultats."""
        chemin_json = dossier_projet / "rapport" / "resultats_longueurs.json"
        chemin_json.write_text(
            json.dumps({"succes": True, "resultats": resultats_longueurs}),
            encoding="utf-8",
        )
        resultats = _charger_resultats_longueurs(str(dossier_projet))
        assert len(resultats) == 2
        assert resultats[0]["id"] == "cable_1"


# --- Tests de generer_rapport_longueur ---


class TestGenererRapportLongueur:
    """Tests de la generation du rapport PDF."""

    def test_genere_fichier_pdf(self, dossier_projet, resultats_longueurs):
        """Le rapport PDF est genere dans le dossier rapport/."""
        chemin_pdf = generer_rapport_longueur(str(dossier_projet), resultats_longueurs)
        assert os.path.isfile(chemin_pdf)
        assert chemin_pdf.endswith(".pdf")

    def test_nom_fichier_pdf(self, dossier_projet, resultats_longueurs):
        """Le fichier PDF a le nom attendu."""
        chemin_pdf = generer_rapport_longueur(str(dossier_projet), resultats_longueurs)
        assert os.path.basename(chemin_pdf) == "rapport_longueurs_cables.pdf"

    def test_rapport_avec_liste_vide(self, dossier_projet):
        """Le rapport est genere meme avec une liste vide."""
        chemin_pdf = generer_rapport_longueur(str(dossier_projet), [])
        assert os.path.isfile(chemin_pdf)

    def test_cree_dossier_rapport_si_absent(self, tmp_path, resultats_longueurs):
        """Le dossier rapport/ est cree s'il n'existe pas."""
        chemin_pdf = generer_rapport_longueur(str(tmp_path), resultats_longueurs)
        assert os.path.isfile(chemin_pdf)
        assert os.path.isdir(tmp_path / "rapport")
