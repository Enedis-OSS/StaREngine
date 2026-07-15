"""
Pipeline globale de controle RecoStaR.

Point d'entree unique executant l'ensemble des pipelines de controle des
sous-repertoires (structuration, projection, altimetrie, cheminement, cable) et
centralisant leurs sorties dans une arborescence unique, accompagnee d'un
rapport PDF de synthese.

Arborescence produite dans le repertoire des donnees controlees :

    controle/
    ├── rapport_controles.pdf
    ├── altimetrie/     (*.geojson, *.json)
    ├── cable/
    ├── cheminement/
    ├── projection/
    └── structuration/

Chaque sous-dossier recoit exactement les fichiers produits par le pipeline
correspondant : les pipelines sont reutilises tels quels, seul leur repertoire
de sortie change. Aucune logique metier n'est dupliquee ni modifiee.

Un echec ou une absence de donnee sur une famille n'interrompt pas les autres :
la famille est reportee comme non executee, avec son motif.

Familles : declarees dans familles_controle.FAMILLES (point d'extension unique).

Usage CLI :
    python pipeline_globale.py --repertoire <chemin> [--sortie <chemin>]
                               [--gml <fichier.gml>] [--numero_affaire <numero>]
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from familles_controle import (
    FAMILLES,
    MODE_GML,
    FamilleControle,
    charger_module_pipeline,
    code_controle,
    libelle_controle,
)
from rapport_pdf import generer_rapport_pdf
from synthese_controles import ResultatControle, ResultatFamille, agreger, normaliser_controle

# Nom du dossier centralisant les sorties, cree dans le repertoire des donnees.
DOSSIER_CONTROLE: str = "controle"

# Nom du rapport PDF de synthese.
FICHIER_RAPPORT_PDF: str = "rapport_controles.pdf"

# Nom du rapport JSON global (pendant machine du PDF).
FICHIER_RAPPORT_JSON: str = "rapport_controles.json"

# Extension des fichiers GML recherches pour la famille de structuration.
EXTENSION_GML: str = "*.gml"


@dataclass(frozen=True, slots=True)
class ContexteExecution:
    """Parametres d'execution communs a toutes les familles.

    `chemin_gml` et `numero_affaire` ne concernent qu'une famille chacun
    (structuration et projection) ; les regrouper ici evite de propager des
    signatures differentes par famille dans l'orchestrateur.
    """

    repertoire: Path
    dossier_controle: Path
    chemin_gml: Path | None = None
    numero_affaire: str | None = None


# ---------------------------------------------------------------------------
# Resolution du fichier GML (famille structuration)
# ---------------------------------------------------------------------------


def resoudre_chemin_gml(repertoire: Path, chemin_gml: Path | None) -> tuple[Path | None, str | None]:
    """Determine le GML a controler. Retourne (chemin, motif_si_absent).

    Un chemin explicite est prioritaire. A defaut, la detection automatique
    n'aboutit que si le repertoire contient exactement un GML : plusieurs
    candidats rendraient le choix arbitraire, la famille est alors ignoree avec
    un motif explicite plutot que de controler un fichier au hasard.
    """
    if chemin_gml is not None:
        chemin = chemin_gml.resolve()
        if not chemin.is_file():
            return None, f"Fichier GML introuvable : {chemin}"
        return chemin, None

    candidats = sorted(repertoire.glob(EXTENSION_GML))
    if not candidats:
        return None, "Aucun fichier GML dans le repertoire"
    if len(candidats) > 1:
        noms = ", ".join(c.name for c in candidats)
        return None, f"{len(candidats)} fichiers GML trouves ({noms}) : precisez --gml"
    return candidats[0], None


# ---------------------------------------------------------------------------
# Execution d'une famille
# ---------------------------------------------------------------------------


def _executer_pipeline_repertoire(
    module: ModuleType,
    contexte: ContexteExecution,
    sortie: Path,
    famille: FamilleControle,
) -> dict[str, Any]:
    """Execute un pipeline recevant un repertoire de GeoJSON.

    Le pipeline de projection accepte un numero d'affaire supplementaire
    (requis par E303) ; il est transmis lorsque la famille le prevoit.
    """
    if famille.cle == "projection":
        return module.executer_pipeline(str(contexte.repertoire), str(sortie), contexte.numero_affaire)
    return module.executer_pipeline(str(contexte.repertoire), str(sortie))


def _executer_pipeline_gml(module: ModuleType, contexte: ContexteExecution, sortie: Path) -> dict[str, Any]:
    """Execute le pipeline de structuration sur le fichier GML resolu."""
    return module.executer_pipeline(contexte.chemin_gml, sortie)


def _normaliser_controles(
    rapport: dict[str, Any],
    priorite_par_defaut: str | None,
) -> tuple[ResultatControle, ...]:
    """Convertit les controles d'un rapport de pipeline en resultats normalises."""
    controles = rapport.get("controles")
    if not isinstance(controles, dict):
        return ()
    return tuple(
        normaliser_controle(code_controle(cle), libelle_controle(cle), rapport_controle, priorite_par_defaut)
        for cle, rapport_controle in controles.items()
    )


