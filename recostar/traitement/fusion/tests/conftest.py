"""Fixtures partagees des tests de fusion GML."""

import pytest

SCHEMA_V1_1 = "https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/RecoStar-v1.1/RecoStaR/SchemaStarElecRecoStar.xsd"

GML_MODELE = """<?xml version="1.0" encoding="utf-8" ?>
<gml:FeatureCollection
    xmlns:RecoStaR="http://StaR-Elec.com"
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://StaR-Elec.com {schema}">
  <gml:featureMember>
    <RecoStaR:Metadata gml:id="{prefixe}_meta">
      <RecoStaR:SRS>{srs}</RecoStaR:SRS>
    </RecoStaR:Metadata>
  </gml:featureMember>
  <gml:featureMember>
    <RecoStaR:ReseauUtilite gml:id="Reseau">
      <RecoStaR:Nom>{prefixe}</RecoStaR:Nom>
    </RecoStaR:ReseauUtilite>
  </gml:featureMember>
  <gml:featureMember>
    <RecoStaR:RPD_Aerien_Reco gml:id="{prefixe}_aerien">
      <RecoStaR:reseau xlink:href="Reseau" />
      <RecoStaR:Geometrie>
        <gml:LineString srsName="{srs}" gml:id="partage.geom0">
          <gml:posList srsDimension="3">650000 6860000 12 651000 6861000 13</gml:posList>
        </gml:LineString>
      </RecoStaR:Geometrie>
    </RecoStaR:RPD_Aerien_Reco>
  </gml:featureMember>
</gml:FeatureCollection>
"""


def _ecrire_gml(chemin, prefixe: str, srs: str, schema: str = SCHEMA_V1_1):
    """Ecrit un GML minimal et retourne son chemin."""
    chemin.write_text(
        GML_MODELE.format(prefixe=prefixe, srs=srs, schema=schema),
        encoding="utf-8",
    )
    return chemin


@pytest.fixture
def gml_a(tmp_path):
    """Premier GML, en Lambert-93."""
    return _ecrire_gml(tmp_path / "a.gml", "a", "EPSG:2154")


@pytest.fixture
def gml_b(tmp_path):
    """Second GML, en Lambert-93 lui aussi."""
    return _ecrire_gml(tmp_path / "b.gml", "b", "EPSG:2154")


@pytest.fixture
def gml_b_cc47(tmp_path):
    """Second GML, dans une projection differente du premier."""
    return _ecrire_gml(tmp_path / "b_cc47.gml", "b", "EPSG:3947")


@pytest.fixture
def gml_autre_version(tmp_path):
    """GML declarant une version de schema differente."""
    schema = SCHEMA_V1_1.replace("RecoStar-v1.1", "RecoStar-v1.0")
    return _ecrire_gml(tmp_path / "v10.gml", "c", "EPSG:2154", schema)


@pytest.fixture
def gml_b_superposable(tmp_path, gml_a):
    """Second GML en CC47, geographiquement identique au premier.

    Produit par le traitement de reprojection lui-meme : les coordonnees sont
    celles de `gml_a`, exprimees dans l'autre projection.
    """
    from recostar.traitement.reprojection.reprojection_gml import executer_reprojection

    chemin = tmp_path / "b_superposable.gml"
    resultat = executer_reprojection(str(gml_a), "EPSG:3947", str(chemin))
    assert resultat.succes
    return chemin
