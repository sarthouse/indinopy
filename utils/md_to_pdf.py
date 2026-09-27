#!/usr/bin/env python3
"""
Convertidor integral de Markdown a PDF con soporte para:
- Portadas y metadatos frontmatter YAML.
- Renderizado de diagramas Mermaid a través de Kroki API en SVG/PNG incrustado en base64.
- Fórmulas LaTeX (inline $...$ y bloque $$...$$) renderizadas e incrustadas.
- Listas estructuradas: numéricas, con viñetas, incisos alfabéticos a), b) y subincisos anidados.
- Tablas GitHub Flavored Markdown con estilo ejecutivo.
- Motor de exportación PDF dual: Playwright/Chromium o WeasyPrint, con fallback a HTML autónomo.
"""

import os
import re
import sys
import zlib
import base64
import argparse
import urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    print("Falta instalar 'requests'. Ejecuta: pip install requests")
    requests = None


def get_mermaid_svg_or_png_b64(mermaid_code: str) -> str:
    """Renderiza diagrama Mermaid vía API de Kroki o mermaid.ink devolviendo base64 Data URL."""
    try:
        compressed = zlib.compress(mermaid_code.strip().encode("utf-8"), 9)
        payload = base64.urlsafe_b64encode(compressed).decode("utf-8")
        url = f"https://kroki.io/mermaid/svg/{payload}"
        resp = requests.get(url, timeout=12)
        if resp.status_code == 200:
            b64_data = base64.b64encode(resp.content).decode("utf-8")
            return f"data:image/svg+xml;base64,{b64_data}"
    except Exception:
        pass

    # Fallback 1: mermaid.ink (rápido y con soporte SVG directo)
    try:
        raw_b64 = base64.b64encode(mermaid_code.strip().encode("utf-8")).decode("utf-8")
        url_ink = f"https://mermaid.ink/svg/{raw_b64}"
        resp_ink = requests.get(url_ink, timeout=12)
        if resp_ink.status_code == 200:
            b64_data = base64.b64encode(resp_ink.content).decode("utf-8")
            return f"data:image/svg+xml;base64,{b64_data}"
    except Exception:
        pass

    return ""


def get_latex_image_b64(latex_code: str) -> str:
    """Renderiza fórmula LaTeX vía CodeCogs devolviendo base64 Data URL."""
    try:
        encoded = urllib.parse.quote(latex_code.strip())
        url = f"https://latex.codecogs.com/png.image?\\dpi{{300}}\\bg{{white}} {encoded}"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            b64_data = base64.b64encode(resp.content).decode("utf-8")
            return f"data:image/png;base64,{b64_data}"
    except Exception as e:
        print(f"[Aviso] No se pudo renderizar fórmula LaTeX: {e}")
    return ""


def parse_frontmatter(md_content: str):
    """Extrae metadatos del frontmatter YAML si existen."""
    lines = md_content.splitlines()
    metadata = {
        "title": "Documento",
        "subtitle": "",
        "author": "",
        "date": "",
        "status": "",
    }
    body_lines = lines

    if lines and lines[0].strip().lstrip("\ufeff") == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_lines = lines[i + 1 :]
                break
            m = re.match(r"^([a-zA-Z_-]+):\s*(.*)", lines[i].strip())
            if m:
                key = m.group(1).lower()
                val = m.group(2).strip().strip('"').strip("'")
                metadata[key] = val

    # Si no había título en frontmatter, buscar el primer H1
    if metadata["title"] == "Documento":
        for line in body_lines:
            m = re.match(r"^#\s+(.*)", line.strip())
            if m:
                metadata["title"] = m.group(1).replace("**", "")
                break

    return metadata, "\n".join(body_lines)


