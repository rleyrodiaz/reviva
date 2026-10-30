(function () {
    "use strict";

    function iniciar() {
        iniciarConfirmar();
        iniciarPrompt();
        iniciarAviso();
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

        document.querySelectorAll("form[data-confirm]").forEach(function (form) {
            form.addEventListener("submit", function (evento) {
                if (form.dataset.confirmado === "true") return; // ya se confirmó, dejar pasar
                evento.preventDefault();
                formPendiente = form;
                textoEl.textContent = form.dataset.confirm;
                dialogo.showModal();
            });
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
