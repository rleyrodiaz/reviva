self.addEventListener("push", function (event) {
    var data = {};
    try { data = event.data ? event.data.json() : {}; } catch (e) { /* payload no era JSON */ }

    var titulo = data.titulo || "Nuevo mensaje";
    var opciones = {
        body: data.cuerpo || "",
        data: { url: data.url || "/" },
        requireInteraction: false,
    };
    event.waitUntil(self.registration.showNotification(titulo, opciones));
});

self.addEventListener("notificationclick", function (event) {
    event.notification.close();
    var url = (event.notification.data && event.notification.data.url) || "/";
    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (lista) {
            for (var i = 0; i < lista.length; i++) {
                if (lista[i].url.indexOf(url) !== -1 && "focus" in lista[i]) {
                    return lista[i].focus();
                }
            }
            if (clients.openWindow) return clients.openWindow(url);
        })
    );
});
