"""
Tests du referentiel des codes du verificateur et de sa table de correspondance.

Deux garde-fous, miroirs de ceux qui protegent deja `LIBELLES_CONTROLES` :

  - **exhaustivite** : tout couple `(code_controle, type_anomalie)` emis par un
    controle possede un `code_erreur` ou est explicitement declare en attente de
    qualification. Ajouter un type d'anomalie sans statuer sur son code echoue ;
  - **integrite** : tout `code_erreur` declare existe dans le referentiel et
    n'est pas un code retire de la nomenclature.

Les couples emis sont releves par analyse syntaxique des modules de controle
(`ast`), et non par import : les modules s'importent a plat et tirent des
dependances tierces (shapely, pyproj) dont la table de correspondance n'a pas
besoin.
"""

import ast
import re
from functools import cache
from pathlib import Path
from typing import Any

from recostar.controle.codes_verificateur import (
    CODES_CONNUS,
    CODES_SUPPRIMES,
    CORRESPONDANCES,
    COUPLES_A_QUALIFIER,
    DEROGATIONS_NIVEAU,
    MOTIFS_A_QUALIFIER,
    NIVEAU_BASSE,
    ORDRE_NIVEAUX,
    PREFIXE_CODE_LOCAL,
    REFERENTIEL,
    REFERENTIEL_LOCAL,
    VERSION_REFERENTIEL,
    libelle_code_erreur,
    niveau_anomalie,
    niveau_code_erreur,
    resoudre_code_erreur,
)
from recostar.controle.fonctions_communes.geojson import (
    CHAMP_CODE_ERREUR,
    CHAMPS_SOCLE,
    ProfilEcarts,
    normaliser_geojson_ecarts,
)

# Racine du paquet de controle (repertoire parent de tests/).
_RACINE_CONTROLE = Path(__file__).resolve().parent.parent

# Forme normalisee d'un code du verificateur en service : « E-5102 ».
_MOTIF_CODE = re.compile(r"^E-\d{4}$")


# ---------------------------------------------------------------------------
# Relevé des couples emis par les modules de controle
# ---------------------------------------------------------------------------


def _constantes_litterales(arbre: ast.Module) -> dict[str, str]:
    """Releve les constantes de module dont la valeur est une chaine litterale.

    Necessaire pour resoudre les cles de `DESCRIPTIONS_ANOMALIES` ecrites sous
    forme de constante (`TYPE_ANO_ABSENT`) plutot que de litteral.
    """
    constantes: dict[str, str] = {}
    for noeud in arbre.body:
        cible = _cible_affectation(noeud)
        valeur = getattr(noeud, "value", None)
        if cible is None or not isinstance(valeur, ast.Constant):
            continue
        if isinstance(valeur.value, str):
            constantes[cible] = valeur.value
    return constantes


# Constantes des modules communs, relevees une fois et offertes a chaque
# controle : un type d'anomalie partage par plusieurs controles y est declare
# (les ruptures de chaine de localisation d'E-6105 et E-6109, par exemple), et le
# module qui l'emet ne le redeclare pas.
@cache
def _constantes_communes() -> dict[str, str]:
    """Constantes litterales declarees dans fonctions_communes/."""
    constantes: dict[str, str] = {}
    for chemin in sorted((_RACINE_CONTROLE / "fonctions_communes").glob("*.py")):
        constantes.update(_constantes_litterales(ast.parse(chemin.read_text(encoding="utf-8"))))
    return constantes


def _cible_affectation(noeud: ast.stmt) -> str | None:
    """Retourne le nom affecte par une instruction d'affectation de module."""
    if isinstance(noeud, ast.AnnAssign) and isinstance(noeud.target, ast.Name):
        return noeud.target.id
    if isinstance(noeud, ast.Assign) and len(noeud.targets) == 1 and isinstance(noeud.targets[0], ast.Name):
        return noeud.targets[0].id
    return None


def _valeur_de_cle(cle: ast.expr, constantes: dict[str, str]) -> str | None:
    """Resout une cle de dictionnaire, litterale ou referencant une constante."""
    if isinstance(cle, ast.Constant) and isinstance(cle.value, str):
        return cle.value
    if isinstance(cle, ast.Name):
        return constantes.get(cle.id)
    return None


