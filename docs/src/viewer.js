mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    securityLevel: 'loose',
    gantt: {
        leftPadding: 200,
        barHeight: 30,
        fontSize: 12,
        useWidth: 1000
    }
});

// Configuración declarativa opcional para documentos con pestañas, badges específicos o PDF descargable.
// Cualquier archivo .md nuevo en docs/md/ funciona automáticamente sin necesidad de agregarlo aquí.
const DOC_CONFIG = {
    proyecto_ley_eop: {
        file: 'proyecto_ley_eop.md',
        title: 'Anteproyecto de Ley de e-OP | Indinopy',
        badge: '🏛️ Anteproyecto de Ley / H. Congreso de la Nación',
        pdf: 'pdf/proyecto_ley_eop.pdf'
    },
    dossier_fimca: {
        file: 'dossier_fimca_ejecutivo.md',
        title: 'Dossier Proyecto FIMCA 2026 | Indinopy',
        badge: '📘 Dossier Integral FIMCA',
        pdf: 'pdf/dossier_fimca_compilado.pdf',
        tabs: [
            { label: 'Resumen Ejecutivo', file: 'dossier_fimca_ejecutivo.md' },
            { label: 'Documento Base', file: 'dossier_fimca_base.md' },
            { label: 'Addenda I', file: 'dossier_fimca_addenda1.md' },
            { label: 'Addenda II', file: 'dossier_fimca_addenda2.md' },
            { label: 'Addenda III', file: 'dossier_fimca_addenda3.md' }
        ]
    },
    dossier_proyecto_fimca_2026: {
        aliasOf: 'dossier_fimca'
    },
    paper_protocolo_eop_gobernanza_industrial: {
        file: 'paper_protocolo_eop_gobernanza_industrial.md',
        title: 'Paper Protocolo e-OP y PoPW | Indinopy',
        badge: '🔬 Paper Académico · Consenso PoPW'
    },
    arquitectura_funcional: {
        file: 'arquitectura_funcional.md',
        title: 'Arquitectura Funcional ERP/MES | Indinopy',
        badge: '⚙️ Especificación de Arquitectura'
    },
    glosario_conceptos_proyecto: {
        file: 'glosario_conceptos_proyecto.md',
        title: 'Glosario Taxonómico del Proyecto | Indinopy',
        badge: '📖 Taxonomía y Definiciones'
    },
    explicacion_tecnica_proyecto: {
        file: 'explicacion_tecnica_proyecto.md',
        title: 'Explicación Técnica y Solución | Indinopy',
        badge: '🧭 Visión y Dispositivos Territoriales'
    },
    analisis_fimca_implementacion: {
        file: 'analisis_fimca_implementacion.md',
        title: 'Análisis de Implementación Django | Indinopy',
        badge: '💻 Ingeniería de Software ERP/MES'
    },
    plan_implementacion: {
        file: 'plan_implementacion.md',
        title: 'Plan de Implementación y Roadmap | Indinopy',
        badge: '🗺️ Hoja de Ruta y Contratos API'
    },
    arquitectura_mes_gobernanza: {
        file: 'arquitectura_mes_gobernanza.md',
        title: 'Arquitectura MES y Comités FDI | Indinopy',
        badge: '⚖️ Gobernanza Tripartita y Arbitraje'
    },
    flujos_documentales: {
        file: 'flujos_documentales.md',
        title: 'Flujos Documentales del ERP/MES | Indinopy',
        badge: '🔄 Workflows y Circuitos Operativos'
    },
    roles: {
        file: 'roles.md',
        title: 'Matriz de Roles y Segregación (SoD) | Indinopy',
        badge: '🔐 Seguridad y Permisos de Nodo'
    },
    manifiesto_de_la_manufactura_soberana: {
        file: 'manifiesto_de_la_manufactura_soberana.md',
        title: 'Manifiesto de la Manufactura Soberana | Indinopy',
        badge: '🔥 Doctrina de la Comunidad Organizada'
    }
};

