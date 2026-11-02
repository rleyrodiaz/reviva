(function () {
    "use strict";

    var box = document.getElementById("chat-messages");
    var inputBar = document.getElementById("chat-input-bar");
    if (!box || !inputBar) return;

    var partes = window.location.pathname.split("/").filter(Boolean); // ["chat", pacienteId, personajeId]
    var pacienteId = partes[1];
    var personajeId = partes[2];
    if (!pacienteId || !personajeId) return;
    var baseUrl = "/chat/" + pacienteId + "/" + personajeId;

    // Timing del "visto": un tilde apenas se manda, el segundo a los 3
    // segundos, y los dos se ponen celestes al llegar a los 4 — como pedido.
    var TIEMPO_SEGUNDO_TILDE = 3000;
    var TIEMPO_LEIDO = 4000;
    // Demora de "está escribiendo" para la devolución del personaje: no
    // aparece antes de que el "visto" termine, y después un poco más según
    // el largo del mensaje, para que se sienta como que lo tipeó.
    var ESCRITURA_MS_POR_CARACTER = 45, ESCRITURA_MIN = 1200, ESCRITURA_MAX = 4000;

    var NS_SVG = "http://www.w3.org/2000/svg";

    function horaActual() {
        var d = new Date();
        function dosDigitos(n) { return (n < 10 ? "0" : "") + n; }
        return dosDigitos(d.getHours()) + ":" + dosDigitos(d.getMinutes());
    }

    function crearBurbujaSalida(texto) {
        var div = document.createElement("div");
        div.className = "bubble bubble-out";
        var textoDiv = document.createElement("div");
        textoDiv.className = "bubble-text";
        textoDiv.textContent = texto;
        var tiempoDiv = document.createElement("div");
        tiempoDiv.className = "bubble-time";
        tiempoDiv.appendChild(document.createTextNode(horaActual()));

        var svg = document.createElementNS(NS_SVG, "svg");
        svg.setAttribute("viewBox", "0 0 16 11");
        svg.setAttribute("width", "16");
        svg.setAttribute("height", "11");
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("class", "tilde-estado");
        var tick1 = document.createElementNS(NS_SVG, "path");
        tick1.setAttribute("class", "tick tick-1");
        tick1.setAttribute("d", "M11.1 0.6 4.6 7.1 2.4 4.9 1 6.3l3.6 3.6L12.5 2z");
        var tick2 = document.createElementNS(NS_SVG, "path");
        tick2.setAttribute("class", "tick tick-2");
        tick2.setAttribute("d", "M15.1 0.6 8.6 7.1l-1-1-1.4 1.4 2.4 2.4L16.5 2z");
        svg.appendChild(tick1);
        svg.appendChild(tick2);
        tiempoDiv.appendChild(svg);

        div.appendChild(textoDiv);
        div.appendChild(tiempoDiv);
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
        return svg;
    }

    function crearBurbujaEntrada(texto) {
        var div = document.createElement("div");
        div.className = "bubble bubble-in";
        var textoDiv = document.createElement("div");
        textoDiv.className = "bubble-text";
        textoDiv.textContent = texto;
        var tiempoDiv = document.createElement("div");
        tiempoDiv.className = "bubble-time";
        tiempoDiv.textContent = horaActual();
        div.appendChild(textoDiv);
        div.appendChild(tiempoDiv);
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }

    function renderizarInputBar(tipo) {
        if (!tipo) {
            inputBar.innerHTML = "";
            return;
        }
        inputBar.innerHTML =
            '<form method="post" action="' + baseUrl + '/responder" class="text-input-form">' +
            '<input type="text" name="texto" placeholder="Escribí un mensaje..." autofocus required autocomplete="off">' +
            '<button type="submit" class="send-btn">&#10148;</button></form>';
    }

    function sincronizarPolling() {
        // notificaciones.js recarga la página si ve subir el contador de
        // mensajes — como ya sabemos que el que subió es el nuestro, le
        // avisamos la marca actual para que no interrumpa la animación.
        fetch("/chat/" + pacienteId + "/estado")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                try {
                    localStorage.setItem("am_ultimo_id_" + pacienteId, data.ultima_interaccion_id);
                } catch (e) { /* localStorage no disponible: no pasa nada */ }
            })
            .catch(function () {});
    }

    function enviar(datos, textoVisible) {
        var svgTilde = crearBurbujaSalida(textoVisible);
        var inicio = Date.now();
        setTimeout(function () { svgTilde.classList.add("tilde-dos"); }, TIEMPO_SEGUNDO_TILDE);
        setTimeout(function () { svgTilde.classList.add("tilde-leido"); }, TIEMPO_LEIDO);

        inputBar.innerHTML = "";

        var cuerpo = Object.keys(datos)
            .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(datos[k]); })
            .join("&");

        fetch(baseUrl + "/responder", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: cuerpo,
        })
            .then(function (r) {
                if (!r.ok) throw new Error("respuesta no ok");
                return r.json();
            })
            .then(function (data) {
                sincronizarPolling();
                var textoRespuesta = data.respuesta_texto;
                var tiempoEscritura = textoRespuesta
                    ? Math.min(ESCRITURA_MAX, Math.max(ESCRITURA_MIN, textoRespuesta.length * ESCRITURA_MS_POR_CARACTER))
                    : 0;
                var esperarHasta = TIEMPO_LEIDO + tiempoEscritura;
                var transcurrido = Date.now() - inicio;
                var faltante = Math.max(0, esperarHasta - transcurrido);
                setTimeout(function () {
                    if (textoRespuesta) crearBurbujaEntrada(textoRespuesta);
                    renderizarInputBar(data.siguiente_tipo);
                }, faltante);
            })
            .catch(function () {
                // Algo falló (red, 400, etc.): recargamos para quedar en
                // sintonía con lo que de verdad pasó en el servidor.
                window.location.reload();
            });
    }

    inputBar.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var form = ev.target;
        var datosForm = new FormData(form);
        var texto = (datosForm.get("texto") || "").trim();
        if (!texto) return;
        enviar({ texto: texto }, texto);
    });
})();
