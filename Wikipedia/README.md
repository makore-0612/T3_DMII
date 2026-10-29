# Wikipedia: PageRank, HITS y PageRank sensible a tópico

Grafo de enlaces entre los artículos de la Wikipedia en inglés: si el artículo *i* enlaza al artículo *j*, hay una arista
*i → j*. Sobre ese grafo se calculan PageRank, HITS y un PageRank por tema.

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
  menús de navegación, no contenido, y cumplen el papel de los seudoartistas de Spotify. PageRank sobre el grafo
  completo se compara en una sección de robustez: Spearman 0.992 y Jaccard del top-100 0.961.
- **Listas y cronologías** (`List of…`, `1982`, `2025 in the United States`) sí son contenido y se conservan; solo se
  marcan.
- **Colgantes y trampas de araña.** Hay 7,634 colgantes (0.11 %) y solo 8 trampas de araña, de 2 nodos cada una. La
  SCC mayor tiene el 91.8 % de los artículos.
- **Título duplicado.** *200th Division* tiene dos `page_id`; los enlaces a ese título cuentan para los dos.

## 4. Decisiones de los algoritmos

Todos se implementan con el **método de potencias sobre `scipy.sparse`**.

- Los productos matriz-vector se hacen en paralelo con 16 bloques de filas.

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
- **Validación:** residuos de las relaciones de la iteración, cociente de Rayleigh, y $\sigma_1^2$ calculado aparte
  con `svds` (`maxiter = 30`). Coinciden con una diferencia relativa de 3e-13.
- Además, un **HITS dependiente de consulta** (Kleinberg):
  - conjunto raíz = artículos de una categoría y sus subcategorías a 2 niveles;
  - conjunto base = raíz + enlazados + hasta 50 artículos que enlazan a cada uno.

**PageRank sensible a tópico (notebook 03).**
- **Raíces.** Las 34 subcategorías de *Main topic classifications*, sin *Lists* ni *Main topic articles*: quedan 32
  tópicos (*Science*, *History*, *Geography*, *Humans*…).
- **Categorías de mantenimiento.** Se quitan del árbol y de los artículos (*Articles with…*, *Pages using…*, *CS1…*,
  *Use dmy dates…*, *Wikipedia…*).
- **Asignación.**
  - Con un BFS desde cada raíz se calcula la distancia de cada categoría.
  - La distancia de un artículo a una raíz es 1 + la mínima de sus categorías.
  - El artículo pertenece al tópico o tópicos **más cercanos**, si esa distancia es ≤ **D = 8**. La pertenencia es
    múltiple, como en Spotify.
  - Con D = 8 tiene tópico el 95.3 % de los artículos del grafo de análisis.
- **Vectores.**
  - Un vector por tópico: teletransportación uniforme a sus artículos, y colgantes de regreso al tópico.
  - Los 32 se calculan a la vez como un producto de $A^\top$ por una matriz densa $n \times 32$.
  - Tolerancia $10^{-8}$ por columna, máximo 1,000 iteraciones.
- **Validación**:
  - se ocultan el 20 % de los artículos con tópico (semilla 42) y se recalculan los vectores;
  - para cada artículo oculto se predice $\arg\max_T r_T(i)$;
  - se compara contra el tópico mayor y contra el voto de los vecinos.

  Resultado: 41.1 % de aciertos, contra 29.6 % de la línea base y 48.3 % del voto de vecinos.
- También se prueba una consulta de usuario como mezcla lineal de tópicos (70 % *Science*, 30 % *History*). Coincide
  con el cálculo directo con una diferencia de 2.7e-04.

Las conclusiones y limitaciones de los tres notebooks están al final de `03_topic_sensitive.ipynb`.

## 5. Orden de replicación

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
| `02_pagerank_hits.ipynb` | `grafo/` | `grafo/adyacencia.npz`, `grafo/puntajes.parquet` y `resultados/02_pagerank_hits/` | 16 min |
| `03_topic_sensitive.ipynb` | `grafo/` y `grafo/puntajes.parquet` | `resultados/03_topic_sensitive/` | 35 min (12 por cada corrida de los 32 vectores) |

Cada paso guarda sus resultados en `data/resultados/`:
- los vectores en Parquet, con `id` y `title`;
- las tablas en CSV;
- las gráficas en PNG.
