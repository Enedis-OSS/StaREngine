"""
Tests du moteur du numéro de dossier et des deux contrôles qu'il sert.

Couvre :
  - les six modèles, un cas conforme et un cas voisin fautif pour chacun
  - les trois modèles qui ne portent aucune référence DR
  - la cascade E-0005 / E-0006 et son exclusivité
  - la résolution dans `reference_dr.json`
  - la feature d'écart sans géométrie
  - l'exécution CLI des deux contrôles
"""

import json
import os
from typing import Any

from recostar.controle.fonctions_communes.numero_affaire import (
    CHAMP_REF_DOSSIER,
    CHAMP_TRIGRAMME,
    MODELES,
    NOMS_MODELES,
    reconnaitre,
    references_connues,
)
from recostar.controle.projection.detection_numero_affaire import (
    TYPE_DR_INCONNUE,
    TYPE_MODELE_INCONNU,
    construire_geojson_ecarts,
    detecter_anomalies,
)
from recostar.controle.projection.e0005 import PROFIL_ECARTS as PROFIL_0005
from recostar.controle.projection.e0005 import TYPES_RETENUS as TYPES_0005
from recostar.controle.projection.e0005 import executer_controle_cli as executer_0005
from recostar.controle.projection.e0006 import FICHIER_SORTIE as SORTIE_0006
from recostar.controle.projection.e0006 import TYPES_RETENUS as TYPES_0006
from recostar.controle.projection.e0006 import executer_controle_cli as executer_0006

# Référentiel de test : deux entrées, une par champ résolvable.
REFERENCES: list[dict[str, Any]] = [
    {"ref_dossier": "DA21", "trigramme_racing": "IFE", "repertoire": "1A"},
    {"ref_dossier": "A743", "trigramme_racing": "CVL", "repertoire": "2B"},
]


class TestModeles:
    """Les six modèles, un conforme et un voisin fautif pour chacun."""

    def test_les_six_modeles_declares(self) -> None:
        assert NOMS_MODELES == ("type1", "type2", "type3", "type4", "type5", "type6")

    def test_type1_prefixe_de_dossier(self) -> None:
        reconnu = reconnaitre("DA21/256553-1")
        assert reconnu is not None
        assert reconnu.modele.nom == "type1"
        assert reconnu.reference == "DA21"

    def test_type2_dr_outre_mer(self) -> None:
        reconnu = reconnaitre("A743/256553-12")
        assert reconnu is not None
        assert reconnu.modele.nom == "type2"
        assert reconnu.reference == "A743"

    def test_type3_trigramme_racing(self) -> None:
        reconnu = reconnaitre("RAC-CVL-25-007998-1")
        assert reconnu is not None
        assert reconnu.modele.nom == "type3"
        assert reconnu.reference == "CVL"

    def test_type4_identifiant_opaque(self) -> None:
        reconnu = reconnaitre("RAC-25-ABC123456789-1")
        assert reconnu is not None
        assert reconnu.modele.nom == "type4"
        assert reconnu.reference is None

    def test_type5_numero_interne(self) -> None:
        reconnu = reconnaitre("12345678-1")
        assert reconnu is not None
        assert reconnu.modele.nom == "type5"

    def test_type6_dossier_osr(self) -> None:
        reconnu = reconnaitre("OSR20250114-1")
        assert reconnu is not None
        assert reconnu.modele.nom == "type6"

    def test_indice_de_version_obligatoire(self) -> None:
        """Tous les modèles se terminent par l'indice du dépôt."""
        for numero in ("DA21/256553", "RAC-CVL-25-007998", "OSR20250114", "12345678"):
            assert reconnaitre(numero) is None, numero

    def test_indice_de_version_au_plus_trois_chiffres(self) -> None:
        assert reconnaitre("DA21/256553-003") is not None
        assert reconnaitre("DA21/256553-0003") is None

    def test_casse_significative(self) -> None:
        """Une casse différente désigne un autre dossier : aucune tolérance."""
        assert reconnaitre("da21/256553-1") is None
        assert reconnaitre("rac-cvl-25-007998-1") is None

    def test_espaces_de_bord_tolerés(self) -> None:
        assert reconnaitre("  DA21/256553-1  ") is not None

    def test_type1_exige_une_lettre_en_seconde_position(self) -> None:
        assert reconnaitre("D123/256553-1") is None

    def test_type1_refuse_une_initiale_hors_da(self) -> None:
        assert reconnaitre("ZZ99/256553-1") is None

    def test_type2_limite_aux_suffixes_prevus(self) -> None:
        assert reconnaitre("A743/256553-1") is not None
        assert reconnaitre("A748/256553-1") is None

    def test_modeles_disjoints(self) -> None:
        """L'ordre d'essai ne change aucun verdict."""
        for numero in ("DA21/256553-1", "A743/256553-1", "RAC-CVL-25-007998-1", "12345678-1", "OSR20250114-1"):
            correspondances = [m.nom for m in MODELES if m.motif.match(numero)]
            assert len(correspondances) == 1, (numero, correspondances)

    def test_trois_modeles_sans_reference(self) -> None:
        sans_reference = {m.nom for m in MODELES if m.champ_reference is None}
        assert sans_reference == {"type4", "type5", "type6"}

    def test_champs_de_reference(self) -> None:
        champs = {m.nom: m.champ_reference for m in MODELES}
        assert champs["type1"] == champs["type2"] == CHAMP_REF_DOSSIER
        assert champs["type3"] == CHAMP_TRIGRAMME


