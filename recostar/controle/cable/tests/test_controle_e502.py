"""
Tests du controle E502 : designation normalisee des cables electriques.

Couvre :
  - la normalisation des valeurs (casse, flottants, sentinelles None)
  - la construction de la cle de designation
  - le chargement du referentiel (absent / illisible / valide)
  - la detection (filtre Statut, conforme / non conforme)
  - la construction du GeoJSON d'ecarts
  - l'execution CLI (referentiel mocke + integration sur le vrai referentiel)
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any
from unittest.mock import patch

from controle_e502 import (
    CHAMPS_DESIGNATION,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    STATUT_CONTROLE,
    TYPE_ANOMALIE,
    _est_a_controler,
    _normaliser_valeur,
    charger_referentiel,
    compter_cables_a_controler,
    construire_cle,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
)
from utils_tests import ecrire_collection

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Combinaison presente dans le vrai referentiel (1re entree, en conventions GeoJSON)
_CONFORME: dict[str, Any] = {
    "DomaineTension": "BT",
    "HierarchieBT": "Reseau",
    "NombreConducteurs": 4,
    "Section": 100.0,
    "SectionNeutre": 70.0,
    "Isolant": "Reticulee",
    "Materiau": "Cuivre",
}


def _feature_cable(
    identifiant: str,
    statut: str = STATUT_CONTROLE,
    champs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cable electrique."""
    props: dict[str, Any] = {"id": identifiant, "Statut": statut}
    props.update(champs or {})
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
    }


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #


class TestNormaliserValeur:
    """Tests de _normaliser_valeur."""

    def test_chaine_minuscule_strip(self) -> None:
        assert _normaliser_valeur("Materiau", "  Cuivre ") == "cuivre"

    def test_flottant_entier_vers_int(self) -> None:
        assert _normaliser_valeur("Section", 70.0) == 70
        assert isinstance(_normaliser_valeur("Section", 70.0), int)

    def test_flottant_non_entier_inchange(self) -> None:
        assert _normaliser_valeur("Section", 70.5) == 70.5

    def test_int_inchange(self) -> None:
        assert _normaliser_valeur("NombreConducteurs", 4) == 4

    def test_none_hierarchie_sentinelle(self) -> None:
        assert _normaliser_valeur("HierarchieBT", None) == "0"

    def test_none_section_neutre_sentinelle(self) -> None:
        assert _normaliser_valeur("SectionNeutre", None) == 0

    def test_none_champ_sans_sentinelle(self) -> None:
        assert _normaliser_valeur("Materiau", None) is None


class TestConstruireCle:
    """Tests de construire_cle."""

    def test_ordre_et_normalisation(self) -> None:
        cle = construire_cle(_CONFORME)
        assert cle == ("bt", "reseau", 4, 100, 70, "reticulee", "cuivre")

    def test_meme_cle_referentiel_et_geojson(self) -> None:
        # Entree referentiel (minuscules, int) vs feature (PascalCase, float)
        entree_ref = {
            "DomaineTension": "BT",
            "HierarchieBT": "reseau",
            "NombreConducteurs": 4,
            "Section": 100,
            "SectionNeutre": 70,
            "Isolant": "reticulee",
            "Materiau": "cuivre",
        }
        assert construire_cle(entree_ref) == construire_cle(_CONFORME)

    def test_champs_absents_donnent_sentinelles(self) -> None:
        cle = construire_cle({"DomaineTension": "HTA"})
        # HierarchieBT -> "0", Section/SectionNeutre -> 0, autres -> None
        assert cle == ("hta", "0", None, 0, 0, None, None)


