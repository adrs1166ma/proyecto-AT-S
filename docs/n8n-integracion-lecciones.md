# Lecciones aprendidas: Integración de generación de archivos binarios en n8n

**Proyecto:** AT&S Certificados Bot  
**Stack:** n8n v2.14.2 (Render) + Supabase + Python FastAPI (fpdf2, python-docx)  
**Fecha:** Abril 2026  

---

## Resumen ejecutivo

La integración de generación de certificados PDF/DOCX en un bot de Telegram via n8n tomó múltiples iteraciones debido a restricciones no documentadas específicas de la combinación **n8n v2.14.2 + task runner + filesystem binary mode + nodo Telegram v1.2**. Este documento registra cada problema, su causa raíz, la solución aplicada, y lo que NO está en la documentación oficial.

---

## Arquitectura final implementada

```
Telegram → n8n Trigger
         → Normalizar Input (Code node)
         → Obtener Sesion (Postgres)
         → Combinar y Determinar Accion (Code node)
         → Enrutador (Switch)
         → [rama confirmación]
         → Construir Payload (Code node)
         → Validar Payload (IF node)
         → Llamar Servicio Python (HTTP Request) ← POST /generar-certificado
         → Preparar Archivos (Code node) ← crea binary inline
         → fan-out:
             ├── Enviar PDF (HTTP Request → Telegram API)
             ├── Enviar DOCX (HTTP Request → Telegram API)
             └── Registrar Cliente BD (Postgres)
                 → Registrar Certificado BD (Postgres)
                     → Limpiar Sesion OK (Postgres)
```

---

## Problemas encontrados y soluciones

### Problema 1: Payload incompleto → 422 del servicio Python

**Síntoma:** El nodo "Llamar Servicio Python" enviaba un JSON con solo 3 campos en vez de los 8 requeridos. FastAPI respondía 422 Unprocessable Entity.

**Causa raíz:**  
En JavaScript, `JSON.stringify()` **descarta silenciosamente** los valores `undefined`. Cuando `certData = {}` (sesión expirada o botón viejo), los campos como `cd.tipo` son `undefined` y no aparecen en el JSON serializado. Sin embargo, los campos con fallback `|| false` o `|| null` sí aparecen (como `prueba_hidrostatica: false`), dando un payload parcialmente formado que confunde a Pydantic.

**Solución aplicada:**  
Validación explícita en el nodo "Construir Payload" antes de llamar al servicio:
```javascript
if (!cd.tipo || !cd.cliente || !cd.extintores || !cd.fecha_emision) {
  return [{ json: { error: true, chatId: d.chatId, msg: '⚠️ Sesión expirada...' } }];
}
```
Seguido de un nodo IF "Validar Payload" que enruta al mensaje de error si `error === true`.

**Lo que NO dice la documentación de n8n:**  
- No hay advertencia sobre `JSON.stringify` y `undefined` en el contexto de Code nodes.
- El error 422 de un HTTP Request downstream no da pista sobre cuál campo falta en la UI de n8n.

---

### Problema 2: CHECK constraint en Supabase rechazaba INSERT

**Síntoma:** Error de Postgres al insertar en `bot_clientes.certificados`: violación de constraint `certificados_estado_check`.

**Causa raíz:**  
La constraint original en la tabla solo permitía `('BORRADOR', 'CANCELADO', 'ERROR')`. El valor `'COMPLETADO'` no estaba incluido.

**Solución aplicada:**  
Migration via Supabase MCP:
```sql
ALTER TABLE bot_clientes.certificados
  DROP CONSTRAINT certificados_estado_check,
  ADD CONSTRAINT certificados_estado_check
    CHECK (estado IN ('BORRADOR', 'COMPLETADO', 'CANCELADO', 'ERROR'));
```

**Lección:** Siempre definir todos los valores del enum desde el inicio del schema.

---

### Problema 3: Telegram sendDocument → 404 Not Found ⚠️ CAUSA RAÍZ NO IDENTIFICADA

