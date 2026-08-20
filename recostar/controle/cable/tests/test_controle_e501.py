"""
Tests du controle E501 : coherence FonctionCable_href / DomaineTension / HierarchieBT.

Couvre :
  - les trois validateurs metier (electrique, terre, telecommunication)
  - toutes les regles et leurs cas limites
  - la detection par fichier
  - la construction du GeoJSON d'ecarts
  - l'execution CLI complete
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

from controle_e501 import (
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TELECOM,
    FICHIER_CABLE_TERRE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    TYPE_DOMAINE_INCOHERENT,
    TYPE_FONCTION_INVALIDE,
    TYPE_HIERARCHIE_INTERDITE,
    _est_renseigne,
    construire_geojson_ecarts,
    detecter_anomalies_fichier,
    executer_controle_cli,
    valider_cable_electrique,
    valider_cable_telecom,
    valider_cable_terre,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _feature_cable(
    identifiant: str,
    fonction: Any = None,
    domaine: Any = None,
    hierarchie: Any = None,
) -> dict[str, Any]:
    """Feature GeoJSON minimale representant un cable avec ses 3 champs metier."""
    return {
        "type": "Feature",
        "properties": {
            "id": identifiant,
            "FonctionCable_href": fonction,
            "DomaineTension": domaine,
            "HierarchieBT": hierarchie,
        },
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
    }


# --------------------------------------------------------------------------- #
# _est_renseigne
# --------------------------------------------------------------------------- #


class TestEstRenseigne:
    """Tests de _est_renseigne."""

    def test_none(self) -> None:
        assert _est_renseigne(None) is False

    def test_chaine_vide(self) -> None:
        assert _est_renseigne("") is False

    def test_chaine_espaces(self) -> None:
        assert _est_renseigne("   ") is False

    def test_chaine_valeur(self) -> None:
        assert _est_renseigne("Reseau") is True


# --------------------------------------------------------------------------- #
# Validateur cable electrique
# --------------------------------------------------------------------------- #


class TestValiderCableElectrique:
    """Tests de valider_cable_electrique (les trois regles)."""

    def test_distribution_bt_avec_hierarchie_conforme(self) -> None:
        # DistributionEnergie + BT + HierarchieBT renseigne -> autorise
        assert valider_cable_electrique("DistributionEnergie", "BT", "Reseau") == []

    def test_distribution_hta_sans_hierarchie_conforme(self) -> None:
        assert valider_cable_electrique("DistributionEnergie", "HTA", None) == []

    def test_transport_htb_conforme(self) -> None:
        assert valider_cable_electrique("TransportEnergie", "HTB", None) == []

    def test_fonction_invalide(self) -> None:
        codes = valider_cable_electrique("Communication", "BT", None)
        assert codes == [TYPE_FONCTION_INVALIDE]

    def test_fonction_none_invalide(self) -> None:
        assert valider_cable_electrique(None, "BT", None) == [TYPE_FONCTION_INVALIDE]

    def test_transport_domaine_non_htb(self) -> None:
        codes = valider_cable_electrique("TransportEnergie", "HTA", None)
        assert codes == [TYPE_DOMAINE_INCOHERENT]

    def test_distribution_domaine_htb_incoherent(self) -> None:
        codes = valider_cable_electrique("DistributionEnergie", "HTB", None)
        assert codes == [TYPE_DOMAINE_INCOHERENT]

    def test_hta_avec_hierarchie_interdite(self) -> None:
        # DistributionEnergie + HTA valide, mais HierarchieBT renseigne hors BT
        codes = valider_cable_electrique("DistributionEnergie", "HTA", "Reseau")
        assert codes == [TYPE_HIERARCHIE_INTERDITE]

    def test_htb_avec_hierarchie_interdite(self) -> None:
        codes = valider_cable_electrique("TransportEnergie", "HTB", "Reseau")
        assert codes == [TYPE_HIERARCHIE_INTERDITE]

    def test_cumul_domaine_et_hierarchie(self) -> None:
        # TransportEnergie + HTA (incoherent) + HierarchieBT renseigne (interdit)
        codes = valider_cable_electrique("TransportEnergie", "HTA", "Reseau")
        assert set(codes) == {TYPE_DOMAINE_INCOHERENT, TYPE_HIERARCHIE_INTERDITE}

    def test_hierarchie_vide_hors_bt_conforme(self) -> None:
        # HierarchieBT vide (chaine) hors BT -> pas d'anomalie
        assert valider_cable_electrique("DistributionEnergie", "HTA", "") == []


# --------------------------------------------------------------------------- #
# Validateur cable de terre
# --------------------------------------------------------------------------- #


class TestValiderCableTerre:
    """Tests de valider_cable_terre."""

    def test_fonctions_autorisees(self) -> None:
        for fonction in ("ProtectionCathodique", "MaltEquipot", "Equipotentialite", "MiseTerre"):
            assert valider_cable_terre(fonction, None, None) == [], fonction

    def test_fonction_invalide(self) -> None:
        assert valider_cable_terre("DistributionEnergie", None, None) == [TYPE_FONCTION_INVALIDE]

    def test_fonction_none_invalide(self) -> None:
        assert valider_cable_terre(None, None, None) == [TYPE_FONCTION_INVALIDE]

    def test_domaine_hierarchie_ignores(self) -> None:
        # Un cable de terre conforme reste conforme quel que soit domaine/hierarchie
        assert valider_cable_terre("MiseTerre", "BT", "Reseau") == []


# --------------------------------------------------------------------------- #
# Validateur cable telecommunication
# --------------------------------------------------------------------------- #


class TestValiderCableTelecom:
    """Tests de valider_cable_telecom."""

    def test_communication_conforme(self) -> None:
        assert valider_cable_telecom("Communication", None, None) == []

    def test_fonction_invalide(self) -> None:
        assert valider_cable_telecom("MiseTerre", None, None) == [TYPE_FONCTION_INVALIDE]

    def test_fonction_none_invalide(self) -> None:
        assert valider_cable_telecom(None, None, None) == [TYPE_FONCTION_INVALIDE]


# --------------------------------------------------------------------------- #
# Detection par fichier
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesFichier:
    """Tests de detecter_anomalies_fichier."""

    def test_cable_conforme_aucune_anomalie(self) -> None:
        features = [_feature_cable("c1", "DistributionEnergie", "BT", "Reseau")]
        anomalies = detecter_anomalies_fichier(features, FICHIER_CABLE_ELECTRIQUE, valider_cable_electrique)
        assert anomalies == []

    def test_anomalie_contient_contexte(self) -> None:
        features = [_feature_cable("c1", "Communication", "BT", None)]
        anomalies = detecter_anomalies_fichier(features, FICHIER_CABLE_ELECTRIQUE, valider_cable_electrique)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["type_anomalie"] == TYPE_FONCTION_INVALIDE
        assert a["id_cable"] == "c1"
        assert a["fonction_cable"] == "Communication"
        assert a["fichier_source"] == FICHIER_CABLE_ELECTRIQUE

    def test_plusieurs_anomalies_pour_un_cable(self) -> None:
        # Cumul : domaine incoherent + hierarchie interdite
        features = [_feature_cable("c1", "TransportEnergie", "HTA", "Reseau")]
        anomalies = detecter_anomalies_fichier(features, FICHIER_CABLE_ELECTRIQUE, valider_cable_electrique)
        assert len(anomalies) == 2

    def test_geometrie_conservee(self) -> None:
        features = [_feature_cable("c1", "MauvaiseFonction", None, None)]
        anomalies = detecter_anomalies_fichier(features, FICHIER_CABLE_TERRE, valider_cable_terre)
        assert anomalies[0]["geometrie"]["type"] == "LineString"


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_HIERARCHIE_INTERDITE,
            "fichier_source": FICHIER_CABLE_ELECTRIQUE,
            "id_cable": "c1",
            "fonction_cable": "DistributionEnergie",
            "domaine_tension": "HTA",
            "hierarchie_bt": "Reseau",
            "geometrie": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
        }

    def test_type_feature_collection(self) -> None:
        assert construire_geojson_ecarts([self._anomalie()])["type"] == "FeatureCollection"

    def test_proprietes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_HIERARCHIE_INTERDITE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_cable"] == "c1"
        assert props["fonction_cable"] == "DistributionEnergie"
        assert props["domaine_tension"] == "HTA"
        assert props["hierarchie_bt"] == "Reseau"

    def test_sans_crs(self) -> None:
        assert "crs" not in construire_geojson_ecarts([self._anomalie()])

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []

    def test_priorite_est_mineure(self) -> None:
        """Contrat explicite : une incoherence metier est signalee sans declasser la famille."""
        assert PRIORITE_ANOMALIE == "mineur"


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichiers_absents_signales(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert set(resultat["fichiers_absents"]) == {
            FICHIER_CABLE_ELECTRIQUE,
            FICHIER_CABLE_TERRE,
            FICHIER_CABLE_TELECOM,
        }

    def test_nominal_sans_anomalie(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "BT", "Reseau")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_TERRE),
            [_feature_cable("t1", "MiseTerre")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_analyses"] == 2

    def test_nominal_avec_anomalies_multi_fichiers(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "TransportEnergie", "BT", None)],  # domaine incoherent
        )
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_TERRE),
            [_feature_cable("t1", "Communication")],  # fonction invalide
        )
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_TELECOM),
            [_feature_cable("tel1", "MiseTerre")],  # fonction invalide
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 3
        assert resultat["anomalies_par_type"][TYPE_DOMAINE_INCOHERENT] == 1
        assert resultat["anomalies_par_type"][TYPE_FONCTION_INVALIDE] == 2

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "TransportEnergie", "HTA", None)],
        )
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        # Hierarchie interdite en HTA : anomalie garantie
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "HTA", "Reseau")],
        )
        dossier_sortie = str(tmp_path / "resultats")
        executer_controle_cli(str(tmp_path), dossier_sortie)
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "BT", "Reseau")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_crs_propage(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "TransportEnergie", "HTA", None)],
            "EPSG:2154",
        )
        executer_controle_cli(str(tmp_path))
        import json

        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            sortie = json.load(fichier)
        assert sortie["crs"]["properties"]["name"].endswith("2154")

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "BT", "Reseau")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "anomalies_par_type",
            "nombre_cables_analyses",
            "fichiers_absents",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le controle doit se comporter identiquement en V1.0 et V1.1.

    Les champs additionnels de la V1.1 (Etiquette, Commentaire) ne doivent pas
    influencer le resultat : seuls FonctionCable_href, DomaineTension et
    HierarchieBT sont pertinents.
    """

    def _cable_v11(self, identifiant: str, fonction: str, domaine: str, hierarchie: Any) -> dict[str, Any]:
        feature = _feature_cable(identifiant, fonction, domaine, hierarchie)
        feature["properties"].update({"Etiquette": "E1", "Commentaire": "note"})
        return feature

    def test_v10_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "HTA", None)],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_v11_conforme_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [self._cable_v11("c1", "DistributionEnergie", "HTA", None)],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_v11_incoherence_detectee(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [self._cable_v11("c1", "DistributionEnergie", "HTA", "Reseau")],  # hierarchie interdite
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["anomalies_par_type"][TYPE_HIERARCHIE_INTERDITE] == 1