function slugifyHeading(text) {
    return text.trim().toLowerCase()
        .replace(/[^\p{L}\p{N}\s\-_]+/gu, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
}

// Configuración de Marked para interceptar bloques de código Mermaid y generar IDs de encabezados consistentes
marked.use({
    renderer: {
        heading(tokenOrText, level) {
            const rawText = typeof tokenOrText === 'object' ? tokenOrText.text : arguments[0];
            const depth = typeof tokenOrText === 'object' ? tokenOrText.depth : arguments[1];
            const plainText = rawText.replace(/<[^>]+>/g, '');
            const slug = slugifyHeading(plainText);
            return `<h${depth} id="${slug}">${rawText}</h${depth}>`;
        },
        code(tokenOrCode) {
            const codeText = typeof tokenOrCode === 'object' ? tokenOrCode.text : arguments[0];
            const lang = typeof tokenOrCode === 'object' ? tokenOrCode.lang : arguments[1];
            if (lang === 'mermaid') {
                return `
                <div class="mermaid-wrapper" data-code="${encodeURIComponent(codeText)}">
                    <div class="mermaid-header">
                        <div class="mermaid-title">📊 Diagrama Mermaid</div>
                        <div class="mermaid-controls">
                            <button class="m-btn btn-zoom-in" title="Acercar">➕</button>
                            <button class="m-btn btn-zoom-out" title="Alejar">➖</button>
                            <button class="m-btn btn-reset" title="Restaurar">🔄</button>
                            <button class="m-btn btn-fullscreen" title="Pantalla Completa">⛶</button>
                            <button class="m-btn btn-collapse" title="Expandir/Contraer">▼</button>
                        </div>
                    </div>
                    <div class="mermaid-viewport">
                        <div class="mermaid" style="transform: scale(1) translate(0px, 0px); transition: transform 0.1s ease-out; transform-origin: center;">${codeText.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
                    </div>
                </div>`;
            }
            return false;
        }
    }
});

// Activar extensión de notas al pie (marked-footnote)
if (typeof markedFootnote !== 'undefined') {
    marked.use(markedFootnote({ prefixId: 'fn-' }));
}

function generateTOC(contentDiv) {
    document.querySelectorAll('.toc-toggle-btn, .toc-sidebar').forEach(el => el.remove());
    const headings = contentDiv.querySelectorAll('h1, h2, h3');
    if (headings.length < 2) return;

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'toc-toggle-btn no-print';
    toggleBtn.innerHTML = '📑 Índice';
    document.body.appendChild(toggleBtn);

    const sidebar = document.createElement('nav');
    sidebar.className = 'toc-sidebar no-print';

    const sidebarHeader = document.createElement('div');
    sidebarHeader.className = 'toc-sidebar-header';
    sidebarHeader.innerHTML = '<h3>Índice de Contenidos</h3><button class="toc-close-btn">✖</button>';
    sidebar.appendChild(sidebarHeader);

    const ul = document.createElement('ul');
    ul.className = 'toc-list';

    headings.forEach((heading) => {
        const innerAnchor = heading.querySelector('a[id], span[id]');
        if (innerAnchor && innerAnchor.id) {
            heading.id = innerAnchor.id;
        } else if (!heading.id) {
            heading.id = slugifyHeading(heading.textContent);
        }

        const li = document.createElement('li');
        li.className = 'toc-item toc-' + heading.tagName.toLowerCase();

        const a = document.createElement('a');
        a.href = '#' + heading.id;
        a.textContent = heading.textContent;

        a.addEventListener('click', () => {
            sidebar.classList.remove('open');
        });

        li.appendChild(a);
        ul.appendChild(li);
    });

    sidebar.appendChild(ul);
    document.body.appendChild(sidebar);

    toggleBtn.addEventListener('click', () => {
        sidebar.classList.add('open');
    });

    const closeBtn = sidebarHeader.querySelector('.toc-close-btn');
    closeBtn.addEventListener('click', () => {
        sidebar.classList.remove('open');
    });
}

function findTargetElement(targetId) {
    if (!targetId) return null;
    let el = document.getElementById(targetId) || document.querySelector(`[name="${targetId}"]`);
    if (el) return el;

    const normTarget = targetId.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const candidates = document.querySelectorAll('h1, h2, h3, h4, h5, h6, [id]');
    for (const cand of candidates) {
        if (cand.id) {
            const candNorm = cand.id.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
            if (candNorm === normTarget) return cand;
        }
    }
    return null;
}

// Navegación suave para anclas (#) e intercepción inteligente de links internos entre documentos .md / .html
document.addEventListener('click', (e) => {
    const anchor = e.target.closest('a[href]');
    if (!anchor) return;
    const href = anchor.getAttribute('href');
    if (!href) return;

    // 1. Enlaces de ancla interna (#seccion)
    if (href.startsWith('#')) {
        if (href === '#') return;
        const targetId = decodeURIComponent(href.slice(1));
        const targetEl = findTargetElement(targetId);
        if (targetEl) {
            e.preventDefault();
            targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            history.pushState(null, null, href);
        }
        return;
    }

    // 2. Enlaces internos hacia otros archivos .md o antiguos wrappers .html
    if (!href.startsWith('http') && !href.startsWith('mailto:') && !href.startsWith('pdf/')) {
        const [pathPart, hashPart] = href.split('#');
        const cleanFile = pathPart.split('/').pop();
        if (cleanFile && cleanFile !== 'index.html' && cleanFile !== 'visor.html' && cleanFile !== 'modelo_orden_produccion.html') {
            if (cleanFile.endsWith('.md') || cleanFile.endsWith('.html')) {
                e.preventDefault();
                const docKey = cleanFile.replace(/\.(md|html)$/, '');
                const targetUrl = `visor.html?doc=${encodeURIComponent(docKey)}${hashPart ? '#' + hashPart : ''}`;
                window.location.href = targetUrl;
            }
        }
    }
});

// Controles interactivos (Zoom, Pan táctil y Mouse, Fullscreen) para Mermaid
function initMermaidInteractivity() {
    document.querySelectorAll('.mermaid-wrapper').forEach(wrapper => {
        if (wrapper.dataset.interactiveInitialized === 'true') return;
        wrapper.dataset.interactiveInitialized = 'true';

        const viewport = wrapper.querySelector('.mermaid-viewport');
        const mermaidDiv = wrapper.querySelector('.mermaid');
        const btnZoomIn = wrapper.querySelector('.btn-zoom-in');
        const btnZoomOut = wrapper.querySelector('.btn-zoom-out');
        const btnReset = wrapper.querySelector('.btn-reset');
        const btnFullscreen = wrapper.querySelector('.btn-fullscreen');
        const btnCollapse = wrapper.querySelector('.btn-collapse');

        let scale = 1, translateX = 0, translateY = 0;
        let isMouseDragging = false, mouseStartX = 0, mouseStartY = 0;

        const updateTransform = () => {
            mermaidDiv.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
        };

        if (btnZoomIn) {
            btnZoomIn.onclick = (e) => {
                e.stopPropagation();
                scale = Math.min(scale * 1.25, 4.5);
                mermaidDiv.style.transition = 'transform 0.15s ease-out';
                updateTransform();
            };
        }
        if (btnZoomOut) {
            btnZoomOut.onclick = (e) => {
                e.stopPropagation();
                scale = Math.max(scale / 1.25, 0.4);
                mermaidDiv.style.transition = 'transform 0.15s ease-out';
                updateTransform();
            };
        }
        if (btnReset) {
            btnReset.onclick = (e) => {
                e.stopPropagation();
                scale = 1;
                translateX = 0;
                translateY = 0;
                mermaidDiv.style.transition = 'transform 0.2s ease-out';
                updateTransform();
            };
        }

        if (btnCollapse) {
            btnCollapse.onclick = (e) => {
                e.stopPropagation();
                wrapper.classList.toggle('collapsed');
                btnCollapse.textContent = wrapper.classList.contains('collapsed') ? '▶' : '▼';
            };
        }

        if (btnFullscreen) {
            btnFullscreen.onclick = (e) => {
                e.stopPropagation();
                wrapper.classList.toggle('fullscreen');
                document.body.style.overflow = wrapper.classList.contains('fullscreen') ? 'hidden' : '';
            };
        }

        viewport.addEventListener('mousedown', (e) => {
            isMouseDragging = true;
            mouseStartX = e.clientX - translateX;
            mouseStartY = e.clientY - translateY;
            viewport.style.cursor = 'grabbing';
            mermaidDiv.style.transition = 'none';
        });

        window.addEventListener('mousemove', (e) => {
            if (!isMouseDragging) return;
            translateX = e.clientX - mouseStartX;
            translateY = e.clientY - mouseStartY;
            updateTransform();
        });

        const stopMouseDrag = () => {
            if (isMouseDragging) {
                isMouseDragging = false;
                viewport.style.cursor = 'grab';
                mermaidDiv.style.transition = 'transform 0.1s ease-out';
            }
        };

        window.addEventListener('mouseup', stopMouseDrag);
        window.addEventListener('mouseleave', stopMouseDrag);

        viewport.addEventListener('wheel', (e) => {
            e.preventDefault();
            const factor = e.deltaY < 0 ? 1.15 : 0.88;
            scale = Math.min(Math.max(scale * factor, 0.4), 4.5);
            mermaidDiv.style.transition = 'transform 0.08s ease-out';
            updateTransform();
        }, { passive: false });

        let isTouchDragging = false;
        let isPanning = false;
        let touchStartX = 0, touchStartY = 0;
        let touchStartTranslateX = 0, touchStartTranslateY = 0;
        let initialPinchDist = 0;
        let initialScale = 1;

        viewport.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
                isTouchDragging = true;
                isPanning = false;
                touchStartX = e.touches[0].clientX;
                touchStartY = e.touches[0].clientY;
                touchStartTranslateX = translateX;
                touchStartTranslateY = translateY;
            } else if (e.touches.length === 2) {
                isTouchDragging = false;
                isPanning = true;
                initialPinchDist = Math.hypot(
                    e.touches[0].clientX - e.touches[1].clientX,
                    e.touches[0].clientY - e.touches[1].clientY
                );
                initialScale = scale;
            }
        }, { passive: true });

        window.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2 && initialPinchDist > 0) {
                if (e.cancelable) e.preventDefault();
                const currentDist = Math.hypot(
                    e.touches[0].clientX - e.touches[1].clientX,
                    e.touches[0].clientY - e.touches[1].clientY
                );
                const factor = currentDist / initialPinchDist;
                scale = Math.min(Math.max(initialScale * factor, 0.4), 4.5);
                mermaidDiv.style.transition = 'none';
                updateTransform();
            } else if (e.touches.length === 1 && isTouchDragging) {
                const curX = e.touches[0].clientX;
                const curY = e.touches[0].clientY;
                const dx = curX - touchStartX;
                const dy = curY - touchStartY;

                if (!isPanning) {
                    if (scale > 1.05 || wrapper.classList.contains('fullscreen')) {
                        isPanning = true;
                    } else if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) {
                        isPanning = true;
                    } else if (Math.abs(dy) > 12) {
                        isTouchDragging = false;
                        return;
                    }
                }

                if (isPanning) {
                    if (e.cancelable) e.preventDefault();
                    translateX = touchStartTranslateX + dx;
                    translateY = touchStartTranslateY + dy;
                    mermaidDiv.style.transition = 'none';
                    updateTransform();
                }
            }
        }, { passive: false });

        const endTouch = () => {
            isTouchDragging = false;
            isPanning = false;
            initialPinchDist = 0;
            mermaidDiv.style.transition = 'transform 0.1s ease-out';
        };

        window.addEventListener('touchend', endTouch);
        window.addEventListener('touchcancel', endTouch);
    });
}

