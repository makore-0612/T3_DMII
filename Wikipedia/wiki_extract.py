"""Extracción paralela del dump multistream de Wikipedia a Parquet.

El archivo ``*-multistream.xml.bz2`` es una concatenación de streams bz2
independientes de 100 páginas cada uno; el archivo ``*-index.txt.bz2`` da el
offset (en bytes) donde empieza cada stream. Con eso se reparte el trabajo en
rangos de streams completos que se procesan en paralelo con ``multiprocessing``.

Las funciones de trabajo viven en este módulo (y no en el notebook) porque en
Windows ``multiprocessing`` arranca los procesos con *spawn* y necesita poder
importarlas.
"""

import bz2
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from multiprocessing import Pool

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# Prefijos de namespace que no son artículos (nombres canónicos de <siteinfo>
# más los alias que acepta MediaWiki). Un enlace [[Prefijo:X]] con uno de estos
# prefijos no apunta a un artículo.
NS_NO_ARTICULO = {
    "media", "special", "talk", "user", "user talk", "wikipedia", "wikipedia talk",
    "file", "file talk", "mediawiki", "mediawiki talk", "template", "template talk",
    "help", "help talk", "category", "category talk", "portal", "portal talk",
    "draft", "draft talk", "mos", "mos talk", "timedtext", "timedtext talk",
    "module", "module talk", "event", "event talk",
    # alias
    "image", "image talk", "wp", "wt", "project", "project talk", "cat", "t",
    "h", "p", "mod", "wikt", "wiktionary", "w", "commons", "c", "s", "wikisource",
    "q", "wikiquote", "n", "wikinews", "b", "wikibooks", "v", "wikiversity",
    "voy", "wikivoyage", "d", "wikidata", "m", "meta", "mw", "species", "phab",
    "foundation", "wmf",
}

# Captura el destino de cada "[[" (también los anidados dentro de pies de foto).
RE_ENLACE = re.compile(r"\[\[([^\[\]\|\n]+)(?:\||\]\])")
# Plantillas de página de desambiguación: {{Disambiguation|…}}, sus alias ({{dab}}, {{disambig}}, {{hndis}},
# {{geodis}}…), las temáticas ({{Hospital disambiguation}}) y {{Disambiguation cleanup}}. El nombre debe terminar
# ahí (seguido de «|» o «}}»), para no confundirlas con {{Disambiguation needed}}, que es una etiqueta de
# mantenimiento dentro de artículos normales. Los «set index articles» no son desambiguaciones, ni tres plantillas
# cuyo nombre termina igual: {{Year dab}} (nota al pie de las páginas de año), {{Italic disambiguation}} (formato del
# título) y {{Cite DAB}} (cita del Dictionary of American Biography).
RE_DESAMBIG = re.compile(
    r"\{\{\s*(?!(?:italic|cite|year)\b)(?:[\w\- ]*\s)?(?:disambiguation|disambig|dab|disamb|dbig|hndis|geodis)"
    r"(?:\s+cleanup)?\s*(?:\||\}\})",
    re.IGNORECASE,
)

ESQUEMA_PAGINAS = pa.schema([
    ("page_id", pa.int64()),
    ("title", pa.string()),
    ("ns", pa.int32()),
    ("is_redirect", pa.bool_()),
    ("redirect_target", pa.string()),
    ("rev_id", pa.int64()),
    ("parent_id", pa.int64()),
    ("timestamp", pa.timestamp("s", tz="UTC")),
    ("contributor_user", pa.string()),
    ("contributor_id", pa.int64()),
    ("contributor_ip", pa.string()),
    ("minor", pa.bool_()),
    ("model", pa.string()),
    ("format", pa.string()),
    ("text_bytes", pa.int64()),
    ("n_enlaces", pa.int32()),
    ("n_categorias", pa.int32()),
    ("is_disambig", pa.bool_()),
])
ESQUEMA_ENLACES = pa.schema([("src_id", pa.int64()), ("dst_title", pa.string())])
ESQUEMA_CATEGORIAS = pa.schema([("page_id", pa.int64()), ("category", pa.string())])


