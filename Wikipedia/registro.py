"""Registro de resultados y avance de los notebooks de Wikipedia.

Después de cada paso, los notebooks guardan sus resultados en ``data/resultados/<notebook>/``:

- vectores y puntajes en Parquet, siempre con ``id`` (page_id) y ``title``;
- tablas en CSV;
- gráficas en PNG.

Además se registra el paso en ``data/resultados/pasos.csv`` y se reescribe ``data/RESUMEN.md`` con lo terminado,
lo pendiente y la duración de cada paso. Todo queda dentro de ``data/``, que no se sube al repositorio.
"""

import csv
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
RESULTADOS = DATA / "resultados"
ARCHIVO_PASOS = RESULTADOS / "pasos.csv"
ARCHIVO_NOTAS = RESULTADOS / "notas.csv"
ARCHIVO_RESUMEN = DATA / "RESUMEN.md"

# Plan completo de la práctica, en orden: clave -> descripción
PLAN = {
    "01": "Carga, extracción y construcción del grafo (notebook 01)",
    "01.DAB": "Corrección de is_disambig: re-extracción con un script",
    "02.1": "02 · Datos: carga de nodos y aristas",
    "02.2": "02 · Matriz de adyacencia CSR",
    "02.3": "02 · Matriz de transición: colgantes, SCC y trampas de araña",
    "02.3.1": "02 · Grafo de análisis sin desambiguaciones",
    "02.4": "02 · PageRank con β ∈ {0.70, 0.85, 0.95} y validación contra networkx",
    "02.4.1": "02 · Sensibilidad a β",
    "02.4.2": "02 · PageRank contra grado de entrada",
    "02.5": "02 · HITS y comprobación contra networkx",
    "02.5.2": "02 · Top de hubs y autoridades",
    "02.5.3": "02 · Efecto TKC",
    "02.5.4": "02 · PageRank contra autoridades",
    "02.E2": "02 · Robustez con y sin desambiguaciones",
    "02.E3": "02 · Sesgo por antigüedad (page_id)",
    "03.1": "03 · Datos y verificación",
    "03.2": "03 · Tópicos con las categorías",
    "03.3": "03 · Un vector de PageRank por tema",
    "03.3.1": "03 · Pureza con cada orden",
    "03.3.2": "03 · Top-10 de 4 temas de ejemplo",
    "03.HITS": "03 · HITS dentro de cada tema",
    "03.5": "03 · Un lector con varios intereses",
    "03.4": "03 · Validación ocultando el 20 % (seed 42)",
    "04.1": "04 · Datos",
    "04.2": "04 · Comprobación contra networkx",
    "04.3": "04 · Recomendaciones de 12 artículos",
    "04.4": "04 · Evaluación con 50 artículos",
    "TEXTO": "Textos y observaciones con las cifras finales",
    "README": "Wikipedia/README.md",
}


def carpeta(notebook):
    """Devuelve (y crea) la carpeta de resultados de un notebook."""
    ruta = RESULTADOS / notebook
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def guardar_tabla(df, nombre, notebook):
    """Guarda una tabla en CSV (con su índice) y devuelve la ruta."""
    ruta = carpeta(notebook) / f"{nombre}.csv"
    df.to_csv(ruta, encoding="utf-8")
    return ruta


def guardar_figura(fig, nombre, notebook):
    """Guarda una figura de matplotlib en PNG y devuelve la ruta."""
    ruta = carpeta(notebook) / f"{nombre}.png"
    fig.savefig(ruta, dpi=120, bbox_inches="tight")
    return ruta


def guardar_parquet(df, nombre, notebook):
    """Guarda vectores o puntajes en Parquet; exige las columnas id y title."""
    assert {"id", "title"} <= set(df.columns), "Los Parquet de resultados llevan id y title"
    ruta = carpeta(notebook) / f"{nombre}.parquet"
    df.to_parquet(ruta, index=False)
    return ruta


def _anexar(archivo, fila):
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    nuevo = not archivo.exists()
    with open(archivo, "a", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(fila))
        if nuevo:
            escritor.writeheader()
        escritor.writerow(fila)


def nota(texto):
    """Agrega una nota (decisión, convergencia, incidencia) al resumen."""
    _anexar(ARCHIVO_NOTAS, {"hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "nota": texto})
    actualizar_resumen()


def registrar_paso(clave, inicio, archivos=(), detalle=""):
    """
    Registra un paso terminado y reescribe RESUMEN.md.

    Parámetros
    ----------
    clave : str
        Clave del paso en PLAN.
    inicio : float
        Marca de tiempo (time.time()) del inicio del paso.
    archivos : iterable of Path
        Archivos de resultados que generó el paso.
    detalle : str
        Cifras o comentarios breves del paso.
    """
    fin = time.time()
    _anexar(ARCHIVO_PASOS, {
        "clave": clave, "paso": PLAN.get(clave, clave),
        "inicio": datetime.fromtimestamp(inicio).strftime("%Y-%m-%d %H:%M:%S"),
        "fin": datetime.fromtimestamp(fin).strftime("%Y-%m-%d %H:%M:%S"),
        "segundos": round(fin - inicio, 1),
        "archivos": "; ".join(str(Path(a).resolve().relative_to(DATA)).replace("\\", "/") for a in archivos),
        "detalle": detalle,
    })
    actualizar_resumen()


def _duracion(segundos):
    segundos = float(segundos)
    return f"{segundos:.0f} s" if segundos < 120 else f"{segundos / 60:.1f} min"


def actualizar_resumen():
    """Reescribe data/RESUMEN.md a partir de pasos.csv y notas.csv."""
    pasos = pd.read_csv(ARCHIVO_PASOS, dtype=str).drop_duplicates("clave", keep="last") if ARCHIVO_PASOS.exists() \
        else pd.DataFrame(columns=["clave", "paso", "inicio", "fin", "segundos", "archivos", "detalle"])
    notas = pd.read_csv(ARCHIVO_NOTAS, dtype=str) if ARCHIVO_NOTAS.exists() else pd.DataFrame(columns=["hora", "nota"])
    hechos = set(pasos["clave"])
    lineas = ["# Resumen de avance: Wikipedia", "",
              f"Actualizado: {datetime.now():%Y-%m-%d %H:%M:%S}", "",
              "## Terminado", "",
              "| Paso | Inicio | Duración | Detalle | Archivos |", "|---|---|---|---|---|"]
    orden = {c: i for i, c in enumerate(PLAN)}
    for _, p in pasos.sort_values("clave", key=lambda s: s.map(lambda c: orden.get(c, 999))).iterrows():
        detalle = "" if pd.isna(p["detalle"]) else p["detalle"]
        archivos = "" if pd.isna(p["archivos"]) else "<br>".join(f"`{a}`" for a in p["archivos"].split("; ") if a)
        lineas.append(f"| {p['paso']} | {p['inicio']} | {_duracion(p['segundos'])} | {detalle} | {archivos} |")
    if len(pasos):
        total = pasos["segundos"].astype(float).sum()
        lineas += ["", f"Tiempo total de los pasos registrados: {_duracion(total)}."]
    lineas += ["", "## Pendiente", ""]
    pendientes = [d for c, d in PLAN.items() if c not in hechos]
    lineas += [f"- [ ] {d}" for d in pendientes] or ["Nada: todo el plan está terminado."]
    lineas += ["", "## Notas", ""]
    lineas += [f"- {n['hora']}: {n['nota']}" for _, n in notas.iterrows()] or ["Sin notas."]
    ARCHIVO_RESUMEN.write_text("\n".join(lineas) + "\n", encoding="utf-8")
