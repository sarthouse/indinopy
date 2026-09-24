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

function slugifyHeading(text) {
    return text.trim().toLowerCase()
        .replace(/[^\p{L}\p{N}\s\-_]+/gu, '') // Permite letras Unicode (acentos, ñ, etc) y números
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
            // Texto limpio sin tags HTML para el slug
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
            return false; // Delega al renderizador por defecto para python, etc.
        }
    }
});


// Activar extensión de notas al pie (marked-footnote)
// La extensión convierte [^1] en <sup><a> y genera un <section class="footnotes"> al final
if (typeof markedFootnote !== 'undefined') {
    marked.use(markedFootnote({ prefixId: 'fn-' }));
}

function generateTOC(contentDiv) {
    document.querySelectorAll('.toc-toggle-btn, .toc-sidebar').forEach(el => el.remove());
    const headings = contentDiv.querySelectorAll('h1, h2, h3');
    if (headings.length < 2) return; // Skip if too few headings

    // Crear el botón flotante para abrir el índice
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'toc-toggle-btn';
    toggleBtn.innerHTML = '📑 Índice';
    document.body.appendChild(toggleBtn);

    // Crear el panel lateral (Drawer)
    const sidebar = document.createElement('nav');
    sidebar.className = 'toc-sidebar';

    const sidebarHeader = document.createElement('div');
    sidebarHeader.className = 'toc-sidebar-header';
    sidebarHeader.innerHTML = '<h3>Índice de Contenidos</h3><button class="toc-close-btn">✖</button>';
    sidebar.appendChild(sidebarHeader);

    const ul = document.createElement('ul');
    ul.className = 'toc-list';

    headings.forEach((heading, index) => {
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

        // Cerrar el panel al hacer clic en un link
        a.addEventListener('click', () => {
            sidebar.classList.remove('open');
        });

        li.appendChild(a);
        ul.appendChild(li);
    });

    sidebar.appendChild(ul);
    document.body.appendChild(sidebar);

    // Lógica de apertura y cierre
    toggleBtn.addEventListener('click', () => {
        sidebar.classList.add('open');
    });

    const closeBtn = sidebarHeader.querySelector('.toc-close-btn');
    closeBtn.addEventListener('click', () => {
        sidebar.classList.remove('open');
    });
}

// Helper para buscar elementos por ID exacto o por su versión normalizada (con/sin acentos)
function findTargetElement(targetId) {
    if (!targetId) return null;
    let el = document.getElementById(targetId) || document.querySelector(`[name="${targetId}"]`);
    if (el) return el;

    // Si no encontró por ID exacto, buscar comparando de forma normalizada
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

// Navegación suave global para cualquier enlace interno (#) dentro del documento
document.addEventListener('click', (e) => {
    const anchor = e.target.closest('a[href^="#"]');
    if (!anchor) return;
    const hash = anchor.getAttribute('href');
    if (!hash || hash === '#') return;
    const targetId = decodeURIComponent(hash.slice(1));
    const targetEl = findTargetElement(targetId);
    if (targetEl) {
        e.preventDefault();
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.pushState(null, null, hash);
    }
});


// Inicializador de controles interactivos (Zoom, Pan táctil y Mouse, Fullscreen) para Mermaid
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
                if (wrapper.classList.contains('fullscreen')) {
                    document.body.style.overflow = 'hidden';
                } else {
                    document.body.style.overflow = '';
                }
            };
        }

        // --- Eventos de Mouse (Desktop) ---
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

        // --- Eventos Táctiles (Mobile & Tablets) ---
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
                // Pellizco para zoom (Pinch-to-zoom)
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
                    // Si ya está ampliado o en pantalla completa, arrastre directo
                    if (scale > 1.05 || wrapper.classList.contains('fullscreen')) {
                        isPanning = true;
                    } else if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) {
                        // Desplazamiento horizontal evidente dentro del diagrama
                        isPanning = true;
                    } else if (Math.abs(dy) > 12) {
                        // Desplazamiento vertical: el usuario quiere hacer scroll en la página
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

async function loadMarkdown() {
    try {
        // Hacemos el fetch() al archivo MD que está en la misma carpeta
        let mdFileName = window.mdOverride || window.location.pathname.split('/').pop().replace('.html', '.md');
        mdFileName = "md/" + mdFileName;
        const response = await fetch(mdFileName);

        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status} - No se pudo cargar el archivo.`);
        }

        let markdownText = await response.text();
        
        // Strip YAML frontmatter si existe
        markdownText = markdownText.replace(/^---\r?\n[\s\S]*?\n---\r?\n/, '');

        // 1. Proteger moneda: extraemos los precios a un array temporal (Regla estricta: espacio-dólar-espacio-número)
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

        // 3. Parseamos a HTML
        let htmlContent = marked.parse(textWithTokens);

        // 4. Restaurar todo
        mathBlocks.forEach((block, index) => {
            htmlContent = htmlContent.replace(`@@MATH_BLOCK_${index}@@`, () => block);
        });
        currencyBlocks.forEach((block, index) => {
            htmlContent = htmlContent.replace(`@@CURRENCY_${index}@@`, () => block);
        });

        // Inyectamos el HTML dinámicamente
        const contentDiv = document.getElementById('content');
        contentDiv.innerHTML = htmlContent;

                // Generar Índice de Contenidos Automático
        generateTOC(contentDiv);
        if (window.hljs) {
            contentDiv.querySelectorAll('pre code').forEach((block) => {
                if (!block.classList.contains('mermaid') && !block.parentElement.classList.contains('mermaid-wrapper')) {
                    hljs.highlightElement(block);
                }
            });
        }

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
        generateTOC(contentDiv);
        if (window.hljs) {
            contentDiv.querySelectorAll('pre code').forEach((block) => {
                if (!block.classList.contains('mermaid') && !block.parentElement.classList.contains('mermaid-wrapper')) {
                    hljs.highlightElement(block);
                }
            });
        }

        // Renderizamos la sintaxis matemática de KaTeX ($ y $$)
        renderMathInElement(contentDiv, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false },
                { left: '\\(', right: '\\)', display: false },
                { left: '\\[', right: '\\]', display: true }
            ],
            throwOnError: false
        });

        // Renderizamos los diagramas de Mermaid que acabamos de inyectar
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
                <p style="color: #cbd5e1;">El archivo markdown no pudo cargarse. (¿Error 404?)</p>
                <div style="background: rgba(0,0,0,0.5); padding: 15px; color: #fca5a5; font-family: monospace; text-align: left; overflow-x: auto; font-size: 12px; margin-top: 20px; border-radius: 6px;">
                    <strong>Message:</strong> ${error.message}<br>
                </div>
            </div>
        `;
    }
}

// Ejecutamos la lógica principal al cargar la estructura del DOM
document.addEventListener('DOMContentLoaded', () => {
    // Inyectar botón de volver al inicio
    const container = document.querySelector('.doc-container');
    if (container) {
        const backBtn = document.createElement('a');
        backBtn.href = 'index.html';
        backBtn.className = 'btn-back-home';
        backBtn.innerHTML = '← Volver al Inicio';
        container.insertBefore(backBtn, container.firstChild);
    }

    loadMarkdown();
});