# Flujo del Bot de Telegram — Generación de Certificados de Extintores
**AT&S Inversiones Antashely S.A.C.**

> **Stack:** n8n (orquestación) + Supabase (base de datos) + Python Service (generación de documentos)
> **Última revisión:** 2026-04-03

---

## Tabla de contenidos

1. [Flujo actual](#1-flujo-actual)
2. [Decisiones de diseño](#2-decisiones-de-diseño)
3. [Datos que se guardan](#3-datos-que-se-guardan)
4. [Estados de sesión](#4-estados-de-sesión)
5. [Mejoras futuras](#5-mejoras-futuras)

---

## 1. Flujo actual

El bot guía al operador paso a paso para registrar la información necesaria y generar un certificado de recarga o de extintor nuevo.

> **Nota:** El paso CERT_AGENTE fue eliminado en 2026-04-03 (Opción B). El `tipo_agente` ahora se deriva automáticamente del agente más frecuente en la lista de extintores.

### Diagrama de pasos

```
Usuario           Bot Telegram           n8n              Supabase       Python Service
  │                    │                  │                  │                 │
  │── /cert ──────────>│                  │                  │                 │
  │                    │── Solicita ──────>│                  │                 │
  │                    │   datos cliente   │                  │                 │
  │<── "Ingrese: ──────│                  │                  │                 │
  │    Nombre, RUC,    │                  │                  │                 │
  │    Dirección,      │                  │                  │                 │
  │    Distrito"       │                  │                  │                 │
  │                    │                  │                  │                 │
  │── datos cliente ──>│                  │                  │                 │
  │                    │── Guarda borrador>│── INSERT ────────>│                 │
  │<── Botones: ───────│                  │   registro_borrador│                │
  │    [Recarga]       │                  │                  │                 │
  │    [Extintor Nuevo]│                  │                  │                 │
  │                    │                  │                  │                 │
  │── selecciona tipo ─>│                 │                  │                 │
  │<── "Ingresa ───────│                  │                  │                 │
  │    extintores:     │                  │                  │                 │
  │    capacidad,clase │                  │                  │                 │
  │    (una por línea)"│                  │                  │                 │
  │                    │                  │                  │                 │
  │── lista extintores ─>│                │                  │                 │
  │<── Botones: ───────│                  │                  │                 │
  │    [Sí] [No]       │                  │                  │                 │
  │    (prueba hidro)  │                  │                  │                 │
  │                    │                  │                  │                 │
  │── responde hidro ──>│                 │                  │                 │
  │<── Resumen ────────│                  │                  │                 │
  │    + Botones:      │                  │                  │                 │
  │    [Generar Cert.] │                  │                  │                 │
  │    [Cancelar]      │                  │                  │                 │
  │                    │                  │                  │                 │
  │── Generar Cert. ───>│                 │── genera PDF/DOCX>│────────────────>│
  │                    │                  │                  │                 │── procesa
  │                    │                  │                  │<── archivo ─────│
  │                    │                  │── registra ──────>│                 │
  │                    │                  │   cliente y cert. │                 │
  │<── PDF + DOCX ─────│                  │                  │                 │
```

### Descripción detallada de cada paso

#### Paso 1 — Comando `/cert`
- El operador escribe `/cert` en el chat de Telegram.
- El bot responde solicitando los datos del cliente.
- Estado de sesión activo: `CERT_CLIENTE`.

#### Paso 2 — Datos del cliente
- El operador envía una línea con el formato:
  ```
  Nombre, RUC (o NN si no tiene), Dirección, Distrito
  ```
  Ejemplo: `Plaza Vea Los Olivos, 20601234567, Av. Universitaria 1234, Los Olivos`
- Si el RUC es `NN`, se registra sin RUC.
- El bot guarda los datos en `registro_borrador` y avanza al paso siguiente.

#### Paso 3 — Tipo de servicio
- El bot muestra dos botones de selección:
  - `Recarga`
  - `Extintor Nuevo`
- El valor seleccionado se almacena en el campo `tipo` del certificado.
- Estado de sesión activo: `CERT_TIPO`.

#### Paso 4 — Lista de extintores
- El bot solicita al operador ingresar cada extintor en una línea nueva:
  ```
  capacidad,clase
  capacidad,clase,marca,serie   (opcional)
  ```
  Ejemplo:
  ```
  6kg,PQS
  4kg,CO2
  9kg,PQS,IMPORTADO,SN2019
  ```
- Cada línea representa un extintor individual.
- La lista completa se guarda serializada en el campo `datos_json`.
- El `tipo_agente` del certificado se deriva automáticamente del agente (`clase`) más frecuente en esta lista. En caso de empate, se usa el del primer extintor.
- Estado de sesión activo: `CERT_EXTINTORES`.

#### Paso 5 — Prueba hidrostática
- El bot pregunta si el servicio incluye prueba hidrostática y muestra dos botones:
  - `Sí`
  - `No`
- La respuesta se incluye en `datos_json`.
- Estado de sesión activo: `CERT_HIDRO`.

#### Paso 6 — Resumen y confirmación
- El bot muestra un resumen completo de todos los datos recopilados:
  - Nombre del cliente, RUC, Dirección, Distrito
  - Tipo de servicio
  - Agente principal (derivado automáticamente)
  - Lista de extintores
  - Prueba hidrostática (sí/no)
- El operador puede confirmar o cancelar:
  - `Generar Certificado`
  - `Cancelar`
- Estado de sesión activo: `CERT_CONFIRMAR`.

#### Paso 7 — Generación de documentos
- Al confirmar, n8n invoca el Python Service con todos los datos.
- El Python Service genera:
  - Certificado en formato **PDF**
  - Certificado en formato **DOCX**
- Ambos archivos se envían directamente al chat de Telegram del operador.

#### Paso 8 — Registro en Supabase
- Se registra o actualiza el cliente en `bot_clientes.clientes`.
- Se crea el registro del certificado en `bot_clientes.certificados`.
- Se elimina la sesión temporal de `bot_clientes.registro_borrador`.

---

## 2. Decisiones de diseño

### 2.1 Eliminación del paso CERT_AGENTE (aplicado 2026-04-03)

**Problema original:** El flujo tenía dos pasos que pedían la misma información:
- Paso 4 (eliminado): botones PQS / CO2 / Gas Presurizada / Acetato Potasio
- Paso 5: campo `clase` por cada extintor (mismo dato, nivel individual)

Esto causaba fricción innecesaria y riesgo de inconsistencia si el operador elegía PQS en el paso 4 pero ingresaba CO2 en el paso 5.

**Decisión adoptada (Opción B):** El campo `tipo_agente` del certificado se deriva automáticamente como el agente más frecuente entre todos los extintores ingresados. En caso de empate, se usa el agente del primer extintor.

**Lógica de derivación (aplicada en "Construir Payload" y "Preparar Resumen"):**
```js
const freq = {};
for (const e of cd.extintores) {
  freq[e.clase] = (freq[e.clase] || 0) + 1;
}
const tipo_agente = Object.entries(freq).sort((a, b) => b[1] - a[1])[0][0];
```

**Resultado:** El flujo pasó de 6 pasos a 5. Se eliminaron 3 nodos del workflow n8n.

### 2.2 Uso del campo `clase` por extintor

El campo `clase` en cada extintor permite registrar servicios mixtos con total precisión. Cada unidad lleva su propio agente, independientemente del `tipo_agente` del certificado.

**Ejemplo de `datos_json` para un servicio mixto:**
```json
{
  "extintores": [
    { "capacidad": "6kg", "clase": "PQS" },
    { "capacidad": "6kg", "clase": "PQS" },
    { "capacidad": "5lb", "clase": "CO2" }
  ],
  "prueba_hidro": false
}
```
`tipo_agente` derivado = `"PQS"` (2 vs 1).

---

## 3. Datos que se guardan

### Schema de Supabase relevante

#### Tabla `bot_clientes.clientes`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | uuid / serial | Identificador único del cliente |
| `nombres` | text | Nombre completo o razón social |
| `nombre_comercial` | text | Nombre comercial (si aplica) |
| `ruc` | text | RUC del cliente (`NN` si no tiene) |
| `direccion` | text | Dirección del local |
| `distrito` | text | Distrito del local |

#### Tabla `bot_clientes.certificados`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | uuid / serial | Identificador único del certificado |
| `numero_certificado` | text | Número correlativo del certificado |
| `tipo` | text | `Recarga` o `Extintor Nuevo` |
| `tipo_agente` | text | Agente principal derivado automáticamente |
| `cliente_id` | uuid / int | Referencia al cliente en `clientes` |
| `fecha_servicio` | date | Fecha en que se realizó el servicio |
| `fecha_vencimiento` | date | Fecha de vencimiento del certificado |
| `datos_json` | jsonb | Lista de extintores y otros datos del servicio |
| `estado` | text | Estado del certificado (emitido, anulado, etc.) |

**Estructura esperada de `datos_json`:**
```json
{
  "extintores": [
    { "capacidad": "6kg", "clase": "PQS" },
    { "capacidad": "4kg", "clase": "PQS" }
  ],
  "prueba_hidro": false
}
```

#### Tabla `bot_clientes.registro_borrador`

| Campo | Tipo | Descripción |
|---|---|---|
| `chat_id` | bigint | ID del chat de Telegram del operador |
| `campo_editando` | text | Estado actual del flujo |
| `backup_texto` | text / jsonb | Datos acumulados de la sesión en curso |

El registro se elimina al confirmar o cancelar el flujo.

---

## 4. Estados de sesión

El campo `campo_editando` en `registro_borrador` indica en qué paso del flujo se encuentra el operador:

```
CERT_CLIENTE
     │
     ▼
CERT_TIPO
     │
     ▼
CERT_EXTINTORES   ← tipo_agente se deriva aquí automáticamente
     │
     ▼
CERT_HIDRO
     │
     ▼
CERT_CONFIRMAR
     │
     ├── [Confirmar] → genera documentos, registra en BD, elimina borrador
     └── [Cancelar]  → elimina borrador, fin del flujo
```

| Estado | Qué espera el bot |
|---|---|
| `CERT_CLIENTE` | Texto con `Nombre, RUC, Dirección, Distrito` |
| `CERT_TIPO` | Callback de botón: `Recarga` o `Extintor Nuevo` |
| `CERT_EXTINTORES` | Texto multilínea con `capacidad,clase` por extintor |
| `CERT_HIDRO` | Callback de botón: `Si` o `No` |
| `CERT_CONFIRMAR` | Callback de botón: `Generar Certificado` o `Cancelar` |

---

## 5. Mejoras futuras

### Corto plazo

- **Validación del formato de extintores:** Verificar que cada línea cumpla el formato `capacidad,clase` y devolver error claro si es incorrecto.
- **Validación del RUC:** Si el RUC no es `NN`, verificar que tenga 11 dígitos numéricos.

### Mediano plazo

- **Búsqueda de cliente existente:** Al ingresar datos del cliente, buscar en `bot_clientes.clientes` por RUC o nombre similar y preguntar si reutilizar o crear nuevo.
- **Edición de campos:** Permitir al operador volver al paso anterior sin reiniciar el flujo.
- **Historial de certificados:** Comando `/historial RUC` con los últimos certificados del cliente.
- **Numeración automática:** Generar `numero_certificado` de forma correlativa desde Supabase sin intervención manual.

### Largo plazo

- **Panel web de consulta:** Interfaz para buscar, ver e imprimir certificados sin Telegram.
- **Notificaciones de vencimiento:** Job que avise al operador 30 días antes del vencimiento.
- **Soporte múltiples operadores:** Control de acceso por `chat_id`.
- **Firma digital en PDF:** QR de verificación en el PDF generado.
