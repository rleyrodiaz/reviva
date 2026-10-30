(function () {
    "use strict";

    var pacienteId = document.body.dataset.pacienteId;
    if (!pacienteId) return;

    var storageKey = "am_ultimo_id_" + pacienteId;
    var INTERVALO_MS = 8000;

    // Web Push (push.js + sw.js) avisa aunque la pestaña esté cerrada, pero
    // depende de permiso otorgado + suscripción viva + que el sistema
    // operativo no lo silencie — puede fallar en silencio por mil motivos.
    // Este beep es el respaldo confiable para cuando la pestaña SÍ está
    // abierta: no reemplaza a Push, lo complementa.
    var audioCtx = null;
    function desbloquearAudio() {
        if (audioCtx) return;
        var Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        try { audioCtx = new Ctx(); } catch (e) { /* sin soporte real */ }
    }
    ["pointerdown", "touchstart", "click"].forEach(function (evento) {
        document.addEventListener(evento, desbloquearAudio, { once: true, passive: true });
    });

    function sonarAviso() {
        if (navigator.vibrate) { try { navigator.vibrate(200); } catch (e) {} }
        if (!audioCtx) return;
        try {
            if (audioCtx.state === "suspended") audioCtx.resume();
            var osc = audioCtx.createOscillator();
            var gain = audioCtx.createGain();
            osc.type = "sine";
            osc.frequency.value = 880;
            gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.5);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.5);
        } catch (e) { /* autoplay bloqueado u otro error: no rompemos el polling por esto */ }
    }

    function chequear() {
        fetch("/chat/" + pacienteId + "/estado")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var actual = data.ultima_interaccion_id;
                var anterior = localStorage.getItem(storageKey);
                if (anterior === null) {
                    // Primera vez que este navegador chequea: solo establecemos la
                    // marca, no recargamos por mensajes que ya estaban ahí.
                    localStorage.setItem(storageKey, actual);
                    return;
                }
                // No solo ">" — un vaciado de chat borra interacciones y el id
                // combinado puede bajar. Cualquier cambio (subida o bajada)
                // significa que lo que ve esta pestaña ya no es lo real.
                if (actual !== Number(anterior)) {
                    localStorage.setItem(storageKey, actual);
                    if (actual > Number(anterior)) {
                        // Solo suena si es un mensaje nuevo de verdad (no si
                        // bajó por un vaciado de chat) — le damos un instante
                        // al beep antes de recargar la página.
                        sonarAviso();
                        setTimeout(function () { window.location.reload(); }, 300);
                        return;
                    }
                    window.location.reload();
                }
            })
            .catch(function () { /* sin conexión momentánea: reintenta en el próximo tick */ });
    }

    chequear();
    setInterval(chequear, INTERVALO_MS);
})();
