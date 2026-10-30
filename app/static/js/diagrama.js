(function () {
    "use strict";

    var contenedor = document.getElementById("diagrama-conversacion");
    var datosEl = document.getElementById("diagrama-datos");
    if (!contenedor || !datosEl) return;

    var baseUrl = contenedor.dataset.baseUrl;
    var datos = JSON.parse(datosEl.textContent);
    var nodos = datos.nodos, aristas = datos.aristas;

    var ANCHO_DEFAULT = 190, ANCHO_MIN = 140, ALTO_NODO = 76, GAP_X = 34, GAP_Y = 70, MARGEN = 30;
    var NS = "http://www.w3.org/2000/svg";

    var porId = {};
    nodos.forEach(function (n) { porId[n.id] = n; });

    // Arrastrar la esquina del recuadro (resize: vertical, en CSS) no
    // dispara ningún evento propio — sin esto, el lienzo de adentro se
    // queda con el tamaño viejo hasta que algo más fuerce un render().
    var resizeObserver = null;

    function anchoDe(n) { return n.ancho || ANCHO_DEFAULT; }

    // ---- Layout automático (BFS por capas) para los nodos que todavía no
    // tienen una posición guardada — una vez que alguien los mueve, pos_x/
    // pos_y quedan fijos y el auto-layout deja de tocarlos.
    function autoLayout() {
        var nivel = {};
        var cola = [];
        nodos.forEach(function (n) {
            if (n.es_entrada) { nivel[n.id] = 0; cola.push(n.id); }
        });
        var salientes = {};
        aristas.forEach(function (a) {
            if (a.destino == null) return;
            (salientes[a.origen] = salientes[a.origen] || []).push(a.destino);
        });
        while (cola.length) {
            var actualId = cola.shift();
            (salientes[actualId] || []).forEach(function (destId) {
                if (!(destId in nivel)) { nivel[destId] = nivel[actualId] + 1; cola.push(destId); }
            });
        }
        var filas = {};
        var desconectados = [];
        nodos.forEach(function (n) {
            if (n.pos_x != null && n.pos_y != null) return;
            if (n.id in nivel) { (filas[nivel[n.id]] = filas[nivel[n.id]] || []).push(n); }
            else { desconectados.push(n); }
        });
        function anchoFila(items) {
            return items.reduce(function (s, n) { return s + anchoDe(n) + GAP_X; }, -GAP_X);
        }
        var niveles = Object.keys(filas).map(Number).sort(function (a, b) { return a - b; });
        niveles.forEach(function (l, filaIdx) {
            var fila = filas[l];
            var x = MARGEN;
            fila.forEach(function (n) {
                n.pos_x = x; n.pos_y = MARGEN + filaIdx * (ALTO_NODO + GAP_Y);
                x += anchoDe(n) + GAP_X;
            });
        });
        if (desconectados.length) {
            var y = MARGEN + (niveles.length ? niveles.length * (ALTO_NODO + GAP_Y) : 0) + GAP_Y;
            var x = MARGEN;
            desconectados.forEach(function (n) {
                n.pos_x = x; n.pos_y = y;
                x += anchoDe(n) + GAP_X;
            });
        }
    }
    autoLayout();

    // ---- Render ----
    var svg, nodoDivs = {}, aristaInfo = [];

    function limitesCanvas() {
        var maxX = 400, maxY = 300;
        nodos.forEach(function (n) {
            maxX = Math.max(maxX, n.pos_x + anchoDe(n) + MARGEN);
            maxY = Math.max(maxY, n.pos_y + ALTO_NODO + MARGEN);
        });
        return { ancho: maxX, alto: maxY };
    }

    function centroInferior(n) { return { x: n.pos_x + anchoDe(n) / 2, y: n.pos_y + ALTO_NODO }; }
    function centroSuperior(n) { return { x: n.pos_x + anchoDe(n) / 2, y: n.pos_y }; }

    function pathArista(origenN, destinoN) {
        var p1 = centroInferior(origenN), p2 = centroSuperior(destinoN);
        var midY = (p1.y + p2.y) / 2;
        return "M" + p1.x + "," + p1.y + " C" + p1.x + "," + midY + " " + p2.x + "," + midY + " " + p2.x + "," + p2.y;
    }

    function iniciarEdicionTexto(n, cuerpoDiv) {
        var textarea = document.createElement("textarea");
        textarea.className = "diagrama-nodo-texto-edit";
        textarea.value = n.texto;
        cuerpoDiv.replaceWith(textarea);
        textarea.focus();
        textarea.select();

        function guardar() {
            var nuevoTexto = textarea.value.trim();
            if (!nuevoTexto || nuevoTexto === n.texto) { render(); return; }
            fetch(baseUrl + "/guiones/" + n.id + "/texto-rapido", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: "texto=" + encodeURIComponent(nuevoTexto),
            }).then(function (r) { return r.json(); }).then(function (data) {
                n.texto = data.texto;
                render();
            }).catch(function () { render(); });
        }
        textarea.addEventListener("blur", guardar);
        textarea.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape") { ev.preventDefault(); render(); }
            if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); textarea.blur(); }
        });
    }

    function guardarPosicion(n) {
        fetch(baseUrl + "/guiones/" + n.id + "/posicion", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: "pos_x=" + Math.round(n.pos_x) + "&pos_y=" + Math.round(n.pos_y) + "&ancho=" + (n.ancho || ""),
        }).catch(function () { /* se reintenta solo en el próximo movimiento */ });
    }

    function actualizarAristasConectadasA(id) {
        aristaInfo.forEach(function (info) {
            if (info.origenId !== id && info.destinoId !== id) return;
            if (info.destinoId == null) {
                // Texto "fin": sigue al nodo de origen, no hay destino que lo ate.
                var p = centroInferior(porId[info.origenId]);
                info.finEl.setAttribute("x", p.x);
                info.finEl.setAttribute("y", p.y + 16);
                return;
            }
            var d = pathArista(porId[info.origenId], porId[info.destinoId]);
            info.pathEl.setAttribute("d", d);
            info.hitEl.setAttribute("d", d);
            if (info.labelEl) {
                var p1 = centroInferior(porId[info.origenId]), p2 = centroSuperior(porId[info.destinoId]);
                info.labelEl.setAttribute("x", (p1.x + p2.x) / 2);
                info.labelEl.setAttribute("y", (p1.y + p2.y) / 2 - 4);
            }
        });
    }

    function hacerArrastrable(n, div, foCuerpo) {
        div.addEventListener("mousedown", function (ev) {
            if (ev.target.closest(".diagrama-resize") || ev.target.closest(".diagrama-conector") || ev.target.closest(".diagrama-menu-boton") || ev.target.closest(".diagrama-nodo-texto-edit")) return;
            ev.preventDefault();
            var startX = ev.clientX, startY = ev.clientY;
            var origX = n.pos_x, origY = n.pos_y;
            var moved = false;

            function mover(ev2) {
                var dx = ev2.clientX - startX, dy = ev2.clientY - startY;
                if (!moved && Math.abs(dx) + Math.abs(dy) > 4) moved = true;
                if (!moved) return;
                n.pos_x = origX + dx; n.pos_y = origY + dy;
                foCuerpo.setAttribute("x", n.pos_x);
                foCuerpo.setAttribute("y", n.pos_y);
                actualizarAristasConectadasA(n.id);
            }
            function soltar() {
                document.removeEventListener("mousemove", mover);
                document.removeEventListener("mouseup", soltar);
                if (moved) {
                    guardarPosicion(n);
                } else {
                    // Un click sin arrastre, en cualquier parte del nodo (que no
                    // sea resize/conector/menú), abre la edición del texto —
                    // antes solo funcionaba si el click caía justo sobre el
                    // texto, y en el resto del nodo no pasaba nada.
                    iniciarEdicionTexto(n, div.querySelector(".diagrama-nodo-texto"));
                }
            }
            document.addEventListener("mousemove", mover);
            document.addEventListener("mouseup", soltar);
        });
    }

    function hacerRedimensionable(n, div, foCuerpo) {
        var handle = document.createElement("div");
        handle.className = "diagrama-resize";
        div.appendChild(handle);
        handle.addEventListener("mousedown", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var startX = ev.clientX;
            var origAncho = anchoDe(n);
            function mover(ev2) {
                var dx = ev2.clientX - startX;
                n.ancho = Math.max(ANCHO_MIN, origAncho + dx);
                foCuerpo.setAttribute("width", n.ancho);
                actualizarAristasConectadasA(n.id);
            }
            function soltar() {
                document.removeEventListener("mousemove", mover);
                document.removeEventListener("mouseup", soltar);
                guardarPosicion(n);
            }
            document.addEventListener("mousemove", mover);
            document.addEventListener("mouseup", soltar);
        });
    }

    var lineaTemporal = null;
    function hacerConectable(n, div) {
        var conector = document.createElement("div");
        conector.className = "diagrama-conector";
        conector.title = "Arrastrá hasta otro guion para conectar";
        div.appendChild(conector);
        conector.addEventListener("mousedown", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var svgRect = svg.getBoundingClientRect();
            lineaTemporal = document.createElementNS(NS, "line");
            lineaTemporal.setAttribute("class", "diagrama-arista-temp");
            svg.appendChild(lineaTemporal);

            function puntoSvg(ev2) {
                return { x: ev2.clientX - svgRect.left, y: ev2.clientY - svgRect.top };
            }
            function mover(ev2) {
                var origen = centroInferior(n);
                var destino = puntoSvg(ev2);
                lineaTemporal.setAttribute("x1", origen.x); lineaTemporal.setAttribute("y1", origen.y);
                lineaTemporal.setAttribute("x2", destino.x); lineaTemporal.setAttribute("y2", destino.y);
            }
            function soltar(ev2) {
                document.removeEventListener("mousemove", mover);
                document.removeEventListener("mouseup", soltar);
                if (lineaTemporal) { lineaTemporal.remove(); lineaTemporal = null; }
                var elDestino = document.elementFromPoint(ev2.clientX, ev2.clientY);
                var divDestino = elDestino && elDestino.closest(".diagrama-nodo");
                var sobreCanvas = elDestino === svg || (elDestino && elDestino.closest(".diagrama-scroll"));
                if (!sobreCanvas) return;
                var destinoId = divDestino ? Number(divDestino.dataset.id) : null;
                if (destinoId === n.id) return;
                var esLibre = n.tipo_respuesta !== "opciones";

                function pedirEtiquetaYConectar() {
                    var titulo = esLibre
                        ? "Criterio de esta rama (dejalo vacío para el camino por defecto / fallback)"
                        : "Texto de la opción";
                    if (destinoId == null) titulo += " — este camino va a terminar en \"fin\"";
                    window.promptApp(titulo).then(function (etiqueta) {
                        if (etiqueta === null) return; // cancelado
                        var etiquetaLimpia = etiqueta.trim();
                        if (!esLibre && !etiquetaLimpia) {
                            window.avisarApp("Hace falta un texto para la opción.");
                            return;
                        }
                        return fetch(baseUrl + "/guiones/" + n.id + "/conectar", {
                            method: "POST",
                            headers: { "Content-Type": "application/x-www-form-urlencoded" },
                            body: "destino_id=" + (destinoId == null ? "" : destinoId) + "&etiqueta=" + encodeURIComponent(etiquetaLimpia),
                        }).then(function (r) {
                            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "error"); });
                            return r.json();
                        }).then(function (data) {
                            var idx = aristas.findIndex(function (x) { return x.id === data.arista.id && x.tipo === data.arista.tipo; });
                            if (idx >= 0) aristas[idx] = data.arista; else aristas.push(data.arista);
                            render();
                        });
                    }).catch(function (e) { window.avisarApp(e.message || "No se pudo conectar."); });
                }

                if (destinoId == null) {
                    // Soltar en un espacio vacío del lienzo crea un camino sin destino
                    // ("fin") — se confirma antes para que no se cree por accidente.
                    window.confirmarApp("Este camino va a terminar la conversación acá (\"fin\"), sin otro guion después. ¿Seguir?").then(function (ok) {
                        if (ok) pedirEtiquetaYConectar();
                    });
                    return;
                }
                pedirEtiquetaYConectar();
            }
            document.addEventListener("mousemove", mover);
            document.addEventListener("mouseup", soltar);
        });
    }

    function quitarNodoDelEstado(id) {
        nodos = nodos.filter(function (n) { return n.id !== id; });
        delete porId[id];
        aristas = aristas.filter(function (a) { return a.origen !== id; });
        aristas.forEach(function (a) { if (a.destino === id) a.destino = null; });
    }

    function duplicarNodo(n) {
        window.confirmarApp("¿Duplicar este guion? Se crea una copia con sus opciones/ramas (mismos destinos).").then(function (ok) {
            if (!ok) return;
            return fetch(baseUrl + "/guiones/" + n.id + "/duplicar", { method: "POST" }).then(function (r) {
                if (!r.ok) throw new Error();
                // La copia trae sus propias opciones/ramas y necesita layout:
                // más simple recargar que armar todo ese estado a mano.
                window.location.reload();
            });
        }).catch(function () { window.avisarApp("No se pudo duplicar el guion."); });
    }

    function reabrirNodo(n) {
        window.promptApp("Nueva fecha y hora para reabrir este guion", "", "datetime-local").then(function (fecha) {
            if (!fecha) return;
            return fetch(baseUrl + "/guiones/" + n.id + "/reabrir", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: "fecha_programada=" + encodeURIComponent(fecha),
            }).then(function (r) {
                if (!r.ok) throw new Error();
                n.estado = "borrador";
                render();
            });
        }).catch(function () { window.avisarApp("No se pudo reabrir el guion."); });
    }

    function borrarNodo(n) {
        window.confirmarApp("¿Borrar este guion? También se borran sus opciones/ramas y queda huérfano cualquier otro guion que lo tuviera como destino.").then(function (ok) {
            if (!ok) return;
            return fetch(baseUrl + "/guiones/" + n.id + "/borrar", { method: "POST" }).then(function (r) {
                if (!r.ok) throw new Error();
                quitarNodoDelEstado(n.id);
                render();
            });
        }).catch(function () { window.avisarApp("No se pudo borrar el guion."); });
    }

    // ---- Menú "⋮" por nodo — un popover flotante fuera del SVG (el
    // foreignObject recorta cualquier cosa que se dibuje dentro suyo, así
    // que no puede ser un hijo del nodo sin que el navegador lo corte).
    var menuAbierto = null;
    function cerrarMenuSiAfuera(ev) {
        if (menuAbierto && !menuAbierto.contains(ev.target)) cerrarMenu();
    }
    function cerrarMenu() {
        if (menuAbierto) { menuAbierto.remove(); menuAbierto = null; }
        document.removeEventListener("mousedown", cerrarMenuSiAfuera);
    }
    function abrirMenu(n, boton) {
        cerrarMenu();
        var rect = boton.getBoundingClientRect();
        var menu = document.createElement("div");
        menu.className = "diagrama-menu-popover";
        menu.style.top = (rect.bottom + 4) + "px";
        menu.style.left = (rect.right - 140) + "px";

        function item(texto, onClick, claseExtra) {
            var b = document.createElement("button");
            b.type = "button";
            b.textContent = texto;
            if (claseExtra) b.className = claseExtra;
            b.addEventListener("click", function () { cerrarMenu(); onClick(); });
            menu.appendChild(b);
        }
        item("Duplicar", function () { duplicarNodo(n); });
        if (n.estado !== "borrador") {
            item("Reabrir", function () { reabrirNodo(n); });
        }
        item("Borrar", function () { borrarNodo(n); }, "danger");

        document.body.appendChild(menu);
        menuAbierto = menu;
        document.addEventListener("mousedown", cerrarMenuSiAfuera);
    }

    function hacerMenu(n, div) {
        var boton = document.createElement("div");
        boton.className = "diagrama-menu-boton";
        boton.title = "Más acciones";
        boton.textContent = "⋮";
        div.appendChild(boton);
        boton.addEventListener("mousedown", function (ev) { ev.stopPropagation(); });
        boton.addEventListener("click", function (ev) {
            ev.stopPropagation();
            abrirMenu(n, boton);
        });
    }

    function borrarArista(a) {
        if (a.fallback) {
            window.avisarApp("El fallback no se puede borrar — todo guion de tipo libre necesita uno.");
            return;
        }
        window.confirmarApp("¿Borrar esta conexión?").then(function (ok) {
            if (!ok) return;
            var tramo = a.tipo === "opcion" ? "opciones" : "ramas";
            return fetch(baseUrl + "/guiones/" + a.origen + "/" + tramo + "/" + a.id + "/borrar", { method: "POST" }).then(function (r) {
                if (!r.ok) throw new Error();
                aristas = aristas.filter(function (x) { return !(x.id === a.id && x.tipo === a.tipo); });
                render();
            });
        }).catch(function () { window.avisarApp("No se pudo borrar la conexión."); });
    }

    function crearNodoEnClick(ev) {
        if (ev.target !== svg) return;
        var svgRect = svg.getBoundingClientRect();
        var x = Math.max(0, ev.clientX - svgRect.left - ANCHO_DEFAULT / 2);
        var y = Math.max(0, ev.clientY - svgRect.top - ALTO_NODO / 2);
        // El doble click abre el modal de siempre (fecha, tipo de respuesta,
        // modo de envío, es_entrada) con la posición ya cargada — así el
        // guion se termina de armar entero desde acá, sin ir a la tarjeta.
        var campoX = document.getElementById("modal-nuevo-guion-pos-x");
        var campoY = document.getElementById("modal-nuevo-guion-pos-y");
        if (campoX) campoX.value = Math.round(x);
        if (campoY) campoY.value = Math.round(y);
        var modal = document.getElementById("modal-nuevo-guion");
        if (modal) modal.showModal();
    }

    function render() {
        cerrarMenu();
        // Si ya habían agrandado el recuadro (tirando de la esquina), ese
        // alto se guarda en el propio elemento — lo rescatamos antes de
        // destruirlo para no perderlo en cada render, y para que el lienzo
        // también crezca hasta ahí (ver más abajo). clientHeight incluye el
        // padding del recuadro, pero el svg solo tiene lugar real adentro
        // del padding — si no se lo resta, el svg queda más alto que el
        // espacio disponible y aparece una scrollbar de más.
        var scrollPrevio = contenedor.querySelector(".diagrama-scroll");
        var altoCajaPrevia = scrollPrevio ? scrollPrevio.clientHeight : 0;
        var altoContenidoPrevio = 0;
        if (scrollPrevio) {
            var estiloScrollPrevio = window.getComputedStyle(scrollPrevio);
            altoContenidoPrevio = altoCajaPrevia
                - parseFloat(estiloScrollPrevio.paddingTop)
                - parseFloat(estiloScrollPrevio.paddingBottom);
        }

        var limites = limitesCanvas();
        // El lienzo nunca es más chico que el recuadro que lo contiene — ni
        // en ancho ni en alto — así el fondo punteado ocupa todo el
        // espacio en vez de dejar un hueco vacío.
        var anchoDisponible = contenedor.clientWidth || 0;
        limites.ancho = Math.max(limites.ancho, anchoDisponible);
        limites.alto = Math.max(limites.alto, altoContenidoPrevio);
        contenedor.innerHTML = "";
        nodoDivs = {};
        aristaInfo = [];

        svg = document.createElementNS(NS, "svg");
        svg.setAttribute("viewBox", "0 0 " + limites.ancho + " " + limites.alto);
        svg.setAttribute("width", limites.ancho);
        svg.setAttribute("height", limites.alto);
        svg.classList.add("diagrama-svg");
        svg.addEventListener("dblclick", crearNodoEnClick);

        var defs = document.createElementNS(NS, "defs");
        defs.innerHTML =
            '<marker id="diagrama-flecha" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
            '<path d="M0,0 L10,5 L0,10 z"></path></marker>';
        svg.appendChild(defs);

        aristas.forEach(function (a) {
            if (!(a.origen in porId)) return;
            var origenN = porId[a.origen];
            if (a.destino == null || !(a.destino in porId)) {
                var p = centroInferior(origenN);
                var texto = document.createElementNS(NS, "text");
                texto.setAttribute("x", p.x);
                texto.setAttribute("y", p.y + 16);
                texto.setAttribute("class", "diagrama-etiqueta fin");
                texto.textContent = (a.etiqueta ? a.etiqueta + " → " : "") + "fin";
                svg.appendChild(texto);
                // Sin destino real no hay arista que actualizar, pero el texto
                // tiene que acompañar al nodo si lo arrastran — se registra
                // igual que una arista, con destinoId null.
                aristaInfo.push({ origenId: a.origen, destinoId: null, finEl: texto });
                return;
            }
            var destinoN = porId[a.destino];
            var d = pathArista(origenN, destinoN);

            var hit = document.createElementNS(NS, "path");
            hit.setAttribute("d", d);
            hit.setAttribute("class", "diagrama-arista-hit");
            hit.addEventListener("click", function () { borrarArista(a); });
            svg.appendChild(hit);

            var path = document.createElementNS(NS, "path");
            path.setAttribute("d", d);
            path.setAttribute("class", "diagrama-arista" + (a.fallback ? " fallback" : ""));
            path.setAttribute("marker-end", "url(#diagrama-flecha)");
            svg.appendChild(path);

            var labelEl = null;
            if (a.etiqueta) {
                labelEl = document.createElementNS(NS, "text");
                labelEl.setAttribute("class", "diagrama-etiqueta");
                labelEl.textContent = a.etiqueta;
                svg.appendChild(labelEl);
            }
            aristaInfo.push({ origenId: a.origen, destinoId: a.destino, pathEl: path, labelEl: labelEl, hitEl: hit });
        });
        aristaInfo.forEach(function (info) {
            if (!info.labelEl) return;
            var p1 = centroInferior(porId[info.origenId]), p2 = centroSuperior(porId[info.destinoId]);
            info.labelEl.setAttribute("x", (p1.x + p2.x) / 2);
            info.labelEl.setAttribute("y", (p1.y + p2.y) / 2 - 4);
        });

        nodos.forEach(function (n) {
            var fo = document.createElementNS(NS, "foreignObject");
            fo.setAttribute("x", n.pos_x);
            fo.setAttribute("y", n.pos_y);
            fo.setAttribute("width", anchoDe(n));
            fo.setAttribute("height", ALTO_NODO);

            var clases = ["diagrama-nodo", "estado-" + n.estado];
            if (n.es_entrada) clases.push("entrada");
            if (n.huerfano) clases.push("huerfano");

            var div = document.createElement("div");
            div.className = clases.join(" ");
            div.dataset.id = n.id;

            var fila = document.createElement("div");
            fila.className = "diagrama-nodo-id";
            if (n.bifurcacion) {
                var rombo = document.createElement("span");
                rombo.className = "diagrama-rombo";
                rombo.title = "Se abre en más de un camino";
                fila.appendChild(rombo);
            }
            fila.appendChild(document.createTextNode(
                "#" + n.id + (n.es_entrada ? " · entrada" : "") + (n.huerfano ? " · ⚠" : "")
            ));

            var cuerpo = document.createElement("div");
            cuerpo.className = "diagrama-nodo-texto";
            cuerpo.textContent = n.texto;

            div.appendChild(fila);
            div.appendChild(cuerpo);
            fo.appendChild(div);
            svg.appendChild(fo);

            nodoDivs[n.id] = div;
            hacerArrastrable(n, div, fo);
            hacerRedimensionable(n, div, fo);
            hacerConectable(n, div);
            hacerMenu(n, div);
        });

        var scroll = document.createElement("div");
        scroll.className = "diagrama-scroll";
        if (altoCajaPrevia) scroll.style.height = altoCajaPrevia + "px";
        scroll.appendChild(svg);
        scroll.addEventListener("scroll", cerrarMenu);
        contenedor.appendChild(scroll);

        if (window.ResizeObserver) {
            if (resizeObserver) resizeObserver.disconnect();
            // Importante: esto NO puede llamar a render() — recrear el
            // propio recuadro que el navegador está arrastrando corta el
            // gesto de resize a mitad de camino (el elemento bajo el mouse
            // deja de existir). Solo se ajustan los atributos del svg ya
            // existente, en el lugar.
            resizeObserver = new ResizeObserver(function () {
                ajustarLienzoAlRecuadro(scroll);
            });
            resizeObserver.observe(scroll);
        }
    }

    function ajustarLienzoAlRecuadro(scrollEl) {
        if (!svg) return;
        var estilo = window.getComputedStyle(scrollEl);
        var altoContenido = scrollEl.clientHeight
            - parseFloat(estilo.paddingTop) - parseFloat(estilo.paddingBottom);
        var limites = limitesCanvas();
        var anchoFinal = Math.max(limites.ancho, contenedor.clientWidth || 0);
        var altoFinal = Math.max(limites.alto, altoContenido);
        svg.setAttribute("viewBox", "0 0 " + anchoFinal + " " + altoFinal);
        svg.setAttribute("width", anchoFinal);
        svg.setAttribute("height", altoFinal);
    }

    render();
})();
