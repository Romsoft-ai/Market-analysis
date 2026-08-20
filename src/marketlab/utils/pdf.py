"""Conversion de documents Markdown en PDF lisibles et présentables.

Pourquoi ce module. Les fichiers `.md` sont pratiques à produire et à versionner,
mais pénibles à lire brut et impossibles à présenter. On les convertit donc en PDF
pour tout ce qui doit être lu ou montré : rapports de diagnostic, plan détaillé,
documents pour l'encadrant.

Comment. Aucun outil lourd à installer : le Markdown est rendu en HTML avec une
feuille de style d'impression, puis **Microsoft Edge** (présent d'office sous
Windows) imprime cette page en PDF en ligne de commande.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path

import markdown

# Emplacements habituels d'Edge sous Windows.
_EDGE_CANDIDATS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

_EXTENSIONS = ["tables", "fenced_code", "attr_list", "sane_lists", "toc"]

# msedge.exe est une application graphique Windows : elle rend la main
# immédiatement et écrit le PDF ensuite, en arrière-plan. Il faut donc attendre
# que le fichier apparaisse ET que sa taille se stabilise.
_ATTENTE_MAX_S = 90.0
_PAS_SONDAGE_S = 0.4

# Feuille de style d'impression. Volontairement sobre : ce sont des documents de
# travail et de soutenance, pas des plaquettes.
_CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }

* { box-sizing: border-box; }

body {
  font-family: "Segoe UI", "Calibri", system-ui, sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: #1a1a1a;
  margin: 0;
}

h1 {
  font-size: 20pt;
  color: #14304f;
  border-bottom: 2.5px solid #14304f;
  padding-bottom: 6px;
  margin: 0 0 18px;
}
h2 {
  font-size: 14pt;
  color: #14304f;
  margin: 22px 0 8px;
  padding-bottom: 3px;
  border-bottom: 1px solid #ccd6e0;
  page-break-after: avoid;
}
h3 { font-size: 11.5pt; color: #24486d; margin: 16px 0 6px; page-break-after: avoid; }
h4 { font-size: 10.5pt; color: #24486d; margin: 12px 0 4px; page-break-after: avoid; }

p, ul, ol { margin: 0 0 9px; }
li { margin-bottom: 3px; }

/* Les tableaux ne doivent jamais être coupés entre deux pages. */
table {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0 16px;
  font-size: 9pt;
  page-break-inside: avoid;
}
th {
  background: #14304f;
  color: #fff;
  text-align: left;
  font-weight: 600;
  padding: 6px 8px;
  border: 1px solid #14304f;
}
td { padding: 5px 8px; border: 1px solid #d4dce4; vertical-align: top; }
tbody tr:nth-child(even) { background: #f5f8fa; }

code {
  font-family: "Cascadia Mono", "Consolas", monospace;
  font-size: 8.8pt;
  background: #eef2f6;
  padding: 1px 4px;
  border-radius: 3px;
  color: #0f3d2e;
}
pre {
  background: #f7f9fb;
  border: 1px solid #d4dce4;
  border-left: 3px solid #14304f;
  padding: 9px 11px;
  font-size: 8.5pt;
  line-height: 1.4;
  overflow-x: auto;
  page-break-inside: avoid;
}
pre code { background: none; padding: 0; color: #1a1a1a; }

blockquote {
  margin: 10px 0;
  padding: 7px 13px;
  background: #f5f8fa;
  border-left: 3px solid #7f9db9;
  color: #33475b;
}
blockquote p:last-child { margin-bottom: 0; }

hr { border: none; border-top: 1px solid #d4dce4; margin: 18px 0; }
strong { color: #0d2237; }
a { color: #14304f; text-decoration: none; }
"""

_GABARIT = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>{titre}</title>
<style>{css}</style></head><body>{corps}</body></html>"""


class PdfError(RuntimeError):
    """La conversion en PDF a échoué."""


def _trouver_edge() -> Path:
    for chemin in _EDGE_CANDIDATS:
        if chemin.exists():
            return chemin
    raise PdfError(
        "Microsoft Edge est introuvable. Emplacements testés :\n  "
        + "\n  ".join(str(c) for c in _EDGE_CANDIDATS)
    )


def _titre_depuis_markdown(texte: str, defaut: str) -> str:
    """Utilise le premier titre de niveau 1 comme titre du document."""
    trouve = re.search(r"^#\s+(.+)$", texte, flags=re.MULTILINE)
    return trouve.group(1).strip() if trouve else defaut


def markdown_vers_pdf(source: Path, destination: Path | None = None) -> Path:
    """Convertit un fichier Markdown en PDF et retourne le chemin du PDF.

    Args:
        source: le fichier `.md` à convertir.
        destination: chemin du PDF. Par défaut, même nom dans `docs/pdf/`.
    """
    source = Path(source)
    if not source.exists():
        raise PdfError(f"Fichier introuvable : {source}")

    texte = source.read_text(encoding="utf-8")
    corps = markdown.markdown(texte, extensions=_EXTENSIONS)
    page = _GABARIT.format(
        titre=_titre_depuis_markdown(texte, source.stem), css=_CSS, corps=corps
    )

    if destination is None:
        destination = source.parent / "pdf" / f"{source.stem}.pdf"
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    edge = _trouver_edge()

    # Une version précédente fausserait la détection de fin d'écriture.
    destination.unlink(missing_ok=True)

    # Le dossier temporaire ne doit pas être supprimé avant qu'Edge ait fini de
    # lire le HTML : on attend le PDF À L'INTÉRIEUR du bloc.
    with tempfile.TemporaryDirectory() as travail:
        html = Path(travail) / "document.html"
        html.write_text(page, encoding="utf-8")

        subprocess.run(
            [
                str(edge),
                "--headless",
                "--disable-gpu",
                # Profil jeté après usage : évite tout conflit avec un Edge ouvert.
                f"--user-data-dir={Path(travail) / 'profil'}",
                "--no-first-run",
                "--no-pdf-header-footer",
                # Laisse le rendu se terminer avant l'impression.
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                f"--print-to-pdf={destination}",
                html.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        if not _attendre_fichier(destination):
            raise PdfError(
                f"Edge n'a pas produit de PDF en {_ATTENTE_MAX_S:.0f} s.\n"
                f"  Cible : {destination}"
            )

    return destination


def _attendre_fichier(cible: Path) -> bool:
    """Attend qu'un fichier existe et que sa taille cesse de changer.

    Deux mesures identiques consécutives et non nulles signifient que l'écriture
    est terminée. Retourne False si le délai est dépassé.
    """
    limite = time.monotonic() + _ATTENTE_MAX_S
    taille_precedente = -1
    while time.monotonic() < limite:
        if cible.exists():
            taille = cible.stat().st_size
            if taille > 0 and taille == taille_precedente:
                return True
            taille_precedente = taille
        time.sleep(_PAS_SONDAGE_S)
    return False
