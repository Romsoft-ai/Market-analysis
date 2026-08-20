"""Convertit un ou plusieurs documents Markdown du projet en PDF.

Les PDF sont écrits dans un sous-dossier `pdf/` à côté du Markdown source,
et ne sont pas versionnés (ils se régénèrent).

Usage :
    python scripts/en_pdf.py docs/etape0-diagnostic.md
    python scripts/en_pdf.py docs/plan-v2.md docs/etape0-diagnostic.md
    python scripts/en_pdf.py --tout          # tous les .md de docs/
"""

from __future__ import annotations

import sys

from marketlab.config import PROJECT_ROOT
from marketlab.utils.pdf import PdfError, markdown_vers_pdf


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    if args == ["--tout"]:
        sources = sorted(
            p for p in (PROJECT_ROOT / "docs").rglob("*.md") if "pdf" not in p.parts
        )
        if not sources:
            print("Aucun fichier .md trouvé dans docs/.")
            return 1
    else:
        sources = [PROJECT_ROOT / a if not a.startswith(("/", "\\")) else a for a in args]

    code = 0
    for source in sources:
        try:
            pdf = markdown_vers_pdf(source)
            taille = pdf.stat().st_size / 1024
            print(f"  OK  {source.relative_to(PROJECT_ROOT)}")
            print(f"      -> {pdf.relative_to(PROJECT_ROOT)}  ({taille:.0f} Ko)")
        except PdfError as exc:
            print(f"  ÉCHEC  {source}\n         {exc}")
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