# ---------------------------------------------------------------------------
# Índice y cabecera
# ---------------------------------------------------------------------------

def leer_indice(ruta_idx, titulos_buscar=()):
    """Recorre el índice una vez.

    Devuelve ``(offsets, n_paginas, encontrados)`` donde ``offsets`` es un
    arreglo ordenado con el inicio de cada stream, ``n_paginas`` el número de
    líneas y ``encontrados`` un dict ``titulo -> (offset, page_id)`` para los
    títulos pedidos en ``titulos_buscar``.
    """
    buscar = set(titulos_buscar)
    encontrados = {}
    offsets = []
    ultimo = None
    n = 0
    with bz2.open(ruta_idx, "rt", encoding="utf-8") as f:
        for linea in f:
            n += 1
            off, pid, titulo = linea.rstrip("\n").split(":", 2)
            if off != ultimo:
                offsets.append(int(off))
                ultimo = off
            if titulo in buscar:
                encontrados[titulo] = (int(off), int(pid))
    return np.array(offsets, dtype=np.int64), n, encontrados


def rangos(offsets, tam_archivo, n_tareas=400):
    """Agrupa streams consecutivos en ``n_tareas`` rangos de bytes similares.

    Cada rango ``(ini, fin)`` empieza y termina en límites de stream; el último
    llega hasta el final del archivo (incluye el cierre ``</mediawiki>``).
    """
    ini0 = int(offsets[0])
    objetivos = np.linspace(ini0, tam_archivo, n_tareas + 1)[1:-1]
    cortes = offsets[np.searchsorted(offsets, objetivos)]
    limites = np.unique(np.concatenate([[ini0], cortes, [tam_archivo]]))
    return [(int(a), int(b)) for a, b in zip(limites[:-1], limites[1:])]


def leer_cabecera(ruta_xml, primer_offset):
    """Descomprime el primer stream (``<siteinfo>``) y lo devuelve como texto."""
    with open(ruta_xml, "rb") as f:
        datos = f.read(primer_offset)
    return bz2.decompress(datos).decode("utf-8")


def leer_stream(ruta_xml, offset):
    """Descomprime solo el stream que empieza en ``offset``."""
    d = bz2.BZ2Decompressor()
    partes = []
    with open(ruta_xml, "rb") as f:
        f.seek(offset)
        while not d.eof:
            bloque = f.read(1 << 20)
            if not bloque:
                break
            partes.append(d.decompress(bloque))
    return b"".join(partes).decode("utf-8")


def leer_articulo(ruta_xml, offset, titulo):
    """Acceso aleatorio: devuelve el XML del ``<page>`` con ese título."""
    for trozo in leer_stream(ruta_xml, offset).split("</page>"):
        if f"<title>{html.escape(titulo, quote=False)}</title>" in trozo:
            return trozo.strip() + "\n</page>"
    return None


# ---------------------------------------------------------------------------
# Parseo de páginas
# ---------------------------------------------------------------------------

def normalizar_titulo(t):
    """Normaliza un destino de enlace como lo hace MediaWiki (aprox.)."""
    if "&" in t:
        t = html.unescape(t)
    t = " ".join(t.replace("_", " ").split())
    if not t:
        return t
    return t[0].upper() + t[1:]


def extraer_enlaces(texto, titulo_propio):
    """Devuelve (enlaces a artículos, categorías) del wikitexto, sin duplicados."""
    enlaces, categorias = set(), set()
    for crudo in RE_ENLACE.findall(texto):
        t = crudo.strip().lstrip(":").split("#", 1)[0]
        if not t.strip():
            continue
        if ":" in t:
            prefijo, resto = t.split(":", 1)
            prefijo = " ".join(prefijo.replace("_", " ").split()).lower()
            if prefijo == "category" and not crudo.strip().startswith(":"):
                c = normalizar_titulo(resto)
                if c:
                    categorias.add(c)
                continue
            if prefijo in NS_NO_ARTICULO or prefijo in IDIOMAS:
                continue
        t = normalizar_titulo(t)
        if t and t != titulo_propio:
            enlaces.add(t)
    return enlaces, categorias