def format_inline_elements(text: str) -> str:
    """Formatea negritas, cursivas, código inline, enlaces, notas y fórmulas LaTeX."""
    # Proteger y renderizar fórmulas LaTeX inline $$...$$ o $...$
    def replace_latex_block(match):
        code = match.group(1)
        b64 = get_latex_image_b64(code)
        if b64:
            return f'<div class="math-block"><img class="math-inline" src="{b64}" alt="{code}" /></div>'
        return f"<code>$${code}$$</code>"

    text = re.sub(r"\$\$(.+?)\$\$", replace_latex_block, text)

    def replace_latex_inline(match):
        code = match.group(1).strip()
        # Variables con subíndices de costo como c_{\text{MOD}}, c_{\text{BOM}}, c_{\text{FDI}} o c_MOD
        simple_sub = re.match(r"^([a-zA-Z])(?:_\{?\\text\{([^\}]+)\}\}?|_([a-zA-Z0-9]+))$", code)
        if simple_sub:
            var_name = simple_sub.group(1)
            sub_text = simple_sub.group(2) if simple_sub.group(2) else simple_sub.group(3)
            return f'<span class="math-sub"><em>{var_name}</em><sub>{sub_text}</sub></span>'

        b64 = get_latex_image_b64(code)
        if b64:
            return f'<img class="math-inline" src="{b64}" alt="{code}" />'
        return f"<em>{code}</em>"

    text = re.sub(r"(?<!\\)\$(?!\s)([^\$\n]+?)(?<!\s)(?<!\\)\$", replace_latex_inline, text)

    # Código inline: `codigo`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Negrita + Cursiva: ***texto*** o ___texto___
    text = re.sub(r"\*\*\*([^\*]+)\*\*\*", r"<strong><em>\1</em></strong>", text)

    # Negrita: **texto**
    text = re.sub(r"\*\*([^\*]+)\*\*", r"<strong>\1</strong>", text)

    # Cursiva: *texto*
    text = re.sub(r"\*([^\*]+)\*", r"<em>\1</em>", text)

    # Enlaces: [texto](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Notas al pie inline: [^1]
    text = re.sub(r"\[\^(\d+)\]", r'<sup><a href="#fn-\1" id="fnref-\1">[\1]</a></sup>', text)

    return text


