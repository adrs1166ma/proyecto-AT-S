import os
import base64
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
from generator import generar_docx, generar_pdf

app = FastAPI(title="AT-S Certificados")

API_SECRET = os.environ.get("PYTHON_SERVICE_SECRET", "dev-secret")


# ---------- Modelos ----------

class Extintor(BaseModel):
    capacidad: str
    clase: str
    fecha_recarga: str        # formato: YYYY-MM-DD
    fecha_vencimiento: str    # formato: YYYY-MM-DD
    marca: Optional[str] = None
    serie: Optional[str] = None

class Cliente(BaseModel):
    nombre: str
    ruc: Optional[str] = None
    direccion: str
    distrito: str

class CertificadoRequest(BaseModel):
    numero_certificado: str
    tipo: str                         # RECARGA | NUEVOS
    cliente: Cliente
    tipo_agente: str                  # PQS | CO2 | GAS_PRESURIZADA | ACETATO_POTASIO
    prueba_hidrostatica: bool = False
    fecha_prueba_hidrostatica: Optional[str] = None
    fecha_emision: str                # formato: YYYY-MM-DD
    extintores: List[Extintor]


# ---------- Endpoints ----------

@app.get("/")
def health():
    return {"status": "ok", "service": "AT-S Certificados"}


@app.post("/generar-certificado")
def generar(req: CertificadoRequest, x_api_key: str = Header(...)):
    if x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="API Key inválida")

    docx_bytes = generar_docx(req)
    pdf_bytes  = generar_pdf(req)

    return {
        "numero_certificado": req.numero_certificado,
        "docx_base64": base64.b64encode(docx_bytes).decode(),
        "pdf_base64":  base64.b64encode(pdf_bytes).decode(),
    }
