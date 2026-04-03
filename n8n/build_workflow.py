"""
build_workflow.py — Generador del workflow n8n "Certificado Extintor - Bot"

Uso:
    python build_workflow.py          → genera certificado-bot.json
    python build_workflow.py --check  → valida conexiones y nodos

Este script define todos los nodos de forma legible en Python y genera
el JSON listo para importar en n8n. Editar aquí en vez de editar el JSON
directamente — mucho más seguro y fácil de mantener.
"""

import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).parent / "certificado-bot.json"

# ─────────────────────────────────────────────
# Credenciales (IDs existentes en el n8n)
# ─────────────────────────────────────────────
CRED_TELEGRAM = {"id": "mdQ5YLhQqIfiBGXG", "name": "Test-CRM"}
CRED_POSTGRES  = {"id": "zq4GDVSwUY2kETtI", "name": "Postgres account"}

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def node(id_, name, type_, params, pos, type_version=None, always_output=False, credentials=None, continue_on_fail=False):
    n = {
        "parameters": params,
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": type_version or _default_version(type_),
        "position": pos,
    }
    if always_output:
        n["alwaysOutputData"] = True
    if credentials:
        n["credentials"] = credentials
    if continue_on_fail:
        n["continueOnFail"] = True
    return n

def _default_version(t):
    defaults = {
        "n8n-nodes-base.telegramTrigger": 1.1,
        "n8n-nodes-base.telegram": 1.2,
        "n8n-nodes-base.code": 2,
        "n8n-nodes-base.postgres": 2.4,
        "n8n-nodes-base.httpRequest": 4.2,
        "n8n-nodes-base.switch": 3,
        "n8n-nodes-base.if": 2,
    }
    return defaults.get(t, 1)

def conn(from_node, to_nodes):
    """to_nodes: str | list[str] — lista de nodos destino (output 0 a N)"""
    if isinstance(to_nodes, str):
        to_nodes = [[to_nodes]]  # un solo output con un solo destino
    # Si es lista de strings → fan-out en el mismo output 0
    if isinstance(to_nodes[0], str):
        return {"main": [[{"node": n, "type": "main", "index": 0} for n in to_nodes]]}
    # Si es lista de listas → múltiples outputs (Switch node)
    return {"main": [[{"node": n, "type": "main", "index": 0} for n in branch] for branch in to_nodes]}

def tg(params, credentials=None):
    return {**params, **({"credentials": {"telegramApi": credentials or CRED_TELEGRAM}} if True else {})}

# ─────────────────────────────────────────────
# NODOS
# ─────────────────────────────────────────────