def markdown_to_html(md_text: str) -> str:
    """Convierte el cuerpo del Markdown a HTML estructurado con soporte de listas complejas."""
    lines = md_text.splitlines()
    html_parts = []

    in_mermaid = False
    mermaid_code = []

    in_table = False
    table_lines = []

    in_list = False
    list_type = None  # 'ul', 'ol'
    first_h1_found = False

    def close_current_list():
        nonlocal in_list, list_type
        if in_list:
            html_parts.append(f"</{list_type}>")
            in_list = False
            list_type = None

    def render_table_block(tbl_lines):
        nonlocal html_parts
        data_rows = [l for l in tbl_lines if not re.match(r"^[\s\|\-\:]+$", l)]
        if not data_rows:
            return
        html_parts.append("<table>")
        for idx, row_line in enumerate(data_rows):
            cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
            tag = "th" if idx == 0 else "td"
            html_parts.append("  <tr>")
            for cell in cells:
                html_parts.append(f"    <{tag}>{format_inline_elements(cell)}</{tag}>")
            html_parts.append("  </tr>")
        html_parts.append("</table>")

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        raw = line.strip()
        leading_spaces = len(line) - len(line.lstrip(" "))
        leading_level = leading_spaces // 2 if "\t" not in line else len(line) - len(line.lstrip("\t"))

        # Bloques de Diagramas Mermaid
        if raw.startswith("```mermaid"):
            close_current_list()
            in_mermaid = True
            mermaid_code = []
            idx += 1
            continue
        elif in_mermaid and raw.startswith("```"):
            in_mermaid = False
            mermaid_text = "\n".join(mermaid_code)
            b64_img = get_mermaid_svg_or_png_b64(mermaid_text)
            if b64_img:
                html_parts.append(
                    f'<div class="figure-container"><img src="{b64_img}" alt="Diagrama Mermaid" /></div>'
                )
            else:
                # Si las APIs externas fallan, inyectar el div para que Playwright lo renderice localmente con mermaid.js
                html_parts.append(
                    f'<div class="figure-container"><div class="mermaid">{mermaid_text}</div></div>'
                )
            idx += 1
            continue

        if in_mermaid:
            mermaid_code.append(line)
            idx += 1
            continue

        # Tablas Markdown
        is_table_row = raw.startswith("|") and raw.endswith("|")
        if in_table and not is_table_row:
            render_table_block(table_lines)
            in_table = False
            table_lines = []

        if is_table_row:
            close_current_list()
            in_table = True
            table_lines.append(raw)
            idx += 1
            continue

        # Líneas vacías
        if not raw:
            close_current_list()
            idx += 1
            continue

        # Encabezados
        h_match = re.match(r"^(#{1,6})\s+(.*)", raw)
        if h_match:
            close_current_list()
            level = len(h_match.group(1))
            h_text = format_inline_elements(h_match.group(2))
            slug = re.sub(r"[^\w\- ]", "", h_match.group(2).lower()).strip().replace(" ", "-")
            if level == 1 and not first_h1_found:
                first_h1_found = True
                html_parts.append(f'<h1 id="{slug}" class="first-title">{h_text}</h1>')
            else:
                html_parts.append(f'<h{level} id="{slug}">{h_text}</h{level}>')
            idx += 1
            continue

        # Regla horizontal
        if re.match(r"^(---|\*\*\*|___)\s*$", raw):
            close_current_list()
            html_parts.append("<hr />")
            idx += 1
            continue

        # Bloque de citas (agrupa líneas consecutivas con > en un único blockquote)
        if raw.startswith(">"):
            close_current_list()
            quote_paras = []
            while idx < len(lines) and lines[idx].strip().startswith(">"):
                q_line = lines[idx].strip()[1:].strip()
                if q_line:
                    quote_paras.append(f"<p>{format_inline_elements(q_line)}</p>")
                idx += 1
            if quote_paras:
                html_parts.append(f"<blockquote>{''.join(quote_paras)}</blockquote>")
            continue

        # Notas al pie: [^1]: texto
        fn_match = re.match(r"^\[\^(\d+)\]:\s*(.*)", raw)
        if fn_match:
            close_current_list()
            fn_id = fn_match.group(1)
            fn_text = format_inline_elements(fn_match.group(2))
            html_parts.append(
                f'<div class="footnote" id="fn-{fn_id}"><p><sup>[{fn_id}]</sup> {fn_text} <a href="#fnref-{fn_id}">↩</a></p></div>'
            )
            idx += 1
            continue

        # Listas de Viñetas (* o -)
        if raw.startswith("* ") or raw.startswith("- "):
            # Subincisos dentro de viñetas: - a) texto o * 1) texto
            bullet_sub = re.match(r"^(\*|-)\s+([a-zA-Z]|\d+)[\.\)]\s+(.*)", raw)
            if bullet_sub:
                close_current_list()
                marker = bullet_sub.group(2)
                txt = format_inline_elements(bullet_sub.group(3))
                # Nivel de indentación basado en espacios iniciales
                lvl_class = f"indent-lvl-{min(leading_level + 1, 3)}"
                html_parts.append(
                    f'<div class="inciso-item {lvl_class}"><span class="inciso-label">{marker})</span><span class="inciso-content">{txt}</span></div>'
                )
                idx += 1
                continue

            if not in_list or list_type != "ul":
                close_current_list()
                lvl_class = f"indent-lvl-{min(leading_level, 3)}"
                html_parts.append(f'<ul class="{lvl_class}">')
                in_list = True
                list_type = "ul"
            html_parts.append(f"  <li>{format_inline_elements(raw[2:])}</li>")
            idx += 1
            continue

        # Listas Numeradas (1. 2. 3.)
        num_match = re.match(r"^(\d+)\.\s+(.*)", raw)
        if num_match:
            item_num = num_match.group(1)
            txt = format_inline_elements(num_match.group(2))
            if not in_list or list_type != "ol":
                close_current_list()
                lvl_class = f"indent-lvl-{min(leading_level, 3)}"
                html_parts.append(f'<ol class="{lvl_class}" start="{item_num}">')
                in_list = True
                list_type = "ol"
            html_parts.append(f"  <li>{txt}</li>")
            idx += 1
            continue

        # Listas de Incisos con letras: a) / b) / (a) / a.
        inciso_match = re.match(r"^(\(?([a-zA-Z])[\.\)])\s+(.*)", raw)
        if inciso_match:
            close_current_list()
            marker = inciso_match.group(1)
            txt = format_inline_elements(inciso_match.group(3))
            # Si tiene espacios o tabulaciones al inicio, aplicar nivel de sangría proporcional
            lvl_class = f"indent-lvl-{min(leading_level, 3)}"
            html_parts.append(
                f'<div class="inciso-item {lvl_class}"><span class="inciso-label">{marker}</span><span class="inciso-content">{txt}</span></div>'
            )
            idx += 1
            continue

        # Párrafo ordinario
        close_current_list()
        html_parts.append(f"<p>{format_inline_elements(raw)}</p>")
        idx += 1

    if in_table:
        render_table_block(table_lines)
    close_current_list()

    return "\n".join(html_parts)


