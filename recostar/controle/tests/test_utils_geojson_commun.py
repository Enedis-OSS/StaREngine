"""
Tests du module commun utils_geojson_commun.

Couvre la ventilation des anomalies par type, mutualisee par les controles a
sortie GeoJSON, et la coherence des shims utils_geojson.py qui la reexportent.
"""

import ast
from pathlib import Path
from typing import Any

from utils_geojson_commun import compter_anomalies_par_type

# Racine du paquet de controle (repertoire parent de tests/).
_RACINE_CONTROLE = Path(__file__).resolve().parent.parent


def _anomalie(type_anomalie: str) -> dict[str, Any]:
    return {"type_anomalie": type_anomalie, "id_entite": "e1"}


class TestCompterAnomaliesParType:
    """Ventilation des anomalies par type pour le rapport JSON."""

    def test_liste_vide(self) -> None:
        assert compter_anomalies_par_type([]) == {}

    def test_type_unique(self) -> None:
        assert compter_anomalies_par_type([_anomalie("a")]) == {"a": 1}

    def test_occurrences_cumulees(self) -> None:
        anomalies = [_anomalie("a"), _anomalie("a"), _anomalie("b")]
        assert compter_anomalies_par_type(anomalies) == {"a": 2, "b": 1}

    def test_dictionnaire_simple_retourne(self) -> None:
        """Le rapport est serialise en JSON : un Counter ne doit pas fuir."""
        resultat = compter_anomalies_par_type([_anomalie("a")])
        assert type(resultat) is dict

    def test_type_absent_leve(self) -> None:
        """Une anomalie sans type_anomalie est un defaut de programmation.

        Le masquer produirait une ventilation silencieusement fausse.
        """
        try:
            compter_anomalies_par_type([{"id_entite": "e1"}])
        except KeyError:
            return
        raise AssertionError("une anomalie sans type_anomalie doit lever")


def _noms_reexportes(chemin: Path) -> set[str]:
    """Noms importes depuis utils_geojson_commun par un shim de domaine."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    noms: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.module == "utils_geojson_commun":
            noms.update(alias.name for alias in noeud.names)
    return noms


class TestCoherenceDesShims:
    """Les shims utils_geojson.py doivent reexporter le meme jeu de noms.

    Ils portent tous le meme nom de module : dans un processus unique
    (pipeline_globale charge les cinq familles), le premier charge occupe
    sys.modules et sert les autres. Un shim exposant moins que son voisin
    provoque un ImportError a distance, dans le domaine charge en second.

    Meme garde que `TestCoherenceDesShims` de test_utils_geometrie_commun, dont
    les shims utils_geojson.py etaient jusqu'ici depourvus.
    """

    def test_shims_identiques(self) -> None:
        shims = sorted(_RACINE_CONTROLE.glob("*/utils_geojson.py"))
        assert len(shims) >= 2, "au moins deux domaines delèguent vers le module commun"
        reference = _noms_reexportes(shims[0])
        assert reference, f"{shims[0]} ne reexporte rien"
        for shim in shims[1:]:
            assert _noms_reexportes(shim) == reference, f"{shim.parent.name} diverge de {shims[0].parent.name}"

    def test_noms_reexportes_existent_dans_le_module_commun(self) -> None:
        """Un nom reexporte mais absent du module commun casserait tous les domaines."""
        import utils_geojson_commun

        for shim in _RACINE_CONTROLE.glob("*/utils_geojson.py"):
            for nom in _noms_reexportes(shim):
                assert hasattr(utils_geojson_commun, nom), f"{nom} absent de utils_geojson_commun"

    def test_fonction_mutualisee_reexportee(self) -> None:
        """La ventilation partagee doit etre servie par chacun des cinq shims."""
        for shim in _RACINE_CONTROLE.glob("*/utils_geojson.py"):
            assert "compter_anomalies_par_type" in _noms_reexportes(shim), shim.parent.name
