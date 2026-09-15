#!/usr/bin/env python3
"""
Pipeline de contrôle de structuration XSD des fichiers GML RecoStaR.

Orchestre l'exécution séquentielle des cinq contrôles de structuration sur un
même fichier GML. Chaque contrôle est exécuté indépendamment : un échec (par
exemple l'indisponibilité du XSD pour la validation native) n'empêche pas
l'exécution des contrôles suivants. Chaque contrôle écrit son propre rapport
JSON et le pipeline produit un rapport global agrégé.

Les codes des contrôles suivent la version contrôlée : **E0110 à E0114 en V1.1**,
**E0010 à E0014 en V1.0**. La version est résolue une seule fois en amont puis
propagée aux cinq contrôles, garantissant une version homogène et des codes
cohérents entre les rapports individuels et le rapport global.

Contrôles enchaînés (rang → code V1.1 / V1.0) :
    1. Ordre de structure des objets RPD     — E0110 / E0010
    2. Règles métier conditionnelles         — E0111 / E0011
    3. Validation XSD native via lxml        — E0112 / E0012
    4. En-tête, namespaces, unicité gml:id   — E0113 / E0013
    5. Valeurs des champs                    — E0114 / E0014

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Un rapport JSON par contrôle + un rapport global agrégé

Usage :
    python -m recostar.controle.xsd_structuration.pipeline_controle_xsd <fichier.gml> [--output-dir <repertoire>]
                                                                        [--xsd <chemin.xsd>] [--cache-dir <repertoire>] [--offline]
                                                                        [--version {auto,1.0,1.1}]
"""

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from recostar.controle.xsd_structuration import (
    e0110,
    e0111,
    e0112,
    e0113,
    e0114,
    e0115,
    e0116,
    e0117,
    e0118,
    e0119,
    e0120,
)
from recostar.controle.xsd_structuration.cli_version import JETON_AUTO, ajouter_argument_version, resoudre_profil_cli
from recostar.controle.xsd_structuration.codes_controle import (
    NB_CONTROLES,
    RANG_DOCUMENT,
    RANG_ENTETE,
    RANG_GEOMETRIE,
    RANG_JOINTURES,
    RANG_JOINTURES_CHAMPS,
    RANG_METIER,
    RANG_ORDRE,
    RANG_SRS_DIMENSION,
    RANG_STATUT_EN_SERVICE,
    RANG_VALEURS,
    RANG_XSD_NATIF,
    codes_version,
    identite_controle,
)
from recostar.controle.xsd_structuration.codes_verificateur_xsd import (
    codes_possibles_rang,
    rang_depuis_code_controle,
    resoudre_code_erreur_xsd,
)
from recostar.controle.xsd_structuration.priorites_structuration import (
    CONFORME,
    NON_CONFORME,
    compter_bloquantes,
    statut_conformite,
    ventiler_par_priorite,
)
from recostar.controle.xsd_structuration.sortie_structuration import (
    agreger_rapports_structuration,
    code_regle_erreur,
)
from recostar.controle.xsd_structuration.versions import VERSIONS_SUPPORTEES
from recostar.controle.xsd_structuration.versions.profil import ProfilVersion

# Sévérité considérée comme bloquante pour la conformité.
SEVERITE_ERREUR = "ERREUR"

# Codes des contrôles, toutes versions supportées confondues. Une exécution
# n'en produit que cinq (ceux de la version contrôlée), mais le registre des
# libellés (controle/familles_controle.py) doit tous les connaître.
NOMS_CONTROLES: tuple[str, ...] = tuple(code for version in VERSIONS_SUPPORTEES for code in codes_version(version))

# Nom du rapport global agrégé (suffixe ajouté au nom du fichier GML).


# ---------------------------------------------------------------------------
# Construction des résumés de contrôle
# ---------------------------------------------------------------------------


def _codes_erreur(type_controle: str, erreurs: list[Any]) -> tuple[str, ...]:
    """Codes du verificateur portes par les anomalies d'un controle.

    Un controle de structuration n'a pas de code propre : il en emet plusieurs
    selon la regle enfreinte. Le rapport expose donc ceux qu'il a reellement
    releves, et a defaut d'anomalie ceux qu'il couvre.

    Le repli sur le code du controle reproduit celui de `harmoniser_erreur` :
    la colonne du rapport et le detail des anomalies doivent porter les memes
    valeurs, y compris pour les regles sans equivalent au verificateur.
    """
    code_controle = type_controle.split("_", 1)[0]
    rang = rang_depuis_code_controle(code_controle)
    if rang is None:
        return ()
    if not erreurs:
        return codes_possibles_rang(rang)

    codes = {
        resoudre_code_erreur_xsd(rang, code_regle_erreur(erreur.vers_dict())) or code_controle for erreur in erreurs
    }
    return tuple(sorted(codes))


