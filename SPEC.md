# SPEC — App de Estimulación Cognitiva con Personajes Ficticios

## 1. Contexto y objetivo

App donde una persona con dificultades cognitivas recibe mensajes de "personajes"
(personas reconocibles de su vida) en una interfaz tipo chat, y responde. Un motor
controla la secuencia: **Personaje → fecha → mensaje → respuesta → próxima interacción**.

**Decisión de transporte:** no se usa WhatsApp (prohíbe mensajería automatizada y
creación de cuentas no autorizadas). Se construye una interfaz propia (PWA) que clona
la experiencia visual de un chat conocido, sin depender de APIs de terceros para el
transporte de mensajes.

## 2. Stack

- Python 3.11 + FastAPI
- SQLAlchemy + PostgreSQL
- Jinja2 (server-side rendering) + HTMX/JS liviano para las partes dinámicas
- APScheduler para el disparo de mensajes programados
- Web Push API (VAPID) para notificaciones, sin dependencias de pago
- Desarrollo local (sin containerización), Windows 11
- Sesiones por cookie (como en el resto de tus proyectos)

## 3. Modelo de usuarios y permisos

Estructura de 3 niveles, análoga a la de movieLeyro:

- **Superadmin (vos):** acceso a todas las familias. Da de alta familias e invita
  familiares.
- **Familia:** unidad que agrupa a un paciente (la persona que recibe los mensajes)
  y a sus familiares.
- **Admin de familia:** familiar designado por el superadmin. Crea personajes,
  redacta guiones, decide fechas, y aprueba envíos en modo manual.
- **Usuario/familiar (rol lectura):** puede ver el progreso pero no edita guiones
  (alcance a definir más adelante, no bloqueante para el MVP).
- **Paciente:** no tiene login propio — accede directo a su vista de chat vía un
  link/dispositivo configurado por el admin (no necesita gestionar usuario/contraseña).

## 4. Modelo de datos (borrador de tablas)

```
Familia
  id, nombre, fecha_alta

Usuario
  id, familia_id (nullable si es superadmin), nombre, email, password_hash, rol
  rol: superadmin | admin_familia | familiar

Paciente
  id, familia_id, nombre, foto, notas

Personaje
  id, familia_id, nombre, foto, descripcion, relacion_con_paciente
  tono_escritura (texto libre, referencia para quien redacta los guiones)

Guion (nodo de conversación)
  id, personaje_id, fecha_programada, texto_mensaje
  modo_envio: manual | automatico
  estado: borrador | pendiente_aprobacion | enviado
  nodo_padre_id (nullable, solo referencia visual — no se usa en ningún cálculo)

RamaRespuestaLibre
  id, guion_id, criterio (descripción en lenguaje natural para el matching por IA),
  guion_siguiente_id
  -- incluye una rama "fallback" sin criterio: si la IA no puede clasificar
     la respuesta con confianza suficiente, se usa esa rama; si tampoco tiene
     un guion_siguiente armado, la IA genera un cierre breve en vez de dejar
     la conversación sin contestar

Interaccion (log)
  id, guion_id, paciente_id, respuesta_texto, rama_elegida_id,
  timestamp_envio, timestamp_respuesta
```

## 5. Motor de conversación — flujo

1. APScheduler corre periódicamente y busca guiones con `fecha_programada` vencida
   y `estado = borrador`.
2. Según `modo_envio`:
   - `manual`: pasa el guion a `pendiente_aprobacion` y aparece en el dashboard
     del admin para confirmar o editar antes de enviarse.
   - `automatico`: se envía directo (pasa a `estado = enviado`, aparece en el chat
     del paciente).
3. El paciente responde desde su interfaz de chat.
4. Si el nodo es de tipo `opciones`: la respuesta ya viene mapeada a un
   `guion_siguiente_id` directo — no hace falta matching.
5. Si el nodo es de tipo `libre`: la respuesta se envía a la API de Claude junto
   con la lista de `criterio` de las ramas posibles de ese guion, pidiendo que
   clasifique a cuál corresponde (o "ninguna" si no hay match claro).
   - Si matchea: avanza al `guion_siguiente_id` de esa rama.
   - Si no matchea (o confianza baja): dispara la rama fallback con quick reply.
6. El nuevo guion queda en estado `borrador` con su propia `fecha_programada`
   (puede ser inmediata o futura, según cómo lo cargó el admin) y vuelve al paso 1.

## 6. Matching con IA — diseño de la llamada

- Modelo: Claude vía API (volumen bajo, costo insignificante para este uso).
- Prompt estructurado: se le pasa el texto de respuesta del paciente + las
  descripciones de las ramas disponibles para ese guion puntual (no el guion
  completo, para mantener el contexto acotado y la clasificación precisa).
- Salida esperada: JSON con `rama_elegida` (id o "ninguna") + nivel de confianza.
- Si confianza baja o "ninguna" → fallback con quick reply.
- Esto es un adaptador aislado (una función `clasificar_respuesta()`) para poder
  ajustar el prompt o cambiar de proveedor sin tocar el resto del motor.

## 7. Interfaz del paciente

- PWA instalable ("Agregar a pantalla de inicio"), sin pasar por App Store/Play Store.
- Clona visualmente un chat conocido: lista de contactos (personajes) con foto y
  nombre, burbujas de conversación, hora de cada mensaje.
- Input de texto libre + botones de quick reply cuando corresponda.
- Notificación de mensaje nuevo vía Web Push.

## 8. Dashboard del admin

- CRUD de Personajes (nombre, foto, descripción, tono de escritura).
- Editor de Guiones: alta de nodos, fecha, texto, tipo de respuesta, ramas y
  guion siguiente por rama.
- Bandeja de `pendiente_aprobacion` para revisar/editar antes de enviar (modo manual).
- Toggle de `modo_envio` por guion (y a futuro, por personaje o global).
- Vista de progreso/log de interacciones del paciente.

## 9. Alcance del MVP

- 1 familia, 1 paciente, 1 personaje.
- Admin único (vos) carga guiones cortos a mano para probar el motor de punta a punta.
- Modo manual por defecto (podés forzar automático en un guion puntual para probar
  ese camino también).
- Sin notificaciones push todavía si complica el arranque — se puede probar primero
  con el paciente abriendo la PWA manualmente, y sumar Web Push en una segunda vuelta.
- Sin gestión de familiares/invitaciones todavía — alta de familia y usuarios a mano
  en la base para esta primera prueba.
- Deploy: local, sin hosting externo por ahora.

## 10. Fuera de alcance (por ahora, no bloqueante)

- Invitación de familiares por email/link.
- Múltiples familias simultáneas.
- Reportes o métricas de progreso cognitivo.
- Edición de guiones desde el celular (se asume que el admin carga desde desktop).