class TestReferencesConnues:
    """Indexation du référentiel DR."""

    def test_index_ref_dossier(self) -> None:
        assert references_connues(REFERENCES, CHAMP_REF_DOSSIER) == frozenset({"DA21", "A743"})

    def test_index_trigramme(self) -> None:
        assert references_connues(REFERENCES, CHAMP_TRIGRAMME) == frozenset({"IFE", "CVL"})

    def test_normalisation_en_majuscules(self) -> None:
        assert references_connues([{"ref_dossier": "da21"}], CHAMP_REF_DOSSIER) == frozenset({"DA21"})

    def test_champ_absent_ignore(self) -> None:
        assert references_connues([{"repertoire": "1A"}], CHAMP_REF_DOSSIER) == frozenset()


class TestDetecterAnomalies:
    """La cascade : le modèle d'abord, la direction régionale ensuite."""

    def _types(self, numero: str) -> list[str]:
        return [a["type_anomalie"] for a in detecter_anomalies(numero, REFERENCES)]

    def test_numero_conforme_et_dr_connue(self) -> None:
        assert self._types("DA21/256553-1") == []

    def test_trigramme_connu(self) -> None:
        assert self._types("RAC-CVL-25-007998-1") == []

    def test_hors_modele(self) -> None:
        assert self._types("n-importe-quoi") == [TYPE_MODELE_INCONNU]

    def test_dr_inconnue(self) -> None:
        assert self._types("DZ99/256553-1") == [TYPE_DR_INCONNUE]

    def test_trigramme_inconnu(self) -> None:
        assert self._types("RAC-ZZZ-25-007998-1") == [TYPE_DR_INCONNUE]

    def test_exclusivite(self) -> None:
        """Un numéro hors modèle n'a aucune référence à résoudre."""
        for numero in ("n-importe-quoi", "DZ99/256553-1", "DA21/256553-1", "OSR20250114-1"):
            assert len(detecter_anomalies(numero, REFERENCES)) <= 1, numero

    def test_modeles_sans_reference_hors_perimetre(self) -> None:
        """Bien formés, ils ne désignent aucune DR : rien à reprocher."""
        for numero in ("RAC-25-ABC123456789-1", "12345678-1", "OSR20250114-1"):
            assert self._types(numero) == [], numero

    def test_anomalie_documentee(self) -> None:
        anomalie = detecter_anomalies("DZ99/256553-1", REFERENCES)[0]
        assert anomalie["numero_affaire"] == "DZ99/256553-1"
        assert anomalie["modele"] == "type1"
        assert anomalie["reference_dr"] == "DZ99"
        assert CHAMP_REF_DOSSIER in anomalie["message"]

    def test_message_hors_modele_cite_les_modeles(self) -> None:
        message = detecter_anomalies("bidon", REFERENCES)[0]["message"]
        assert all(nom in message for nom in NOMS_MODELES)


