"""
Tests des utilitaires geometriques communs (utils_geometrie_commun.py).

Couvre la correction des altitudes manquantes, mutualisee entre le calcul des
longueurs de cables (traitement/calcul_longueurs) et les controles E504 et E505.
La convention verifiee ici est celle du format RecoStaR : une altitude absente
est ecrite 0.0 dans la posList, elle ne designe pas le niveau de la mer.
"""

import ast
from pathlib import Path

import pytest
from utils_geometrie_commun import (
    TOLERANCE_SUPERPOSITION,
    TOLERANCE_Z,
    corriger_z_nuls,
    est_z_nul,
    extraire_parties_lineaires,
    recoller_parties_lineaires,
)

# Racine du paquet de controle (repertoire parent de tests/).
_RACINE_CONTROLE = Path(__file__).resolve().parent.parent

# Autres domaines portant un shim utils_geometrie.py, hors controle/.
_AUTRES_SHIMS = (_RACINE_CONTROLE.parent / "traitement" / "calcul_longueurs" / "utils_geometrie.py",)


def _noms_reexportes(chemin: Path) -> set[str]:
    """Noms importes depuis utils_geometrie_commun par un shim de domaine."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    noms: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.module == "utils_geometrie_commun":
            noms.update(alias.name for alias in noeud.names)
    return noms


class TestCoherenceDesShims:
    """Les shims utils_geometrie.py doivent reexporter le meme jeu de noms.

    Ils portent tous le meme nom de module : dans un processus unique
    (pipeline_globale charge les cinq familles), le premier charge occupe
    sys.modules et sert les autres. Un shim exposant moins que son voisin
    provoque un ImportError a distance, dans le domaine charge en second.
    """

    def test_shims_identiques(self) -> None:
        shims = sorted(_RACINE_CONTROLE.glob("*/utils_geometrie.py"))
        assert len(shims) >= 2, "au moins deux domaines delèguent vers le module commun"
        reference = _noms_reexportes(shims[0])
        assert reference, f"{shims[0]} ne reexporte rien"
        for shim in shims[1:]:
            assert _noms_reexportes(shim) == reference, f"{shim.parent.name} diverge de {shims[0].parent.name}"

    def test_noms_reexportes_existent_dans_le_module_commun(self) -> None:
        """Un nom reexporte mais absent du module commun casserait tous les domaines."""
        import utils_geometrie_commun

        for shim in _RACINE_CONTROLE.glob("*/utils_geometrie.py"):
            for nom in _noms_reexportes(shim):
                assert hasattr(utils_geometrie_commun, nom), f"{nom} absent de utils_geometrie_commun"

    def test_shims_hors_controle_alignes(self) -> None:
        """Les shims des autres paquets partagent le meme nom de module.

        `traitement/calcul_longueurs` en porte un : charge en premier dans un
        processus commun, il servirait les domaines de controle avec un jeu de
        noms plus court, provoquant un ImportError a distance.
        """
        reference = _noms_reexportes(sorted(_RACINE_CONTROLE.glob("*/utils_geometrie.py"))[0])
        for shim in _AUTRES_SHIMS:
            assert shim.is_file(), f"{shim} introuvable"
            assert _noms_reexportes(shim) == reference, f"{shim} diverge des shims de controle"


class TestExtrairePartiesLineaires:
    """Decomposition brute d'une geometrie lineaire, sans recollement."""

    def test_linestring(self) -> None:
        coords = [[0.0, 0.0], [1.0, 1.0]]
        assert extraire_parties_lineaires({"type": "LineString", "coordinates": coords}) == [coords]

    def test_multilinestring_parties_conservees(self) -> None:
        parties = [[[0.0, 0.0], [1.0, 0.0]], [[5.0, 0.0], [6.0, 0.0]]]
        assert extraire_parties_lineaires({"type": "MultiLineString", "coordinates": parties}) == parties

    def test_geometrie_absente_ou_non_lineaire(self) -> None:
        assert extraire_parties_lineaires(None) == []
        assert extraire_parties_lineaires({"type": "Point", "coordinates": [0.0, 0.0]}) == []
        assert extraire_parties_lineaires({"type": "LineString", "coordinates": []}) == []