// Mapa de alias históricos (antiguos wrappers .html, sub-archivos y nombres cortos) -> ruta canónica
const DOC_ALIASES = {
    'proyecto_ley_eop.html': { doc: 'proyecto_ley_eop' },
    'ley_eop': { doc: 'proyecto_ley_eop' },
    'dossier_proyecto_fimca_2026': { doc: 'dossier_fimca' },
    'dossier_proyecto_fimca_2026.html': { doc: 'dossier_fimca' },
    'dossier_fimca.html': { doc: 'dossier_fimca' },
    'dossier_fimca_ejecutivo': { doc: 'dossier_fimca', tab: 'dossier_fimca_ejecutivo.md' },
    'dossier_fimca_base': { doc: 'dossier_fimca', tab: 'dossier_fimca_base.md' },
    'dossier_fimca_addenda1': { doc: 'dossier_fimca', tab: 'dossier_fimca_addenda1.md' },
    'dossier_fimca_addenda2': { doc: 'dossier_fimca', tab: 'dossier_fimca_addenda2.md' },
    'dossier_fimca_addenda3': { doc: 'dossier_fimca', tab: 'dossier_fimca_addenda3.md' },
    'paper_protocolo_eop_gobernanza_industrial.html': { doc: 'paper_protocolo_eop_gobernanza_industrial' },
    'paper': { doc: 'paper_protocolo_eop_gobernanza_industrial' },
    'arquitectura_funcional.html': { doc: 'arquitectura_funcional' },
    'glosario_conceptos_proyecto.html': { doc: 'glosario_conceptos_proyecto' },
    'glosario': { doc: 'glosario_conceptos_proyecto' },
    'explicacion_tecnica_proyecto.html': { doc: 'explicacion_tecnica_proyecto' },
    'analisis_fimca_implementacion.html': { doc: 'analisis_fimca_implementacion' },
    'plan_implementacion.html': { doc: 'plan_implementacion' },
    'arquitectura_mes_gobernanza.html': { doc: 'arquitectura_mes_gobernanza' },
    'flujos_documentales.html': { doc: 'flujos_documentales' },
    'roles.html': { doc: 'roles' },
    'manifiesto_de_la_manufactura_soberana.html': { doc: 'manifiesto_de_la_manufactura_soberana' },
    'manifiesto': { doc: 'manifiesto_de_la_manufactura_soberana' }
};