NODES = [

    # ── Trigger ──────────────────────────────
    node("cb01-trig-0001", "Telegram Trigger", "n8n-nodes-base.telegramTrigger",
         {"updates": ["message", "callback_query"], "additionalFields": {}},
         [-1000, 300],
         credentials={"telegramApi": CRED_TELEGRAM},
         type_version=1.1),

    # ── Normalizar Input ─────────────────────
    node("cb01-norm-0002", "Normalizar Input", "n8n-nodes-base.code",
         {"jsCode": (
             "const data = $input.first().json;\n"
             "const isCallback = !!data.callback_query;\n"
             "let chatId, text, callbackData, messageId;\n\n"
             "if (isCallback) {\n"
             "  chatId = data.callback_query.message.chat.id;\n"
             "  callbackData = data.callback_query.data || '';\n"
             "  messageId = data.callback_query.message.message_id;\n"
             "  text = null;\n"
             "} else {\n"
             "  chatId = data.message?.chat?.id;\n"
             "  text = data.message?.text || '';\n"
             "  callbackData = '';\n"
             "  messageId = data.message?.message_id;\n"
             "}\n\n"
             "return [{ json: { chatId, text, callbackData, messageId, isCallback } }];"
         )},
         [-800, 300]),

    # ── Obtener Sesion ───────────────────────
    node("cb01-sesn-0003", "Obtener Sesion", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "SELECT campo_editando, backup_texto FROM bot_clientes.registro_borrador WHERE chat_id = {{ $json.chatId }} LIMIT 1;",
          "options": {}},
         [-600, 300], always_output=True,
         credentials={"postgres": CRED_POSTGRES}),

    # ── Combinar y Determinar Accion ─────────
    node("cb01-comb-0004", "Combinar y Determinar Accion", "n8n-nodes-base.code",
         {"jsCode": (
             "const input = $('Normalizar Input').first().json;\n"
             "const rows = $input.all();\n"
             "const session = rows.length > 0 ? rows[0].json : {};\n"
             "const estado = session.campo_editando || '';\n"
             "const certData = session.backup_texto ? JSON.parse(session.backup_texto) : {};\n"
             "const text = input.text || '';\n"
             "const cb = input.callbackData || '';\n"
             "const isCallback = input.isCallback;\n\n"
             "let accion = 'IGNORAR';\n"
             "if (!isCallback) {\n"
             "  if (text === '/cert' || text === '/certificado') accion = 'INICIAR';\n"
             "  else if (estado === 'CERT_CLIENTE') accion = 'CERT_CLIENTE';\n"
             "  else if (estado === 'CERT_EXTINTORES') accion = 'CERT_EXTINTORES';\n"
             "} else {\n"
             "  if (cb.startsWith('cert_tipo_')) accion = 'CERT_TIPO_CB';\n"
             "  else if (cb.startsWith('cert_hidro_')) accion = 'CERT_HIDRO_CB';\n"
             "  else if (cb === 'cert_confirmar' || cb === 'cert_cancelar') accion = 'CERT_CONFIRMAR_CB';\n"
             "}\n\n"
             "return [{ json: { ...input, estado, certData, accion } }];"
         )},
         [-400, 300]),

    # ── Enrutador (Switch) ───────────────────
    node("cb01-rout-0005", "Enrutador", "n8n-nodes-base.switch",
         {"mode": "expression",
          "numberOutputs": 6,
          "fallbackOutput": "none",
          "output": "={{ ['INICIAR','CERT_CLIENTE','CERT_TIPO_CB','CERT_EXTINTORES','CERT_HIDRO_CB','CERT_CONFIRMAR_CB'].indexOf($json.accion) }}"},
         [-200, 300]),

    # ══ BRANCH 0: INICIAR ════════════════════

    node("cb01-ini1-0006", "Iniciar Sesion Cert", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": (
              "INSERT INTO bot_clientes.registro_borrador (chat_id, campo_editando, backup_texto, estado)\n"
              "VALUES ({{ $json.chatId }}, 'CERT_CLIENTE', '{}', 'EDICION')\n"
              "ON CONFLICT (chat_id) DO UPDATE SET\n"
              "  campo_editando = 'CERT_CLIENTE',\n"
              "  backup_texto = '{}',\n"
              "  updated_at = NOW();"
          ), "options": {}},
         [50, 100], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-ini2-0007", "Pedir Datos Cliente", "n8n-nodes-base.telegram",
         {"chatId": "={{ $('Enrutador').item.json.chatId }}",
          "text": (
              "🔥 *Generador de Certificado*\n\n"
              "Ingresa los datos del cliente separados por coma:\n\n"
              "`Nombre o Razón Social, RUC (o NN si no tiene), Dirección, Distrito`\n\n"
              "*Ejemplo:*\n"
              "`CAFE AROMA DE JULIANA, 20608753037, Mega Plaza Express, Villa El Salvador`"
          ),
          "additionalFields": {"parse_mode": "Markdown", "appendAttribution": False}},
         [250, 100], credentials={"telegramApi": CRED_TELEGRAM}),

    # ══ BRANCH 1: CERT_CLIENTE ═══════════════

    node("cb01-clt1-0008", "Parsear Cliente", "n8n-nodes-base.code",
         {"jsCode": (
             "const d = $('Combinar y Determinar Accion').first().json;\n"
             "const vals = d.text.split(',').map(v => v.trim());\n"
             "const nombre = vals[0] || '';\n"
             "const ruc = (vals[1] && vals[1].toUpperCase() !== 'NN') ? vals[1].trim() : null;\n"
             "const direccion = vals[2] || '';\n"
             "const distrito = vals[3] || '';\n\n"
             "if (!nombre || !direccion || !distrito) {\n"
             "  return [{ json: { error: true, chatId: d.chatId, msg: '⚠️ Formato incorrecto. Usa: Nombre, RUC (o NN), Dirección, Distrito' } }];\n"
             "}\n\n"
             "const certData = { cliente: { nombre, ruc, direccion, distrito } };\n\n"
             "return [{ json: { error: false, chatId: d.chatId, certData, certDataJson: JSON.stringify(certData) } }];"
         )},
         [50, 300]),

    node("cb01-clt2-0009", "Guardar Cliente", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "UPDATE bot_clientes.registro_borrador SET campo_editando = 'CERT_TIPO', backup_texto = '{{ $json.certDataJson }}', updated_at = NOW() WHERE chat_id = {{ $json.chatId }};",
          "options": {}},
         [250, 300], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-clt3-0010", "Pedir Tipo Cert", "n8n-nodes-base.telegram",
         {"chatId": "={{ $('Parsear Cliente').item.json.chatId }}",
          "text": "✅ *Cliente registrado*\n\n¿Tipo de certificado?",
          "replyMarkup": "inlineKeyboard",
          "inlineKeyboard": {"rows": [{"row": {"buttons": [
              {"text": "🔄 Recarga",       "additionalFields": {"callback_data": "cert_tipo_RECARGA"}},
              {"text": "🆕 Extintor Nuevo","additionalFields": {"callback_data": "cert_tipo_NUEVOS"}},
          ]}}]},
          "additionalFields": {"parse_mode": "Markdown", "appendAttribution": False}},
         [450, 300], credentials={"telegramApi": CRED_TELEGRAM}),

    # ══ BRANCH 2: CERT_TIPO_CB ═══════════════

    node("cb01-lmp-0038", "Limpiar Botones Tipo", "n8n-nodes-base.httpRequest",
         {"method": "POST",
          "url": "={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/editMessageReplyMarkup' }}",
          "sendBody": True, "contentType": "json", "specifyBody": "json",
          "jsonBody": "={{ JSON.stringify({ chat_id: $json.chatId, message_id: $json.messageId, reply_markup: {} }) }}",
          "options": {}},
         [-150, 500], continue_on_fail=True),

    node("cb01-tip1-0011", "Guardar Tipo", "n8n-nodes-base.code",
         {"jsCode": (
             "const d = $('Combinar y Determinar Accion').first().json;\n"
             "const tipo = d.callbackData.replace('cert_tipo_', '');\n"
             "const certData = { ...d.certData, tipo };\n"
             "return [{ json: { chatId: d.chatId, certData, certDataJson: JSON.stringify(certData) } }];"
         )},
         [50, 500]),

    node("cb01-tip2-0012", "Guardar Tipo BD", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "UPDATE bot_clientes.registro_borrador SET campo_editando = 'CERT_EXTINTORES', backup_texto = '{{ $json.certDataJson }}', updated_at = NOW() WHERE chat_id = {{ $json.chatId }};",
          "options": {}},
         [250, 500], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-tip3-0013", "Pedir Extintores", "n8n-nodes-base.telegram",
         {"chatId": "={{ $('Guardar Tipo').item.json.chatId }}",
          "text": (
              "📋 *Ingresa los extintores*, uno por línea:\n\n"
              "`capacidad,clase`\n"
              "`capacidad,clase,marca,serie` _(opcional)_\n\n"
              "📅 La *fecha de recarga* es hoy y *vence en 1 año* \\(automáticas\\)\\.\n\n"
              "*Ejemplo:*\n"
              "```\n6kg,PQS\n4kg,CO2\n9kg,PQS,IMPORTADO,SN2019\n```\n\n"
              "Cuando termines envía la lista completa\\."
          ),
          "additionalFields": {"parse_mode": "MarkdownV2", "appendAttribution": False}},
         [450, 500], credentials={"telegramApi": CRED_TELEGRAM}),

    # ══ BRANCH 4: CERT_EXTINTORES ════════════

    node("cb01-ext1-0017", "Parsear Extintores", "n8n-nodes-base.code",
         {"jsCode": (
             "const d = $('Combinar y Determinar Accion').first().json;\n"
             "const lineas = d.text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);\n\n"
             "const hoy = new Date();\n"
             "const vence = new Date(hoy);\n"
             "vence.setFullYear(vence.getFullYear() + 1);\n"
             "const fmt = (d) => d.toISOString().split('T')[0];\n\n"
             "const extintores = lineas.map(linea => {\n"
             "  const partes = linea.split(',').map(p => p.trim());\n"
             "  return {\n"
             "    capacidad: partes[0] || '',\n"
             "    clase: partes[1] || '',\n"
             "    fecha_recarga: fmt(hoy),\n"
             "    fecha_vencimiento: fmt(vence),\n"
             "    marca: partes[2] || null,\n"
             "    serie: partes[3] || null\n"
             "  };\n"
             "}).filter(e => e.capacidad && e.clase);\n\n"
             "if (extintores.length === 0) {\n"
             "  return [{ json: { error: true, chatId: d.chatId, msg: '⚠️ No pude leer los extintores. Revisa el formato.' } }];\n"
             "}\n\n"
             "const certData = { ...d.certData, extintores };\n"
             "return [{ json: { error: false, chatId: d.chatId, certData, certDataJson: JSON.stringify(certData), total: extintores.length } }];"
         )},
         [50, 900]),

    node("cb01-ext2-0018", "Guardar Extintores BD", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "UPDATE bot_clientes.registro_borrador SET campo_editando = 'CERT_HIDRO', backup_texto = '{{ $json.certDataJson }}', updated_at = NOW() WHERE chat_id = {{ $json.chatId }};",
          "options": {}},
         [250, 900], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-ext3-0019", "Pedir Hidro", "n8n-nodes-base.telegram",
         {"chatId": "={{ $('Parsear Extintores').item.json.chatId }}",
          "text": "={{ '✅ ' + $('Parsear Extintores').item.json.total + ' extintores registrados.' + String.fromCharCode(10) + String.fromCharCode(10) + '¿Se realizó prueba hidrostática?' }}",
          "replyMarkup": "inlineKeyboard",
          "inlineKeyboard": {"rows": [{"row": {"buttons": [
              {"text": "✅ Sí", "additionalFields": {"callback_data": "cert_hidro_SI"}},
              {"text": "❌ No", "additionalFields": {"callback_data": "cert_hidro_NO"}},
          ]}}]},
          "additionalFields": {"appendAttribution": False}},
         [450, 900], credentials={"telegramApi": CRED_TELEGRAM}),

    # ══ BRANCH 5: CERT_HIDRO_CB ══════════════

    node("cb01-lmp-0039", "Limpiar Botones Hidro", "n8n-nodes-base.httpRequest",
         {"method": "POST",
          "url": "={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/editMessageReplyMarkup' }}",
          "sendBody": True, "contentType": "json", "specifyBody": "json",
          "jsonBody": "={{ JSON.stringify({ chat_id: $json.chatId, message_id: $json.messageId, reply_markup: {} }) }}",
          "options": {}},
         [-150, 1100], continue_on_fail=True),

    node("cb01-hid1-0020", "Preparar Resumen", "n8n-nodes-base.code",
         {"jsCode": (
             "const d = $('Combinar y Determinar Accion').first().json;\n"
             "const tieneHidro = d.callbackData === 'cert_hidro_SI';\n"
             "const hoy = new Date().toISOString().split('T')[0];\n"
             "const certData = {\n"
             "  ...d.certData,\n"
             "  prueba_hidrostatica: tieneHidro,\n"
             "  fecha_prueba_hidrostatica: tieneHidro ? hoy : null,\n"
             "  fecha_emision: hoy\n"
             "};\n\n"
             "// Derivar tipo_agente del agente más frecuente en los extintores\n"
             "const freq = {};\n"
             "for (const e of certData.extintores) { freq[e.clase] = (freq[e.clase] || 0) + 1; }\n"
             "const tipo_agente = Object.entries(freq).sort((a, b) => b[1] - a[1])[0][0];\n\n"
             "const c = certData.cliente;\n"
             "const exts = certData.extintores.map((e, i) => `${i+1}. ${e.capacidad} ${e.clase}${e.marca ? ' - '+e.marca : ''}${e.serie ? ' ['+e.serie+']' : ''}`).join('\\n');\n\n"
             "const resumen = `📋 *RESUMEN DEL CERTIFICADO*\\n\\n` +\n"
             "  `👤 *Cliente:* ${c.nombre}\\n` +\n"
             "  (c.ruc ? `🆔 *RUC:* ${c.ruc}\\n` : '') +\n"
             "  `📍 *Dirección:* ${c.direccion}\\n` +\n"
             "  `🏘️ *Distrito:* ${c.distrito}\\n\\n` +\n"
             "  `📄 *Tipo:* ${certData.tipo}\\n` +\n"
             "  `🧯 *Agente:* ${tipo_agente}\\n` +\n"
             "  `🔬 *Prueba hidro:* ${tieneHidro ? 'SÍ' : 'NO'}\\n\\n` +\n"
             "  `*Extintores (${certData.extintores.length}):*\\n${exts}\\n\\n` +\n"
             "  `¿Generar certificado?`;\n\n"
             "return [{ json: { chatId: d.chatId, certData: {...certData, tipo_agente}, certDataJson: JSON.stringify({...certData, tipo_agente}), resumen } }];"
         )},
         [50, 1100]),

    node("cb01-hid2-0021", "Guardar Hidro BD", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "UPDATE bot_clientes.registro_borrador SET campo_editando = 'CERT_CONFIRMAR', backup_texto = '{{ $json.certDataJson }}', updated_at = NOW() WHERE chat_id = {{ $json.chatId }};",
          "options": {}},
         [250, 1100], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-hid3-0022", "Mostrar Resumen", "n8n-nodes-base.telegram",
         {"chatId": "={{ $('Preparar Resumen').item.json.chatId }}",
          "text": "={{ $('Preparar Resumen').item.json.resumen }}",
          "replyMarkup": "inlineKeyboard",
          "inlineKeyboard": {"rows": [{"row": {"buttons": [
              {"text": "✅ Generar Certificado", "additionalFields": {"callback_data": "cert_confirmar"}},
              {"text": "❌ Cancelar",            "additionalFields": {"callback_data": "cert_cancelar"}},
          ]}}]},
          "additionalFields": {"parse_mode": "Markdown", "appendAttribution": False}},
         [450, 1100], credentials={"telegramApi": CRED_TELEGRAM}),

    # ══ BRANCH 6: CERT_CONFIRMAR_CB ══════════

    node("cb01-lmp-0040", "Limpiar Botones Confirmar", "n8n-nodes-base.httpRequest",
         {"method": "POST",
          "url": "={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/editMessageReplyMarkup' }}",
          "sendBody": True, "contentType": "json", "specifyBody": "json",
          "jsonBody": "={{ JSON.stringify({ chat_id: $json.chatId, message_id: $json.messageId, reply_markup: {} }) }}",
          "options": {}},
         [-150, 1300], continue_on_fail=True),

    node("cb01-cnf1-0023", "Confirmar o Cancelar", "n8n-nodes-base.if",
         {"conditions": {
             "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
             "conditions": [{
                 "id": "cnf-cond-001",
                 "leftValue": "={{ $('Combinar y Determinar Accion').item.json.callbackData }}",
                 "rightValue": "cert_confirmar",
                 "operator": {"type": "string", "operation": "equals", "name": "filter.operator.equals"}
             }],
             "combinator": "and"
         }},
         [50, 1300]),

    # ── Rama CONFIRMAR ────────────────────────

    node("cb01-gen1-0024", "Obtener Numero Cert", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "SELECT 'CERT-' || TO_CHAR(NOW(), 'YYYY') || '-' || LPAD(NEXTVAL('bot_clientes.certificado_seq')::TEXT, 4, '0') AS numero_certificado;",
          "options": {}},
         [250, 1200], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-gen2-0025", "Construir Payload", "n8n-nodes-base.code",
         {"jsCode": (
             "const d = $('Combinar y Determinar Accion').first().json;\n"
             "const numCert = $('Obtener Numero Cert').first().json.numero_certificado;\n"
             "const cd = d.certData;\n\n"
             "// Validar que certData tiene todos los campos necesarios\n"
             "if (!cd.tipo || !cd.cliente || !cd.extintores || !cd.fecha_emision) {\n"
             "  return [{ json: {\n"
             "    error: true,\n"
             "    chatId: d.chatId,\n"
             "    msg: '⚠️ Sesión expirada o datos incompletos. Por favor escribe /cert para comenzar de nuevo.'\n"
             "  }}];\n"
             "}\n\n"
             "// Derivar tipo_agente del agente más frecuente (por si certData no lo trae ya)\n"
             "const freq = {};\n"
             "for (const e of cd.extintores) { freq[e.clase] = (freq[e.clase] || 0) + 1; }\n"
             "const tipo_agente = cd.tipo_agente || Object.entries(freq).sort((a, b) => b[1] - a[1])[0][0];\n\n"
             "const payload = {\n"
             "  numero_certificado: numCert,\n"
             "  tipo: cd.tipo,\n"
             "  cliente: cd.cliente,\n"
             "  tipo_agente,\n"
             "  prueba_hidrostatica: cd.prueba_hidrostatica || false,\n"
             "  fecha_prueba_hidrostatica: cd.fecha_prueba_hidrostatica || null,\n"
             "  fecha_emision: cd.fecha_emision,\n"
             "  extintores: cd.extintores\n"
             "};\n\n"
             "return [{ json: { error: false, chatId: d.chatId, payload, numeroCert: numCert } }];"
         )},
         [450, 1200]),

    node("cb01-val1-0036", "Validar Payload", "n8n-nodes-base.if",
         {"conditions": {
             "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
             "conditions": [{
                 "id": "val-cond-001",
                 "leftValue": "={{ $json.error }}",
                 "rightValue": False,
                 "operator": {"type": "boolean", "operation": "equals", "name": "filter.operator.equals"}
             }],
             "combinator": "and"
         }},
         [650, 1200]),

    node("cb01-val2-0037", "Error Sesion Expirada", "n8n-nodes-base.telegram",
         {"chatId": "={{ $json.chatId }}",
          "text": "={{ $json.msg }}",
          "additionalFields": {"appendAttribution": False}},
         [850, 1400], credentials={"telegramApi": CRED_TELEGRAM}),

    node("cb01-gen3-0026", "Llamar Servicio Python", "n8n-nodes-base.httpRequest",
         {"method": "POST",
          "url": "https://proyecto-at-s.onrender.com/generar-certificado",
          "sendHeaders": True,
          "headerParameters": {"parameters": [
              {"name": "x-api-key", "value": "={{ $env.PYTHON_SERVICE_SECRET }}"},
          ]},
          "sendBody": True,
          "contentType": "json",
          "specifyBody": "json",
          "jsonBody": "={{ JSON.stringify($json.payload) }}",
          "options": {"timeout": 60000}},
         [650, 1200]),

    node("cb01-gen4-0027", "Preparar Archivos", "n8n-nodes-base.code",
         {"jsCode": (
             "const response = $input.first().json;\n"
             "const chatId = $('Construir Payload').first().json.chatId;\n"
             "const numCert = $('Construir Payload').first().json.numeroCert;\n"
             "const payload = $('Construir Payload').first().json.payload;\n"
             "const cd = $('Combinar y Determinar Accion').first().json.certData;\n"
             "const cliente = cd.cliente;\n\n"
             "const maxVenc = cd.extintores.map(e => e.fecha_vencimiento).sort().pop() || cd.fecha_emision;\n\n"
             "return [{\n"
             "  json: {\n"
             "    chatId, numCert,\n"
             "    nombre: cliente.nombre,\n"
             "    ruc: cliente.ruc || null,\n"
             "    direccion: cliente.direccion,\n"
             "    distrito: cliente.distrito,\n"
             "    tipo: cd.tipo,\n"
             "    tipo_agente: cd.tipo_agente,\n"
             "    prueba_hidrostatica: cd.prueba_hidrostatica || false,\n"
             "    fecha_prueba_hidrostatica: cd.fecha_prueba_hidrostatica || null,\n"
             "    fecha_emision: cd.fecha_emision,\n"
             "    fecha_vencimiento: maxVenc,\n"
             "    datos_json: JSON.stringify(payload)\n"
             "  },\n"
             "  binary: {\n"
             "    pdfFile:  { data: response.pdf_base64,  mimeType: 'application/pdf', fileName: `${numCert}.pdf`,  fileExtension: 'pdf' },\n"
             "    docxFile: { data: response.docx_base64, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', fileName: `${numCert}.docx`, fileExtension: 'docx' }\n"
             "  }\n"
             "}];"
         )},
         [850, 1200]),

    node("cb01-db1-0033", "Registrar Cliente BD", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": (
              "INSERT INTO bot_clientes.clientes (nombres, nombre_comercial, ruc, direccion, distrito)\n"
              "VALUES ($1, $1, $2, $3, $4)\n"
              "ON CONFLICT (ruc) WHERE ruc IS NOT NULL DO UPDATE SET\n"
              "  nombre_comercial = EXCLUDED.nombre_comercial,\n"
              "  direccion = EXCLUDED.direccion,\n"
              "  distrito = EXCLUDED.distrito,\n"
              "  updated_at = NOW()\n"
              "RETURNING id"
          ),
          "options": {"queryReplacement": "={{ [$json.nombre, $json.ruc, $json.direccion, $json.distrito] }}"}},
         [1050, 1200], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-db2-0034", "Registrar Certificado BD", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": (
              "INSERT INTO bot_clientes.certificados (\n"
              "  numero_certificado, tipo, tipo_agente,\n"
              "  prueba_hidrostatica, fecha_prueba_hidrostatica,\n"
              "  cliente_id, fecha_servicio, fecha_vencimiento,\n"
              "  datos_json, estado\n"
              ") VALUES (\n"
              "  $1, $2, $3,\n"
              "  $4, $5::date,\n"
              "  $6, $7::date, $8::date,\n"
              "  $9::jsonb, 'COMPLETADO'\n"
              ")"
          ),
          "options": {"queryReplacement": (
              "={{ [\n"
              "  $('Preparar Archivos').first().json.numCert,\n"
              "  $('Preparar Archivos').first().json.tipo,\n"
              "  $('Preparar Archivos').first().json.tipo_agente,\n"
              "  $('Preparar Archivos').first().json.prueba_hidrostatica,\n"
              "  $('Preparar Archivos').first().json.fecha_prueba_hidrostatica,\n"
              "  $json.id,\n"
              "  $('Preparar Archivos').first().json.fecha_emision,\n"
              "  $('Preparar Archivos').first().json.fecha_vencimiento,\n"
              "  $('Preparar Archivos').first().json.datos_json\n"
              "] }}"
          )}},
         [1250, 1200], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-gen5-0028", "Enviar PDF", "n8n-nodes-base.httpRequest",
         {"method": "POST",
          "url": "={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/sendDocument' }}",
          "sendBody": True,
          "contentType": "multipart-form-data",
          "bodyParameters": {"parameters": [
              {"name": "chat_id",  "value": "={{ $json.chatId }}"},
              {"name": "document", "parameterType": "formBinaryData", "inputDataFieldName": "pdfFile"},
              {"name": "caption",  "value": "={{ '📄 Certificado ' + $json.numCert + '.pdf' }}"},
          ]},
          "options": {}},
         [1050, 1100]),

    node("cb01-gen6-0029", "Enviar DOCX", "n8n-nodes-base.httpRequest",
         {"method": "POST",
          "url": "={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/sendDocument' }}",
          "sendBody": True,
          "contentType": "multipart-form-data",
          "bodyParameters": {"parameters": [
              {"name": "chat_id",  "value": "={{ $json.chatId }}"},
              {"name": "document", "parameterType": "formBinaryData", "inputDataFieldName": "docxFile"},
              {"name": "caption",  "value": "={{ '📝 Certificado ' + $json.numCert + '.docx' }}"},
          ]},
          "options": {}},
         [1050, 1300]),

    node("cb01-gen7-0030", "Limpiar Sesion OK", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "UPDATE bot_clientes.registro_borrador SET campo_editando = NULL, backup_texto = NULL, updated_at = NOW() WHERE chat_id = {{ $('Preparar Archivos').first().json.chatId }};",
          "options": {}},
         [1850, 1200], credentials={"postgres": CRED_POSTGRES}),

    # ── Rama CANCELAR ─────────────────────────

    node("cb01-can1-0031", "Limpiar Sesion Cancelar", "n8n-nodes-base.postgres",
         {"operation": "executeQuery",
          "query": "UPDATE bot_clientes.registro_borrador SET campo_editando = NULL, backup_texto = NULL, updated_at = NOW() WHERE chat_id = {{ $('Combinar y Determinar Accion').item.json.chatId }};",
          "options": {}},
         [250, 1400], credentials={"postgres": CRED_POSTGRES}),

    node("cb01-can2-0032", "Mensaje Cancelado", "n8n-nodes-base.telegram",
         {"chatId": "={{ $('Combinar y Determinar Accion').item.json.chatId }}",
          "text": "❌ Certificado cancelado. Escribe /cert para comenzar de nuevo.",
          "additionalFields": {"appendAttribution": False}},
         [450, 1400], credentials={"telegramApi": CRED_TELEGRAM}),
]

