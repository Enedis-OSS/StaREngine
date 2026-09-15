"""
Tests des règles portant sur le document GML lui-même (E0118 / E0018).

Couvre :
  - la lecture qui rattrape l'erreur d'analyse au lieu de la laisser remonter
  - le décompte des objets du document
  - l'exclusivité des deux règles
  - la résolution du code d'erreur et de la priorité
  - l'enveloppe d'analyse et le rapport JSON
"""

import json
from pathlib import Path
from typing import Any

from recostar.controle.xsd_structuration.codes_controle import RANG_DOCUMENT
from recostar.controle.xsd_structuration.codes_verificateur_xsd import resoudre_code_erreur_xsd
from recostar.controle.xsd_structuration.e0118 import AnalyseurDocument, generer_rapport
from recostar.controle.xsd_structuration.priorites_structuration import (
    PRIORITE_FORTE,
)
from recostar.controle.xsd_structuration.regles_document import (
    CODE_ILLISIBLE,
    CODE_VIDE,
    IDENTITE_DOCUMENT,
    compter_objets,
    detecter,
    lire_document,
)
from recostar.controle.xsd_structuration.versions.v1_1 import PROFIL_V1_1

ENTETE = '<?xml version="1.0"?>\n<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2" xmlns="http://StaR-Elec.com">'
PIED = "</gml:FeatureCollection>"
MEMBRE = '<gml:featureMember><RPD_Coffret_Reco gml:id="c1"/></gml:featureMember>'


def _ecrire(tmp_path: Any, contenu: str) -> Path:
    chemin = tmp_path / "document.gml"
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


class TestLireDocument:
    """L'échec d'analyse est un résultat, non une exception."""

    def test_document_valide(self, tmp_path: Any) -> None:
        constat = lire_document(_ecrire(tmp_path, f"{ENTETE}{MEMBRE}{PIED}"))
        assert constat.racine is not None
        assert constat.motif is None

    def test_document_mal_forme(self, tmp_path: Any) -> None:
        constat = lire_document(_ecrire(tmp_path, "<FeatureCollection><pas ferme"))
        assert constat.racine is None
        assert constat.motif

    def test_fichier_absent(self, tmp_path: Any) -> None:
        """Un chemin qui n'aboutit pas se rend comme une anomalie, pas comme une erreur."""
        constat = lire_document(tmp_path / "inexistant.gml")
        assert constat.racine is None
        assert constat.motif

    def test_racine_et_motif_exclusifs(self, tmp_path: Any) -> None:
        for contenu in (f"{ENTETE}{PIED}", "<casse"):
            constat = lire_document(_ecrire(tmp_path, contenu))
            assert (constat.racine is None) != (constat.motif is None)


class TestCompterObjets:
    """Ce qui compte comme donnée : les featureMember, quels qu'ils portent."""

    def test_document_vide(self, tmp_path: Any) -> None:
        constat = lire_document(_ecrire(tmp_path, f"{ENTETE}{PIED}"))
        assert constat.racine is not None
        assert compter_objets(constat.racine) == 0

    def test_plusieurs_objets(self, tmp_path: Any) -> None:
        constat = lire_document(_ecrire(tmp_path, f"{ENTETE}{MEMBRE * 3}{PIED}"))
        assert constat.racine is not None
        assert compter_objets(constat.racine) == 3

    def test_entete_seule_ne_compte_pas(self, tmp_path: Any) -> None:
        """Un GML réduit à ses métadonnées s'analyse mais ne décrit aucun ouvrage."""
        entete = '<Metadata xmlns="http://StaR-Elec.com"><Logiciel>x</Logiciel></Metadata>'
        constat = lire_document(_ecrire(tmp_path, f"{ENTETE}{entete}{PIED}"))
        assert constat.racine is not None
        assert compter_objets(constat.racine) == 0


