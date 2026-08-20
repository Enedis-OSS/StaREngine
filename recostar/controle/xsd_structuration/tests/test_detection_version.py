"""
Tests de la détection automatique de version (detection_version).

Couvre les cas nominaux (jetons canoniques v1.0, v1.1), le repli par nom de
branche (`main` → V1.0) et les cas limites (tag legacy v1.10 non reconnu,
schemaLocation absent, jeton inconnu, branche inconnue, XML malformé, fichier
inexistant) qui doivent tous retourner None sans exception.
"""

from pathlib import Path

import pytest
from detection_version import detecter_version

# Préfixe d'URL canonique des schémas RecoStaR sur le dépôt amont.
_BASE_URL = "http://StaR-Elec.com https://gitlab.com/StaR-Elec/StaR-Elec/-/raw"


def _schema_location(jeton: str) -> str:
    """Construit une valeur xsi:schemaLocation pointant un tag de version donné."""
    return f"{_BASE_URL}/{jeton}/RecoStaR/SchemaStarElecRecoStar.xsd"


# ---------------------------------------------------------------------------
# Cas nominaux : un jeton reconnu donne le bon code de version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "jeton, version_attendue",
    [
        ("RecoStar-v1.0", "1.0"),
        ("RecoStar-v1.1", "1.1"),
    ],
)
def test_detection_jeton_connu(chemin_gml_entete_tmp, jeton, version_attendue):
    """Chaque jeton de version canonique est traduit en code de registre."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_schema_location(jeton))
    assert detecter_version(chemin) == version_attendue


def test_detection_tag_legacy_v1_10_non_reconnu(chemin_gml_entete_tmp):
    """L'ancien tag v1.10 n'est plus reconnu (canonique v1.1 uniquement) → None.

    Le canonique étant v1.1, un fichier portant l'ancien tag retombe sur le
    repli de version par défaut géré côté CLI.
    """
    chemin = chemin_gml_entete_tmp([], schema_location_override=_schema_location("RecoStar-v1.10"))
    assert detecter_version(chemin) is None


def test_detection_v1_0_non_confondue_avec_v1_1(chemin_gml_entete_tmp):
    """Le jeton v1.0 ne doit pas être confondu avec v1.1 (piège de sous-chaîne)."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_schema_location("RecoStar-v1.0"))
    assert detecter_version(chemin) == "1.0"


# ---------------------------------------------------------------------------
# Repli sur la branche : `main` désigne la V1.0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("branche", ["main", "MAIN", "Main"])
def test_detection_branche_main_vaut_v1_0(chemin_gml_entete_tmp, branche):
    """Une URL sans tag pointant la branche `main` est rattachée à la V1.0."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_schema_location(branche))
    assert detecter_version(chemin) == "1.0"


def test_detection_tag_prioritaire_sur_branche(chemin_gml_entete_tmp):
    """Un tag de version explicite prime sur le repli par nom de branche."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_schema_location("RecoStar-v1.1"))
    assert detecter_version(chemin) == "1.1"


def test_detection_branche_inconnue(chemin_gml_entete_tmp):
    """Une branche non répertoriée (autre que `main`) reste indétectable."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_schema_location("develop"))
    assert detecter_version(chemin) is None


# ---------------------------------------------------------------------------
# Cas limites : détection impossible → None, sans exception
# ---------------------------------------------------------------------------


def test_detection_schema_location_absent(chemin_gml_entete_tmp):
    """Sans schemaLocation, la détection retourne None."""
    chemin = chemin_gml_entete_tmp([], inclure_schema_location=False)
    assert detecter_version(chemin) is None


def test_detection_jeton_inconnu(chemin_gml_entete_tmp):
    """Un jeton de version non répertorié donne None (et non une erreur)."""
    chemin = chemin_gml_entete_tmp([], schema_location_override=_schema_location("RecoStar-v9.9"))
    assert detecter_version(chemin) is None


def test_detection_url_sans_jeton(chemin_gml_entete_tmp):
    """Une URL de schéma sans motif RecoStar-v donne None."""
    chemin = chemin_gml_entete_tmp([], schema_location_override="http://StaR-Elec.com http://exemple.org/s.xsd")
    assert detecter_version(chemin) is None


def test_detection_xml_malforme(tmp_path: Path):
    """Un fichier XML non valide ne fait pas planter la détection."""
    chemin = tmp_path / "casse.gml"
    chemin.write_bytes(b"<gml:FeatureCollection><pas-ferme>")
    assert detecter_version(chemin) is None


def test_detection_fichier_inexistant(tmp_path: Path):
    """Un fichier absent retourne None (OSError absorbée)."""
    assert detecter_version(tmp_path / "absent.gml") is None