class TestHierarchieBtIgnoreeEnHta:
    """HierarchieBT n'est pas discriminant en HTA : sa valeur est neutralisee.

    Le champ ne qualifie que les cables BT ; toutes les entrees HTA du
    referentiel portent la sentinelle « 0 ». Un HierarchieBT renseigne sur un
    cable HTA ne doit donc pas empecher la reconnaissance de sa designation —
    ce defaut releve d'E501 (hierarchie_bt_interdite), pas d'E502.
    """

    _CABLE_HTA: dict[str, Any] = {
        "DomaineTension": "HTA",
        "NombreConducteurs": 3,
        "Section": 150.0,
        "SectionNeutre": None,
        "Isolant": "Reticulee",
        "Materiau": "Alu",
    }

    def test_hierarchie_renseignee_donne_la_meme_cle_que_absente(self) -> None:
        avec = construire_cle({**self._CABLE_HTA, "HierarchieBT": "Reseau"})
        sans = construire_cle(self._CABLE_HTA)
        assert avec == sans

    def test_valeur_neutralisee_en_sentinelle(self) -> None:
        cle = construire_cle({**self._CABLE_HTA, "HierarchieBT": "Reseau"})
        assert cle == ("hta", "0", 3, 150, 0, "reticulee", "alu")

    def test_toute_valeur_de_hierarchie_est_neutralisee(self) -> None:
        """La neutralisation ne depend pas de la valeur portee."""
        cles = {
            construire_cle({**self._CABLE_HTA, "HierarchieBT": valeur})
            for valeur in ("Reseau", "TronconCommun", "DerivationIndividuelle", "valeur_inattendue")
        }
        assert len(cles) == 1

    def test_bt_reste_discrimine_par_hierarchie(self) -> None:
        """Non-regression : en BT, HierarchieBT reste un critere a part entiere."""
        reseau = construire_cle({**_CONFORME, "HierarchieBT": "Reseau"})
        troncon = construire_cle({**_CONFORME, "HierarchieBT": "TronconCommun"})
        assert reseau != troncon

    def test_htb_reste_discrimine_par_hierarchie(self) -> None:
        """Seul le domaine HTA est neutralise, conformement a la demande."""
        htb = {**self._CABLE_HTA, "DomaineTension": "HTB"}
        assert construire_cle({**htb, "HierarchieBT": "Reseau"}) != construire_cle(htb)


# --------------------------------------------------------------------------- #
# Chargement du referentiel
# --------------------------------------------------------------------------- #


class TestChargerReferentiel:
    """Tests de charger_referentiel."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        index, erreur = charger_referentiel(str(tmp_path / "absent.json"))
        assert index == set()
        assert erreur is not None
        assert "introuvable" in erreur

    def test_json_invalide(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "ref.json")
        with open(chemin, "w", encoding="utf-8") as fichier:
            fichier.write("{ pas du json")
        index, erreur = charger_referentiel(chemin)
        assert index == set()
        assert erreur is not None
        assert "illisible" in erreur

    def test_chargement_et_deduplication(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "ref.json")
        # Deux entrees de meme designation (sig_id differents) -> 1 seule cle
        entrees = [
            {**_CONFORME, "sig_id": 1},
            {**_CONFORME, "sig_id": 2},
            {**_CONFORME, "Section": 240.0, "sig_id": 3},
        ]
        with open(chemin, "w", encoding="utf-8") as fichier:
            json.dump(entrees, fichier)
        index, erreur = charger_referentiel(chemin)
        assert erreur is None
        assert len(index) == 2


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies et du filtre de statut."""

    def _index(self) -> set[tuple[Any, ...]]:
        return {construire_cle(_CONFORME)}

    def test_conforme_aucune_anomalie(self) -> None:
        features = [_feature_cable("c1", champs=_CONFORME)]
        assert detecter_anomalies(features, self._index()) == []

    def test_non_conforme_anomalie(self) -> None:
        champs = {**_CONFORME, "Section": 99999.0}
        anomalies = detecter_anomalies([_feature_cable("c1", champs=champs)], self._index())
        assert len(anomalies) == 1
        assert anomalies[0]["id_cable"] == "c1"
        assert anomalies[0]["valeurs"]["Section"] == 99999.0

    def test_statut_non_controle_ignore(self) -> None:
        # Meme designation non conforme mais statut != UnderCommissionning
        champs = {**_CONFORME, "Section": 99999.0}
        features = [_feature_cable("c1", statut="Projected", champs=champs)]
        assert detecter_anomalies(features, self._index()) == []

    def test_est_a_controler(self) -> None:
        assert _est_a_controler({"Statut": STATUT_CONTROLE}) is True
        assert _est_a_controler({"Statut": "Functional"}) is False
        assert _est_a_controler({}) is False

    def test_compter_cables_a_controler(self) -> None:
        features = [
            _feature_cable("c1", champs=_CONFORME),
            _feature_cable("c2", statut="Projected", champs=_CONFORME),
            _feature_cable("c3", champs=_CONFORME),
        ]
        assert compter_cables_a_controler(features) == 2


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "id_cable": "c1",
            "valeurs": dict(_CONFORME),
            "geometrie": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
        }

    def test_proprietes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["fichier_source"] == FICHIER_CABLE_ELECTRIQUE
        assert props["id_cable"] == "c1"
        # Les 7 champs bruts sont exposes sous leur nom d'origine
        for champ in CHAMPS_DESIGNATION:
            assert props[champ] == _CONFORME[champ]

    def test_geometrie_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geom["type"] == "LineString"

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI (referentiel mocke)
# --------------------------------------------------------------------------- #