class TestRecollerPartiesLineaires:
    """Recollement des troncons en polylignes continues maximales."""

    def test_linestring_inchange(self) -> None:
        coords = [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]
        assert recoller_parties_lineaires({"type": "LineString", "coordinates": coords}) == [coords]

    def test_troncons_contigus_recolles(self) -> None:
        """Deux troncons partageant un bout donnent une seule polyligne."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0]], [[1.0, 0.0], [2.0, 0.0]]],
        }
        (polyligne,) = recoller_parties_lineaires(geometrie)
        # Le noeud partage n'est pas duplique : 3 sommets et non 4.
        assert [sommet[:2] for sommet in polyligne] == [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]

    def test_troncons_desordonnes_et_inverses(self) -> None:
        """Les parties RecoStaR ne sont ni ordonnees ni orientees : les deux sont corrigees."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[2.0, 0.0], [1.0, 0.0]], [[0.0, 0.0], [1.0, 0.0]]],
        }
        (polyligne,) = recoller_parties_lineaires(geometrie)
        assert len(polyligne) == 3
        assert {tuple(sommet[:2]) for sommet in polyligne} == {(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)}

    def test_z_preserve(self) -> None:
        """Le recollement ne doit pas degrader la geometrie en 2D."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0, 10.0], [1.0, 0.0, 11.0]],
                [[1.0, 0.0, 11.0], [2.0, 0.0, 12.0]],
            ],
        }
        (polyligne,) = recoller_parties_lineaires(geometrie)
        assert [sommet[2] for sommet in polyligne] == [10.0, 11.0, 12.0]

    def test_troncons_disjoints_restent_separes(self) -> None:
        """Rien n'est invente entre deux troncons qui ne se touchent pas."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0]], [[50.0, 0.0], [51.0, 0.0]]],
        }
        assert len(recoller_parties_lineaires(geometrie)) == 2

    def test_recollement_partiel(self) -> None:
        """Deux troncons contigus et un isole donnent deux polylignes."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0], [1.0, 0.0]],
                [[1.0, 0.0], [2.0, 0.0]],
                [[50.0, 0.0], [51.0, 0.0]],
            ],
        }
        assert sorted(len(p) for p in recoller_parties_lineaires(geometrie)) == [2, 3]

    def test_partie_degeneree_ne_leve_pas(self) -> None:
        """Un troncon d'un seul sommet ne decrit aucune ligne : pas de recollement force."""
        geometrie = {"type": "MultiLineString", "coordinates": [[[0.0, 0.0]], [[1.0, 0.0], [2.0, 0.0]]]}
        assert recoller_parties_lineaires(geometrie) == [[[0.0, 0.0]], [[1.0, 0.0], [2.0, 0.0]]]

    def test_geometrie_absente_ou_non_lineaire(self) -> None:
        assert recoller_parties_lineaires(None) == []
        assert recoller_parties_lineaires({"type": "Point", "coordinates": [0.0, 0.0]}) == []

    def test_sommets_de_raccord_deviennent_intermediaires(self) -> None:
        """Interet du recollement : les bouts de troncon deviennent evaluables.

        Sans recollement, le sommet partage est un bout de partie dans les deux
        troncons — donc jamais un sommet intermediaire, donc jamais evalue par un
        controle qui raisonne sur des triplets consecutifs.
        """
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0]], [[1.0, 0.0], [2.0, 1.0]]],
        }
        intermediaires_sans = sum(max(len(p) - 2, 0) for p in extraire_parties_lineaires(geometrie))
        intermediaires_avec = sum(max(len(p) - 2, 0) for p in recoller_parties_lineaires(geometrie))
        assert intermediaires_sans == 0
        assert intermediaires_avec == 1


class TestToleranceSuperposition:
    """La tolerance planimetrique est partagee par E205 et E209.

    Elle est calee sur l'arrondi millimetrique de la posList GML : la modifier
    change simultanement le verdict des deux controles, d'ou ce garde-fou.
    """

    def test_vaut_un_millimetre(self) -> None:
        assert TOLERANCE_SUPERPOSITION == 0.001

    def test_plus_stricte_que_l_adjacence_metier_de_e404(self) -> None:
        # E404 tolere 1 cm pour arbitrer une adjacence entre cheminements ;
        # ici on ne compense qu'un artefact numerique, bien plus petit.
        assert TOLERANCE_SUPERPOSITION < 0.01

    def test_plus_large_que_la_tolerance_altimetrique(self) -> None:
        # TOLERANCE_Z compare un flottant a zero ; les deux ne sont pas
        # interchangeables et ne doivent pas converger par megarde.
        assert TOLERANCE_SUPERPOSITION > TOLERANCE_Z


