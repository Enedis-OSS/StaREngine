"""Fixtures partagees des tests de reprojection GML."""

import pytest

GML_MINIMAL = """<?xml version="1.0" encoding="utf-8" ?>
<gml:FeatureCollection
    xmlns:RecoStaR="http://StaR-Elec.com"
    xmlns:gml="http://www.opengis.net/gml/3.2">
<!-- GML au format RecoStar-v1.1. -->
  <gml:featureMember>
    <RecoStaR:Metadata gml:id="meta1">
      <RecoStaR:SRS>{srs}</RecoStaR:SRS>
    </RecoStaR:Metadata>
  </gml:featureMember>
  <gml:featureMember>
    <RecoStaR:RPD_Aerien_Reco gml:id="aerien1">
      <RecoStaR:Geometrie>
        <gml:LineString srsName="{srs_geometrie}" gml:id="geom0">
          <gml:posList srsDimension="3">650000 6860000 123.45 651000 6861000 -7.5</gml:posList>
        </gml:LineString>
      </RecoStaR:Geometrie>
    </RecoStaR:RPD_Aerien_Reco>
  </gml:featureMember>
</gml:FeatureCollection>
"""


@pytest.fixture
def gml_lambert93(tmp_path):
    """GML minimal declarant EPSG:2154 dans les metadonnees et les geometries."""
    chemin = tmp_path / "recolement.gml"
    chemin.write_text(
        GML_MINIMAL.format(srs="EPSG:2154", srs_geometrie="EPSG:2154"),
        encoding="utf-8",
    )
    return chemin


@pytest.fixture
def gml_sans_metadata(tmp_path):
    """GML dont seule la geometrie porte la projection."""
    contenu = GML_MINIMAL.format(srs="EPSG:2154", srs_geometrie="EPSG:2154")
    debut = contenu.index("  <gml:featureMember>")
    fin = contenu.index("</gml:featureMember>", debut) + len("</gml:featureMember>\n")
    chemin = tmp_path / "sans_metadata.gml"
    chemin.write_text(contenu[:debut] + contenu[fin:], encoding="utf-8")
    return chemin


@pytest.fixture
def gml_projections_divergentes(tmp_path):
    """GML dont le Metadata/SRS contredit le srsName des geometries."""
    chemin = tmp_path / "divergent.gml"
    chemin.write_text(
        GML_MINIMAL.format(srs="EPSG:2154", srs_geometrie="EPSG:3947"),
        encoding="utf-8",
    )
    return chemin
