(function () {
    "use strict";

    function iniciar() {
        iniciarConfirmar();
        iniciarPrompt();
        iniciarAviso();
        iniciarBotonesSinPermiso();
        iniciarModalesDesplazables();
        iniciarModalesAjax();
        iniciarModalesIframe();
        iniciarMenuMovil();
        iniciarBotonesCerrarModal();
        iniciarTabs();
        iniciarBotonesEditarTexto();
        iniciarConfirmarEscribiendo();
        dispararAutoAbrirChat(document);
    }

    // ---- MODO_DEMO: tras aprobar/disparar un guion o una historia (lo que
    // manda el mensaje de verdad), el backend deja un link oculto
    // [#auto-abrir-chat-iframe] (con data-modal-iframe) en el HTML que
    // devuelve — clickearlo por código dispara el mismo listener delegado
    // de iniciarModalesIframe, así se abre la ventana de WhatsApp sola,
    // directo a esa conversación. Hay que llamarlo tanto al cargar la
    // página entera (detalle de historia) como cada vez que
    // iniciarModalesAjax pisa el innerHTML del modal (Bandeja, que siempre
    // se abre así — ver data-modal-titulo en el nav). ----
    function dispararAutoAbrirChat(raiz) {
        var auto = raiz.querySelector("#auto-abrir-chat-iframe");
        if (auto) auto.click();
    }

    // ---- MODO_DEMO: tras aprobar algo con data-cerrar-y-recargar=true
    // (Bandeja), la respuesta real está en una URL con ?chat_disparado=...
    // (porque fetch sigue el redirect 303 solo) pero esa URL nunca llega a
    // la barra de direcciones — recargarDetras() la lee de ahí y la suma a
    // la página de atrás antes de recargarla, para que admin_base.html la
    // vea y abra la ventana de WhatsApp sola. ----
    function recargarDetras(urlRespuesta) {
        var params;
        try { params = new URL(urlRespuesta, window.location.href).searchParams; }
        catch (e) { params = new URLSearchParams(); }
        var personajeId = params.get("chat_disparado");
        var pacienteId = params.get("chat_disparado_paciente");
        if (!personajeId || !pacienteId) {
            window.location.reload();
            return;
        }
        var destino = new URL(window.location.href);
        destino.searchParams.set("chat_disparado", personajeId);
        destino.searchParams.set("chat_disparado_paciente", pacienteId);
        window.location.href = destino.toString();
    }

    // ---- Botones "Editar" genéricos (ej. hechos de familia validados):
    // [data-editar-texto] abre el mismo prompt de texto de siempre con el
    // valor actual precargado, y al confirmar manda el form hermano
    // [data-editar-form] con el nuevo valor — pasa por el mismo delegado de
    // submit de iniciarModalesAjax, así funciona igual dentro de un modal
    // o en la página completa. ----
    function iniciarBotonesEditarTexto() {
        document.addEventListener("click", function (ev) {
            var boton = ev.target.closest("[data-editar-texto]");
            if (!boton) return;
            var form = document.getElementById(boton.dataset.editarForm);
            if (!form) return;
            window.promptApp("Editar", boton.dataset.editarTexto).then(function (valor) {
                if (valor === null) return;
                form.querySelector('input[name="texto"]').value = valor;
                form.requestSubmit();
            });
        });
    }

    // ---- Modales desplazables: arrastrar desde el título (<h2>) mueve el
    // <dialog> entero. Se vuelve a centrar sola al cerrarse, para que la
    // próxima vez que se abra no aparezca corrida de donde la dejaron. ----
    function iniciarModalesDesplazables() {
        document.addEventListener("mousedown", function (ev) {
            var titulo = ev.target.closest("dialog > h2");
            if (!titulo) return;
            var dialogo = titulo.closest("dialog");
            if (!dialogo || !dialogo.open) return;
            ev.preventDefault();
            var rect = dialogo.getBoundingClientRect();
            dialogo.style.position = "fixed";
            dialogo.style.margin = "0";
            dialogo.style.left = rect.left + "px";
            dialogo.style.top = rect.top + "px";
            var startX = ev.clientX, startY = ev.clientY;
            var origLeft = rect.left, origTop = rect.top;

            function mover(ev2) {
                dialogo.style.left = (origLeft + ev2.clientX - startX) + "px";
                dialogo.style.top = (origTop + ev2.clientY - startY) + "px";
            }
            function soltar() {
                document.removeEventListener("mousemove", mover);
                document.removeEventListener("mouseup", soltar);
            }
            document.addEventListener("mousemove", mover);
            document.addEventListener("mouseup", soltar);
        });

        document.addEventListener("close", function (ev) {
            if (ev.target.tagName !== "DIALOG") return;
            ev.target.style.position = "";
            ev.target.style.margin = "";
            ev.target.style.left = "";
            ev.target.style.top = "";
        }, true);
    }

    // ---- X para cerrar, arriba a la derecha, en todos los <dialog> además
    // del botón de cerrar/cancelar que ya tengan abajo. Simula lo mismo que
    // haría Escape (dispara "cancel" y recién después cierra), así cualquier
    // Promise pendiente (confirmarApp/promptApp/avisarApp) se resuelve igual
    // que si lo hubieran cancelado por ese botón de abajo. ----
    function iniciarBotonesCerrarModal() {
        document.querySelectorAll("dialog").forEach(function (dialogo) {
            if (dialogo.querySelector(".modal-cerrar-x")) return;
            var boton = document.createElement("button");
            boton.type = "button";
            boton.className = "modal-cerrar-x";
            boton.setAttribute("aria-label", "Cerrar");
            boton.innerHTML = "&times;";
            boton.addEventListener("click", function () {
                dialogo.dispatchEvent(new Event("cancel", { cancelable: true }));
                dialogo.close();
            });
            dialogo.appendChild(boton);
        });
    }

    // ---- Tabs (ej. Pendientes/Validados/Descartados en Hechos de familia):
    // un grupo de botones [data-tabs] con [data-tab-btn] que muestran/ocultan
    // paneles hermanos [data-tab-panel] con el mismo nombre. Delegado en
    // document para que siga funcionando después de que iniciarModalesAjax
    // reemplace el contenido del modal. ----
    function iniciarTabs() {
        document.addEventListener("click", function (ev) {
            var boton = ev.target.closest("[data-tab-btn]");
            if (!boton) return;
            var grupo = boton.closest("[data-tabs]");
            if (!grupo) return;
            var destino = boton.dataset.tabBtn;
            grupo.querySelectorAll("[data-tab-btn]").forEach(function (b) {
                b.classList.toggle("activo", b === boton);
            });
            grupo.parentElement.querySelectorAll("[data-tab-panel]").forEach(function (panel) {
                panel.hidden = panel.dataset.tabPanel !== destino;
            });
        });
    }

    // ---- Botón que solo se habilita escribiendo un texto exacto (ej.
    // "BORRAR"/"RESET" en los resets de Settings) y, opcionalmente, con al
    // menos un checkbox de un grupo tildado. Delegado en document (no
    // document.getElementById + addEventListener puntual de la página)
    // porque un <script> propio de la página no se ejecuta cuando ese HTML
    // se carga adentro de un modal vía innerHTML (ver iniciarModalesAjax) —
    // así funciona igual en la página completa o adentro del modal.
    // [data-confirma-escribiendo]=texto esperado,
    // [data-habilita-boton]=id del botón a habilitar,
    // [data-requiere-chk]=selector opcional de checkboxes (alguno tildado). ----
    function iniciarConfirmarEscribiendo() {
        function evaluarTodos() {
            document.querySelectorAll("[data-confirma-escribiendo]").forEach(function (input) {
                var boton = document.getElementById(input.dataset.habilitaBoton);
                if (!boton) return;
                var textoOk = input.value === input.dataset.confirmaEscribiendo;
                var grupoOk = true;
                if (input.dataset.requiereChk) {
                    grupoOk = [].slice.call(document.querySelectorAll(input.dataset.requiereChk))
                        .some(function (c) { return c.checked; });
                }
                boton.disabled = !(textoOk && grupoOk);
            });
        }
        document.addEventListener("input", evaluarTodos);
        document.addEventListener("change", evaluarTodos);
    }

    // ---- Modal genérico "cargado por AJAX": lo usan los links con
    // data-modal-titulo (Bandeja, Hechos de familia) para abrir esa pantalla
    // en un <dialog> en vez de navegar — se trae el HTML de la página de
    // siempre y se le saca solo el fragmento #contenido-modal, así no hay
    // que duplicar ninguna plantilla. Los forms de adentro (aprobar,
    // desactivar, validar...) también se interceptan: se mandan por fetch
    // y, como el backend responde con un redirect 303 a la misma pantalla,
    // la respuesta ya trae el HTML actualizado — se vuelve a pisar el
    // contenido del modal con eso, sin cerrarlo. ----
    function iniciarModalesAjax() {
        var dialogo = document.getElementById("dialog-modal-contenido");
        if (!dialogo) return;
        var tituloEl = document.getElementById("dialog-modal-contenido-titulo");
        var cuerpoEl = document.getElementById("dialog-modal-contenido-cuerpo");

        function extraerFragmento(html) {
            var doc = new DOMParser().parseFromString(html, "text/html");
            var fragmento = doc.getElementById("contenido-modal");
            return fragmento ? fragmento.innerHTML : html;
        }

        function cargar(url) {
            cuerpoEl.innerHTML = "<p class=\"hint\">Cargando…</p>";
            return fetch(url)
                .then(function (resp) { return resp.text(); })
                .then(function (html) { cuerpoEl.innerHTML = extraerFragmento(html); dispararAutoAbrirChat(cuerpoEl); })
                .catch(function () { cuerpoEl.innerHTML = "<p class=\"hint\">No se pudo cargar. Probá de nuevo.</p>"; });
        }

        document.addEventListener("click", function (ev) {
            var link = ev.target.closest("a[data-modal-titulo]");
            if (!link) return;
            ev.preventDefault();
            tituloEl.textContent = link.dataset.modalTitulo;
            dialogo.showModal();
            cargar(link.getAttribute("href"));
        });

        document.addEventListener("submit", function (ev) {
            var form = ev.target.closest("form");
            if (!form || !cuerpoEl.contains(form)) return;
            if (form.dataset.confirm && form.dataset.confirmado !== "true") return; // dialogos.js confirma primero
            ev.preventDefault();
            // Respeta el method real del form — un form de filtros (ej.
            // Activity log) es GET: forzarlo a POST le pegaría a una ruta
            // que no la acepta.
            var esGet = (form.getAttribute("method") || "").toLowerCase() === "get";
            var url = form.action;
            var opciones = {};
            if (esGet) {
                url = form.action.split("?")[0] + "?" + new URLSearchParams(new FormData(form)).toString();
            } else {
                opciones = { method: "POST", body: new FormData(form) };
            }
            // Aprobar/desactivar desde la Bandeja: en vez de quedarse mirando
            // la lista actualizada, cierra el modal y recarga la página de
            // atrás — así se ve al toque el nuevo estado de la conversación
            // en la pantalla donde estabas parado.
            if (form.dataset.cerrarYRecargar === "true") {
                fetch(url, opciones)
                    .then(function (resp) { recargarDetras(resp.url); })
                    .catch(function () { window.location.reload(); });
                return;
            }
            fetch(url, opciones)
                .then(function (resp) { return resp.text(); })
                .then(function (html) { cuerpoEl.innerHTML = extraerFragmento(html); dispararAutoAbrirChat(cuerpoEl); })
                .catch(function () { cuerpoEl.innerHTML = "<p class=\"hint\">No se pudo guardar. Probá de nuevo.</p>"; });
        });
    }

    // ---- Modal "iframe" (MODO_DEMO): para páginas que no encajan como
    // fragmento de #contenido-modal (la app de chat del paciente, con su
    // propio layout/CSS/JS de PWA) — en vez de extraer un fragmento, carga
    // la URL entera en un <iframe> dentro de un modal con forma de teléfono.
    // Pensado para que una sola persona pueda probar la app haciendo de
    // usuario y de paciente a la vez, sin salir de la pestaña del admin. ----
    function iniciarModalesIframe() {
        var dialogo = document.getElementById("dialog-modal-iframe");
        if (!dialogo) return;
        var tituloEl = document.getElementById("dialog-modal-iframe-titulo");
        var frame = document.getElementById("dialog-modal-iframe-frame");

        document.addEventListener("click", function (ev) {
            var link = ev.target.closest("a[data-modal-iframe]");
            if (!link) return;
            ev.preventDefault();
            tituloEl.textContent = link.dataset.modalIframe || "WhatsApp";
            frame.src = link.getAttribute("href");
            dialogo.showModal();
        });

        // Al cerrar, descarga el iframe (about:blank) para no dejar corriendo
        // de fondo el polling de mensajes nuevos de chat.js.
        dialogo.addEventListener("close", function () {
            frame.src = "about:blank";
        });
    }

    // ---- Menú hamburguesa (mobile): colapsa el bloque .who del topbar
    // (links de familia + Admin + selector de familia + usuario) detrás de
    // un botón, para que no se amontone en pantallas chicas. ----
    function iniciarMenuMovil() {
        var boton = document.querySelector(".hamburguesa");
        var topbar = document.querySelector(".topbar");
        if (!boton || !topbar) return;
        boton.addEventListener("click", function (ev) {
            ev.stopPropagation();
            var abierto = topbar.classList.toggle("menu-abierto");
            boton.setAttribute("aria-expanded", abierto ? "true" : "false");
        });
        document.addEventListener("click", function (ev) {
            if (!topbar.contains(ev.target)) topbar.classList.remove("menu-abierto");
        });
    }

    // ---- Botones de acciones sin permiso (reemplazan el form real por uno
    // que solo avisa por qué no se puede, sin pasar por el modal de
    // confirmación — no hace falta confirmar algo que no se va a hacer). ----
    function iniciarBotonesSinPermiso() {
        document.querySelectorAll("[data-aviso]").forEach(function (boton) {
            boton.addEventListener("click", function (ev) {
                ev.preventDefault();
                window.avisarApp(boton.dataset.aviso);
            });
        });
    }

    // ---- Confirmar (reemplaza window.confirm) ----
    // Sirve a los forms con data-confirm (como siempre) y además expone
    // window.confirmarApp(texto) -> Promise<boolean> para el mapa visual.
    function iniciarConfirmar() {
        var dialogo = document.getElementById("dialog-confirmar");
        if (!dialogo) return;
        var textoEl = document.getElementById("dialog-confirmar-texto");
        var btnAceptar = document.getElementById("dialog-confirmar-aceptar");
        var btnCancelar = document.getElementById("dialog-confirmar-cancelar");
        var formPendiente = null;
        var resolverPendiente = null;

        function resolver(valor) {
            if (resolverPendiente) {
                var r = resolverPendiente;
                resolverPendiente = null;
                r(valor);
            }
        }

        // Delegado en document (no querySelectorAll+forEach fijo) para que
        // también funcione con forms cargados después por iniciarModalesAjax.
        document.addEventListener("submit", function (evento) {
            var form = evento.target.closest("form[data-confirm]");
            if (!form) return;
            if (form.dataset.confirmado === "true") return; // ya se confirmó, dejar pasar
            evento.preventDefault();
            formPendiente = form;
            textoEl.textContent = form.dataset.confirm;
            dialogo.showModal();
        });

        btnCancelar.addEventListener("click", function () {
            formPendiente = null;
            dialogo.close();
            resolver(false);
        });

        dialogo.addEventListener("cancel", function () {
            formPendiente = null;
            resolver(false);
        });

        btnAceptar.addEventListener("click", function () {
            dialogo.close();
            if (formPendiente) {
                var f = formPendiente;
                formPendiente = null;
                f.dataset.confirmado = "true";
                f.requestSubmit();
            }
            resolver(true);
        });

        window.confirmarApp = function (texto) {
            return new Promise(function (resolve) {
                resolverPendiente = resolve;
                textoEl.textContent = texto;
                dialogo.showModal();
            });
        };
    }

    // ---- Prompt de texto libre (reemplaza window.prompt) ----
    function iniciarPrompt() {
        var dialogo = document.getElementById("dialog-prompt");
        if (!dialogo) return;
        var tituloEl = document.getElementById("dialog-prompt-titulo");
        var input = document.getElementById("dialog-prompt-input");
        var btnAceptar = document.getElementById("dialog-prompt-aceptar");
        var btnCancelar = document.getElementById("dialog-prompt-cancelar");
        var resolverPendiente = null;

        function resolver(valor) {
            if (resolverPendiente) {
                var r = resolverPendiente;
                resolverPendiente = null;
                r(valor);
            }
        }

        function confirmarValor() {
            // Devuelve el texto tal cual (puede ser "" — algunos usos lo
            // tratan como una elección válida, no como un cancelar). Solo
            // Cancelar/Escape resuelven null.
            var valor = input.type === "text" ? input.value.trim() : input.value;
            dialogo.close();
            resolver(valor);
        }

        btnCancelar.addEventListener("click", function () {
            dialogo.close();
            resolver(null);
        });

        dialogo.addEventListener("cancel", function () { resolver(null); });

        btnAceptar.addEventListener("click", confirmarValor);

        input.addEventListener("keydown", function (ev) {
            if (ev.key === "Enter") { ev.preventDefault(); confirmarValor(); }
        });

        window.promptApp = function (titulo, valorInicial, tipo) {
            return new Promise(function (resolve) {
                resolverPendiente = resolve;
                tituloEl.textContent = titulo;
                input.type = tipo || "text";
                input.value = valorInicial || "";
                dialogo.showModal();
                input.focus();
                if (input.type === "text") input.select();
            });
        };
    }

    // ---- Aviso (reemplaza window.alert) ----
    function iniciarAviso() {
        var dialogo = document.getElementById("dialog-aviso");
        if (!dialogo) return;
        var textoEl = document.getElementById("dialog-aviso-texto");
        var btnCerrar = document.getElementById("dialog-aviso-cerrar");
        var resolverPendiente = null;

        function cerrar() {
            dialogo.close();
            if (resolverPendiente) {
                var r = resolverPendiente;
                resolverPendiente = null;
                r();
            }
        }

        btnCerrar.addEventListener("click", cerrar);
        dialogo.addEventListener("cancel", cerrar);

        window.avisarApp = function (texto) {
            return new Promise(function (resolve) {
                resolverPendiente = resolve;
                textoEl.textContent = texto;
                dialogo.showModal();
            });
        };
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