def _types_anomalie(arbre: ast.Module, constantes: dict[str, str]) -> tuple[str, ...]:
    """Releve les cles de `DESCRIPTIONS_ANOMALIES`, source des type_anomalie."""
    for noeud in arbre.body:
        if _cible_affectation(noeud) != "DESCRIPTIONS_ANOMALIES":
            continue
        valeur = getattr(noeud, "value", None)
        if not isinstance(valeur, ast.Dict):
            continue
        releves = (_valeur_de_cle(cle, constantes) for cle in valeur.keys if cle is not None)
        return tuple(type_anomalie for type_anomalie in releves if type_anomalie is not None)
    return ()


def _couples_emis() -> frozenset[tuple[str, str]]:
    """Releve tous les couples (code_controle, type_anomalie) des controles GeoJSON.

    Les controles de structuration XSD sont ignores : ils n'exposent pas de
    `DESCRIPTIONS_ANOMALIES` et relevent de `codes_verificateur_xsd`.
    """
    couples: set[tuple[str, str]] = set()
    for chemin in _RACINE_CONTROLE.glob("*/e[0-9]*.py"):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        constantes = {**_constantes_communes(), **_constantes_litterales(arbre)}
        code_controle = constantes.get("CODE_CONTROLE")
        if code_controle is None:
            continue
        couples.update((code_controle, type_anomalie) for type_anomalie in _types_anomalie(arbre, constantes))
    return frozenset(couples)


# Releve une seule fois : l'analyse syntaxique des 40 modules est le cout
# dominant de ce fichier de tests.
_COUPLES_EMIS = _couples_emis()


# ---------------------------------------------------------------------------
# Integrite du referentiel
# ---------------------------------------------------------------------------


class TestIntegriteReferentiel:
    """Le referentiel doit rester conforme a la nomenclature du verificateur."""

    def test_version_declaree(self) -> None:
        assert VERSION_REFERENTIEL == "2.14.0"

    def test_codes_bien_formes(self) -> None:
        for code in REFERENTIEL:
            assert _MOTIF_CODE.match(code), f"code mal forme : {code}"

    def test_index_coherent_avec_les_fiches(self) -> None:
        """La cle d'index doit etre le code porte par la fiche."""
        for code, fiche in REFERENTIEL.items():
            assert fiche.code == code

    def test_libelles_renseignes(self) -> None:
        for code, fiche in REFERENTIEL.items():
            assert fiche.libelle.strip(), f"libelle vide pour {code}"

    def test_niveaux_dans_l_echelle(self) -> None:
        for code, fiche in REFERENTIEL.items():
            assert fiche.niveau in ORDRE_NIVEAUX, f"niveau inconnu pour {code}"

    def test_versions_renseignees(self) -> None:
        for code, fiche in REFERENTIEL.items():
            assert fiche.version_introduction, f"version d'introduction absente pour {code}"

    def test_codes_en_service_denombres(self) -> None:
        """97 codes actifs au sommaire des fiches, 109 au total moins 12 retires."""
        assert len(REFERENTIEL) == 97

    def test_activation_reservee_aux_paliers(self) -> None:
        """Seuls les triplets E-71xx / E-72xx / E-73xx portent un calendrier."""
        for code, fiche in REFERENTIEL.items():
            if fiche.activation is not None:
                assert code.startswith(("E-71", "E-72", "E-73")), code

    def test_aucun_code_supprime_reintroduit(self) -> None:
        assert not (REFERENTIEL.keys() & CODES_SUPPRIMES)

    def test_codes_supprimes_declares(self) -> None:
        """Les douze codes retires de la nomenclature restent listes."""
        assert len(CODES_SUPPRIMES) == 12


