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

// Configuración de Marked para interceptar bloques de código Mermaid
marked.use({
    renderer: {
        code(tokenOrCode) {
            const codeText = typeof tokenOrCode === 'object' ? tokenOrCode.text : arguments[0];
            const lang = typeof tokenOrCode === 'object' ? tokenOrCode.lang : arguments[1];

            if (lang === 'mermaid') {
                return `
                <div class="mermaid-wrapper">
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

async function loadMarkdown() {
    try {
        // Hacemos el fetch() al archivo MD que está en la misma carpeta
        const mdFileName = window.location.pathname.split('/').pop().replace('.html', '.md');
        const response = await fetch(mdFileName);

        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status} - No se pudo cargar el archivo.`);
        }

        const markdownText = await response.text();

        // 1. Extraer bloques matemáticos (inline y block) para protegerlos de Marked
        const mathBlocks = [];
        // La regex ahora evita hacer match cruzando saltos de línea en el $ inline y verifica que no esté escapado con \
        const mathRegex = /(\$\$[\s\S]*?\$\$|(?<!\\)\$(?:\\.|[^\$\\\n])*?(?<!\\)\$)/g;
        const textWithTokens = markdownText.replace(mathRegex, (match) => {
            mathBlocks.push(match);
            return `@@MATH_BLOCK_${mathBlocks.length - 1}@@`;
        });

        // 2. Parseamos el markdown a HTML en memoria
        let htmlContent = marked.parse(textWithTokens);

        // 3. Restaurar los bloques matemáticos intactos
        mathBlocks.forEach((block, index) => {
            htmlContent = htmlContent.replace(`@@MATH_BLOCK_${index}@@`, block);
        });

        // Inyectamos el HTML dinámicamente
        const contentDiv = document.getElementById('content');
        contentDiv.innerHTML = htmlContent;

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

            // Inicializar interactividad (Zoom, Pan, Fullscreen)
            document.querySelectorAll('.mermaid-wrapper').forEach(wrapper => {
                const viewport = wrapper.querySelector('.mermaid-viewport');
                const mermaidDiv = wrapper.querySelector('.mermaid');
                const btnZoomIn = wrapper.querySelector('.btn-zoom-in');
                const btnZoomOut = wrapper.querySelector('.btn-zoom-out');
                const btnReset = wrapper.querySelector('.btn-reset');
                const btnFullscreen = wrapper.querySelector('.btn-fullscreen');
                const btnCollapse = wrapper.querySelector('.btn-collapse');

                let scale = 1, translateX = 0, translateY = 0;
                let isDragging = false, startX, startY;

                const updateTransform = () => {
                    mermaidDiv.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
                };

                btnZoomIn.onclick = () => { scale *= 1.2; updateTransform(); };
                btnZoomOut.onclick = () => { scale /= 1.2; updateTransform(); };
                btnReset.onclick = () => { scale = 1; translateX = 0; translateY = 0; updateTransform(); };

                btnCollapse.onclick = () => {
                    wrapper.classList.toggle('collapsed');
                    btnCollapse.textContent = wrapper.classList.contains('collapsed') ? '▶' : '▼';
                };

                btnFullscreen.onclick = () => {
                    wrapper.classList.toggle('fullscreen');
                };

                viewport.addEventListener('mousedown', (e) => {
                    isDragging = true;
                    startX = e.clientX - translateX;
                    startY = e.clientY - translateY;
                    viewport.style.cursor = 'grabbing';
                });

                window.addEventListener('mousemove', (e) => {
                    if (!isDragging) return;
                    translateX = e.clientX - startX;
                    translateY = e.clientY - startY;
                    mermaidDiv.style.transition = 'none';
                    updateTransform();
                });

                window.addEventListener('mouseup', () => {
                    isDragging = false;
                    viewport.style.cursor = 'grab';
                    mermaidDiv.style.transition = 'transform 0.1s ease-out';
                });

                window.addEventListener('mouseleave', () => {
                    if (isDragging) {
                        isDragging = false;
                        viewport.style.cursor = 'grab';
                        mermaidDiv.style.transition = 'transform 0.1s ease-out';
                    }
                });

                viewport.addEventListener('wheel', (e) => {
                    e.preventDefault();
                    scale *= e.deltaY < 0 ? 1.1 : 0.9;
                    updateTransform();
                }, { passive: false });
            });
        }

    } catch (error) {
        console.warn('Error loading Markdown via fetch (CORS block on file://). Falling back to manual file input.', error);

        document.getElementById('content').innerHTML = `
                    <div class="error" style="background-color: transparent; border-color: #ef4444; text-align: center;">
                        <h3 style="color: #f87171;">Error Real de Renderizado</h3>
                        <p style="color: #cbd5e1; margin-bottom: 20px;">El archivo markdown no pudo cargarse o procesarse correctamente.</p>
                        <div style="background: rgba(0,0,0,0.5); padding: 15px; color: #fca5a5; font-family: monospace; text-align: left; overflow-x: auto; font-size: 12px; margin-bottom: 20px; border-radius: 6px;">
                            <strong>Message:</strong> ${error.message}<br>
                            <strong>Stack:</strong><br><pre>${error.stack}</pre>
                        </div>
                        <div style="padding: 20px; border: 2px dashed #3b82f6; border-radius: 8px; background: rgba(59, 130, 246, 0.05); display: inline-block;">
                            <p style="margin-top: 0; font-weight: bold; color: #93c5fd;">Por favor, seleccioná manualmente el archivo .md para forzar la carga:</p>
                            <input type="file" id="file-input" accept=".md,.txt" style="color: #e2e8f0; font-size: 14px; padding: 10px; cursor: pointer;">
                        </div>
                    </div>
                `;

        // Agregar listener para el selector de archivos
        document.getElementById('file-input').addEventListener('change', function (e) {
            const file = e.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = function (e) {
                const markdownText = e.target.result;

                // Parsear y renderizar (misma lógica que el try)
                const htmlContent = marked.parse(markdownText);
                const contentDiv = document.getElementById('content');
                contentDiv.innerHTML = htmlContent;

                renderMathInElement(contentDiv, {
                    delimiters: [
                        { left: '$$', right: '$$', display: true },
                        { left: '$', right: '$', display: false },
                        { left: '\\(', right: '\\)', display: false },
                        { left: '\\[', right: '\\]', display: true }
                    ],
                    throwOnError: false
                });

                const mermaidElements = document.querySelectorAll('.mermaid');
                if (mermaidElements.length > 0) {
                    mermaid.run({ nodes: mermaidElements });
                }
            };
            reader.readAsText(file);
        });
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