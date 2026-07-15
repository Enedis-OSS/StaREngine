"""
Modele normalise des resultats de controle.

Les pipelines de famille ne partagent pas le meme format de rapport : les
pipelines GeoJSON (altimetrie, cable, cheminement, projection) exposent
`nombre_anomalies` et une `priorite` scalaire, le pipeline de structuration XSD
expose `nb_erreurs` et une `conformite`, et certains controles multi-regles
(E506) exposent un dictionnaire `priorites` indexe par type d'anomalie.

Ce module convertit ces formats heterogenes en un modele unique, seul connu du
rapport PDF. Les pipelines existants ne sont pas modifies : la normalisation est
une couche d'adaptation en lecture, ce qui garantit l'absence de regression.

Module pur (aucune E/S) : entierement testable sans jeu de donnees.
"""

from dataclasses import dataclass
from typing import Any

# Priorites d'anomalie. Le projet n'en utilise que deux a ce jour (bloquant,
# information) ; l'echelle complete est declaree pour que l'ajout eventuel d'un
# niveau intermediaire soit pris en charge sans modifier le rendu.
PRIORITE_BLOQUANT: str = "bloquant"
PRIORITE_MAJEUR: str = "majeur"
PRIORITE_MINEUR: str = "mineur"
PRIORITE_INFORMATION: str = "information"
PRIORITE_INCONNUE: str = "non_precisee"

# Ordre d'affichage, de la plus grave a la moins grave.
ORDRE_PRIORITES: tuple[str, ...] = (
    PRIORITE_BLOQUANT,
    PRIORITE_MAJEUR,
    PRIORITE_MINEUR,
    PRIORITE_INFORMATION,
    PRIORITE_INCONNUE,
)

# Libelles affiches dans le rapport.
LIBELLES_PRIORITES: dict[str, str] = {
    PRIORITE_BLOQUANT: "Bloquante",
    PRIORITE_MAJEUR: "Majeure",
    PRIORITE_MINEUR: "Mineure",
    PRIORITE_INFORMATION: "Information",
    PRIORITE_INCONNUE: "Non précisée",
}

# Seules les anomalies de ces priorites declassent une famille : une anomalie
# d'information est signalee et comptee, mais reste non bloquante (convention
# documentee par les controles E505 et E506).
PRIORITES_DECLASSANTES: frozenset[str] = frozenset({PRIORITE_BLOQUANT, PRIORITE_MAJEUR, PRIORITE_MINEUR})

STATUT_CONFORME: str = "Conforme"
STATUT_NON_CONFORME: str = "Non conforme"
# Aucune anomalie bloquante, mais un controle au moins n'a pas pu s'executer :
# la conformite n'est ni infirmee ni verifiable. Le cas est courant et legitime
# (E303 sans numero d'affaire, E300 sans _metadata.json, couche source absente) ;
# le confondre avec « Non conforme » signalerait un defaut inexistant, et avec
# « Conforme » affirmerait une verification non faite.
STATUT_INCOMPLET: str = "Incomplet"
STATUT_NON_EXECUTE: str = "Non exécuté"


@dataclass(frozen=True, slots=True)
class ResultatControle:
    """Resultat normalise d'un controle unitaire."""

    code: str  # "E200", "E506"...
    libelle: str
    succes: bool
    nombre_anomalies: int
    anomalies_par_priorite: dict[str, int]
    erreur: str | None = None


@dataclass(frozen=True, slots=True)
class ResultatFamille:
    """Resultat normalise d'une famille de controles.

    `execute` a False signale une famille volontairement ignoree (absence de
    donnee d'entree, par exemple) ; `motif` en porte la raison, affichee telle
    quelle dans le rapport pour qu'aucune famille ne disparaisse silencieusement.
    """

    cle: str
    libelle: str
    controles: tuple[ResultatControle, ...] = ()
    execute: bool = True
    motif: str | None = None

    @property
    def nombre_controles(self) -> int:
        """Nombre de controles executes dans la famille."""
        return len(self.controles)

    @property
    def nombre_anomalies(self) -> int:
        """Nombre total d'anomalies, toutes priorites confondues."""
        return sum(c.nombre_anomalies for c in self.controles)

    @property
    def controles_en_echec(self) -> tuple[str, ...]:
        """Codes des controles n'ayant pas pu s'executer."""
        return tuple(c.code for c in self.controles if not c.succes)

    @property
    def anomalies_par_priorite(self) -> dict[str, int]:
        """Ventilation des anomalies de la famille par priorite."""
        ventilation: dict[str, int] = {}
        for controle in self.controles:
            for priorite, nombre in controle.anomalies_par_priorite.items():
                ventilation[priorite] = ventilation.get(priorite, 0) + nombre
        return ventilation

    @property
    def nombre_anomalies_declassantes(self) -> int:
        """Nombre d'anomalies dont la priorite invalide la conformite."""
        ventilation = self.anomalies_par_priorite
        return sum(ventilation.get(p, 0) for p in PRIORITES_DECLASSANTES)

    @property
    def statut(self) -> str:
        """Statut global de la famille.

        Trois issues, dans cet ordre de priorite :
          - Non conforme : au moins une anomalie declassante. Un defaut avere
            reste avere meme si la verification est par ailleurs incomplete ;
          - Incomplet : aucune anomalie declassante, mais un controle au moins
            n'a pas pu s'executer — la conformite n'est pas verifiable ;
          - Conforme : tous les controles ont abouti sans anomalie declassante.
        """
        if not self.execute:
            return STATUT_NON_EXECUTE
        if self.nombre_anomalies_declassantes > 0:
            return STATUT_NON_CONFORME
        if self.controles_en_echec:
            return STATUT_INCOMPLET
        return STATUT_CONFORME