class TestReferentielLocal:
    """La serie E-9xxx couvre les controles que le verificateur ne nomme pas.

    Elle est tenue a part du referentiel officiel : `REFERENTIEL` doit rester
    comparable ligne a ligne aux fiches du verificateur, c'est `CODES_CONNUS`
    qui sert de vue de resolution.
    """

    def test_denombrement(self) -> None:
        assert len(REFERENTIEL_LOCAL) == 23

    def test_prefixe_reserve(self) -> None:
        for code in REFERENTIEL_LOCAL:
            assert code.startswith(PREFIXE_CODE_LOCAL), code

    def test_codes_bien_formes(self) -> None:
        for code, fiche in REFERENTIEL_LOCAL.items():
            assert _MOTIF_CODE.fullmatch(code), code
            assert fiche.code == code
            assert fiche.libelle.strip(), code
            assert fiche.niveau in ORDRE_NIVEAUX, code
            assert fiche.version_introduction.strip(), code

    def test_aucune_activation_calendaire(self) -> None:
        """Les paliers calendaires sont propres au verificateur."""
        for code, fiche in REFERENTIEL_LOCAL.items():
            assert fiche.activation is None, code

    def test_aucune_collision_avec_le_verificateur(self) -> None:
        assert not (REFERENTIEL.keys() & REFERENTIEL_LOCAL.keys())
        assert not (REFERENTIEL_LOCAL.keys() & CODES_SUPPRIMES)

    def test_serie_neuf_mille_etrangere_au_verificateur(self) -> None:
        """Le verificateur n'emet aucun code en E-9 : la serie reste libre."""
        for code in (*REFERENTIEL, *CODES_SUPPRIMES):
            assert not code.startswith(PREFIXE_CODE_LOCAL), code

    def test_vue_de_resolution_complete(self) -> None:
        assert CODES_CONNUS == REFERENTIEL | REFERENTIEL_LOCAL

    def test_niveaux_resolus_par_les_accesseurs(self) -> None:
        for code, fiche in REFERENTIEL_LOCAL.items():
            assert niveau_code_erreur(code) == fiche.niveau
            assert libelle_code_erreur(code) == fiche.libelle

    def test_tout_code_local_est_utilise(self) -> None:
        """Un code local qu'aucun couple ne pointe n'a pas lieu d'exister.

        Les familles GeoJSON resolvent leurs codes par `CORRESPONDANCES` ; la
        structuration par sa propre table, a la maille du rang. Les deux
        sources sont donc confrontees au referentiel local.
        """
        from recostar.controle.xsd_structuration.codes_verificateur_xsd import (
            CODE_PAR_DEFAUT_RANG,
            CORRESPONDANCES_XSD,
        )

        vises = set(CORRESPONDANCES.values()) | set(CORRESPONDANCES_XSD.values())
        vises |= {code for code in CODE_PAR_DEFAUT_RANG if code is not None}
        assert set(REFERENTIEL_LOCAL) == {code for code in vises if code.startswith(PREFIXE_CODE_LOCAL)}


class TestIntegriteCorrespondances:
    """Toute correspondance doit pointer un code existant et en service."""

    def test_codes_erreur_references(self) -> None:
        for couple, code_erreur in CORRESPONDANCES.items():
            assert code_erreur in CODES_CONNUS, f"{couple} pointe le code inconnu {code_erreur}"

    def test_codes_erreur_non_supprimes(self) -> None:
        for couple, code_erreur in CORRESPONDANCES.items():
            assert code_erreur not in CODES_SUPPRIMES, f"{couple} pointe le code retire {code_erreur}"

    def test_couples_bien_formes(self) -> None:
        for code_controle, type_anomalie in CORRESPONDANCES:
            assert code_controle.startswith("E"), code_controle
            assert type_anomalie == type_anomalie.lower(), type_anomalie

    def test_aucun_couple_a_la_fois_correspondu_et_en_attente(self) -> None:
        assert not (CORRESPONDANCES.keys() & COUPLES_A_QUALIFIER)

    def test_motifs_renseignes(self) -> None:
        for couple, motif in MOTIFS_A_QUALIFIER.items():
            assert motif.strip(), f"motif vide pour {couple}"


# ---------------------------------------------------------------------------
# Exhaustivite
# ---------------------------------------------------------------------------


