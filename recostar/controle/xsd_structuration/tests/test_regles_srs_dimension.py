"""
Tests des règles portant sur l'attribut `srsDimension` (E0119 / E0019).

Couvre :
  - la propagation de la dimension déclarée sur un ascendant
  - la distinction entre déclaration absente et déclaration héritée
  - la cascade des trois règles, et leur exclusivité sur un même nœud
  - le cas propre à `pos`, qui ne porte qu'une position
  - la résolution des codes et des trois priorités distinctes
  - le périmètre : objets EP et types hors profil exclus
"""

from typing import Any

import defusedxml.ElementTree as DefusedET  # type: ignore

from recostar.controle.xsd_structuration.codes_controle import RANG_SRS_DIMENSION
from recostar.controle.xsd_structuration.codes_verificateur_xsd import resoudre_code_erreur_xsd
from recostar.controle.xsd_structuration.e0119 import AnalyseurSrsDimension
from recostar.controle.xsd_structuration.priorites_structuration import (
    PRIORITE_BASSE,
    PRIORITE_FORTE,
    PRIORITE_MOYENNE,
)
from recostar.controle.xsd_structuration.regles_srs_dimension import (
    CODE_ABSENTE,
    CODE_INCOHERENTE,
    CODE_INCORRECTE,
    DIMENSION_ATTENDUE,
    classifier,
    detecter,
    parcourir_positions,
)
from recostar.controle.xsd_structuration.versions.v1_1 import PROFIL_V1_1

NS = 'xmlns:gml="http://www.opengis.net/gml/3.2"'
ENTETE = f'<?xml version="1.0"?>\n<gml:FeatureCollection {NS} xmlns="http://StaR-Elec.com">'


def _geometrie(interieur: str) -> Any:
    """Élément `Geometrie` portant le fragment GML donné."""
    return DefusedET.fromstring(f"<Geometrie {NS}>{interieur}</Geometrie>")


def _types(erreurs: list) -> list[str]:
    return [e.type_erreur for e in erreurs]


class TestParcourirPositions:
    """La dimension se déclare à des niveaux variables et se propage en descendant."""

    def test_declaree_sur_le_noeud(self) -> None:
        noeuds = parcourir_positions(_geometrie('<gml:Point><gml:pos srsDimension="3">1 2 3</gml:pos></gml:Point>'))
        assert len(noeuds) == 1
        assert noeuds[0].dimension == 3
        assert noeuds[0].declaree_ici is True

    def test_heritee_du_parent(self) -> None:
        noeuds = parcourir_positions(_geometrie('<gml:Point srsDimension="3"><gml:pos>1 2 3</gml:pos></gml:Point>'))
        assert noeuds[0].dimension == 3
        assert noeuds[0].declaree_ici is True

    def test_heritee_de_deux_niveaux(self) -> None:
        fragment = (
            '<gml:MultiGeometry srsDimension="3"><gml:Point><gml:pos>1 2 3</gml:pos></gml:Point></gml:MultiGeometry>'
        )
        assert parcourir_positions(_geometrie(fragment))[0].dimension == 3

    def test_aucune_declaration(self) -> None:
        noeuds = parcourir_positions(_geometrie("<gml:Point><gml:pos>1 2 3</gml:pos></gml:Point>"))
        assert noeuds[0].dimension is None
        assert noeuds[0].declaree_ici is False

    def test_le_noeud_le_plus_proche_gagne(self) -> None:
        """Une redéclaration plus bas prime sur celle du conteneur."""
        fragment = '<gml:Point srsDimension="3"><gml:pos srsDimension="2">1 2</gml:pos></gml:Point>'
        assert parcourir_positions(_geometrie(fragment))[0].dimension == 2

    def test_nombre_de_valeurs(self) -> None:
        fragment = '<gml:LineString srsDimension="3"><gml:posList>1 2 3 4 5 6</gml:posList></gml:LineString>'
        assert parcourir_positions(_geometrie(fragment))[0].nombre_valeurs == 6

    def test_plusieurs_noeuds(self) -> None:
        fragment = (
            '<gml:MultiGeometry srsDimension="3">'
            "<gml:Point><gml:pos>1 2 3</gml:pos></gml:Point>"
            "<gml:Point><gml:pos>4 5 6</gml:pos></gml:Point>"
            "</gml:MultiGeometry>"
        )
        assert len(parcourir_positions(_geometrie(fragment))) == 2