**Síntoma:** El nodo Telegram v1.2 con `resource: "file"`, `operation: "sendDocument"`, `binaryData: true` devolvía `404 - {"ok":false,"error_code":404,"description":"Not Found"}` de la API de Telegram.

**Lo que SE descartó como causa:**
- ❌ chatId incorrecto (sendMessage funcionaba con el mismo chatId)
- ❌ Token inválido (otros nodos Telegram del mismo credential funcionaban)
- ❌ Binary data ausente (visible y descargable en la UI de n8n con el botón Download)
- ❌ Parámetros JSON incorrectos (`binaryData: true`, `binaryPropertyName: "pdfFile"` son los nombres correctos según el source code de `Telegram.node.ts`)

**Análisis del source code de n8n (Telegram.node.ts):**
```typescript
// Para sendDocument con binaryData:
const binaryPropertyName = this.getNodeParameter('binaryPropertyName', i);
const itemBinaryData = this.helpers.assertBinaryData(i, binaryPropertyName);
if (itemBinaryData.id) {
    uploadData = await this.helpers.getBinaryStream(itemBinaryData.id);
} else {
    uploadData = Buffer.from(itemBinaryData.data, BINARY_ENCODING);
}
const formData = { ...body, [propertyName]: { value: uploadData, options: { filename, contentType } } };
responseData = await apiRequest.call(this, requestMethod, endpoint, {}, qs, { formData });
```

**Hipótesis más probable (no confirmada):**  
Posible conflicto entre `json: true` y `formData` en la función `apiRequest` al serializar el request multipart cuando el binary viene del task runner (Code node aislado). El task runner guarda el binary en filesystem pero podría haber una discrepancia en cómo el nodo Telegram lee el stream vs cómo lo guardó el task runner.

**Solución aplicada (workaround):**  
Reemplazar los nodos Telegram de `sendDocument` con **nodos HTTP Request** que llaman a `https://api.telegram.org/bot{TOKEN}/sendDocument` directamente via multipart form-data:
```json
{
  "method": "POST",
  "url": "={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/sendDocument' }}",
  "contentType": "multipart-form-data",
  "bodyParameters": {
    "parameters": [
      {"name": "chat_id", "value": "={{ $json.chatId }}"},
      {"name": "document", "parameterType": "formBinaryData", "inputDataFieldName": "pdfFile"},
      {"name": "caption", "value": "={{ $json.numCert + '.pdf' }}"}
    ]
  }
}
```

---

### Problema 4: `$helpers.prepareBinaryData` no disponible en Code node

**Síntoma:** `ReferenceError: $helpers is not defined` en el nodo "Preparar Archivos".

**Causa raíz:**  
En n8n v2.14.2 con `N8N_RUNNERS_ENABLED=true`, los Code nodes se ejecutan en un subprocess aislado (`@n8n/task-runner`) vía `@n8n/task-runner/dist/js-task-runner/js-task-runner.js`. Este entorno **no expone** `$helpers` ni `this.helpers`.

**Variables/funciones disponibles en Code node (task runner):**
- ✅ `$input`, `$('NodeName')`, `$json`, `$binary`
- ✅ `$vars` (requiere plan Enterprise), `$env` (si no está bloqueado)
- ✅ `$workflow`, `$execution`, `$item`
- ❌ `$helpers.prepareBinaryData()`
- ❌ `this.helpers`

**Formato correcto para binary data en Code node (task runner):**
```javascript
return [{
  json: { chatId, numCert, ... },
  binary: {
    pdfFile: {
      data: base64String,        // string base64
      mimeType: 'application/pdf',
      fileName: 'CERT-2026-001.pdf',
      fileExtension: 'pdf'
    }
  }
}];
```
Este formato SÍ funciona. n8n convierte el base64 a un archivo en el filesystem binary storage.

**Lo que NO dice la documentación oficial:**  
La documentación de n8n para Code nodes menciona `$helpers.prepareBinaryData()` como método recomendado, pero no advierte que este método **no está disponible cuando `N8N_RUNNERS_ENABLED=true`**.

---

### Problema 5: `$env` bloqueado por defecto