# ─────────────────────────────────────────────
# CONEXIONES
# ─────────────────────────────────────────────

CONNECTIONS = {
    "Telegram Trigger":            conn("Telegram Trigger",            "Normalizar Input"),
    "Normalizar Input":            conn("Normalizar Input",            "Obtener Sesion"),
    "Obtener Sesion":              conn("Obtener Sesion",              "Combinar y Determinar Accion"),
    "Combinar y Determinar Accion":conn("Combinar y Determinar Accion","Enrutador"),
    "Enrutador": {"main": [
        [{"node": "Iniciar Sesion Cert",       "type": "main", "index": 0}],
        [{"node": "Parsear Cliente",            "type": "main", "index": 0}],
        [{"node": "Limpiar Botones Tipo",       "type": "main", "index": 0}],
        [{"node": "Parsear Extintores",         "type": "main", "index": 0}],
        [{"node": "Limpiar Botones Hidro",      "type": "main", "index": 0}],
        [{"node": "Limpiar Botones Confirmar",  "type": "main", "index": 0}],
    ]},
    "Limpiar Botones Tipo":     conn("Limpiar Botones Tipo",     "Guardar Tipo"),
    "Limpiar Botones Hidro":    conn("Limpiar Botones Hidro",    "Preparar Resumen"),
    "Limpiar Botones Confirmar":conn("Limpiar Botones Confirmar","Confirmar o Cancelar"),
    "Iniciar Sesion Cert":         conn("Iniciar Sesion Cert",         "Pedir Datos Cliente"),
    "Parsear Cliente":             conn("Parsear Cliente",             "Guardar Cliente"),
    "Guardar Cliente":             conn("Guardar Cliente",             "Pedir Tipo Cert"),
    "Guardar Tipo":                conn("Guardar Tipo",                "Guardar Tipo BD"),
    "Guardar Tipo BD":             conn("Guardar Tipo BD",             "Pedir Extintores"),
    "Parsear Extintores":          conn("Parsear Extintores",          "Guardar Extintores BD"),
    "Guardar Extintores BD":       conn("Guardar Extintores BD",       "Pedir Hidro"),
    "Preparar Resumen":            conn("Preparar Resumen",            "Guardar Hidro BD"),
    "Guardar Hidro BD":            conn("Guardar Hidro BD",            "Mostrar Resumen"),
    "Confirmar o Cancelar": {"main": [
        [{"node": "Obtener Numero Cert",     "type": "main", "index": 0}],
        [{"node": "Limpiar Sesion Cancelar", "type": "main", "index": 0}],
    ]},
    "Obtener Numero Cert":         conn("Obtener Numero Cert",         "Construir Payload"),
    "Construir Payload":           conn("Construir Payload",           "Validar Payload"),
    "Validar Payload": {"main": [
        [{"node": "Llamar Servicio Python",  "type": "main", "index": 0}],
        [{"node": "Error Sesion Expirada",   "type": "main", "index": 0}],
    ]},
    "Llamar Servicio Python":      conn("Llamar Servicio Python",      "Preparar Archivos"),
    "Preparar Archivos": {"main": [[
        {"node": "Enviar PDF",           "type": "main", "index": 0},
        {"node": "Enviar DOCX",          "type": "main", "index": 0},
        {"node": "Registrar Cliente BD", "type": "main", "index": 0},
    ]]},
    "Registrar Cliente BD":        conn("Registrar Cliente BD",        "Registrar Certificado BD"),
    "Registrar Certificado BD":    conn("Registrar Certificado BD",    "Limpiar Sesion OK"),
    "Limpiar Sesion Cancelar":     conn("Limpiar Sesion Cancelar",     "Mensaje Cancelado"),
}

# ─────────────────────────────────────────────
# BUILD
# ─────────────────────────────────────────────

def build():
    # Validar que todos los nodos en conexiones existen
    node_names = {n["name"] for n in NODES}
    errors = []
    for src, c in CONNECTIONS.items():
        for branch in c["main"]:
            for dest in branch:
                if dest["node"] not in node_names:
                    errors.append(f"Conexion rota: {src} → {dest['node']} (nodo no existe)")
    if errors:
        for e in errors:
            print("ERROR:", e)
        sys.exit(1)

    workflow = {
        "name": "Certificado Extintor - Bot",
        "nodes": NODES,
        "connections": CONNECTIONS,
        "active": False,
        "settings": {"executionOrder": "v1"},
    }
    OUTPUT.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK Workflow generado: {OUTPUT}")
    print(f"   Nodos: {len(NODES)}  |  Conexiones: {len(CONNECTIONS)}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        build()  # build ya valida
    else:
        build()