class TestExhaustivite:
    """Tout type d'anomalie emis doit avoir ete statue, dans un sens ou l'autre."""

    def test_releve_non_vide(self) -> None:
        """Garde-fou du releve lui-meme : un extracteur muet rendrait tout vert."""
        assert len(_COUPLES_EMIS) == 98

    def test_tout_couple_emis_est_statue(self) -> None:
        non_statues = sorted(_COUPLES_EMIS - CORRESPONDANCES.keys() - COUPLES_A_QUALIFIER)
        assert not non_statues, f"couples sans code_erreur ni motif d'attente : {non_statues}"

    def test_aucune_correspondance_orpheline(self) -> None:
        """Une correspondance visant un couple qui n'est plus emis est morte."""
        orphelines = sorted(CORRESPONDANCES.keys() - _COUPLES_EMIS)
        assert not orphelines, f"correspondances sans anomalie emise : {orphelines}"

    def test_aucune_attente_orpheline(self) -> None:
        """Un couple qualifie doit sortir de la liste d'attente."""
        orphelines = sorted(COUPLES_A_QUALIFIER - _COUPLES_EMIS)
        assert not orphelines, f"attentes sans anomalie emise : {orphelines}"


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolution:
    """Resolution du code d'erreur depuis le couple controle / anomalie."""

    def test_couple_correspondu(self) -> None:
        assert resoudre_code_erreur("E-5102", "point_leve_absent") == "E-5102"

    def test_deux_codes_issus_d_un_meme_moteur(self) -> None:
        """Deux controles servis par un meme moteur resolvent chacun son code.

        La resolution se reduit a l'identite : le code du controle est celui de
        l'anomalie.
        """
        assert resoudre_code_erreur("E-5102", "point_leve_absent") == "E-5102"
        assert resoudre_code_erreur("E-5103", "coordonnees_differentes") == "E-5103"

    def test_deux_formes_d_une_meme_anomalie(self) -> None:
        """Z absent et Z nul sont deux formes d'un seul code, donc d'un seul controle.

        Sous E-5107, le `type_anomalie` porte seul la distinction que le code ne
        fait pas.
        """
        assert resoudre_code_erreur("E-5107", "absence_coordonnee_z") == "E-5107"
        assert resoudre_code_erreur("E-5107", "z_null") == "E-5107"

    def test_type_non_declare_pour_ce_code(self) -> None:
        """Un type d'anomalie absent de la table ne resout aucun code."""
        assert resoudre_code_erreur("E-4200", "longueur_excessive") is None

    def test_un_moteur_deux_mailles(self) -> None:
        """Un seul moteur rend deux mailles de superposition, sous deux codes."""
        assert resoudre_code_erreur("E-3300", "plor_superpose_meme_type") == "E-3300"
        assert resoudre_code_erreur("E-6206", "plor_superpose_xy_meme_type") == "E-6206"
        assert resoudre_code_erreur("E-3300", "doublons_spatiaux") is None

    def test_controle_inconnu(self) -> None:
        assert resoudre_code_erreur("E0999", "peu_importe") is None

    def test_type_anomalie_absent(self) -> None:
        assert resoudre_code_erreur("E-5102", None) is None


class TestLectureDuReferentiel:
    """Acces au niveau et au libelle, socle de la derivation des priorites."""

    def test_niveau_connu(self) -> None:
        assert niveau_code_erreur("E-5107") == "basse"

    def test_niveau_forte(self) -> None:
        assert niveau_code_erreur("E-5102") == "forte"

    def test_niveau_code_inconnu(self) -> None:
        assert niveau_code_erreur("E-9999") is None

    def test_niveau_sans_code(self) -> None:
        assert niveau_code_erreur(None) is None

    def test_libelle_connu(self) -> None:
        assert libelle_code_erreur("E-5102") == "Le sommet n'est pas associé à un PLOR / PTRL"

    def test_libelle_code_inconnu(self) -> None:
        assert libelle_code_erreur("E-9999") is None

    def test_libelle_sans_code(self) -> None:
        assert libelle_code_erreur(None) is None


# ---------------------------------------------------------------------------
# Insertion dans le socle des features d'ecarts
# ---------------------------------------------------------------------------


def _geojson(type_anomalie: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": None,
                "properties": {"type_anomalie": type_anomalie, "id_entite": "e1", "priorite": "bloquant"},
            }
        ],
    }


