document.addEventListener('DOMContentLoaded', () => {
    // Cargar pako dinámicamente para zlib
    const pakoScript = document.createElement('script');
    pakoScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js';
    document.head.appendChild(pakoScript);

    // 1. Inyectar botón de Imprimir
    const tabsContainer = document.querySelector('.tabs');
    if (tabsContainer) {
        const printBtn = document.createElement('button');
        printBtn.className = 'tab-btn';
        printBtn.style.marginLeft = 'auto'; // empuja a la derecha
        printBtn.style.backgroundColor = '#10b981';
        printBtn.style.color = '#fff';
        printBtn.innerHTML = '🖨️ Exportar a PDF / Imprimir';
        
        printBtn.onclick = async () => {
            printBtn.innerHTML = '⏳ Preparando imágenes...';
            printBtn.disabled = true;

            const wrappers = document.querySelectorAll('.mermaid-wrapper');
            const originalContents = [];

            // Reemplazar cada diagrama por su imagen PNG de Kroki
            for (let i = 0; i < wrappers.length; i++) {
                const wrapper = wrappers[i];
                const codeEnc = wrapper.getAttribute('data-code');
                if (codeEnc && window.pako) {
                    const code = decodeURIComponent(codeEnc);
                    
                    // Comprimir y codificar base64 URL-safe (mismo algoritmo que md_to_docx.py)
                    const data = new TextEncoder().encode(code);
                    const compressed = pako.deflate(data, { level: 9 });
                    
                    let binary = '';
                    for (let j = 0; j < compressed.length; j++) {
                        binary += String.fromCharCode(compressed[j]);
                    }
                    const b64 = btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
                    
                    const url = `https://kroki.io/mermaid/png/${b64}`;
                    
                    // Guardar referencia al wrapper y sus hijos para restaurarlos
                    originalContents.push({ wrapper, border: wrapper.style.border, bg: wrapper.style.background });
                    
                    // Ocultar los elementos interactivos temporalmente
                    const children = Array.from(wrapper.children);
                    children.forEach(child => child.style.display = 'none');
                    
                    // Inyectar la imagen limpia para impresión
                    const img = document.createElement('img');
                    img.src = url;
                    img.className = 'print-kroki-img';
                    img.style.cssText = 'max-width: 100%; display: block; margin: 0 auto; background: white; padding: 20px;';
                    
                    wrapper.appendChild(img);
                    wrapper.style.border = 'none';
                    wrapper.style.background = 'transparent';
                    
                    // Esperar a que la imagen cargue
                    await new Promise(resolve => {
                        img.onload = resolve;
                        img.onerror = resolve; // si falla, seguimos
                    });
                }
            }

            // Llamar a imprimir
            window.print();

            // Restaurar el DOM original después de imprimir
            setTimeout(() => {
                originalContents.forEach(item => {
                    // Remover la imagen inyectada
                    const img = item.wrapper.querySelector('.print-kroki-img');
                    if (img) img.remove();
                    
                    // Volver a mostrar los elementos interactivos
                    const children = Array.from(item.wrapper.children);
                    children.forEach(child => child.style.display = '');
                    
                    item.wrapper.style.border = item.border;
                    item.wrapper.style.background = item.bg;
                });
                printBtn.innerHTML = '🖨️ Exportar a PDF / Imprimir';
                printBtn.disabled = false;
            }, 1000);
        };
        tabsContainer.appendChild(printBtn);
    }

    // 2. Inyectar CSS de Impresión estilo DOCX
    const printStyles = `
    @media print {
        @page {
            size: A4;
            margin: 1in 1in 1in 1.18in;
        }

        body {
            background-color: #ffffff !important;
            color: #1F1F1F !important;
            font-family: "Calibri", sans-serif !important;
            font-size: 12pt !important;
            line-height: 1.5 !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Ocultar UI que no debe imprimirse */
        .tabs, .doc-header-badge, .btn-back-home, .toc-toggle-btn, .toc-sidebar, .code-wrapper .btn-copy, .mermaid-controls, #file-input {
            display: none !important;
        }

        .doc-container {
            max-width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            background-color: #ffffff !important;
            border: none !important;
            box-shadow: none !important;
        }

        h1, h2, h3, h4 {
            color: #1F1F1F !important;
            page-break-after: avoid;
            font-family: "Calibri", sans-serif !important;
        }

        h1 { font-size: 20pt !important; border-bottom: 1px solid #1F1F1F !important; }
        h2 { font-size: 16pt !important; border-bottom: 1px solid #A0A0A0 !important; }
        h3 { font-size: 14pt !important; }

        p, ul, ol, li {
            color: #1F1F1F !important;
            text-align: justify !important;
        }

        /* Enlaces */
        a {
            color: #0369A1 !important;
            text-decoration: underline !important;
        }

        /* Tablas */
        table {
            width: 100% !important;
            border-collapse: collapse !important;
            margin-bottom: 15pt !important;
            page-break-inside: auto;
        }
        
        tr {
            page-break-inside: avoid;
            page-break-after: auto;
        }

        th, td {
            border: 1pt solid #000000 !important;
            padding: 4pt 6pt !important;
            font-size: 10pt !important;
            text-align: left !important;
        }

        th {
            background-color: #E0F2FE !important;
            color: #0369A1 !important;
            font-weight: bold !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }

        /* Bloques de código (evitar corte) */
        pre, code {
            color: #1F1F1F !important;
            background-color: #F8F9FA !important;
            border: 1pt solid #D1D5DB !important;
            page-break-inside: avoid !important;
            white-space: pre-wrap !important;
        }

        /* Citas en bloque */
        blockquote {
            border-left: 3pt solid #1A3A5C !important;
            background-color: #F3F4F6 !important;
            padding: 8pt 10pt !important;
            margin: 10pt 0 !important;
            color: #374151 !important;
            page-break-inside: avoid !important;
        }
        
        /* Asegurar que se impriman los colores de fondo de los diagramas */
        * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }
    }
    `;

    const styleEl = document.createElement('style');
    styleEl.innerHTML = printStyles;
    document.head.appendChild(styleEl);
});