# Códigos de idioma frecuentes usados como interwiki ([[fr:Paris]], [[de:...]]).
IDIOMAS = set(
    "aa ab af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz "
    "ee el eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik "
    "io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk "
    "ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa "
    "sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur "
    "uz ve vi vo wa wo xh yi yo za zh zu ang arz ast bar bcl bpy ceb ckb diq frr hak hif hsb ilo jbo kaa "
    "lmo mzn nah nap nds new pam pms pnb sah scn sco sh simple szl tgl vec war wuu yue zea".split()
)


def _texto(elem, ruta):
    e = elem.find(ruta)
    return e.text if e is not None else None


def _entero(elem, ruta):
    v = _texto(elem, ruta)
    return int(v) if v is not None else None


def parsear_pagina(xml_pagina):
    """Convierte un ``<page>...</page>`` en (fila, enlaces, categorías)."""
    p = ET.fromstring(xml_pagina)
    titulo = p.findtext("title")
    ns = int(p.findtext("ns"))
    pid = int(p.findtext("id"))
    red = p.find("redirect")
    rev = p.find("revision")
    contrib = rev.find("contributor")
    tx = rev.find("text")
    texto = (tx.text or "") if tx is not None else ""
    tbytes = tx.get("bytes") if tx is not None else None

    es_redirect = red is not None
    enlaces, categorias = set(), set()
    model = rev.findtext("model")
    if model == "wikitext" and not es_redirect and ns in (0, 14):
        enlaces, categorias = extraer_enlaces(texto, titulo)
        if ns != 0:
            enlaces = set()

    fila = {
        "page_id": pid,
        "title": titulo,
        "ns": ns,
        "is_redirect": es_redirect,
        "redirect_target": red.get("title") if es_redirect else None,
        "rev_id": _entero(rev, "id"),
        "parent_id": _entero(rev, "parentid"),
        "timestamp": rev.findtext("timestamp"),
        "contributor_user": _texto(contrib, "username") if contrib is not None else None,
        "contributor_id": _entero(contrib, "id") if contrib is not None else None,
        "contributor_ip": _texto(contrib, "ip") if contrib is not None else None,
        "minor": rev.find("minor") is not None,
        "model": model,
        "format": rev.findtext("format"),
        "text_bytes": int(tbytes) if tbytes is not None else None,
        "n_enlaces": len(enlaces) if ns == 0 and not es_redirect else None,
        "n_categorias": len(categorias) if ns in (0, 14) and not es_redirect else None,
        "is_disambig": bool(ns == 0 and not es_redirect and RE_DESAMBIG.search(texto)),
    }
    return fila, enlaces, categorias


def paginas_de_texto(texto):
    """Itera los ``<page>...</page>`` completos de un trozo de XML."""
    for trozo in texto.split("</page>"):
        i = trozo.find("<page>")
        if i >= 0:
            yield trozo[i:] + "</page>"


# ---------------------------------------------------------------------------
# Procesamiento de un rango y orquestación
# ---------------------------------------------------------------------------

def _escribir(tabla, ruta):
    tmp = ruta + ".tmp"
    pq.write_table(tabla, tmp, compression="zstd")
    os.replace(tmp, ruta)


