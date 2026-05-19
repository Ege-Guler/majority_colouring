# Graph Dashboard

Interactive Streamlit dashboard for the majority-colouring graph enumeration results.

## Features

- Reads any `notebooks/results_<n>vertex.csv` — including the 38 GB 6-vertex file — without loading the full table into memory. DuckDB streams the file with a 4 GB memory cap, keeping the process under 5 GB total.
- Charts (Plotly) for every CSV property: `mask`, `num_edges`, `chromatic_number`, `is_isomorphic`, `is_cyclic`, `connectivity_number`, `stability_number`, `clique_number`, `has_hamiltonian_path`.
- Filter widgets for every property, paginated result table.
- Pick one graph (by row click or by typing its `mask`) and render the directed graph **on demand** with NetworkX + matplotlib. The figure is freed from memory immediately after display — nothing is written to disk.

## Install

From the repo root, with the existing `.venv` activated:

```bash
pip install -r dashboard/requirements.txt
```

## Run

```bash
streamlit run dashboard/app.py
```

The app opens at <http://localhost:8501>.

## Tips

- For repeat use of the 6-vertex CSV, click **Build Parquet cache** in the sidebar once. Subsequent queries become ~10× faster. The Parquet sibling lives next to the CSV in `notebooks/`.
- Every chart is computed by SQL aggregates over the file, so memory use is bounded regardless of vertex count.

## Layout

```
dashboard/
├── app.py            # Streamlit entrypoint
├── data_access.py    # DuckDB-backed query helpers
├── graph_decode.py   # mask → directed-edge list (mirrors enumerate_graphs.jl)
├── visualize.py      # On-demand graph rendering with explicit cleanup
├── requirements.txt
└── README.md
```