class TestDetecter:
    """Les deux règles sont exclusives, et un document conforme n'en porte aucune."""

    def _detecter(self, tmp_path: Any, contenu: str) -> list:
        return detecter(lire_document(_ecrire(tmp_path, contenu)))

    def test_document_conforme(self, tmp_path: Any) -> None:
        assert self._detecter(tmp_path, f"{ENTETE}{MEMBRE}{PIED}") == []

    def test_document_illisible(self, tmp_path: Any) -> None:
        erreurs = self._detecter(tmp_path, "<casse")
        assert [e.type_erreur for e in erreurs] == [CODE_ILLISIBLE]

    def test_document_vide(self, tmp_path: Any) -> None:
        erreurs = self._detecter(tmp_path, f"{ENTETE}{PIED}")
        assert [e.type_erreur for e in erreurs] == [CODE_VIDE]

    def test_une_anomalie_au_plus(self, tmp_path: Any) -> None:
        """Un document illisible ne livre rien à compter : jamais les deux codes."""
        for contenu in ("<casse", f"{ENTETE}{PIED}", f"{ENTETE}{MEMBRE}{PIED}"):
            assert len(self._detecter(tmp_path, contenu)) <= 1

    def test_identite_de_repli(self, tmp_path: Any) -> None:
        """Le défaut est celui du document : aucun objet ne le porte."""
        erreur = self._detecter(tmp_path, f"{ENTETE}{PIED}")[0]
        assert erreur.gml_id == erreur.type_rpd == IDENTITE_DOCUMENT

    def test_message_renseigne(self, tmp_path: Any) -> None:
        for contenu in ("<casse", f"{ENTETE}{PIED}"):
            assert self._detecter(tmp_path, contenu)[0].message.strip()


class TestCodesEtPriorites:
    """Chaque règle résout son code du vérificateur."""

    def test_codes_resolus(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_DOCUMENT, CODE_ILLISIBLE) == "E-0001"
        assert resoudre_code_erreur_xsd(RANG_DOCUMENT, CODE_VIDE) == "E-0004"

    def test_priorites(self, tmp_path: Any) -> None:
        """Les deux codes sont `bloquante` au référentiel, ramenés à `forte`."""
        for contenu in ("<casse", f"{ENTETE}{PIED}"):
            erreur = detecter(lire_document(_ecrire(tmp_path, contenu)))[0]
            assert erreur.priorite == PRIORITE_FORTE

    def test_severite_fixe(self, tmp_path: Any) -> None:
        assert detecter(lire_document(_ecrire(tmp_path, "<casse")))[0].severite == "ERREUR"


class TestAnalyseurEtRapport:
    """Enveloppe du contrôle : analyse puis rapport JSON."""

    def test_analyseur(self, tmp_path: Any) -> None:
        chemin = _ecrire(tmp_path, f"{ENTETE}{PIED}")
        erreurs = AnalyseurDocument(chemin, PROFIL_V1_1).analyser()
        assert [e.type_erreur for e in erreurs] == [CODE_VIDE]

    def test_rapport_v1_1(self, tmp_path: Any) -> None:
        chemin = _ecrire(tmp_path, f"{ENTETE}{PIED}")
        erreurs = AnalyseurDocument(chemin, PROFIL_V1_1).analyser()
        rapport = json.loads(generer_rapport(chemin, erreurs, tmp_path, "1.1").read_text(encoding="utf-8"))
        assert rapport["type_controle"] == "E0118_DOCUMENT"
        assert rapport["nb_erreurs"] == 1
        assert rapport["conformite"] == "NON_CONFORME"
        assert rapport["erreurs"][0]["type_erreur"] == CODE_VIDE

    def test_rapport_v1_0_change_de_code(self, tmp_path: Any) -> None:
        chemin = _ecrire(tmp_path, f"{ENTETE}{PIED}")
        erreurs = AnalyseurDocument(chemin, PROFIL_V1_1).analyser()
        chemin_rapport = generer_rapport(chemin, erreurs, tmp_path, "1.0")
        assert chemin_rapport.name.endswith("_controle_e0018.json")
        assert json.loads(chemin_rapport.read_text(encoding="utf-8"))["type_controle"] == "E0018_DOCUMENT"

    def test_document_conforme_rapport_vide(self, tmp_path: Any) -> None:
        chemin = _ecrire(tmp_path, f"{ENTETE}{MEMBRE}{PIED}")
        erreurs = AnalyseurDocument(chemin, PROFIL_V1_1).analyser()
        rapport = json.loads(generer_rapport(chemin, erreurs, tmp_path, "1.1").read_text(encoding="utf-8"))
        assert rapport["nb_erreurs"] == 0
        assert rapport["conformite"] == "CONFORME"