class TestClassifierCascade:
    """Trois règles en cascade : déclarer, puis la valeur, puis les coordonnées."""

    def _classifier(self, fragment: str) -> str | None:
        constat = classifier(parcourir_positions(_geometrie(fragment))[0])
        return constat[0] if constat is not None else None

    def test_conforme(self) -> None:
        assert self._classifier('<gml:Point srsDimension="3"><gml:pos>1 2 3</gml:pos></gml:Point>') is None

    def test_absente(self) -> None:
        assert self._classifier("<gml:Point><gml:pos>1 2 3</gml:pos></gml:Point>") == CODE_ABSENTE

    def test_valeur_deux(self) -> None:
        assert self._classifier('<gml:Point srsDimension="2"><gml:pos>1 2</gml:pos></gml:Point>') == CODE_INCORRECTE

    def test_valeur_illisible(self) -> None:
        fragment = '<gml:Point srsDimension="trois"><gml:pos>1 2 3</gml:pos></gml:Point>'
        assert self._classifier(fragment) == CODE_INCORRECTE

    def test_valeur_negative(self) -> None:
        fragment = '<gml:Point srsDimension="-3"><gml:pos>1 2 3</gml:pos></gml:Point>'
        assert self._classifier(fragment) == CODE_INCORRECTE

    def test_poslist_non_divisible(self) -> None:
        fragment = '<gml:LineString srsDimension="3"><gml:posList>0 0 0 1 1 1 2 2</gml:posList></gml:LineString>'
        assert self._classifier(fragment) == CODE_INCOHERENTE

    def test_poslist_divisible(self) -> None:
        fragment = '<gml:LineString srsDimension="3"><gml:posList>0 0 0 1 1 1</gml:posList></gml:LineString>'
        assert self._classifier(fragment) is None

    def test_pos_exige_le_compte_exact(self) -> None:
        """`pos` ne porte qu'une position : 6 valeurs pour une dimension de 3 est fautif."""
        fragment = '<gml:Point srsDimension="3"><gml:pos>1 2 3 4 5 6</gml:pos></gml:Point>'
        assert self._classifier(fragment) == CODE_INCOHERENTE

    def test_balise_vide_releve_du_controle_de_geometrie(self) -> None:
        """Une géométrie sans position est signalée par E-1108, pas ici."""
        assert self._classifier('<gml:Point srsDimension="3"><gml:pos></gml:pos></gml:Point>') is None

    def test_une_regle_au_plus_par_noeud(self) -> None:
        """Une valeur illisible ne permet pas de juger la divisibilité."""
        fragment = '<gml:LineString srsDimension="x"><gml:posList>0 0 0 1 1</gml:posList></gml:LineString>'
        assert self._classifier(fragment) == CODE_INCORRECTE

    def test_dimension_attendue(self) -> None:
        """Le modèle RecoStaR est tridimensionnel."""
        assert DIMENSION_ATTENDUE == 3