def _resumer(type_controle: str, erreurs: list[Any], chemin_rapport: Path) -> dict[str, Any]:
    """Construit le résumé d'un contrôle réussi à partir de sa liste d'erreurs.

    Tous les contrôles (E0110-E0114) sont mono-sévérité : la ventilation par
    sévérité ne comporte que des entrées ERREUR. La **priorité**, elle, varie :
    deux règles seulement dérogent au niveau bloquant (cf.
    `priorites_structuration`), et seules les erreurs bloquantes invalident la
    conformité.

    `anomalies_par_priorite` est la clé lue par `synthese_controles` pour
    ventiler la famille dans le rapport PDF ; `nb_erreurs` y reste le total
    toutes priorités confondues.
    """
    par_severite: dict[str, int] = {}
    for erreur in erreurs:
        par_severite[erreur.severite] = par_severite.get(erreur.severite, 0) + 1

    nb_erreurs = par_severite.get(SEVERITE_ERREUR, 0)
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "succes": True,
        "type_controle": type_controle,
        "codes_erreur": list(_codes_erreur(type_controle, erreurs)),
        "conformite": statut_conformite(par_priorite),
        "nb_erreurs": nb_erreurs,
        "nb_erreurs_bloquantes": compter_bloquantes(par_priorite),
        "nb_par_severite": par_severite,
        "anomalies_par_priorite": par_priorite,
        "rapport": str(chemin_rapport),
    }


def _echec(type_controle: str, message: str) -> dict[str, Any]:
    """Construit le résumé d'un contrôle qui n'a pas pu s'exécuter."""
    return {"succes": False, "type_controle": type_controle, "erreur": message}


def _proteger(type_controle: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Exécute un contrôle en isolant ses erreurs pour ne pas bloquer le pipeline.

    Un contrôle peut échouer pour des raisons variées (XML mal formé, XSD non
    compilable, dépendance réseau indisponible). L'exception est convertie en
    résumé d'échec afin que les contrôles suivants s'exécutent malgré tout.
    """
    try:
        return action()
    except Exception as exc:  # orchestrateur : un échec ne doit pas bloquer les contrôles suivants
        return _echec(type_controle, str(exc))


# ---------------------------------------------------------------------------
# Exécution individuelle de chaque contrôle
# ---------------------------------------------------------------------------


def _executer_ordre(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle d'ordre de structure des objets RPD (E0110 / E0010)."""
    erreurs = e0110.AnalyseurGML(chemin_gml, profil).analyser()
    chemin = e0110.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_ORDRE).type_controle, erreurs, chemin)


def _executer_metier(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle des règles métier conditionnelles (E0111 / E0011)."""
    erreurs = e0111.AnalyseurGML(chemin_gml, profil).analyser()
    chemin = e0111.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_METIER).type_controle, erreurs, chemin)


def _executer_xsd_natif(
    chemin_gml: Path,
    sortie: Path | None,
    chemin_xsd: Path,
    cache_dir: Path | None,
    offline: bool,
    profil: ProfilVersion,
) -> dict[str, Any]:
    """Exécute le contrôle de validation XSD native via lxml (E0112 / E0012)."""
    validateur = e0112.ValidateurXsd(chemin_xsd, cache_dir=cache_dir, mode_offline=offline)
    erreurs = validateur.valider(chemin_gml)
    chemin = e0112.generer_rapport(chemin_gml, chemin_xsd, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_XSD_NATIF).type_controle, erreurs, chemin)


def _executer_entete(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle d'en-tête, namespaces et métadonnées (E0113 / E0013)."""
    erreurs = e0113.AnalyseurEntete(chemin_gml, profil).analyser()
    chemin = e0113.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_ENTETE).type_controle, erreurs, chemin)


def _executer_valeurs(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle des valeurs des champs (E0114 / E0014)."""
    erreurs = e0114.AnalyseurValeurs(chemin_gml, profil).analyser()
    chemin = e0114.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_VALEURS).type_controle, erreurs, chemin)


def _executer_geometrie(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle de validité des géométries (E0115 / E0015)."""
    erreurs = e0115.AnalyseurGeometries(chemin_gml, profil).analyser()
    chemin = e0115.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_GEOMETRIE).type_controle, erreurs, chemin)


def _executer_jointures(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Execute le controle des doublons de table de jointure."""
    erreurs = e0116.AnalyseurJointures(chemin_gml, profil).analyser()
    chemin = e0116.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_JOINTURES).type_controle, erreurs, chemin)


def _executer_champs_jointure(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Execute le controle des champs manquants de table de jointure."""
    erreurs = e0117.AnalyseurChampsJointure(chemin_gml, profil).analyser()
    chemin = e0117.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_JOINTURES_CHAMPS).type_controle, erreurs, chemin)