_INDEX_MOCK = ({("bt", "reseau", 4, 100, 70, "reticulee", "cuivre")}, None)


class TestCli:
    """Tests de executer_controle_cli avec referentiel mocke."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    @patch("controle_e502.charger_referentiel")
    def test_referentiel_absent_erreur(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = (set(), "Referentiel introuvable : x")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "Referentiel" in resultat["erreur"]

    @patch("controle_e502.charger_referentiel")
    def test_fichier_cable_absent_non_bloquant(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = _INDEX_MOCK
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_cable_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    @patch("controle_e502.charger_referentiel")
    def test_nominal_conforme(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = _INDEX_MOCK
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=_CONFORME)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 1
        assert resultat["nombre_entrees_referentiel"] == 1

    @patch("controle_e502.charger_referentiel")
    def test_nominal_non_conforme(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = _INDEX_MOCK
        champs = {**_CONFORME, "Materiau": "Inconnu"}
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=champs)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    @patch("controle_e502.charger_referentiel")
    def test_fichier_ecarts_cree(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = _INDEX_MOCK
        champs = {**_CONFORME, "Materiau": "Inconnu"}
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=champs)])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    @patch("controle_e502.charger_referentiel")
    def test_aucun_fichier_sans_anomalie(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = _INDEX_MOCK
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=_CONFORME)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    @patch("controle_e502.charger_referentiel")
    def test_rapport_champs_obligatoires(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = _INDEX_MOCK
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=_CONFORME)])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_cables_controles",
            "nombre_entrees_referentiel",
            "fichier_cable_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Integration sur le vrai referentiel du depot
# --------------------------------------------------------------------------- #


class TestIntegrationReferentielReel:
    """Tests utilisant le referentiel reel versionne dans le depot."""

    def test_cable_conforme_reel(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=_CONFORME)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_entrees_referentiel"] > 0

    def test_cable_non_conforme_reel(self, tmp_path: Any) -> None:
        champs = {**_CONFORME, "Section": 123456.0}
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=champs)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    def test_cable_hta_avec_hierarchie_bt_reconnu(self, tmp_path: Any) -> None:
        """Cas reel : un cable HTA « 150 AL S6 » portant HierarchieBT = Reseau.

        Les 6 autres champs correspondent a une entree du referentiel : seule la
        presence indue de HierarchieBT le faisait echouer. E502 doit desormais le
        reconnaitre, le defaut d'attribut restant du ressort d'E501.
        """
        champs = {
            "DomaineTension": "HTA",
            "HierarchieBT": "Reseau",
            "NombreConducteurs": 3,
            "Section": 150.0,
            "SectionNeutre": None,
            "Isolant": "Reticulee",
            "Materiau": "Alu",
        }
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=champs)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_cable_hta_inconnu_reste_signale(self, tmp_path: Any) -> None:
        """La neutralisation n'ouvre pas d'angle mort sur les 6 autres champs."""
        champs = {
            "DomaineTension": "HTA",
            "HierarchieBT": "Reseau",
            "NombreConducteurs": 3,
            "Section": 123456.0,
            "SectionNeutre": None,
            "Isolant": "Reticulee",
            "Materiau": "Alu",
        }
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=champs)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """La designation est controlee identiquement en V1.0 et V1.1.

    Les champs additionnels de la V1.1 (Etiquette, Commentaire) n'influencent
    pas la cle de designation (seuls les 7 champs cibles sont pris en compte).
    """

    @patch("controle_e502.charger_referentiel")
    def test_v11_champs_extra_sans_effet(self, mock_ref: Any, tmp_path: Any) -> None:
        mock_ref.return_value = _INDEX_MOCK
        champs = {**_CONFORME, "Etiquette": "E1", "Commentaire": "note"}
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1", champs=champs)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
