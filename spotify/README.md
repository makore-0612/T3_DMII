# Práctica 3: Red de colaboraciones de Spotify

**Datos Masivos II · Equipo Tres:** Castrillo Cruz Karen Arlet, Ramos González Nadia, Zamora Antiga Ángel Javier.

Análisis de la red de colaboraciones entre artistas de Spotify con tres algoritmos de análisis de enlaces: PageRank, HITS y PageRank sensible a tópico.

## Contenido

```
.
├── Notebooks/ 
|   └── pagerank_hits_spotify.ipynb     # Notebook con todo el análisis
├── requirements.txt                    # Dependencias de Python
└── Datos/                              # No incluida en el repositorio (ver más abajo)
    ├── nodes.csv
    └── edges.csv
```

### Datos

Se usa el conjunto [*Spotify Artist Feature Collaboration Network*](https://www.kaggle.com/datasets/jfreyberg/spotify-artist-feature-collaboration-network): cada nodo es un artista y cada arista indica que dos artistas colaboraron en al menos una canción.

| Archivo | Registros | Columnas |
| :--- | :--- | :--- |
| `nodes.csv` | 156,422 artistas | `spotify_id`, `name`, `followers`, `popularity`, `genres`, `chart_hits` |
| `edges.csv` | 300,386 colaboraciones | `id_0`, `id_1` |

### Notebook

1. **Selección de datos:** revisión de calidad y limpieza (IDs repetidos, aristas con extremos inexistentes, seudoartistas como `Traditional`, artistas aislados).
2. **Análisis exploratorio:** seguidores, popularidad, géneros, *charts* y distribución del grado.
3. **Transformación:** matriz de adyacencia dispersa, componentes conexas, agrupación de géneros en 10 macrogéneros (los tópicos) y versión dirigida de la red para HITS.
4. **Aplicación de algoritmos:**
   * **PageRank**, implementado por el método de potencias, con un barrido del factor de amortiguamiento.
   * **HITS**, en la red no dirigida y en una versión dirigida por popularidad, con y sin el clúster de música clásica.
   * **PageRank sensible a tópico**, con un vector por macrogénero y una combinación lineal de ejemplo.
5. **Validación y comparación:** recuperación de macrogéneros ocultos con PageRank por tópico y comparación de todas las medidas de importancia.
6. **Conclusiones.**

PageRank y HITS están implementados con `scipy.sparse` y se validan contra `networkx` y contra el vector propio principal de la matriz de adyacencia.

## Cómo replicarlo

### 1. Requisitos

* Python 3.12 (versión con la que se desarrolló; las versiones exactas de las bibliotecas están en `requirements.txt`).
* Memoria: la red es dispersa, por lo que no requiere más que unos pocos GB de RAM.
* Tiempo de ejecución: alrededor de 4 minutos para correr el notebook completo.

### 2. Instalar las dependencias

```bash
pip install -r requirements.txt
```

### 3. Descargar los datos

Los datos no se incluyen en el repositorio. Descarga `nodes.csv` y `edges.csv` desde [Kaggle](https://www.kaggle.com/datasets/jfreyberg/spotify-artist-feature-collaboration-network) y colócalos en una carpeta `Datos/` en la raíz del proyecto:

```
Datos/nodes.csv
Datos/edges.csv
```

El notebook los lee con rutas relativas (`Datos/nodes.csv` y `Datos/edges.csv`).

> Los resultados son deterministas: PageRank y HITS no usan aleatoriedad, y la única selección aleatoria (el 20% de artistas ocultos en la validación) usa una semilla fija (`42`).