def _executer_document(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Execute le controle d'exploitabilite du document (E0118 / E0018)."""
    erreurs = e0118.AnalyseurDocument(chemin_gml, profil).analyser()
    chemin = e0118.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_DOCUMENT).type_controle, erreurs, chemin)


def _executer_srs_dimension(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Execute le controle de l'attribut srsDimension (E0119 / E0019)."""
    erreurs = e0119.AnalyseurSrsDimension(chemin_gml, profil).analyser()
    chemin = e0119.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_SRS_DIMENSION).type_controle, erreurs, chemin)


def _executer_statut_en_service(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Execute le controle de presence d'ouvrages en service (E0120 / E0020)."""
    erreurs = e0120.AnalyseurStatutEnService(chemin_gml, profil).analyser()
    chemin = e0120.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_STATUT_EN_SERVICE).type_controle, erreurs, chemin)


def _construire_controles(
    chemin_gml: Path,
    sortie: Path | None,
    xsd: Path,
    cache_dir: Path | None,
    offline: bool,
    profil: ProfilVersion,
) -> dict[str, dict[str, Any]]:
    """Exécute les contrôles de la famille et les indexe sous le code de la version.

    Les clés du rapport global suivent la version contrôlée : E0110 à E0120 en
    V1.1, E0010 à E0020 en V1.0.
    """
    # Actions indexées par rang : l'ordre du tuple est l'ordre d'exécution.
    actions: tuple[Callable[[], dict[str, Any]], ...] = (
        lambda: _executer_ordre(chemin_gml, sortie, profil),
        lambda: _executer_metier(chemin_gml, sortie, profil),
        lambda: _executer_xsd_natif(chemin_gml, sortie, xsd, cache_dir, offline, profil),
        lambda: _executer_entete(chemin_gml, sortie, profil),
        lambda: _executer_valeurs(chemin_gml, sortie, profil),
        lambda: _executer_geometrie(chemin_gml, sortie, profil),
        lambda: _executer_jointures(chemin_gml, sortie, profil),
        lambda: _executer_champs_jointure(chemin_gml, sortie, profil),
        lambda: _executer_document(chemin_gml, sortie, profil),
        lambda: _executer_srs_dimension(chemin_gml, sortie, profil),
        lambda: _executer_statut_en_service(chemin_gml, sortie, profil),
    )

    resultats: dict[str, dict[str, Any]] = {}
    for rang in range(NB_CONTROLES):
        identite = identite_controle(profil.code, rang)
        resultats[identite.code] = _proteger(identite.type_controle, actions[rang])
    return resultats


# ---------------------------------------------------------------------------
# Orchestration du pipeline
# ---------------------------------------------------------------------------