**Síntoma:** `ExpressionError: access to env vars denied` al usar `$env.TELEGRAM_BOT_TOKEN` en un nodo HTTP Request.

**Causa raíz:**  
n8n v2.14.2 activa `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` por defecto (o via configuración interna). La variable **no aparece** en el panel de Environment de Render pero aun así está activa.

**Solución:** Agregar explícitamente en Render Environment:
```
N8N_BLOCK_ENV_ACCESS_IN_NODE = false
```

**Lo que NO dice la documentación:**  
No hay advertencia de que esta variable cambia su valor por defecto en versiones recientes ni que puede estar activa sin aparecer en las variables de entorno configuradas por el usuario.

---

### Problema 6: n8n Variables requiere plan de pago

**Síntoma:** Al intentar usar `$vars.TELEGRAM_BOT_TOKEN`, la sección Variables en n8n muestra "Upgrade to unlock variables".

**Causa raíz:** La función Variables de n8n es una feature de pago incluso en self-hosted.

**Alternativa funcional:** Variables de entorno en Render + `$env.VARIABLE_NAME` (una vez desbloqueado el acceso).

---

## Restricciones no documentadas de n8n (resumen)

| Restricción | Versión detectada | Documentada |
|-------------|-------------------|-------------|
| `$helpers` no disponible con task runner | v2.14.2 | ❌ No |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` activo por defecto | v2.14.2 | ❌ No |
| Nodos Postgres no pasan binary data downstream | General | ⚠️ Implícito |
| `$vars` requiere plan Enterprise | v2.x | ✅ Sí (letra pequeña) |
| Telegram node v1.2 sendDocument falla con filesystem binary | v2.14.2 | ❌ No |
| Code node binary inline requiere formato `{data, mimeType, fileName, fileExtension}` | v2.14.2 | ⚠️ Parcial |

---

## Patrón de arquitectura recomendado para binary files en n8n

```
[Code node] → genera binary inline {data: base64, ...}
     ↓ fan-out (NO pasar por Postgres nodes)
[HTTP Request node] → llama API externa con formBinaryData
     ↓ (rama paralela)
[Postgres node] → registra en BD (ignora binary, solo usa $json)
```

**Regla crítica:** Los nodos Postgres **rompen la cadena de binary data**. Si necesitas enviar un archivo Y guardar en BD, usa **fan-out paralelo** desde el nodo que tiene el binary, no secuencial.

---

## Herramienta: build_workflow.py

Para proyectos n8n con lógica compleja, se recomienda el patrón de generar el workflow JSON desde Python en lugar de editarlo directamente.

**Estructura del patrón:**
```python
# Constantes de credenciales
CRED_TELEGRAM = {"id": "...", "name": "..."}
CRED_POSTGRES  = {"id": "...", "name": "..."}

# Helper para definir nodos
def node(id, name, type, params, pos, ...): ...
def conn(from_node, to_nodes): ...

# Lista de nodos
NODES = [
    node("id-001", "Nombre Nodo", "n8n-nodes-base.code", {...}, [x, y]),
    ...
]

# Mapa de conexiones
CONNECTIONS = {
    "Nodo A": conn("Nodo A", "Nodo B"),
    ...
}
```

**Ventajas sobre editar JSON directamente:**
- Legible y mantenible
- Regeneración en segundos tras cambios
- Detección de errores antes de importar
- Versionable en git de forma legible
- Reutilizable: solo cambiar NODES, CONNECTIONS y credenciales para nuevo proyecto

---

## Referencias técnicas consultadas

- `packages/nodes-base/nodes/Telegram/Telegram.node.ts` — lógica sendDocument
- `packages/nodes-base/nodes/Telegram/GenericFunctions.ts` — construcción de URL `${baseUrl}/bot${token}/${endpoint}`
- `packages/nodes-base/nodes/HttpRequest/V3/HttpRequestV3.node.ts` — `parameterType: "formBinaryData"`
- `packages/nodes-base/credentials/TelegramApi.credentials.ts` — estructura de credencial
- `packages/@n8n/task-runner/dist/js-task-runner/js-task-runner.js` — entorno aislado de Code nodes
