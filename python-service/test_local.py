"""
test_local.py — Preview del certificado en el navegador (sin desplegar).

Uso:
    python test_local.py              → abre en el navegador (HTML)
    python test_local.py --pdf        → también genera PDF (requiere WeasyPrint)
    python test_local.py --extintores 15  → prueba con N extintores
"""

import sys
import os
import tempfile
import webbrowser
import argparse
from types import SimpleNamespace

# Asegura que Python encuentre generator_html en la misma carpeta
sys.path.insert(0, os.path.dirname(__file__))
from generator_html import generar_html, generar_pdf_html


# ── Datos de prueba ────────────────────────────────────────────────
def make_extintor(i, con_marca=False, con_serie=False):
    clases = ["PQS", "CO2", "PQS", "K", "PQS"]
    caps   = ["6kg", "4kg", "9kg", "2kg", "12kg"]
    return SimpleNamespace(
        capacidad       = caps[i % len(caps)],
        clase           = clases[i % len(clases)],
        marca           = f"MARCA-{i}" if con_marca and i % 3 == 0 else None,
        serie           = f"SN{2019+i}" if con_serie and i % 2 == 0 else None,
        fecha_recarga   = "2026-04-03",
        fecha_vencimiento = "2027-04-03",
    )

def build_req(n_extintores: int = 3):
    extintores = [make_extintor(i, con_marca=True, con_serie=True) for i in range(n_extintores)]
    return SimpleNamespace(
        numero_certificado      = f"CERT-2026-{n_extintores:04d}",
        tipo                    = "RECARGA",
        tipo_agente             = "PQS",
        prueba_hidrostatica     = True,
        fecha_prueba_hidrostatica = "2026-04-03",
        fecha_emision           = "2026-04-03",
        extintores              = extintores,
        cliente = SimpleNamespace(
            nombre    = "Café Aroma de Juliana",
            ruc       = "20608753037",
            direccion = "Av. Mega Plaza Express, Independencia",
            distrito  = "Villa El Salvador",
        ),
    )


# ── Main ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Preview certificado AT&S")
    parser.add_argument("--pdf",         action="store_true", help="Generar PDF con WeasyPrint")
    parser.add_argument("--extintores",  type=int, default=3, help="Cantidad de extintores (default: 3)")
    parser.add_argument("--no-browser",  action="store_true", help="No abrir el navegador automáticamente")
    args = parser.parse_args()

    req = build_req(args.extintores)
    html = generar_html(req)

    # Guardar HTML
    html_path = os.path.join(tempfile.gettempdir(), "cert_preview.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML generado: {html_path}")

    if not args.no_browser:
        webbrowser.open(f"file:///{html_path}")
        print("🌐 Abriendo en el navegador...")

    # Generar PDF (opcional)
    if args.pdf:
        try:
            pdf_bytes = generar_pdf_html(req)
            pdf_path = os.path.join(os.path.dirname(__file__), "cert_preview.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            print(f"✅ PDF generado: {pdf_path}")
        except ImportError:
            print("⚠️  WeasyPrint no instalado. Ejecuta: pip install weasyprint")
        except Exception as e:
            print(f"❌ Error generando PDF: {e}")


if __name__ == "__main__":
    main()