def _synthese_par_controle(controles: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Resume chaque controle pour l'en-tete du fichier de famille.

    La cle `rapport` est retiree : elle designait le fichier par controle, que
    l'agregation supprime. La laisser pointerait vers un fichier absent.
    """
    return {
        code: {champ: valeur for champ, valeur in resume.items() if champ != "rapport"}
        for code, resume in controles.items()
    }


def executer_pipeline(
    chemin_gml: Path,
    sortie: Path | None = None,
    chemin_xsd: Path | None = None,
    cache_dir: Path | None = None,
    offline: bool = False,
    profil: ProfilVersion | None = None,
) -> dict[str, Any]:
    """Exécute l'ensemble des contrôles de structuration XSD sur un fichier GML.

    Chaque contrôle est exécuté indépendamment ; un échec n'empêche pas
    l'exécution des suivants. Les résumés sont centralisés avec le nombre
    total d'erreurs bloquantes et la conformité globale.

    Le `profil` de version est résolu une seule fois en amont puis propagé à
    tous les contrôles, garantissant une version homogène. S'il n'est pas
    fourni, la version est **détectée depuis le fichier GML** (repli sur la
    version par défaut si l'en-tête est absent ou illisible), afin que les
    appels programmatiques — dont le pipeline global — contrôlent chaque
    fichier dans sa propre version. Les clés du dictionnaire `controles` sont
    les codes de cette version : E0110 à E0114 en V1.1, E0010 à E0014 en V1.0.
    """
    chemin_gml = chemin_gml.resolve()
    if not chemin_gml.is_file():
        return {"succes": False, "erreur": f"Fichier introuvable : {chemin_gml}"}

    if sortie is not None:
        sortie = sortie.resolve()
        os.makedirs(sortie, exist_ok=True)

    profil_actif = profil if profil is not None else resoudre_profil_cli(chemin_gml, JETON_AUTO)
    # XSD explicite prioritaire ; sinon XSD officiel de la version active.
    xsd = chemin_xsd if chemin_xsd is not None else profil_actif.chemin_xsd

    controles = _construire_controles(chemin_gml, sortie, xsd, cache_dir, offline, profil_actif)

    reussis = [r for r in controles.values() if r.get("succes")]
    nb_erreurs_total = sum(r.get("nb_erreurs", 0) for r in reussis)
    # La conformité globale ne retient que les erreurs bloquantes : une anomalie
    # majeure ou mineure est comptée et listée, mais ne déclasse pas le fichier
    # (même règle qu'au niveau famille, cf. synthese_controles).
    nb_erreurs_bloquantes = sum(r.get("nb_erreurs_bloquantes", 0) for r in reussis)
    controles_en_echec = [code for code, r in controles.items() if not r.get("succes")]
    conforme = nb_erreurs_bloquantes == 0 and not controles_en_echec

    rapport: dict[str, Any] = {
        "succes": True,
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "version_controlee": profil_actif.code,
        "controles": controles,
        "nb_erreurs_total": nb_erreurs_total,
        "nb_erreurs_bloquantes": nb_erreurs_bloquantes,
        "controles_en_echec": controles_en_echec,
        "conformite_globale": CONFORME if conforme else NON_CONFORME,
    }
    # Les rapports des six controles sont refondus en un fichier unique, aux
    # champs communs a toutes les familles : c'est la sortie que lisent les
    # trois modes d'execution. La synthese par controle y est reportee en
    # en-tete, ce qui rend le rapport global separe sans objet.
    agregation = agreger_rapports_structuration(
        (resultat.get("rapport") for resultat in controles.values()),
        str(chemin_gml),
        str(sortie) if sortie is not None else str(chemin_gml.parent),
        entete={
            "date_controle": rapport["date_controle"],
            "version_controlee": rapport["version_controlee"],
            "controles": _synthese_par_controle(controles),
            "controles_en_echec": controles_en_echec,
            "conformite_globale": rapport["conformite_globale"],
        },
    )
    rapport["anomalies_famille"] = agregation
    rapport["rapport_famille"] = agregation["sortie"]
    return rapport


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------


def _construire_parseur() -> argparse.ArgumentParser:
    """Construit et retourne le parseur d'arguments CLI."""
    parseur = argparse.ArgumentParser(
        description=(
            "Pipeline de contrôle de structuration XSD : exécute les cinq "
            "contrôles de structuration sur un fichier GML RecoStaR et agrège "
            "leurs rapports (E0110 à E0114 en V1.1, E0010 à E0014 en V1.0)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parseur.add_argument(
        "fichier_gml",
        type=Path,
        help="Fichier GML RecoStaR à contrôler",
    )
    parseur.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help=("Répertoire de sortie pour les rapports JSON (par défaut : même répertoire que le fichier GML)"),
    )
    parseur.add_argument(
        "--xsd",
        type=Path,
        default=None,
        metavar="CHEMIN_XSD",
        help=("Chemin du XSD utilisé par E0112 (par défaut : XSD officiel de la version contrôlée, voir --version)."),
    )
    ajouter_argument_version(parseur)
    parseur.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help="Répertoire des XSD externes en cache local (utilisé par E0112).",
    )
    parseur.add_argument(
        "--offline",
        action="store_true",
        help="Désactive l'accès réseau lors de la compilation du XSD (E0112).",
    )
    return parseur


def _valider_arguments(args: argparse.Namespace) -> None:
    """Vérifie la validité des arguments CLI. Termine le programme si invalides."""
    args.fichier_gml = args.fichier_gml.resolve()
    if not args.fichier_gml.exists() or not args.fichier_gml.is_file():
        print(
            f"Erreur : le fichier '{args.fichier_gml}' n'existe pas.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output_dir is not None:
        args.output_dir = args.output_dir.resolve()
        if not args.output_dir.is_dir():
            print(
                f"Erreur : le répertoire de sortie '{args.output_dir}' n'existe pas.",
                file=sys.stderr,
            )
            sys.exit(1)


def main() -> None:
    """Point d'entrée principal du pipeline de contrôles XSD."""
    parseur = _construire_parseur()
    args = parseur.parse_args()
    _valider_arguments(args)

    profil = resoudre_profil_cli(args.fichier_gml, args.version)
    print(f"Pipeline de controle XSD du fichier : {args.fichier_gml}")
    print(f"Version controlee : {profil.code}")

    resultat = executer_pipeline(
        args.fichier_gml,
        sortie=args.output_dir,
        chemin_xsd=args.xsd,
        cache_dir=args.cache_dir,
        offline=args.offline,
        profil=profil,
    )

    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