class TestSocleCodeErreur:
    """`code_erreur` doit etre resolu au point d'insertion unique du socle."""

    profil = ProfilEcarts(code_controle="E-5102", descriptions={"point_leve_absent": "Sommet sans point de leve."})

    def test_champ_present_dans_le_socle(self) -> None:
        assert CHAMPS_SOCLE[1] == CHAMP_CODE_ERREUR

    def test_socle_a_sept_champs(self) -> None:
        """Le septieme est `couche`, qui alimente DESIGNATION_RPD en sortie."""
        assert len(CHAMPS_SOCLE) == 7

    def test_code_resolu(self) -> None:
        resultat = normaliser_geojson_ecarts(_geojson("point_leve_absent"), self.profil)
        assert resultat["features"][0]["properties"][CHAMP_CODE_ERREUR] == "E-5102"

    def test_code_nul_si_couple_non_qualifie(self) -> None:
        """Un couple sans code ne doit pas empecher l'emission de l'ecart."""
        resultat = normaliser_geojson_ecarts(_geojson("type_inconnu"), self.profil)
        proprietes = resultat["features"][0]["properties"]
        assert proprietes[CHAMP_CODE_ERREUR] is None
        assert proprietes["code_controle"] == "E-5102"

    def test_position_du_champ(self) -> None:
        """Le code d'erreur suit immediatement le code de controle dans QGIS."""
        resultat = normaliser_geojson_ecarts(_geojson("point_leve_absent"), self.profil)
        assert list(resultat["features"][0]["properties"])[:2] == ["code_controle", CHAMP_CODE_ERREUR]

    def test_champs_metier_conserves(self) -> None:
        geojson = _geojson("point_leve_absent")
        geojson["features"][0]["properties"]["distance_m"] = 1.5
        resultat = normaliser_geojson_ecarts(geojson, self.profil)
        assert resultat["features"][0]["properties"]["distance_m"] == 1.5


# ---------------------------------------------------------------------------
# Derogations de niveau
# ---------------------------------------------------------------------------


class TestDerogationsNiveau:
    """Les ecarts au niveau du referentiel restent explicites et vivants."""

    def test_niveaux_declares_connus(self) -> None:
        """Une derogation ne peut viser qu'un niveau de l'echelle."""
        for couple, niveau in DEROGATIONS_NIVEAU.items():
            assert niveau in ORDRE_NIVEAUX, f"niveau inconnu pour {couple} : {niveau}"

    def test_couples_correspondus(self) -> None:
        """Deroger au niveau d'un couple suppose que son code soit etabli."""
        orphelines = sorted(DEROGATIONS_NIVEAU.keys() - CORRESPONDANCES.keys())
        assert not orphelines, f"derogations sans code d'erreur : {orphelines}"

    def test_derogation_prime_sur_le_code(self) -> None:
        """Le niveau derogatoire l'emporte sur celui du code d'erreur."""
        for (code_controle, type_anomalie), niveau in DEROGATIONS_NIVEAU.items():
            assert niveau_anomalie(code_controle, type_anomalie) == niveau

    def test_derogation_effectivement_ecartee(self) -> None:
        """Une derogation alignee sur le code serait inutile : elle doit l'abaisser."""
        for (code_controle, type_anomalie), niveau in DEROGATIONS_NIVEAU.items():
            code_erreur = resoudre_code_erreur(code_controle, type_anomalie)
            assert niveau != niveau_code_erreur(code_erreur), (
                f"derogation sans effet pour {(code_controle, type_anomalie)}"
            )


class TestNoeudTerreSansRattachement:
    """E-9605 sur un noeud de terre : un signalement qui ne declasse pas."""

    COUPLE = ("E-9605", "cables_href_absent_noeud_terre")

    def test_niveau_abaisse(self) -> None:
        """Le noeud de terre remonte en « basse »."""
        assert niveau_anomalie(*self.COUPLE) == NIVEAU_BASSE

    def test_meme_code_que_le_cas_general(self) -> None:
        """La derogation change le niveau, jamais le code : c'est le meme defaut."""
        assert resoudre_code_erreur(*self.COUPLE) == resoudre_code_erreur("E-9605", "cables_href_absent")

    def test_cas_general_inchange(self) -> None:
        """Les autres couches de noeud gardent le niveau du code."""
        assert niveau_anomalie("E-9605", "cables_href_absent") != NIVEAU_BASSE
