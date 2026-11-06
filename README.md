<img src="https://mmss.iimas.unam.mx/dmmss/wp-content/uploads/2026/02/cropped-LogoUNAM_IIMAS_Negro50-scaled-2.png" width="200"/>

### Datos Masivos II
# Práctica 3: Análisis de enlaces con PageRank, HITS y PageRank sensible a tópico
> Equipo Tres: Castrillo Cruz Karen Arlet, Ramos González Nadia, Zamora Antiga Ángel Javier.

---

Este repositorio mide la importancia de los nodos de tres redes con tres algoritmos de análisis de enlaces: **PageRank**
(con teletransportación), **HITS** (hubs y autoridades) y **PageRank sensible a tópico**.

| Carpeta | Dataset | Red | Tópicos |
|---|---|---|---|
| `cit-HepPh/` | [cit-HepPh (SNAP)](https://snap.stanford.edu/data/cit-HepPh.html): citas entre artículos de arXiv `hep-ph`, 1992–2003 | Dirigida: 34,546 artículos y 421,578 citas | Comunidades de Louvain del grafo de citas |
| `spotify/` | [Spotify Artist Feature Collaboration Network (Kaggle)](https://www.kaggle.com/datasets/jfreyberg/spotify-artist-feature-collaboration-network) | No dirigida: 156,422 artistas y 300,386 colaboraciones | Macrogéneros musicales |
| `Wikipedia/` | [Dump de la Wikipedia en inglés (Wikimedia)](https://dumps.wikimedia.org/enwiki/latest/): enlaces entre artículos, revisiones hasta octubre de 2026 | Dirigida: 7,249,099 artículos y 236,242,098 enlaces | Temas de *Main topic classifications* (árbol de categorías) |

```text
T3_DMII/
├── cit-HepPh/
│   ├── notebooks/
│   │   ├── 01_eda_calidad_preprocesamiento.ipynb   # perfilado, calidad, enlace aristas–fechas y limpieza
│   │   ├── 02_pagerank_hits.ipynb                  # matriz dispersa, PageRank (β, cohortes, robustez) y HITS
│   │   └── 03_topic_sensitive.ipynb                # Louvain, PageRank por tópico, FP-Growth, NMF, t-SNE, conclusiones
│   ├── requirements.txt
│   ├── README.md                                   # descarga de los datos y orden de ejecución
│   └── data/                                       # no incluida: ver cit-HepPh/README.md
├── spotify/
│   ├── Notebooks/
│   │   └── pagerank_hits_spotify.ipynb             # limpieza, EDA, PageRank, HITS y PageRank por macrogénero
│   ├── requirements.txt
│   ├── README.md                                   # descarga de los datos y cómo replicarlo
│   └── Datos/                                      # no incluida: ver spotify/README.md
└── Wikipedia/
    ├── notebooks/
    │   ├── 01_carga_exploracion.ipynb              # lectura paralela del dump, exploración y grafo de enlaces (Spark)
    │   ├── 02_pagerank_hits.ipynb                  # matriz dispersa, PageRank (β, robustez, antigüedad) y HITS
    │   ├── 03_topic_sensitive.ipynb                # temas por categorías, PageRank y HITS por tema, validación
    │   └── 04_recomendaciones.ipynb                # recomendaciones a partir de un artículo, evaluación, conclusiones
    ├── wiki_extract.py                             # extracción en paralelo del dump multistream
    ├── registro.py                                 # guardado de resultados y resumen de avance
    ├── requirements.txt
    ├── README.md                                   # descarga de los datos, decisiones y orden de ejecución
    └── data/                                       # no incluida: ver Wikipedia/README.md
```

Los datos no se incluyen en el repositorio; cada carpeta explica cómo obtenerlos. Cada dataset tiene su propio
`requirements.txt` con las versiones con las que se ejecutaron sus notebooks.

> Instituto de Investigaciones en Matemáticas Aplicadas y en Sistemas, Universidad Nacional Autónoma de México. 29 de octubre de 2026.
