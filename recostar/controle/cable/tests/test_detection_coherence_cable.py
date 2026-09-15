"""
Tests du moteur de coherence FonctionCable_href / DomaineTension / HierarchieBT.

Couvre :
  - les deux validateurs metier (electrique, terre)
  - l'exclusion du cable de telecommunication, qui ne porte aucun des trois champs
  - toutes les regles et leurs cas limites
  - la detection par fichier
  - la construction du GeoJSON d'ecarts
  - l'execution CLI complete
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

from recostar.controle.cable.detection_coherence_cable import (
    TYPE_DOMAINE_INCOHERENT,
    TYPE_FONCTION_INVALIDE,
    TYPE_HIERARCHIE_INTERDITE,
    VALIDATEURS,
    _est_renseigne,
    construire_geojson_ecarts,
    detecter_anomalies_fichier,
    executer_analyse,
    valider_cable_electrique,
    valider_cable_terre,
)
from recostar.controle.cable.e3104 import PROFIL_ECARTS as _PROFIL_3104
from recostar.controle.cable.e3104 import TYPES_RETENUS as _TYPES_3104
from recostar.controle.cable.e3302 import PROFIL_ECARTS as _PROFIL_3302
from recostar.controle.cable.e3302 import TYPES_RETENUS as _TYPES_3302
from recostar.controle.cable.tests.utils_tests import ecrire_collection, ecrire_collection_avec_crs
from recostar.controle.fonctions_communes.geojson import PRIORITE_BASSE, PRIORITE_FORTE
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TELECOM,
    FICHIER_CABLE_TERRE,
)

# Le moteur est partage : chaque type d'anomalie revient au controle qui porte
# son code. Les tests lui passent ce profil, faute de quoi le code d'erreur et
# la priorite des ecarts ne seraient pas resolus.
_PROFIL_PAR_TYPE = {
    **dict.fromkeys(_TYPES_3104, _PROFIL_3104),
    **dict.fromkeys(_TYPES_3302, _PROFIL_3302),
}

_PROFIL_DEFAUT = _PROFIL_3104
_TOUS_LES_TYPES = frozenset(_PROFIL_PAR_TYPE)
_FICHIER_TEST = "ecarts_moteur_test.geojson"


def _profil(anomalies):
    """Profil du controle a qui revient le type de la premiere anomalie."""
    if not anomalies:
        return _PROFIL_DEFAUT
    return _PROFIL_PAR_TYPE.get(anomalies[0].get("type_anomalie"), _PROFIL_DEFAUT)


def _executer(repertoire, sortie=None, **options):
    """Execute le moteur sur tous ses types, comme avant la scission."""
    return executer_analyse(repertoire, _TOUS_LES_TYPES, _PROFIL_DEFAUT, _FICHIER_TEST, sortie, **options)


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
# Exclusion du cable de telecommunication
# --------------------------------------------------------------------------- #


class TestCableTelecomHorsPerimetre:
    """Le cable de telecommunication ne porte aucun des trois champs du moteur.

    Il etait controle comme s'il portait un FonctionCable valant
    « Communication » : tout cable conforme au XSD ressortait en anomalie. La
    valeur de son champ `Fonction` releve d'E0114 / E0014, sous le code E-2100.
    """

    def test_couche_absente_des_validateurs(self) -> None:
        assert FICHIER_CABLE_TELECOM not in {fichier for fichier, _ in VALIDATEURS}

    def test_seules_deux_couches_validees(self) -> None:
        assert [fichier for fichier, _ in VALIDATEURS] == [FICHIER_CABLE_ELECTRIQUE, FICHIER_CABLE_TERRE]


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
        assert construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]))["type"] == "FeatureCollection"

    def test_proprietes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]))["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_HIERARCHIE_INTERDITE
        assert props["code_erreur"] == "E-3302"
        assert props["priorite"] == PRIORITE_BASSE
        assert props["id_cable"] == "c1"
        assert props["fonction_cable"] == "DistributionEnergie"
        assert props["domaine_tension"] == "HTA"
        assert props["hierarchie_bt"] == "Reseau"

    def test_sans_crs(self) -> None:
        assert "crs" not in construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]))

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]), crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([], _PROFIL_DEFAUT)["features"] == []

    def test_priorite_derivee_du_code_erreur(self) -> None:
        """Lot 2 : la priorite n'est plus declaree, elle est le niveau du code du verificateur.

        Les deux familles d'anomalie du controle ne relevent pas du meme niveau :
        une fonction de cable invalide est forte (E-3104), une hierarchie BT
        interdite reste basse (E-3302).
        """
        attendus = {
            TYPE_FONCTION_INVALIDE: (PRIORITE_FORTE, "E-3104"),
            TYPE_HIERARCHIE_INTERDITE: (PRIORITE_BASSE, "E-3302"),
        }
        for type_anomalie, (priorite, code_erreur) in attendus.items():
            anomalie = {**self._anomalie(), "type_anomalie": type_anomalie}
            props = construire_geojson_ecarts([anomalie], _profil([anomalie]))["features"][0]["properties"]
            assert props["code_erreur"] == code_erreur
            assert props["priorite"] == priorite


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        resultat = _executer("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichiers_absents_signales(self, tmp_path: Any) -> None:
        resultat = _executer(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert set(resultat["fichiers_absents"]) == {
            FICHIER_CABLE_ELECTRIQUE,
            FICHIER_CABLE_TERRE,
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
        resultat = _executer(str(tmp_path))
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
            # Cable telecom tel que le convertisseur l'ecrit : champ `Fonction`
            # (CodeList RRTT/TLC), sans FonctionCable_href. Il ne doit produire
            # aucune anomalie, ni etre compte parmi les cables analyses.
            [{"type": "Feature", "properties": {"id": "tel1", "Fonction": "TLC"}, "geometry": None}],
        )
        resultat = _executer(str(tmp_path))
        assert resultat["nombre_anomalies"] == 2
        assert resultat["anomalies_par_type"][TYPE_DOMAINE_INCOHERENT] == 1
        assert resultat["anomalies_par_type"][TYPE_FONCTION_INVALIDE] == 1
        assert resultat["nombre_cables_analyses"] == 2

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "TransportEnergie", "HTA", None)],
        )
        _executer(str(tmp_path))
        assert os.path.isfile(str(tmp_path / _FICHIER_TEST))

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        # Hierarchie interdite en HTA : anomalie garantie
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "HTA", "Reseau")],
        )
        dossier_sortie = str(tmp_path / "resultats")
        _executer(str(tmp_path), dossier_sortie)
        assert os.path.isfile(os.path.join(dossier_sortie, _FICHIER_TEST))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "BT", "Reseau")],
        )
        resultat = _executer(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / _FICHIER_TEST))

    def test_crs_propage(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "TransportEnergie", "HTA", None)],
            "EPSG:2154",
        )
        _executer(str(tmp_path))
        import json

        with open(str(tmp_path / _FICHIER_TEST), encoding="utf-8") as fichier:
            sortie = json.load(fichier)
        assert sortie["crs"]["properties"]["name"].endswith("2154")

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", "DistributionEnergie", "BT", "Reseau")],
        )
        resultat = _executer(str(tmp_path))
        for champ in (
            "succes",
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
        assert _executer(str(tmp_path))["nombre_anomalies"] == 0

    def test_v11_conforme_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [self._cable_v11("c1", "DistributionEnergie", "HTA", None)],
        )
        assert _executer(str(tmp_path))["nombre_anomalies"] == 0

    def test_v11_incoherence_detectee(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [self._cable_v11("c1", "DistributionEnergie", "HTA", "Reseau")],  # hierarchie interdite
        )
        resultat = _executer(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["anomalies_par_type"][TYPE_HIERARCHIE_INTERDITE] == 1
