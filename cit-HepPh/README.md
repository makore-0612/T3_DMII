# cit-HepPh: PageRank, HITS y PageRank sensible a tópico

Red de citas entre artículos de la categoría *High Energy Physics – Phenomenology* de arXiv
([SNAP, cit-HepPh](https://snap.stanford.edu/data/cit-HepPh.html)): si el artículo *i* cita al artículo *j*, hay una arista
*i → j*.

## Cómo replicarlo

1. **Datos.** Descarga los dos archivos de SNAP y colócalos, sin descomprimir, en `cit-HepPh/data/`:

   ```bash
   mkdir -p cit-HepPh/data
   curl -o cit-HepPh/data/cit-HepPh.txt.gz       https://snap.stanford.edu/data/cit-HepPh.txt.gz
   curl -o cit-HepPh/data/cit-HepPh-dates.txt.gz https://snap.stanford.edu/data/cit-HepPh-dates.txt.gz
   ```

2. **Dependencias.** Desde la raíz del repositorio: `pip install -r cit-HepPh/requirements.txt`. Los notebooks se
   ejecutaron con Python 3.14.7 y las versiones fijadas en ese archivo.
3. **Orden de ejecución**, desde `cit-HepPh/notebooks/` (cada uno usa las salidas del anterior):

   | Notebook | Lee | Genera en `data/processed/` | Tiempo aprox. |
   |---|---|---|---|
   | `01_eda_calidad_preprocesamiento.ipynb` | `data/cit-HepPh.txt.gz`, `data/cit-HepPh-dates.txt.gz` | `aristas_limpias.parquet`, `nodos_limpios.parquet`, `fechas_cross_listed.parquet` | 1 min |
   | `02_pagerank_hits.ipynb` | los Parquet del notebook 1 | `adyacencia.npz` (matriz CSR con el arreglo de IDs) | 1–2 min |
   | `03_topic_sensitive.ipynb` | `adyacencia.npz` y los Parquet | — | 1–2 min |

   Los resultados son reproducibles: las partes aleatorias (muestreo de BFS, Louvain, Isolation Forest) usan
   `random_state` / `seed` = 42.

## Decisiones principales

- **IDs.** Los de las aristas perdieron los ceros a la izquierda y se normalizan a 7 dígitos. Los artículos
  *cross-listed* del archivo de fechas se separan y no se usan para fechar nodos, incluidos los que aparecen disfrazados
  de IDs normales (notebook 1, sección 2).
- **Limpieza.** Se eliminan las 44 autocitas. Los pares recíprocos y las citas al futuro se conservan con las marcas
  `es_reciproca` y `es_futuro`.
- **Grafo de análisis.** PageRank, HITS y el PageRank sensible a tópico se calculan **sin las 1,852 citas al futuro**,
  que crean los ciclos del grafo. El grafo completo se compara en una sección de robustez (notebook 2, sección 4.4).
- **Fechas.** El archivo de fechas termina el 12/03/2002. Los nodos posteriores usan el año y mes de su ID (`mes_id`).
- **Tópicos.** Son las 15 comunidades de Louvain (`seed=42`, `resolution=1`) con al menos el 1 % de los nodos, sin nombres
  de tema porque no se usa texto.