def procesar_rango(args):
    """Procesa los streams en ``[ini, fin)`` y escribe tres Parquet.

    ``args = (ruta_xml, ini, fin, out_dir, idx)``. Devuelve un dict con
    estadísticas. El Parquet de ``paginas`` se escribe al final y sirve de
    marca de tarea terminada.
    """
    ruta_xml, ini, fin, out_dir, idx = args
    nombre = f"part-{idx:05d}.parquet"
    destino_pag = os.path.join(out_dir, "paginas", nombre)
    destino_stats = os.path.join(out_dir, "stats", f"part-{idx:05d}.json")
    if os.path.exists(destino_pag) and os.path.exists(destino_stats):
        with open(destino_stats) as f:
            return {**json.load(f), "omitido": True}

    t0 = time.time()
    with open(ruta_xml, "rb") as f:
        f.seek(ini)
        datos = f.read(fin - ini)

    filas = {c: [] for c in ESQUEMA_PAGINAS.names}
    src, dst = [], []
    cat_pid, cat_nom = [], []
    bytes_xml = 0
    n_streams = 0
    while datos:
        d = bz2.BZ2Decompressor()
        texto = d.decompress(datos)
        datos = d.unused_data
        n_streams += 1
        bytes_xml += len(texto)
        for xml_pagina in paginas_de_texto(texto.decode("utf-8")):
            fila, enlaces, categorias = parsear_pagina(xml_pagina)
            for c, v in fila.items():
                filas[c].append(v)
            pid = fila["page_id"]
            src.extend([pid] * len(enlaces))
            dst.extend(enlaces)
            cat_pid.extend([pid] * len(categorias))
            cat_nom.extend(categorias)

    ts = pc.strptime(pa.array(filas.pop("timestamp"), pa.string()),
                     format="%Y-%m-%dT%H:%M:%SZ", unit="s")
    arrays = {c: pa.array(v, ESQUEMA_PAGINAS.field(c).type) for c, v in filas.items()}
    arrays["timestamp"] = ts.cast(pa.timestamp("s", tz="UTC"))
    t_pag = pa.table([arrays[c] for c in ESQUEMA_PAGINAS.names], schema=ESQUEMA_PAGINAS)
    t_enl = pa.table([pa.array(src, pa.int64()), pa.array(dst, pa.string())], schema=ESQUEMA_ENLACES)
    t_cat = pa.table([pa.array(cat_pid, pa.int64()), pa.array(cat_nom, pa.string())],
                     schema=ESQUEMA_CATEGORIAS)

    _escribir(t_enl, os.path.join(out_dir, "enlaces", nombre))
    _escribir(t_cat, os.path.join(out_dir, "categorias", nombre))
    _escribir(t_pag, destino_pag)
    stats = {
        "idx": idx, "ini": ini, "fin": fin, "bytes_comp": fin - ini, "bytes_xml": bytes_xml,
        "streams": n_streams, "paginas": t_pag.num_rows, "enlaces": t_enl.num_rows,
        "categorias": t_cat.num_rows, "segundos": time.time() - t0, "fin_unix": time.time(),
    }
    with open(destino_stats, "w") as f:
        json.dump(stats, f)
    return {**stats, "omitido": False}


def extraer_todo(ruta_xml, offsets, out_dir, procesos=14, n_tareas=400, progreso=True):
    """Procesa el dump completo en paralelo. Es reanudable: las tareas cuyo
    Parquet ya existe se omiten. Devuelve la lista de estadísticas por tarea."""
    for sub in ("paginas", "enlaces", "categorias", "stats"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    tam = os.path.getsize(ruta_xml)
    tareas = [(ruta_xml, a, b, out_dir, i) for i, (a, b) in enumerate(rangos(offsets, tam, n_tareas))]
    # Las tareas grandes primero para equilibrar la carga al final.
    tareas.sort(key=lambda t: t[2] - t[1], reverse=True)

    barra = None
    if progreso:
        from tqdm.auto import tqdm
        barra = tqdm(total=sum(t[2] - t[1] for t in tareas), unit="B", unit_scale=True,
                     desc="bz2 procesado")
    resultados = []
    with Pool(procesos) as pool:
        for r in pool.imap_unordered(procesar_rango, tareas):
            resultados.append(r)
            if barra is not None:
                barra.update(r["bytes_comp"])
    if barra is not None:
        barra.close()
    return sorted(resultados, key=lambda r: r["idx"])
