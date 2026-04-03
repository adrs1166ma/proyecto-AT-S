# Estrategia de paginación del certificado PDF

## Objetivo
Gerencia requiere que el certificado ocupe **1 sola página A4** en la mayoría de casos.

## Análisis de espacio (A4 = 29.7cm, márgenes 1.5cm arriba/abajo)

| Sección | Altura estimada |
|---------|----------------|
| Header (empresa + logo) | ~2.0 cm |
| Datos del cliente (4 campos) | ~2.5 cm |
| Título CERTIFICADO | ~1.5 cm |
| Cuerpo del texto | ~2.0 cm |
| Prueba hidrostática (si aplica) | ~0.5 cm |
| Tabla extintores (cabecera) | ~0.8 cm |
| **Por cada fila de extintor** | **~0.7 cm** |
| Garantía + firma | ~3.5 cm |
| **Total fijo (sin tabla)** | **~12.8 cm** |
| **Espacio disponible para tabla** | **~13.4 cm** |

## Límite de extintores en 1 página

Con `font-size: 9.5pt` y filas compactas:

| Columnas visibles | Filas máximas en 1 página |
|-------------------|---------------------------|
| Sin MARCA ni SERIE | ~17 extintores |
| Con MARCA o SERIE | ~15 extintores |
| Con MARCA y SERIE | ~13 extintores |

**Regla práctica: hasta 10 extintores → 1 página garantizada** (margen de seguridad).

## Casos en que se generan 2 páginas

| Caso | Condición | Frecuencia esperada |
|------|-----------|---------------------|
| Muchos extintores | > 12 extintores en el pedido | Baja (clientes grandes) |
| Extintores con marca y serie largos | Texto desborda celda y hace wrap | Ocasional |
| Dirección del cliente muy larga | > 80 caracteres en dirección | Rara |
| Prueba hidrostática + extintores bordeline | Suma de líneas extras | Muy rara |

## Estrategia implementada en el template HTML

### 1. Escala automática de fuente según cantidad de extintores

```python
# En generator.py, antes de renderizar el template:
n_ext = len(req.extintores)
tiene_marca = any(e.marca for e in req.extintores)
tiene_serie = any(e.serie for e in req.extintores)

# Calcular font_scale
if n_ext <= 8:
    font_scale = 1.0      # normal, sobra espacio
elif n_ext <= 12:
    font_scale = 0.92     # ligeramente comprimido
elif n_ext <= 16:
    font_scale = 0.85     # comprimido, 1 página probable
else:
    font_scale = 1.0      # 2 páginas inevitables, no comprimir más
```

### 2. CSS para página única

```css
@page {
    size: A4;
    margin: 1.5cm 2cm;
}

body {
    font-family: 'Arial', sans-serif;
    font-size: calc(9.5pt * {{ font_scale }});
    line-height: 1.3;
}

.extintor-table {
    font-size: calc(8.5pt * {{ font_scale }});
    width: 100%;
    border-collapse: collapse;
}

.extintor-table td, .extintor-table th {
    padding: 3px 6px;
}
```

### 3. Marca de agua (si se requiere)

```html
<!-- Colocar justo después del <body> -->
<img class="watermark"
     src="data:image/png;base64,{{ logo_b64 }}"
     alt="">
```

```css
.watermark {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-30deg);
    opacity: 0.06;
    z-index: -1;
    width: 380px;
    pointer-events: none;
}
```

La variable `logo_b64` se genera en Python al iniciar el servicio:
```python
import base64
with open("assets/logo.png", "rb") as f:
    LOGO_B64 = base64.b64encode(f.read()).decode()
```

## Comportamiento esperado en producción

```
1–10 extintores   → 1 página (99% de los casos reales)
11–16 extintores  → 1 página con font comprimido
17+ extintores    → 2 páginas (cliente muy grande, aceptable)
```

## TODO cuando se implemente el template HTML

- [ ] Medir alturas reales con WeasyPrint y ajustar los valores de la tabla
- [ ] Testear con 5, 10, 15 y 20 extintores
- [ ] Confirmar con gerencia si 2 páginas es aceptable para clientes grandes
- [ ] Decidir si el logo va como marca de agua, como header, o ambos