class TestGeojsonEcarts:
    """L'écart porte le numéro, et n'a pas de géométrie."""

    def _props(self, numero: str, profil: Any = PROFIL_0005) -> dict[str, Any]:
        geojson = construire_geojson_ecarts(detecter_anomalies(numero, REFERENCES), profil)
        return geojson["features"][0]["properties"]

    def test_sans_geometrie(self) -> None:
        """Le défaut porte sur le numéro : aucune entité ne le localise."""
        geojson = construire_geojson_ecarts(detecter_anomalies("bidon", REFERENCES), PROFIL_0005)
        assert geojson["features"][0]["geometry"] is None

    def test_sans_crs(self) -> None:
        geojson = construire_geojson_ecarts(detecter_anomalies("bidon", REFERENCES), PROFIL_0005)
        assert "crs" not in geojson

    def test_socle_commun(self) -> None:
        props = self._props("bidon")
        assert props["code_controle"] == "E-0005"
        assert props["code_erreur"] == "E-0005"
        assert props["id_entite"] == "bidon"
        assert props["priorite"] == "forte"

    def test_numero_et_modele_exposes(self) -> None:
        props = self._props("bidon")
        assert props["numero_affaire"] == "bidon"
        assert props["modele_reconnu"] is None

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([], PROFIL_0005)["features"] == []


class TestRepartitionDesTypes:
    """Chaque type revient à un contrôle, et à un seul."""

    def test_types_disjoints(self) -> None:
        assert TYPES_0005 & TYPES_0006 == frozenset()

    def test_tous_les_types_retenus(self) -> None:
        assert TYPES_0005 | TYPES_0006 == {TYPE_MODELE_INCONNU, TYPE_DR_INCONNUE}


class TestCli:
    """Exécution des deux contrôles."""

    def test_repertoire_introuvable(self) -> None:
        assert executer_0005("/chemin/inexistant", "DA21/256553-1")["succes"] is False

    def test_numero_absent(self, tmp_path: Any) -> None:
        resultat = executer_0005(str(tmp_path), None)
        assert resultat["succes"] is False
        assert "numero_affaire" in resultat["erreur"]

    def test_numero_conforme(self, tmp_path: Any) -> None:
        """DA21 figure au référentiel réel du projet."""
        assert executer_0005(str(tmp_path), "DA21/256553-1")["nombre_anomalies"] == 0
        assert executer_0006(str(tmp_path), "DA21/256553-1")["nombre_anomalies"] == 0

    def test_hors_modele_rendu_par_e0005_seul(self, tmp_path: Any) -> None:
        assert executer_0005(str(tmp_path), "bidon")["anomalies_par_type"] == {TYPE_MODELE_INCONNU: 1}
        assert executer_0006(str(tmp_path), "bidon")["nombre_anomalies"] == 0

    def test_dr_inconnue_rendue_par_e0006_seul(self, tmp_path: Any) -> None:
        assert executer_0005(str(tmp_path), "DZ99/256553-1")["nombre_anomalies"] == 0
        assert executer_0006(str(tmp_path), "DZ99/256553-1")["anomalies_par_type"] == {TYPE_DR_INCONNUE: 1}

    def test_rapport_documente(self, tmp_path: Any) -> None:
        resultat = executer_0006(str(tmp_path), "DA21/256553-1")
        assert resultat["modele_reconnu"] == "type1"
        assert resultat["reference_dr"] == "DA21"
        assert resultat["nombre_references_dr"] > 0

    def test_fichier_ecrit(self, tmp_path: Any) -> None:
        executer_0006(str(tmp_path), "DZ99/256553-1")
        chemin = os.path.join(str(tmp_path), SORTIE_0006)
        assert os.path.isfile(chemin)
        with open(chemin, encoding="utf-8") as fichier:
            feature = json.load(fichier)["features"][0]
        assert feature["geometry"] is None
        assert feature["properties"]["code_erreur"] == "E-0006"

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        executer_0006(str(tmp_path), "DA21/256553-1")
        assert not os.path.isfile(os.path.join(str(tmp_path), SORTIE_0006))

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        destination = tmp_path / "dst"
        executer_0006(str(tmp_path), "DZ99/256553-1", str(destination))
        assert os.path.isfile(os.path.join(str(destination), SORTIE_0006))