def generate_html_document(md_path: str, template_path: str) -> tuple[dict, str]:
    """Genera el HTML completo inyectando el Markdown parseado en la plantilla."""
    with open(md_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    meta, clean_md = parse_frontmatter(content)
    body_html = markdown_to_html(clean_md)

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # Reemplazo de variables en plantilla
    doc_html = template
    doc_html = doc_html.replace("{{ title }}", meta.get("title", ""))
    doc_html = doc_html.replace("{{ subtitle }}", meta.get("subtitle", ""))
    doc_html = doc_html.replace("{{ author }}", meta.get("author", ""))
    doc_html = doc_html.replace("{{ date }}", meta.get("date", ""))
    doc_html = doc_html.replace("{{ status }}", meta.get("status", ""))
    doc_html = doc_html.replace("{{ content }}", body_html)
    doc_html = doc_html.replace("{% if show_header %}", "")
    doc_html = doc_html.replace("{% endif %}", "")
    doc_html = doc_html.replace("{% if status %}", "")
    doc_html = doc_html.replace("{% if subtitle %}", "")
    doc_html = doc_html.replace("{% if author %}", "")
    doc_html = doc_html.replace("{% if date %}", "")

    return meta, doc_html


def convert_to_pdf_weasyprint(html_file: str, pdf_file: str) -> bool:
    """Convierte el HTML a PDF usando WeasyPrint (módulo python o CLI uv/weasyprint)."""
    import subprocess
    import shutil

    # 1. Intentar importar WeasyPrint directamente en el intérprete
    try:
        from weasyprint import HTML

        HTML(filename=html_file).write_pdf(pdf_file)
        if os.path.exists(pdf_file) and os.path.getsize(pdf_file) > 0:
            return True
    except ImportError:
        pass
    except Exception as e:
        print(f"[Aviso] Excepción en módulo Python weasyprint: {e}")

    # 2. Intentar ejecutar a través de 'uv run weasyprint'
    if shutil.which("uv"):
        try:
            cmd = ["uv", "run", "weasyprint", str(html_file), str(pdf_file)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            if os.path.exists(pdf_file) and os.path.getsize(pdf_file) > 0:
                return True
        except Exception as e:
            print(f"[Aviso] Excepción ejecutando uv run weasyprint: {e}")

    # 3. Intentar binario 'weasyprint' en PATH
    if shutil.which("weasyprint"):
        try:
            cmd = ["weasyprint", str(html_file), str(pdf_file)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            if os.path.exists(pdf_file) and os.path.getsize(pdf_file) > 0:
                return True
        except Exception as e:
            print(f"[Aviso] Excepción ejecutando weasyprint: {e}")

    return False


def find_system_browser() -> str:
    """Busca el ejecutable de Chrome o Edge instalado en Windows para imprimir directo a PDF."""
    candidates = [
        # Microsoft Edge (presente en todas las instalaciones de Windows 10/11)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        # Google Chrome
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""


def convert_to_pdf_browser(html_file: str, pdf_file: str) -> bool:
    """Convierte el HTML a PDF usando Edge o Chrome headless nativo de Windows (sin librerías C/GTK)."""
    import subprocess
    browser_exe = find_system_browser()
    if not browser_exe:
        return False

    file_url = Path(html_file).resolve().as_uri()
    cmd = [
        browser_exe,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={str(Path(pdf_file).resolve())}",
        file_url,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        return os.path.exists(pdf_file) and os.path.getsize(pdf_file) > 0
    except Exception as e:
        print(f"[Aviso] Error en navegador headless: {e}")
        return False


def convert_to_pdf_playwright(html_file: str, pdf_file: str, title: str = "", date: str = "") -> bool:
    """Convierte el HTML a PDF usando Playwright (Chromium Headless) como motor principal."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(Path(html_file).resolve().as_uri(), wait_until="networkidle")

            # Escapar caracteres HTML para el header y footer
            h_title = title.replace('"', '&quot;').replace('<', '&lt;')
            f_date = date.replace('"', '&quot;').replace('<', '&lt;')

            header_html = (
                f'<div style="font-size: 8.5pt; width: 100%; box-sizing: border-box; padding: 0 2cm; '
                f'display: flex; justify-content: center; align-items: center; color: #718096; '
                f'font-family: \'Segoe UI\', Roboto, sans-serif; border-bottom: 0.5pt solid #E2E8F0; '
                f'padding-bottom: 4px; margin-bottom: 4px;">'
                f'<span>{h_title}</span></div>'
            )
            footer_html = (
                f'<div style="font-size: 8.5pt; width: 100%; box-sizing: border-box; padding: 0 2cm; '
                f'display: flex; justify-content: flex-end; align-items: center; color: #718096; '
                f'font-family: \'Segoe UI\', Roboto, sans-serif; border-top: 0.5pt solid #E2E8F0; '
                f'padding-top: 4px; margin-top: 4px;">'
                f'<span>{f_date} | pág. <span class="pageNumber"></span></span></div>'
            )

            page.pdf(
                path=pdf_file,
                format="A4",
                margin={"top": "2.4cm", "right": "2cm", "bottom": "2.4cm", "left": "2cm"},
                print_background=True,
                display_header_footer=True,
                header_template=header_html,
                footer_template=footer_html,
            )
            browser.close()
            return True
    except ImportError:
        return False
    except Exception as e:
        print(f"[Aviso] Error en Playwright: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Convertidor directo de Markdown a PDF corporativo."
    )
    parser.add_argument("archivo_md", help="Ruta al archivo Markdown")
    parser.add_argument(
        "--output",
        "-o",
        dest="output",
        help="Ruta de salida (puede ser la ruta completa del archivo .pdf o un directorio de destino)",
        default=None,
    )
    parser.add_argument(
        "--output_dir",
        dest="output_dir",
        help="Directorio de salida opcional (alias de --output)",
        default=None,
    )
    parser.add_argument(
        "--keep-html", help="Conserva el HTML intermedio", action="store_true"
    )
    args = parser.parse_args()

    md_file = Path(args.archivo_md).resolve()
    if not md_file.exists():
        print(f"Error: El archivo '{md_file}' no existe.")
        sys.exit(1)

    base_name = md_file.stem
    output_target = args.output or args.output_dir

    if output_target:
        target_path = Path(output_target).resolve()
        if target_path.suffix.lower() == ".pdf":
            pdf_file = target_path
            out_dir = target_path.parent
        else:
            out_dir = target_path
            pdf_file = out_dir / f"{base_name}.pdf"
    else:
        out_dir = md_file.parent
        pdf_file = out_dir / f"{base_name}.pdf"

    out_dir.mkdir(parents=True, exist_ok=True)
    html_file = out_dir / f"{base_name}.html"

    template_file = Path(__file__).parent / "templates" / "document_template.html"
    if not template_file.exists():
        print(f"Error: Plantilla no encontrada en '{template_file}'")
        sys.exit(1)

    print(f"-> Procesando '{md_file.name}' con plantilla...")
    meta, html_content = generate_html_document(str(md_file), str(template_file))

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"-> HTML preparado: {html_file.name}")

    print("-> Compilando PDF...")
    # Asegurar reescritura si el archivo PDF ya existe
    if pdf_file.exists():
        try:
            pdf_file.unlink()
        except Exception:
            pass

    # 1. Motor principal: Playwright (Chromium)
    pdf_ok = convert_to_pdf_playwright(
        str(html_file),
        str(pdf_file),
        title=meta.get("title", ""),
        date=meta.get("date", ""),
    )
    # 2. Fallback: Edge / Chrome headless nativo de Windows
    if not pdf_ok:
        pdf_ok = convert_to_pdf_browser(str(html_file), str(pdf_file))
    # 3. Fallback: WeasyPrint
    if not pdf_ok:
        pdf_ok = convert_to_pdf_weasyprint(str(html_file), str(pdf_file))

    if pdf_ok:
        print(f"¡Éxito! PDF generado: {pdf_file}")
        if not args.keep_html:
            try:
                os.remove(html_file)
            except OSError:
                pass
    else:
        print("\n[Aviso] No se pudo compilar el PDF de forma desatendida.")
        print(f"-> El archivo HTML estilizado quedó disponible en: {html_file}")


if __name__ == "__main__":
    main()
