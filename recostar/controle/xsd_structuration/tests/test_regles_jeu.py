#!/usr/bin/env python3
"""Tests du constat de jeu porte par la structuration (E0120 / E0020)."""

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element, SubElement  # nosec B405

from recostar.controle.xsd_structuration.priorites_structuration import PRIORITE_MOYENNE
from recostar.controle.xsd_structuration.regles_jeu import (
    CODE_AUCUN_EN_SERVICE,
    IDENTITE_JEU,
    NS_RECOSTAR,
    STATUT_EN_SERVICE,
    compter_ouvrages_en_service,
    detecter_statut_en_service,
)


def _racine(*statuts: str) -> Element:
    """Document portant les statuts donnés, un par objet."""
    racine = Element("FeatureCollection")
    for statut in statuts:
        objet = SubElement(racine, f"{{{NS_RECOSTAR}}}RPD_Support_Reco")
        SubElement(objet, f"{{{NS_RECOSTAR}}}Statut").text = statut
    return racine


class TestStatutEnService:
    """Au moins un ouvrage doit être en attente de mise en service."""

    def test_livraison_conforme(self) -> None:
        """Un seul ouvrage au bon statut suffit."""
        assert detecter_statut_en_service(_racine("Functional", STATUT_EN_SERVICE)) == []

    def test_aucun_ouvrage_en_service(self) -> None:
        """Une livraison sans ouvrage à mettre en service est signalée."""
        anomalies = detecter_statut_en_service(_racine("Functional", "Projected"))
        assert len(anomalies) == 1
        assert anomalies[0].type_erreur == CODE_AUCUN_EN_SERVICE

    def test_document_vide(self) -> None:
        """Un document sans objet ne porte aucun statut : le constat s'applique."""
        assert len(detecter_statut_en_service(_racine())) == 1

    def test_criticite_moyenne(self) -> None:
        """Le constat ne déclasse pas la livraison : il l'avertit."""
        assert detecter_statut_en_service(_racine("Functional"))[0].priorite == PRIORITE_MOYENNE

    def test_statut_espace_tolere(self) -> None:
        """Un statut entouré d'espaces reste reconnu."""
        assert detecter_statut_en_service(_racine(f"  {STATUT_EN_SERVICE}  ")) == []

    def test_comptage(self) -> None:
        """Le décompte ne retient que le statut de mise en service."""
        racine = _racine(STATUT_EN_SERVICE, "Functional", STATUT_EN_SERVICE)
        assert compter_ouvrages_en_service(racine) == 2

    def test_anomalie_nomme_le_jeu(self) -> None:
        """Aucun objet n'est en cause : le constat désigne la livraison."""
        anomalie = detecter_statut_en_service(_racine("Functional"))[0]
        assert anomalie.type_rpd == anomalie.gml_id == IDENTITE_JEU


class TestSerialisation:
    """Le constat se sérialise comme les autres erreurs de structuration."""

    def test_champs_du_dictionnaire(self) -> None:
        """Le dictionnaire porte les champs attendus par le rapport commun."""
        donnees = detecter_statut_en_service(_racine("Functional"))[0].vers_dict()
        assert set(donnees) == {
            "type_rpd",
            "gml_id",
            "severite",
            "priorite",
            "type_erreur",
            "nombre",
            "message",
        }
        assert donnees["severite"] == "ERREUR"