# ---------------------------------------------------------------------------
# Normalisation des rapports de pipeline
# ---------------------------------------------------------------------------


def nombre_anomalies_rapport(rapport: dict[str, Any]) -> int:
    """Extrait le nombre d'anomalies d'un rapport de controle.

    Accepte les deux conventions du projet : `nombre_anomalies` (pipelines
    GeoJSON) et `nb_erreurs` (pipeline de structuration XSD).
    """
    valeur = rapport.get("nombre_anomalies")
    if valeur is None:
        valeur = rapport.get("nb_erreurs", 0)
    return int(valeur) if isinstance(valeur, (int, float)) else 0


def _ventiler_par_type(priorites: dict[str, Any], anomalies_par_type: dict[str, Any]) -> dict[str, int]:
    """Ventile les anomalies d'un controle multi-priorites (convention E506)."""
    ventilation: dict[str, int] = {}
    for type_anomalie, nombre in anomalies_par_type.items():
        priorite = priorites.get(type_anomalie, PRIORITE_INCONNUE)
        ventilation[priorite] = ventilation.get(priorite, 0) + int(nombre)
    return ventilation


def ventiler_anomalies(
    rapport: dict[str, Any],
    priorite_par_defaut: str | None = None,
) -> dict[str, int]:
    """Ventile les anomalies d'un rapport de controle par priorite.

    Trois conventions sont prises en charge, sans cas particulier code en dur :
      - `priorites` (type -> priorite) + `anomalies_par_type` : controle
        multi-priorites (E506) ;
      - `priorite` scalaire : convention majoritaire (E200 a E507) ;
      - aucune des deux : `priorite_par_defaut` de la famille (le pipeline XSD
        ne porte pas de priorite, ses erreurs sont bloquantes par nature).
    """
    nombre = nombre_anomalies_rapport(rapport)
    if nombre == 0:
        return {}

    priorites = rapport.get("priorites")
    anomalies_par_type = rapport.get("anomalies_par_type")
    if isinstance(priorites, dict) and isinstance(anomalies_par_type, dict):
        return _ventiler_par_type(priorites, anomalies_par_type)

    priorite = rapport.get("priorite") or priorite_par_defaut or PRIORITE_INCONNUE
    return {str(priorite): nombre}


def normaliser_controle(
    code: str,
    libelle: str,
    rapport: dict[str, Any],
    priorite_par_defaut: str | None = None,
) -> ResultatControle:
    """Convertit le rapport d'un controle en ResultatControle normalise.

    Un controle en echec ne porte aucune anomalie exploitable : seul son motif
    d'erreur est conserve.
    """
    succes = bool(rapport.get("succes"))
    if not succes:
        return ResultatControle(
            code=code,
            libelle=libelle,
            succes=False,
            nombre_anomalies=0,
            anomalies_par_priorite={},
            erreur=str(rapport.get("erreur", "Echec non precise")),
        )
    return ResultatControle(
        code=code,
        libelle=libelle,
        succes=True,
        nombre_anomalies=nombre_anomalies_rapport(rapport),
        anomalies_par_priorite=ventiler_anomalies(rapport, priorite_par_defaut),
    )


# ---------------------------------------------------------------------------
# Agregation globale
# ---------------------------------------------------------------------------


def priorites_presentes(familles: tuple[ResultatFamille, ...]) -> tuple[str, ...]:
    """Retourne les priorites effectivement rencontrees, dans l'ordre de gravite.

    Le rapport n'affiche que les colonnes de priorite reellement alimentees :
    afficher des colonnes toujours vides nuirait a la lisibilite.
    """
    presentes: set[str] = set()
    for famille in familles:
        presentes.update(famille.anomalies_par_priorite)
    return tuple(p for p in ORDRE_PRIORITES if p in presentes)


def _statut_global(non_conformes: tuple[str, ...], incompletes: tuple[str, ...]) -> str:
    """Determine le statut global a partir des statuts de famille.

    Meme hierarchie qu'au niveau d'une famille : un defaut avere prime sur une
    verification incomplete.
    """
    if non_conformes:
        return STATUT_NON_CONFORME
    return STATUT_INCOMPLET if incompletes else STATUT_CONFORME


def agreger(familles: tuple[ResultatFamille, ...]) -> dict[str, Any]:
    """Agrege les familles en une synthese globale serialisable en JSON."""
    executees = tuple(f for f in familles if f.execute)
    ventilation: dict[str, int] = {}
    for famille in executees:
        for priorite, nombre in famille.anomalies_par_priorite.items():
            ventilation[priorite] = ventilation.get(priorite, 0) + nombre

    non_conformes = tuple(f.cle for f in executees if f.statut == STATUT_NON_CONFORME)
    incompletes = tuple(f.cle for f in executees if f.statut == STATUT_INCOMPLET)
    return {
        "statut_global": _statut_global(non_conformes, incompletes),
        "familles_non_conformes": non_conformes,
        "familles_incompletes": incompletes,
        "nombre_familles_executees": len(executees),
        "nombre_controles_executes": sum(f.nombre_controles for f in executees),
        "nombre_controles_en_echec": sum(len(f.controles_en_echec) for f in executees),
        "nombre_anomalies_total": sum(f.nombre_anomalies for f in executees),
        "anomalies_par_priorite": ventilation,
    }