class TestDetecter:
    """L'anomalie porte l'objet, la balise et le compte constaté."""

    def test_anomalie_documentee(self) -> None:
        fragment = '<gml:LineString srsDimension="3"><gml:posList>0 0 0 1 1</gml:posList></gml:LineString>'
        erreur = detecter("RPD_CableElectrique_Reco", "k1", _geometrie(fragment))[0]
        assert erreur.type_rpd == "RPD_CableElectrique_Reco"
        assert erreur.gml_id == "k1"
        assert erreur.balise == "posList"
        assert erreur.nombre_valeurs == 5
        assert erreur.dimension == "3"

    def test_une_anomalie_par_noeud_fautif(self) -> None:
        fragment = (
            "<gml:MultiGeometry>"
            "<gml:Point><gml:pos>1 2 3</gml:pos></gml:Point>"
            "<gml:Point><gml:pos>4 5 6</gml:pos></gml:Point>"
            "</gml:MultiGeometry>"
        )
        assert _types(detecter("RPD_Coffret_Reco", "c1", _geometrie(fragment))) == [CODE_ABSENTE, CODE_ABSENTE]

    def test_geometrie_conforme(self) -> None:
        fragment = '<gml:Point srsDimension="3"><gml:pos>1 2 3</gml:pos></gml:Point>'
        assert detecter("RPD_Coffret_Reco", "c1", _geometrie(fragment)) == []


class TestCodesEtPriorites:
    """Les trois règles portent trois codes, et trois priorités distinctes."""

    def test_codes_resolus(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_SRS_DIMENSION, CODE_ABSENTE) == "E-1201"
        assert resoudre_code_erreur_xsd(RANG_SRS_DIMENSION, CODE_INCORRECTE) == "E-1300"
        assert resoudre_code_erreur_xsd(RANG_SRS_DIMENSION, CODE_INCOHERENTE) == "E-0009"

    def test_priorites_distinctes(self) -> None:
        attendu = {
            CODE_ABSENTE: PRIORITE_MOYENNE,
            CODE_INCORRECTE: PRIORITE_BASSE,
            CODE_INCOHERENTE: PRIORITE_FORTE,
        }
        for fragment, code in (
            ("<gml:Point><gml:pos>1 2 3</gml:pos></gml:Point>", CODE_ABSENTE),
            ('<gml:Point srsDimension="2"><gml:pos>1 2</gml:pos></gml:Point>', CODE_INCORRECTE),
            (
                '<gml:LineString srsDimension="3"><gml:posList>0 0 0 1 1</gml:posList></gml:LineString>',
                CODE_INCOHERENTE,
            ),
        ):
            erreur = detecter("RPD_Coffret_Reco", "c1", _geometrie(fragment))[0]
            assert erreur.type_erreur == code
            assert erreur.priorite == attendu[code]


class TestPerimetre:
    """Le contrôle visite les mêmes objets que celui de géométrie."""

    def _analyser(self, tmp_path: Any, membre: str) -> list:
        chemin = tmp_path / "jeu.gml"
        chemin.write_text(f"{ENTETE}{membre}</gml:FeatureCollection>", encoding="utf-8")
        return AnalyseurSrsDimension(chemin, PROFIL_V1_1).analyser()

    def _membre(self, type_rpd: str) -> str:
        geom = "<Geometrie><gml:Point><gml:pos>1 2 3</gml:pos></gml:Point></Geometrie>"
        return f'<gml:featureMember><{type_rpd} gml:id="x1">{geom}</{type_rpd}></gml:featureMember>'

    def test_type_rpd_controle(self, tmp_path: Any) -> None:
        assert _types(self._analyser(tmp_path, self._membre("RPD_Coffret_Reco"))) == [CODE_ABSENTE]

    def test_objet_ep_exclu(self, tmp_path: Any) -> None:
        assert self._analyser(tmp_path, self._membre("EP_Quelconque")) == []

    def test_type_hors_profil_exclu(self, tmp_path: Any) -> None:
        assert self._analyser(tmp_path, self._membre("RPD_TypeInexistant_Reco")) == []

    def test_objet_sans_geometrie(self, tmp_path: Any) -> None:
        membre = '<gml:featureMember><RPD_Coffret_Reco gml:id="c1"/></gml:featureMember>'
        assert self._analyser(tmp_path, membre) == []

    def test_document_vide(self, tmp_path: Any) -> None:
        assert self._analyser(tmp_path, "") == []
