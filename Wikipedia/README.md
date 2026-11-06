# Wikipedia: PageRank, HITS y PageRank sensible a tópico

Grafo de enlaces entre los artículos de la Wikipedia en inglés: si el artículo *i* enlaza al artículo *j*, hay una arista
*i → j*. Sobre ese grafo se calculan PageRank, HITS, un PageRank por tema y recomendaciones a partir de un artículo.

## 1. Los datos

**El archivo.** Se usa el dump `enwiki-latest-pages-articles-multistream.xml.bz2` que publica la Fundación Wikimedia en
[dumps.wikimedia.org/enwiki/latest/](https://dumps.wikimedia.org/enwiki/latest/), junto con su índice
`enwiki-latest-pages-articles-multistream-index.txt.bz2`.

- La copia usada se descargó el 25 de octubre de 2026. Fue generada con MediaWiki 1.47.0-wmf.21, y su revisión más
  reciente es del 7 de octubre de 2026.
- El dump pesa 26.9 GB comprimido (117.8 GB de XML) y el índice 285 MB.
- Como `latest` cambia con cada publicación, quien replique obtendrá un dump más nuevo, con cifras parecidas pero no
  idénticas.

**Qué contiene.** La **última revisión** de cada página de contenido: 25,932,219 páginas de artículos, redirecciones,
categorías, plantillas, archivos, páginas de ayuda y módulos, con su texto en *wikitexto*.

**Qué no contiene.**
- El historial de ediciones.
- Las páginas de discusión ni de usuario (los namespaces impares).
- El texto con las plantillas expandidas.
- Visitas ni fechas de creación.

**Multistream.** El archivo es una concatenación de 259,358 streams bz2 independientes de 100 páginas cada uno. El
índice dice en qué byte empieza cada stream (`offset:page_id:título`). Eso permite leer cualquier artículo sin recorrer
el archivo y repartir el trabajo entre varios procesos.

**El grafo final** (`data/grafo/`):
- 7,249,099 nodos (artículos) y 236,242,098 aristas (enlaces), con un grado medio de 32.6.
- El grafo de análisis, sin páginas de desambiguación, tiene 6,879,374 nodos y 233,221,445 aristas.

## 2. Decisiones de extracción

Están en [`wiki_extract.py`](wiki_extract.py) y en el notebook 01.

- **Lectura en streaming.** El XML no se descomprime a disco; cada stream se descomprime en memoria con
  `bz2.BZ2Decompressor`.
- **Paralelismo con el índice multistream.** Los offsets del índice parten el archivo en 400 rangos de streams
  completos. 14 procesos (`multiprocessing`) los procesan y escriben Parquet por rango.
  - La extracción tarda unos 26 minutos (17 MB/s comprimidos).
  - Se puede reanudar: los rangos ya escritos se omiten.
- **Verificación.** Las páginas extraídas coinciden exactamente con las líneas del índice. Hay 2 streams sin páginas
  que el índice no lista: uno vacío y el cierre `</mediawiki>`.
- **Filtro `ns = 0`.** Los nodos son los artículos: namespace 0 y que no sean redirección. Los enlaces se toman solo
  de su wikitexto.
- **Enlaces.**
  - Se toma el destino de cada `[[Destino]]` o `[[Destino|texto]]`, incluidos los anidados en pies de foto.
  - Se quita `#sección`.
  - Se descartan los prefijos de otros namespaces (`File:`, `Template:`…) y los interwiki (`fr:`, `wikt:`…).
  - Los enlaces se cuentan sin duplicados por artículo y sin autolazos.
- **Normalización de títulos**, como MediaWiki: `_` → espacio, espacios colapsados, entidades HTML decodificadas y
  primera letra en mayúscula.
- **Redirecciones resueltas con un salto.** Un enlace a una redirección (`[[USA]]`) se reemplaza por el artículo
  destino (*United States*). El 99.8 % de las redirecciones llega a un artículo. Las que no:
  - 27,559 apuntan a otro namespace;
  - 155 son dobles redirecciones;
  - unas 55 apuntan a páginas inexistentes.

  Los enlaces a páginas que no existen se descartan.
- **Enlaces de plantillas no expandidos.** Los enlaces que agregan las plantillas (navboxes, infoboxes) **no** se
  cuentan, porque el wikitexto no se expande. Tampoco las categorías que agregan las plantillas.
- **Categorías.** Se guardan las `[[Category:…]]` explícitas de artículos y de páginas de categoría. Con las segundas
  se arma el árbol de categorías.
- **Desambiguación.** Una página es de desambiguación si usa `{{Disambiguation}}` o una de sus variantes (`{{dab}}`,
  `{{hndis}}`, `{{geodis}}`, `{{… disambiguation}}`…).
  - La primera versión de la expresión tenía falsos positivos (`{{Disambiguation needed}}`, `{{Year dab}}`,
    `{{Cite DAB}}`…).
  - Se corrigió y la marca se recalculó leyendo otra vez el dump (ver `data/RESUMEN.md`).

## 3. Decisiones de modelado del grafo

- **Grafo dirigido y no ponderado.** $A_{ij} = 1$ si *i* enlaza a *j*, se mencione el enlace una o varias veces.
- **Índices.** Cada artículo recibe un índice denso `idx` en orden de `page_id`. El `page_id` crece con el orden de
  creación, así que sirve como proxy de antigüedad, con advertencias.
- **Matriz dispersa.** $A$ se guarda en CSR: 2.86 GB, contra 420 TB de la densa. La matriz de transición
  $M = A^\top D_{out}^{-1}$ no se construye: $Mv = A^\top (v / k_{out})$.
- **Grafo de análisis sin páginas de desambiguación.** Se quitan las 369,725 desambiguaciones con sus aristas. Son
  menús de navegación, no contenido. PageRank sobre el grafo
  completo se compara en una sección de robustez: Spearman 0.992 y Jaccard del top-100 0.961.
- **Listas y cronologías** (`List of…`, `1982`, `2025 in the United States`) sí son contenido y se conservan; solo se
  marcan.
- **Colgantes y trampas de araña.** Hay 7,634 colgantes (0.11 %) y solo 8 trampas de araña, de 2 nodos cada una. La
  SCC mayor tiene el 91.8 % de los artículos.
- **Título duplicado.** *200th Division* tiene dos `page_id`; los enlaces a ese título cuentan para los dos.

## 4. Decisiones de los algoritmos

Todos se implementan con el **método de potencias sobre `scipy.sparse`**, sin `networkx` (no cabría en memoria).

- Los productos matriz-vector se hacen en paralelo con 16 bloques de filas.
- Los vectores son `float64`.
- Si algo no converge, se guarda el resultado y se anota el residuo en `data/RESUMEN.md`. En esta ejecución todo
  convergió.

**PageRank (notebook 02).**
- $r = \beta M r + (1-\beta)\,e/n$ con $\beta \in \{0.70, 0.85, 0.95\}$. El análisis usa $\beta = 0.85$.
- La masa de los colgantes se reparte según el vector de teletransportación, como `nx.pagerank` con `dangling=None`.
- Tolerancia $\lVert r_{t+1} - r_t \rVert_1 < 10^{-10}$, máximo 1,000 iteraciones. Converge en 42, 70 y 163
  iteraciones.
- **Validación:** el residuo del punto fijo es 6.5e-11, y la diferencia con `nx.pagerank` en un subgrafo de 20,000
  nodos es 6.7e-13.

**HITS (notebook 02).**
- $a \leftarrow A^\top h$, $h \leftarrow A a$, con normalización $L_1$.
- Tolerancia $10^{-10}$, máximo 500 iteraciones; converge en 106.
- **Validación:** la diferencia con `nx.hits` en el mismo subgrafo de 20,000 nodos es menor a $10^{-16}$.

**PageRank por tema (notebook 03).**
- **Raíces.** Las 34 subcategorías de *Main topic classifications*, sin *Lists* ni *Main topic articles*: quedan 32
  temas (*Science*, *History*, *Geography*, *Humans*…).
- **Categorías de mantenimiento.** Se quitan del árbol y de los artículos (*Articles with…*, *Pages using…*, *CS1…*,
  *Use dmy dates…*, *Wikipedia…*).
- **Pertenencia.**
  - Con un BFS desde cada raíz se calcula la distancia de cada categoría.
  - La distancia de un artículo a una raíz es 1 + la mínima de sus categorías.
  - El artículo pertenece al tema o temas **más cercanos**, si esa distancia es ≤ 8. Puede pertenecer a varios.
  - Así tiene tema el 95.3 % de los artículos del grafo de análisis.
- **Semillas.** El salto de cada vector va solo a los artículos del tema que están a 5 niveles o menos de la raíz. Un
  camino largo se puede desviar del tema.
- **Vectores.**
  - Un vector por tema: salto uniforme a sus semillas, y colgantes de regreso a ellas.
  - Los 32 se calculan a la vez como un producto de $A^\top$ por una matriz densa $n \times 32$.
  - Tolerancia $10^{-8}$ por columna, máximo 1,000 iteraciones; converge en 61, en unos 13 minutos.
- **Orden por especificidad.** $r_S(i)\,\ln(r_S(i) / r(i))$ premia lo que el tema sube respecto al PageRank general.
  La pureza mediana del top-100 pasa de 17 % a 49 %, y mejora en 30 de 32 temas.
- **HITS dentro de cada tema.** Se corre con los enlaces entre las semillas de cada tema; los 32 tardan 17 segundos.
- **Lector con varios intereses.** Mezcla lineal de vectores. Con 70 % *Science* y 30 % *History* coincide con el
  cálculo directo con una diferencia de 1.3e-04.
- **Validación:** se oculta el 20 % de los artículos con tema (semilla 42) y se recalculan los vectores.

| Forma de elegir el tema | Aciertos |
|---|---|
| Voto de vecinos | 48.3 % |
| Mayor $r_T(i)$ | 39.2 % |
| Corregido por tamaño, $r_T(i)\,\lvert S_T\rvert$ | 37.5 % |
| Percentil dentro del tema | 31.8 % |
| Tema más grande (línea base) | 29.6 % |

**Recomendaciones (notebook 04).**
- 10 recomendaciones por artículo, a partir de los puntajes de los 6.88 millones de artículos, sin recortar candidatos.
- **Tres señales:** PageRank que siempre regresa al artículo, ordenado por especificidad (tolerancia $10^{-6}$); artículos
  que se mencionan junto con él, y artículos que enlazan a lo mismo. Las dos últimas pesan menos a páginas y destinos
  muy comunes.
- **Combinación:** se suma $1 / (60 + \text{lugar})$ de cada señal (*reciprocal rank fusion*).
- **Validación:** la diferencia de la primera señal con `nx.pagerank` en un subgrafo de 20,000 nodos es 4.1e-13.
- **Evaluación con 50 artículos al azar** (semilla 42), ocultando el 20 % de sus enlaces de salida. Intervalos de 95 %
  por remuestreo:

| Método | Enlaces ocultos recuperados | Comparten categoría | Del top-1,000 general |
|---|---|---|---|
| PageRank general | 1.3 % (0.4–2.6) | 0.0 % | 100 % |
| Navegación sin especificidad | 12.0 % (7.1–17.7) | 3.8 % (1.6–6.6) | 61.8 % |
| Navegación | 15.0 % (10.1–20.9) | 13.8 % (9.6–18.4) | 12.6 % |
| Se mencionan juntos | 5.1 % (2.6–8.2) | 45.6 % (36.6–54.2) | 0 % |
| Enlazan a lo mismo | 3.8 % (1.6–6.6) | 48.2 % (39.0–57.4) | 0 % |
| Combinación | 8.2 % (5.2–11.9) | 54.2 % (44.8–63.2) | 0 % |

Ningún método gana en todo. No hay clics, así que no se mide si a un lector le sirve una recomendación.

Las conclusiones y limitaciones de toda la práctica están al final de `04_recomendaciones.ipynb`.

## 5. Orden de replicación

**Hardware usado.**
- Disco: unos 27 GB para el dump y el índice, más unos 11 GB para `data/`:
  - extracción, 4 GB;
  - grafo y matriz, 4 GB;
  - resultados, 3 GB.
- Memoria: los notebooks 02, 03 y 04 mantienen en memoria la matriz por bloques (~3 GB por copia) y, en el 03, matrices
  densas de $n \times 32$ (~1.8 GB cada una).

**Software.**
- Python 3.11 y `pip install -r Wikipedia/requirements.txt`.
- **Java 17** para PySpark (notebook 01), por ejemplo `winget install EclipseAdoptium.Temurin.17.JDK`.
- En Windows, además, **`winutils.exe` y `hadoop.dll`** de Hadoop 3.4
  ([kontext-tech/winutils](https://github.com/kontext-tech/winutils/tree/master/hadoop-3.4.0-win10-x64/bin)) en
  `C:\hadoop\bin`. El notebook fija `HADOOP_HOME=C:\hadoop` si no está definido.

**Datos.** Descarga los dos archivos en `Wikipedia/data/`, sin descomprimir:

```bash
mkdir -p Wikipedia/data
curl -o Wikipedia/data/enwiki-latest-pages-articles-multistream.xml.bz2 \
     https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles-multistream.xml.bz2
curl -o Wikipedia/data/enwiki-latest-pages-articles-multistream-index.txt.bz2 \
     https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles-multistream-index.txt.bz2
```

**Orden de ejecución**, desde `Wikipedia/notebooks/` (cada uno usa las salidas del anterior). Los tiempos son los
reales de esta ejecución:

| Notebook | Lee | Genera en `data/` | Tiempo |
|---|---|---|---|
| `01_carga_exploracion.ipynb` | el dump y su índice | `paginas/`, `enlaces/`, `categorias/` y `grafo/` (`nodos`, `aristas`, `categorias_nodo`, `jerarquia_categorias`) | 36 min (26 de extracción) |
| `02_pagerank_hits.ipynb` | `grafo/` y una muestra del dump | `grafo/adyacencia.npz`, `grafo/puntajes.parquet` y `resultados/02_pagerank_hits/` | 15 min |
| `03_topic_sensitive.ipynb` | `grafo/` y `grafo/puntajes.parquet` | `resultados/03_topic_sensitive/` | 33 min (unos 13 por cada corrida de los 32 vectores) |
| `04_recomendaciones.ipynb` | `grafo/`, `grafo/puntajes.parquet` y `resultados/03_topic_sensitive/` | `resultados/04_recomendaciones/` | 31 min (24 de la evaluación) |

Cada paso guarda sus resultados en `data/resultados/`:
- los vectores en Parquet, con `id` y `title`;
- las tablas en CSV;
- las gráficas en PNG.

Además, actualiza `data/RESUMEN.md` con lo terminado, lo pendiente y la duración de cada paso
([`registro.py`](registro.py)). Nada de `data/` se sube al repositorio.