// Resuelve qué documento cargar a partir de ?doc=, alias histórico o nombre de archivo
function resolveDocContext() {
    const params = new URLSearchParams(window.location.search);
    let rawDoc = params.get('doc');

    if (!rawDoc) {
        const pageName = window.location.pathname.split('/').pop().replace('.html', '');
        rawDoc = (pageName && pageName !== 'visor' && pageName !== 'index') ? pageName : 'proyecto_ley_eop';
    }

    const cleanRaw = rawDoc.trim();
    const strippedKey = cleanRaw.replace(/\.(md|html)$/, '');
    let docKey = strippedKey;
    let initialTabFile = params.get('tab') || null;

    // 1. Verificar si coincide con un alias directo (con o sin extensión .html/.md)
    const aliasMatch = DOC_ALIASES[cleanRaw] || DOC_ALIASES[strippedKey];
    if (aliasMatch) {
        docKey = aliasMatch.doc;
        if (aliasMatch.tab && !initialTabFile) {
            initialTabFile = aliasMatch.tab;
        }
    }

    // 2. Verificar alias declarados dentro de DOC_CONFIG
    let config = DOC_CONFIG[docKey];
    if (config && config.aliasOf) {
        docKey = config.aliasOf;
        config = DOC_CONFIG[docKey];
    }

    // 3. Si el usuario entró mediante un alias (ej. ?doc=dossier_proyecto_fimca_2026 o ?doc=roles.html),
    // reescribir la URL en la barra de direcciones hacia la ruta canónica real.
    if (params.get('doc') && params.get('doc') !== docKey) {
        const canonicalUrl = `visor.html?doc=${encodeURIComponent(docKey)}${window.location.hash || ''}`;
        window.history.replaceState(null, '', canonicalUrl);
    }

    if (!config) {
        config = {
            file: docKey + '.md',
            title: null,
            badge: '📚 Documentación Oficial Indinopy'
        };
    }

    return {
        docKey,
        config,
        activeFile: window.mdOverride || initialTabFile || config.file
    };
}

