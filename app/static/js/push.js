(function () {
    "use strict";

    var pacienteId = document.body.dataset.pacienteId;
    var pushHabilitado = document.body.dataset.pushHabilitado === "true";
    if (!pacienteId || !("serviceWorker" in navigator) || !("PushManager" in window)) return;

    function urlBase64ToUint8Array(base64String) {
        var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
        var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
        var raw = atob(base64);
        var arr = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
        return arr;
    }

    function suscribir(registration) {
        fetch("/push/vapid-public-key")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.public_key) throw new Error("VAPID no configurado");
                return registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(data.public_key),
                });
            })
            .then(function (subscription) {
                return fetch("/push/" + pacienteId + "/suscribir", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(subscription.toJSON()),
                });
            })
            .catch(function () { /* permiso denegado, o navegador sin soporte: no hacemos nada */ });
    }

    function desuscribirSiHaceFalta(registration) {
        registration.pushManager.getSubscription().then(function (existente) {
            if (!existente) return;
            var info = existente.toJSON();
            existente.unsubscribe().then(function () {
                fetch("/push/" + pacienteId + "/desuscribir", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ endpoint: info.endpoint }),
                }).catch(function () {});
            });
        });
    }

    navigator.serviceWorker.register("/sw.js").then(function (registration) {
        if (!pushHabilitado) {
            desuscribirSiHaceFalta(registration);
            return;
        }
        registration.pushManager.getSubscription().then(function (existente) {
            if (existente) return;
            if (Notification.permission === "denied") return;
            Notification.requestPermission().then(function (permiso) {
                if (permiso === "granted") suscribir(registration);
            });
        });
    }).catch(function () { /* service worker no disponible en este navegador */ });
})();