def executer_famille(famille: FamilleControle, contexte: ContexteExecution) -> ResultatFamille:
    """Execute le pipeline d'une famille et normalise son rapport.

    Toute defaillance (pipeline introuvable, erreur d'execution, donnee d'entree
    absente) est convertie en famille non executee : les autres familles
    s'executent malgre tout, conformement au comportement de chaque pipeline
    vis-a-vis de ses propres controles.
    """
    if famille.mode == MODE_GML and contexte.chemin_gml is None:
        return ResultatFamille(famille.cle, famille.libelle, execute=False, motif="Aucun fichier GML a controler")

    sortie = contexte.dossier_controle / famille.sortie
    os.makedirs(sortie, exist_ok=True)

    try:
        module = charger_module_pipeline(famille.cle)
        if famille.mode == MODE_GML:
            rapport = _executer_pipeline_gml(module, contexte, sortie)
        else:
            rapport = _executer_pipeline_repertoire(module, contexte, sortie, famille)
    except Exception as exc:  # orchestrateur : l'echec d'une famille ne bloque pas les autres
        return ResultatFamille(famille.cle, famille.libelle, execute=False, motif=f"{type(exc).__name__}: {exc}")

    if not rapport.get("succes"):
        motif = str(rapport.get("erreur", "Echec non precise"))
        return ResultatFamille(famille.cle, famille.libelle, execute=False, motif=motif)

    return ResultatFamille(
        cle=famille.cle,
        libelle=famille.libelle,
        controles=_normaliser_controles(rapport, famille.priorite_par_defaut),
    )


# ---------------------------------------------------------------------------
# Orchestration globale
# ---------------------------------------------------------------------------


def _serialiser_famille(famille: ResultatFamille) -> dict[str, Any]:
    """Convertit une famille normalisee en structure serialisable en JSON."""
    return {
        "libelle": famille.libelle,
        "statut": famille.statut,
        "execute": famille.execute,
        "motif": famille.motif,
        "nombre_controles": famille.nombre_controles,
        "nombre_anomalies": famille.nombre_anomalies,
        "anomalies_par_priorite": famille.anomalies_par_priorite,
        "controles_en_echec": list(famille.controles_en_echec),
        "controles": [
            {
                "code": c.code,
                "libelle": c.libelle,
                "succes": c.succes,
                "nombre_anomalies": c.nombre_anomalies,
                "anomalies_par_priorite": c.anomalies_par_priorite,
                "erreur": c.erreur,
            }
            for c in famille.controles
        ],
    }


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
    chemin_gml: str | None = None,
    numero_affaire: str | None = None,
) -> dict[str, Any]:
    """Execute toutes les familles de controle et produit l'arborescence de sortie.

    `sortie` designe le repertoire dans lequel creer le dossier controle/ ; par
    defaut, le repertoire des donnees controlees.
    """
    repertoire_resolu = Path(repertoire).resolve()
    if not repertoire_resolu.is_dir():
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire_resolu}"}

    racine_sortie = Path(sortie).resolve() if sortie is not None else repertoire_resolu
    dossier_controle = racine_sortie / DOSSIER_CONTROLE
    os.makedirs(dossier_controle, exist_ok=True)

    gml_resolu, motif_gml = resoudre_chemin_gml(
        repertoire_resolu,
        Path(chemin_gml) if chemin_gml is not None else None,
    )
    contexte = ContexteExecution(
        repertoire=repertoire_resolu,
        dossier_controle=dossier_controle,
        chemin_gml=gml_resolu,
        numero_affaire=numero_affaire,
    )

    resultats: list[ResultatFamille] = []
    for famille in FAMILLES:
        if famille.mode == MODE_GML and gml_resolu is None:
            resultats.append(ResultatFamille(famille.cle, famille.libelle, execute=False, motif=motif_gml))
            continue
        resultats.append(executer_famille(famille, contexte))

    familles = tuple(resultats)
    synthese = agreger(familles)

    chemin_pdf = dossier_controle / FICHIER_RAPPORT_PDF
    generer_rapport_pdf(familles, synthese, chemin_pdf, repertoire_resolu)

    rapport: dict[str, Any] = {
        "succes": True,
        "repertoire": str(repertoire_resolu),
        "dossier_controle": str(dossier_controle),
        **synthese,
        "familles": {f.cle: _serialiser_famille(f) for f in familles},
        "rapport_pdf": str(chemin_pdf),
    }
    # tuple -> list : json.dump serialise les deux, mais le rapport relu doit
    # exposer des listes homogenes.
    rapport["familles_non_conformes"] = list(synthese["familles_non_conformes"])
    rapport["familles_incompletes"] = list(synthese["familles_incompletes"])

    chemin_json = dossier_controle / FICHIER_RAPPORT_JSON
    with open(chemin_json, "w", encoding="utf-8") as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)
    rapport["rapport_json"] = str(chemin_json)
    return rapport


def main() -> None:
    """Point d'entree CLI de la pipeline globale de controle."""
    parseur = argparse.ArgumentParser(
        description=(
            "Pipeline globale de controle RecoStaR : execute toutes les familles "
            "de controle, centralise leurs sorties dans un dossier controle/ et "
            "produit un rapport PDF de synthese."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les donnees a controler",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire dans lequel creer le dossier controle/ (defaut : repertoire d'entree)",
    )
    parseur.add_argument(
        "--gml",
        default=None,
        help=(
            "Fichier GML pour les controles de structuration (defaut : detection "
            "automatique si le repertoire n'en contient qu'un seul)"
        ),
    )
    parseur.add_argument(
        "--numero_affaire",
        default=None,
        help="Numero d'affaire pour le controle d'emprise DR (E303)",
    )
    arguments = parseur.parse_args()
    resultat = executer_pipeline(
        arguments.repertoire,
        arguments.sortie,
        arguments.gml,
        arguments.numero_affaire,
    )
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
