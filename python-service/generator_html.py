"""
generator_html.py — Genera certificados PDF usando HTML + Jinja2 + WeasyPrint.
Reemplaza al generator.py original (fpdf2) con un diseño basado en plantilla HTML.
"""

import os
import base64
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "assets")

MESES = {
    1: "enero", 2: "febrero", 3: "marzo",    4: "abril",
    5: "mayo",  6: "junio",   7: "julio",    8: "agosto",
    9: "setiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

AGENTES = {
    "PQS":             "PQS POLVOS QUÍMICOS SECO",
    "CO2":             "GAS CARBÓNICO (CO2)",
    "GAS_PRESURIZADA": "GAS PRESURIZADA",
    "ACETATO_POTASIO": "ACETATO DE POTASIO",
}

# ── Assets: se cargan una sola vez al iniciar el proceso ──────────
def _load_asset_b64(filename: str) -> str | None:
    path = os.path.join(ASSETS_DIR, filename)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

LOGO_B64  = _load_asset_b64("logo.png")
MARCA_B64 = _load_asset_b64("marca-de-agua.png")

# ── Helpers de fecha ───────────────────────────────────────────────
def _fecha_corta(s: str) -> str:
    d = datetime.strptime(s, "%Y-%m-%d")
    return f"{d.day:02d}-{d.month:02d}-{d.year}"

def _fecha_larga(s: str) -> str:
    d = datetime.strptime(s, "%Y-%m-%d")
    return f"Lima, {d.day:02d} de {MESES[d.month]} del {d.year}"

# ── Escala de fuente según cantidad de extintores ──────────────────
def _font_scale(n_ext: int) -> float:
    if n_ext <= 8:   return 1.00
    if n_ext <= 12:  return 0.93
    if n_ext <= 16:  return 0.86
    return 0.86  # más de 16 → 2 páginas, no comprimir más

# ── Construcción del contexto ─────────────────────────────────────
def _build_context(req) -> dict:
    scale       = _font_scale(len(req.extintores))
    tiene_marca = any(e.marca for e in req.extintores)
    tiene_serie = any(e.serie for e in req.extintores)

    extintores_data = [
        {
            "capacidad":        e.capacidad,
            "clase":            e.clase,
            "marca":            e.marca or "",
            "serie":            e.serie or "",
            "fecha_recarga":    _fecha_corta(e.fecha_recarga),
            "fecha_vencimiento": _fecha_corta(e.fecha_vencimiento),
        }
        for e in req.extintores
    ]

    return {
        # diseño
        "logo_b64":   LOGO_B64,
        "marca_b64":  MARCA_B64,
        "font_main":   round(scale * 9.5,  1),
        "font_body":   round(scale * 9.0,  1),
        "font_table":  round(scale * 8.5,  1),
        "font_small":  round(scale * 8.5,  1),
        "font_title":  round(scale * 19.0, 1),
        "font_subtitle": round(scale * 11.0, 1),
        # certificado
        "num_cert":    req.numero_certificado,
        "label_nombre": "NOMBRE O RAZÓN SOCIAL" if req.cliente.ruc else "NOMBRE",
        "nombre":      req.cliente.nombre.upper(),
        "ruc":         req.cliente.ruc,
        "direccion":   req.cliente.direccion,
        "distrito":    req.cliente.distrito.upper(),
        "tipo_txt":    "RECARGA DE EXTINTOR" if req.tipo == "RECARGA" else "EXTINTOR NUEVO",
        "accion":      "RECARGA" if req.tipo == "RECARGA" else "INSTALACIÓN",
        "agente":      AGENTES.get(req.tipo_agente, req.tipo_agente),
        "prueba_hidrostatica": req.prueba_hidrostatica,
        "fecha_prueba": _fecha_corta(req.fecha_prueba_hidrostatica) if req.fecha_prueba_hidrostatica else "",
        "extintores":  extintores_data,
        "tiene_marca": tiene_marca,
        "tiene_serie": tiene_serie,
        "fecha_larga": _fecha_larga(req.fecha_emision),
    }

# ── API pública ────────────────────────────────────────────────────
_jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)

def generar_html(req) -> str:
    """Devuelve el HTML renderizado (útil para preview local)."""
    template = _jinja_env.get_template("certificado.html")
    return template.render(**_build_context(req))

def generar_pdf_html(req) -> bytes:
    """Devuelve el PDF como bytes (usa WeasyPrint)."""
    import weasyprint  # import tardío: solo se importa si se necesita PDF
    html = generar_html(req)
    return bytes(weasyprint.HTML(string=html).write_pdf())