function setupDocumentChrome(context) {
    const { config, activeFile } = context;

    // 1. Badge
    const badgeEl = document.getElementById('doc-badge');
    if (badgeEl && config.badge) {
        badgeEl.textContent = config.badge;
    }

    // 2. Título de la pestaña
    if (config.title) {
        document.title = config.title;
    }

    // 3. Acciones (Botón Descargar PDF si aplica)
    const actionsEl = document.getElementById('doc-actions');
    if (actionsEl) {
        actionsEl.innerHTML = '';
        if (config.pdf) {
            const pdfBtn = document.createElement('a');
            pdfBtn.href = config.pdf;
            pdfBtn.className = 'btn-download-pdf';
            pdfBtn.target = '_blank';
            pdfBtn.rel = 'noopener noreferrer';
            pdfBtn.innerHTML = '📥 Descargar PDF Oficial';
            actionsEl.appendChild(pdfBtn);
        }
    }

    // 4. Pestañas (Dossier FIMCA o documentos multi-capítulo)
    const tabsEl = document.getElementById('doc-tabs');
    if (tabsEl) {
        if (config.tabs && config.tabs.length > 0) {
            tabsEl.style.display = 'flex';
            tabsEl.innerHTML = '';
            config.tabs.forEach(tab => {
                const btn = document.createElement('button');
                btn.className = 'tab-btn' + (tab.file === activeFile ? ' active' : '');
                btn.textContent = tab.label;
                btn.onclick = () => switchTab(tab.file, btn);
                tabsEl.appendChild(btn);
            });
        } else {
            tabsEl.style.display = 'none';
            tabsEl.innerHTML = '';
        }
    }
}

