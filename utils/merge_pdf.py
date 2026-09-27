r"""
merge_pdf.py — Utilidad para unir múltiples documentos PDF en un único archivo.

Uso:
    uv run python .\utils\merge_pdf.py doc1.pdf doc2.pdf -o compilado.pdf
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from pypdf import PdfWriter
except ImportError:
    try:
        from PyPDF2 import PdfWriter
    except ImportError:
        PdfWriter = None


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> bool:
    """Une los PDFs usando PdfWriter de pypdf / PyPDF2."""
    if PdfWriter is None:
        return False
    try:
        writer = PdfWriter()
        for p in pdf_paths:
            writer.append(str(p))
        with open(output_path, "wb") as f_out:
            writer.write(f_out)
        writer.close()
        return output_path.exists() and output_path.stat().st_size > 0
    except Exception as e:
        print(f"[Error] Falló la unión con PdfWriter: {e}")
        return False


def merge_with_pymupdf(pdf_paths: list[Path], output_path: Path) -> bool:
    """Intenta unir PDFs usando PyMuPDF (fitz)."""
    try:
        import fitz

        doc_final = fitz.open()
        for p in pdf_paths:
            with fitz.open(str(p)) as doc:
                doc_final.insert_pdf(doc)
        doc_final.save(str(output_path))
        doc_final.close()
        return output_path.exists() and output_path.stat().st_size > 0
    except ImportError:
        return False
    except Exception as e:
        print(f"[Aviso] Error con PyMuPDF (fitz): {e}")
        return False


def merge_with_cli_tools(pdf_paths: list[Path], output_path: Path) -> bool:
    """Intenta unir PDFs usando herramientas CLI en PATH (pdfunite, pdftk, qpdf)."""
    # 1. pdfunite
    if shutil.which("pdfunite"):
        try:
            cmd = ["pdfunite"] + [str(p) for p in pdf_paths] + [str(output_path)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return True
        except Exception:
            pass

    # 2. pdftk
    if shutil.which("pdftk"):
        try:
            cmd = ["pdftk"] + [str(p) for p in pdf_paths] + ["cat", "output", str(output_path)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return True
        except Exception:
            pass

    # 3. qpdf
    if shutil.which("qpdf"):
        try:
            cmd = ["qpdf", "--empty", "--pages"] + [str(p) for p in pdf_paths] + ["--", str(output_path)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return True
        except Exception:
            pass

    return False


def merge_with_uv_pypdf(pdf_paths: list[Path], output_path: Path) -> bool:
    """Ejecuta pypdf al vuelo utilizando 'uv run --with pypdf' si uv está en el sistema."""
    if not shutil.which("uv"):
        return False

    script_inline = """
import sys
from pypdf import PdfMerger

out_file = sys.argv[1]
inputs = sys.argv[2:]

merger = PdfMerger()
for f in inputs:
    merger.append(f)
merger.write(out_file)
merger.close()
"""
    try:
        cmd = [
            "uv",
            "run",
            "--with",
            "pypdf",
            "python",
            "-c",
            script_inline,
            str(output_path),
        ] + [str(p) for p in pdf_paths]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        return res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
    except Exception as e:
        print(f"[Aviso] Error ejecutando uv con pypdf: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Une múltiples archivos PDF en uno solo en el orden especificado."
    )
    parser.add_argument(
        "archivos_pdf",
        nargs="+",
        help="Rutas a los archivos PDF a unir (en orden de aparición)",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output",
        required=True,
        help="Ruta del archivo PDF de salida resultante",
    )
    args = parser.parse_args()

    pdf_paths: list[Path] = []
    for f in args.archivos_pdf:
        p = Path(f).resolve()
        if not p.exists():
            print(f"[Error] El archivo '{p}' no existe.")
            sys.exit(1)
        if p.suffix.lower() != ".pdf":
            print(f"[Error] El archivo '{p}' no es un archivo PDF.")
            sys.exit(1)
        pdf_paths.append(p)

    if len(pdf_paths) < 2:
        print("[Aviso] Se especificó un solo archivo. Creando copia con el nombre de salida...")

    out_file = Path(args.output).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Eliminar salida previa si existe
    if out_file.exists():
        try:
            out_file.unlink()
        except Exception:
            pass

    print(f"-> Uniendo {len(pdf_paths)} archivos PDF:")
    for idx, p in enumerate(pdf_paths, start=1):
        print(f"   {idx}. {p.name}")

    # Secuencia de intentos de unión
    exito = (
        merge_pdfs(pdf_paths, out_file)
        or merge_with_pymupdf(pdf_paths, out_file)
        or merge_with_cli_tools(pdf_paths, out_file)
        or merge_with_uv_pypdf(pdf_paths, out_file)
    )

    if exito:
        print(f"\n¡Éxito! PDF unificado creado en: {out_file}")
    else:
        print("\n[Error] No se encontró ninguna librería ni herramienta para unir PDFs.")
        print("Sugerencia: ejecutá con 'uv run --with pypdf python utils/merge_pdf.py ...'")
        sys.exit(1)


if __name__ == "__main__":
    main()