class TestEstZNul:
    """Detection d'une altitude non renseignee."""

    def test_zero_exact(self) -> None:
        assert est_z_nul(0.0)

    def test_altitude_ngf_valide(self) -> None:
        assert not est_z_nul(310.92)

    def test_altitude_negative_valide(self) -> None:
        """Une altitude sous le niveau de la mer reste une altitude renseignee."""
        assert not est_z_nul(-4.5)

    def test_sous_la_tolerance_considere_nul(self) -> None:
        """Le Z est un flottant issu du parsing GML : la comparaison est tolerante."""
        assert est_z_nul(TOLERANCE_Z / 10)

    def test_au_dessus_de_la_tolerance_considere_valide(self) -> None:
        assert not est_z_nul(TOLERANCE_Z * 10)


class TestCorrigerZNuls:
    """Propagation des altitudes valides vers les sommets a Z nul."""

    def test_aucun_z_nul(self) -> None:
        """Aucun Z a corriger : les valeurs restent identiques."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0], [2.0, 2.0, 30.0]]
        assert corriger_z_nuls(coords) == [10.0, 20.0, 30.0]

    def test_z_nul_debut(self) -> None:
        """Z=0.0 en debut : corrige par le premier Z valide suivant (passe arriere)."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 15.0], [2.0, 2.0, 20.0]]
        assert corriger_z_nuls(coords) == [15.0, 15.0, 20.0]

    def test_z_nul_fin(self) -> None:
        """Z=0.0 en fin : corrige par le dernier Z valide precedent (passe avant)."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0], [2.0, 2.0, 0.0]]
        assert corriger_z_nuls(coords) == [10.0, 20.0, 20.0]

    def test_z_nul_milieu(self) -> None:
        """Z=0.0 au milieu : corrige par propagation avant (Z precedent)."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 0.0], [2.0, 2.0, 30.0]]
        assert corriger_z_nuls(coords) == [10.0, 10.0, 30.0]

    def test_tous_z_nuls(self) -> None:
        """Tous les Z a 0.0 : aucun Z valide, tout reste a 0.0."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]
        assert corriger_z_nuls(coords) == [0.0, 0.0]

    def test_plusieurs_z_nuls_consecutifs(self) -> None:
        """Plusieurs Z=0.0 consecutifs : propages par le Z precedent valide."""
        coords = [
            [0.0, 0.0, 10.0],
            [1.0, 1.0, 0.0],
            [2.0, 2.0, 0.0],
            [3.0, 3.0, 25.0],
        ]
        assert corriger_z_nuls(coords) == [10.0, 10.0, 10.0, 25.0]

    def test_sans_composante_z(self) -> None:
        """Coordonnees 2D sans Z : traitees comme Z=0.0."""
        coords = [[0.0, 0.0], [1.0, 1.0, 10.0]]
        assert corriger_z_nuls(coords) == [10.0, 10.0]

    def test_polyligne_vide(self) -> None:
        assert corriger_z_nuls([]) == []

    def test_sommet_unique_a_z_nul(self) -> None:
        """Aucun voisin pour propager : la valeur reste a 0.0."""
        assert corriger_z_nuls([[0.0, 0.0, 0.0]]) == [0.0]

    def test_altitude_negative_propagee(self) -> None:
        """Une altitude negative est valide et sert donc de source de propagation."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, -4.5]]
        assert corriger_z_nuls(coords) == [-4.5, -4.5]

    def test_coordonnees_non_modifiees(self) -> None:
        """La fonction ne retourne que les Z : la polyligne source reste intacte."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 15.0]]
        corriger_z_nuls(coords)
        assert coords == [[0.0, 0.0, 0.0], [1.0, 1.0, 15.0]]

    def test_cas_reel_extremite_non_levee(self) -> None:
        """Cas rencontre en production : extremite accrochee, altitude jamais saisie.

        Le premier sommet est un point calcule par le logiciel de saisie (Z=0),
        les suivants sont leves autour de 310,9 m NGF. Sans correction, le premier
        segment mesure l'altitude du terrain au lieu de sa longueur reelle.
        """
        coords = [
            [850054.073151229, 6799803.32580639, 0.0],
            [850053.6, 6799802.91, 310.92],
            [850053.524504169, 6799802.59986505, 310.9],
        ]
        z = corriger_z_nuls(coords)
        assert z[0] == pytest.approx(310.92)
        assert z[1] == pytest.approx(310.92)
        assert z[2] == pytest.approx(310.9)