window.switchTab = function (filename, btnElement) {
    window.mdOverride = filename;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    if (btnElement) btnElement.classList.add('active');

    document.getElementById('content').innerHTML = '<div class="loading">Cargando capítulo...</div>';
    loadMarkdown(filename);
};

async function loadMarkdown(explicitFile) {
    try {
        const context = resolveDocContext();
        setupDocumentChrome(context);

        let mdFileName = explicitFile || context.activeFile;
        if (!mdFileName.endsWith('.md')) {
            mdFileName += '.md';
        }
        const fetchPath = mdFileName.startsWith('md/') ? mdFileName : 'md/' + mdFileName;
        const response = await fetch(fetchPath);

        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status} - No se encontró ${fetchPath}`);
        }

        let markdownText = await response.text();

        // Strip YAML frontmatter si existe
        markdownText = markdownText.replace(/^---\r?\n[\s\S]*?\n---\r?\n/, '');

        // 1. Proteger moneda: espacio-dólar-espacio-número
        const currencyBlocks = [];
        let textWithTokens = markdownText.replace(/(^|\s)\$\s+(\d)/g, (match, spaceBefore, digit) => {
            currencyBlocks.push(`${spaceBefore}<span class="math-ignore">&#36; </span>${digit}`);
            return `@@CURRENCY_${currencyBlocks.length - 1}@@`;
        });

        // 2. Extraer bloques matemáticos (block e inline)
        const mathBlocks = [];
        textWithTokens = textWithTokens.replace(/\$\$([\s\S]*?)\$\$/g, (match) => {
            mathBlocks.push(match);
            return `@@MATH_BLOCK_${mathBlocks.length - 1}@@`;
        });

        textWithTokens = textWithTokens.replace(/(?<!\\)\$([\s\S]+?)(?<!\\)\$/g, (match) => {
            mathBlocks.push(match);
            return `@@MATH_BLOCK_${mathBlocks.length - 1}@@`;
        });

        // 3. Parsear a HTML
        let htmlContent = marked.parse(textWithTokens);

        // 4. Restaurar bloques matemáticos y moneda
        mathBlocks.forEach((block, index) => {
            htmlContent = htmlContent.replace(`@@MATH_BLOCK_${index}@@`, () => block);
        });
        currencyBlocks.forEach((block, index) => {
            htmlContent = htmlContent.replace(`@@CURRENCY_${index}@@`, () => block);
        });

        const contentDiv = document.getElementById('content');
        contentDiv.innerHTML = htmlContent;

        // Si el documento no tenía título preconfigurado, usar el primer H1 del Markdown
        if (!context.config.title) {
            const firstH1 = contentDiv.querySelector('h1');
            if (firstH1) {
                document.title = `${firstH1.textContent.trim()} | Indinopy`;
            }
        }

        // Generar Índice de Contenidos Automático
        generateTOC(contentDiv);

        // Highlight.js para bloques de código y Botón de Copiar
        if (window.hljs) {
            contentDiv.querySelectorAll('pre').forEach((pre) => {
                const block = pre.querySelector('code');
                if (block && !block.classList.contains('mermaid') && !pre.classList.contains('mermaid-wrapper')) {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'code-wrapper';
                    pre.parentNode.insertBefore(wrapper, pre);
                    wrapper.appendChild(pre);

                    const btn = document.createElement('button');
                    btn.className = 'btn-copy';
                    btn.textContent = 'Copiar';

                    btn.addEventListener('click', () => {
                        navigator.clipboard.writeText(block.innerText).then(() => {
                            btn.textContent = '¡Copiado!';
                            btn.classList.add('copied');
                            setTimeout(() => {
                                btn.textContent = 'Copiar';
                                btn.classList.remove('copied');
                            }, 2000);
                        });
                    });

                    wrapper.appendChild(btn);
                    hljs.highlightElement(block);
                }
            });
        }

        // Renderizar sintaxis matemática de KaTeX ($ y $$)
        renderMathInElement(contentDiv, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false },
                { left: '\\(', right: '\\)', display: false },
                { left: '\\[', right: '\\]', display: true }
            ],
            throwOnError: false
        });

        // Renderizar diagramas Mermaid
        const mermaidElements = document.querySelectorAll('.mermaid');
        if (mermaidElements.length > 0) {
            await mermaid.run({ nodes: mermaidElements });
            initMermaidInteractivity();
        }

        // Si la URL vino con un hash (#), hacer scroll suave hasta el elemento
        if (window.location.hash) {
            const targetId = decodeURIComponent(window.location.hash.slice(1));
            const targetEl = findTargetElement(targetId);
            if (targetEl) {
                setTimeout(() => targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' }), 200);
            }
        }

    } catch (error) {
        console.warn('Error loading Markdown via fetch:', error);
        document.getElementById('content').innerHTML = `
            <div class="error" style="background-color: transparent; border-color: #ef4444; text-align: center;">
                <h3 style="color: #f87171;">Error de Renderizado</h3>
                <p style="color: #cbd5e1;">El documento solicitado no pudo cargarse.</p>
                <div style="background: rgba(0,0,0,0.5); padding: 15px; color: #fca5a5; font-family: monospace; text-align: left; overflow-x: auto; font-size: 12px; margin-top: 20px; border-radius: 6px;">
                    <strong>Detalle:</strong> ${error.message}<br>
                </div>
            </div>
        `;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const container = document.querySelector('.doc-container');
    if (container && !document.querySelector('.btn-back-home')) {
        const backBtn = document.createElement('a');
        backBtn.href = 'index.html';
        backBtn.className = 'btn-back-home';
        backBtn.innerHTML = '← Volver al Inicio';
        container.insertBefore(backBtn, container.firstChild);
    }

    loadMarkdown();
});
