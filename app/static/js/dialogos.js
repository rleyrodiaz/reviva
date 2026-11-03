(function () {
    "use strict";

    function iniciar() {
        iniciarConfirmar();
        iniciarPrompt();
        iniciarAviso();
        iniciarBotonesSinPermiso();
        iniciarModalesDesplazables();
        iniciarModalesAjax();
        iniciarMenuMovil();
        iniciarBotonesCerrarModal();
        iniciarTabs();
        iniciarBotonesEditarTexto();
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
                .then(function (html) { cuerpoEl.innerHTML = extraerFragmento(html); })
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
            // Aprobar/desactivar desde la Bandeja: en vez de quedarse mirando
            // la lista actualizada, cierra el modal y recarga la página de
            // atrás — así se ve al toque el nuevo estado de la conversación
            // en la pantalla donde estabas parado.
            if (form.dataset.cerrarYRecargar === "true") {
                fetch(form.action, { method: "POST", body: new FormData(form) })
                    .then(function () { window.location.reload(); })
                    .catch(function () { window.location.reload(); });
                return;
            }
            fetch(form.action, { method: "POST", body: new FormData(form) })
                .then(function (resp) { return resp.text(); })
                .then(function (html) { cuerpoEl.innerHTML = extraerFragmento(html); })
                .catch(function () { cuerpoEl.innerHTML = "<p class=\"hint\">No se pudo guardar. Probá de nuevo.</p>"; });
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
