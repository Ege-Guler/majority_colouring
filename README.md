# Majority Colouring

A computational study of the **majority colouring conjecture** for directed graphs. The conjecture states that every directed graph can be coloured with 4 colours such that for every vertex v and every colour c, at most half of v's out-neighbours have colour c.

This repo enumerates all directed graphs up to N vertices, computes the minimum number of majority colours needed for each one via a Gurobi MILP, and stores the results for analysis.

**Published results:** [5-vertex analysis notebook](https://github.com/Ege-Guler/majority_colouring/blob/main/notebooks/graph_analysis.ipynb)

---

## Table of contents

1. [What is majority colouring?](#1-what-is-majority-colouring)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
4. [Repository layout](#4-repository-layout)
5. [Running the enumeration](#5-running-the-enumeration)
6. [Understanding the output](#6-understanding-the-output)
7. [Exploring results](#7-exploring-results)
8. [Expected runtimes](#8-expected-runtimes)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. What is majority colouring?

A **majority colouring** of a directed graph assigns a colour to each vertex so that for every vertex v and every colour c:

> at most ⌊ d⁺(v) / 2 ⌋ of v's out-neighbours share colour c

where d⁺(v) is the out-degree of v. In other words, no colour is a *majority* among any vertex's out-neighbours — at best a tie.

The **majority colouring conjecture** (Kreutzer, Oum, Seymour, van der Zypen, Wood — 2017) states that 4 colours always suffice. This project verifies the conjecture exhaustively for all graphs on up to 6 vertices by solving a Mixed-Integer Linear Program (MILP) for each graph.

---

## 2. Prerequisites

### Required

| Tool | Version | Purpose |
|---|---|---|
| [Julia](https://julialang.org/downloads/) | 1.12 | Graph enumeration and MILP solving |
| [Gurobi](https://www.gurobi.com/downloads/) | ≥ 10 | MILP solver (free academic licence available) |
| Python | 3.12 | Analysis scripts and dashboard |

### Installing Julia

The easiest way is [juliaup](https://github.com/JuliaLang/juliaup):

```bash
# Linux / macOS
curl -fsSL https://install.julialang.org | sh

# Windows (PowerShell)
winget install julia -s msstore
```

After installation, confirm it works:

```bash
julia --version
```

### Installing Gurobi

1. Register for a free academic licence at [gurobi.com](https://www.gurobi.com/academia/academic-program-and-licenses/).
2. Download and install Gurobi (follow their installer).
3. Activate your licence with `grbgetkey <your-key>`.
4. Set the environment variable `GUROBI_HOME` to your Gurobi installation directory if it isn't set automatically.

Confirm it works:

```bash
gurobi_cl --version
```

---

## 3. Installation

### Clone the repository

```bash
git clone https://github.com/Ege-Guler/majority_colouring.git
cd majority_colouring
```

### Julia environment setup

Run the setup script once. It installs all Julia dependencies and registers a Jupyter kernel (optional — only needed if you want to run the `.ipynb` notebooks).

**Linux / macOS:**
```bash
./setup.sh
```

**Windows (PowerShell):**
```powershell
# Allow running local scripts once
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

.\setup.ps1
```

Both scripts:
- Run `Pkg.instantiate()` to install every Julia package listed in `Project.toml`
- Run `Pkg.precompile()` so the first Julia run isn't slow
- Install an IJulia kernel named `MajorityColoring` (skipped gracefully if Jupyter is not installed)

You can pass a custom kernel name:
```bash
./setup.sh "MyKernelName"
```

What gets installed (from `Project.toml`):

| Package | Role |
|---|---|
| `Graphs` | Graph data structures and algorithms |
| `JuMP` | Mathematical optimisation modelling |
| `Gurobi` | JuMP solver backend |
| `GraphPlot`, `Compose`, `Cairo`, `Colors` | Graph visualisation |
| `Combinatorics` | Permutation generation for isomorphism |
| `IJulia` | Julia kernel for Jupyter |

### Python environment setup

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# Install all Python dependencies
pip install -r requirements.txt
```

---

## 4. Repository layout

```
majority_colouring/
│
├── julia/                        ← Julia computation scripts
│   ├── enumerate_graphs.jl       #   main entry point — run this
│   ├── solve_majority_coloring_out.jl  # Gurobi MILP (used by enumerate_graphs.jl)
│   ├── plot_digraph.jl           #   basic graph plotter
│   ├── plot_advanced_digraph.jl  #   coloring-aware plotter
│   └── README.md                 #   full function-level documentation
│
├── notebooks/                    ← Jupyter notebooks (analysis & exploration)
│   ├── graph_analysis.ipynb      #   5-vertex results analysis
│   ├── graph_analysis_6vertex.ipynb
│   ├── graph_generation.ipynb
│   └── GraphPlotTest.ipynb
│
├── scripts/                      ← Standalone Python analysis scripts
│   ├── analyze_6vertex.py        #   quick chromatic distribution summary
│   └── comprehensive_analyze_6vertex.py  # full statistical analysis + plots
│
├── results/                      ← CSV output from Julia runs lands here
│   └── (results_<N>vertex.csv appear here after you run enumerate_graphs.jl)
│
├── dashboard/                    ← Streamlit web dashboard
│   ├── app.py
│   ├── data_access.py
│   ├── visualize.py
│   └── README.md
│
├── tools/                        ← C++ utilities for post-processing large CSVs
│
├── Project.toml                  ← Julia package manifest
├── requirements.txt              ← Python package list
├── setup.sh                      ← Linux/macOS one-time setup
└── setup.ps1                     ← Windows one-time setup
```

---

## 5. Running the enumeration

The main script is `julia/enumerate_graphs.jl`. It generates every weakly connected directed graph on N vertices and writes one CSV row per graph with its majority chromatic number and structural properties.

### Basic usage

```bash
# Default: N=5 (≈1 million graphs, ~30 seconds on a modern CPU)
julia --project -t auto julia/enumerate_graphs.jl

# Explicit N
julia --project -t auto julia/enumerate_graphs.jl 3
julia --project -t auto julia/enumerate_graphs.jl 4
julia --project -t auto julia/enumerate_graphs.jl 5
```

`-t auto` tells Julia to use all available CPU threads. You can pin a specific count:

```bash
julia --project -t 4 julia/enumerate_graphs.jl 5
```

Output is written to `results/results_<N>vertex.csv`.

### The `--filter-odd-cycles` flag

By **Proposition 1 of [arXiv:1911.01954](https://arxiv.org/pdf/1911.01954)**, any directed graph with no directed odd cycle is provably majority 2-colourable. Passing this flag skips those graphs entirely — Gurobi is never called for them, and they are not written to the CSV.

```bash
julia --project -t auto julia/enumerate_graphs.jl 5 --filter-odd-cycles
julia --project -t auto julia/enumerate_graphs.jl 6 --filter-odd-cycles
```

Output goes to `results/results_<N>vertex_odd_only.csv`.

For N=5, ~98.9% of graphs are 2-colourable, so this flag eliminates the vast majority of Gurobi calls and makes the 6-vertex run significantly faster.

### What the script prints while running

```
Precomputing 5-vertex permutation maps...
Enumerating all 1048576 directed graphs on 5 vertices...
Threads (Julia):    8
CSV Output:         /path/to/results/results_5vertex.csv
Filter odd cycles:  false
Progress: 20000 / 1048576  (1.91%)
Progress: 40000 / 1048576  (3.81%)
...
Done.

Timing Summary (Cumulative Thread Time):
  solve_majority           : 4821.3 seconds
  property_computation     : 312.1 seconds
  isomorphism_check        : 28.4 seconds
  mask_to_graph            : 6.2 seconds
  odd_cycle_check          : 0.0 seconds

Summary by chromatic number for N=5:
  2 color(s) : 983041 graphs
  3 color(s) : 62145 graphs
  4 color(s) : 0 graphs
Total graphs written: 1045186
```

---

## 6. Understanding the output

Each run produces a CSV file in `results/` with one row per weakly connected directed graph:

| Column | Type | Description |
|---|---|---|
| `mask` | integer | Bitmask encoding which edges are present. Bit k = 1 means edge `ALL_EDGES[k]` exists. |
| `num_edges` | integer | Total number of edges in the graph. |
| `chromatic_number` | integer | Minimum number of majority colours needed. Always 2, 3, or 4 for connected graphs; -1 for disconnected ones (excluded from output). |
| `is_isomorphic` | bool | `true` if this graph is an isomorphic copy of an earlier graph in the file. Only one representative per isomorphism class has `false`. |
| `is_cyclic` | bool | `true` if the graph contains at least one directed cycle. |
| `connectivity_number` | integer | Vertex connectivity κ(G): minimum vertices to remove to disconnect the graph. |
| `stability_number` | integer | Independence number α(G): size of the largest independent set (in the undirected sense). |
| `clique_number` | integer | Clique number ω(G): size of the largest clique in the underlying undirected graph. |
| `has_hamiltonian_path` | bool | `true` if a path visiting every vertex exactly once exists. |

### Reading the bitmask

The edge list for N vertices is ordered as:

```
(1→2), (1→3), …, (1→N), (2→1), (2→3), …, (N→N-1)
```

i.e. `ALL_EDGES = [(i,j) for i in 1:N for j in 1:N if i≠j]`

Bit k (0-indexed) of `mask` is 1 if `ALL_EDGES[k+1]` is present. To decode a mask in Python:

```python
N = 5
all_edges = [(i, j) for i in range(1, N+1) for j in range(1, N+1) if i != j]
mask = 12345

edges = [all_edges[k] for k in range(len(all_edges)) if (mask >> k) & 1]
```

---

## 7. Exploring results

### Interactive dashboard (recommended)

The Streamlit dashboard lets you filter, chart, and visualise individual graphs without loading large files into memory. It uses DuckDB to query CSVs with a 4 GB memory cap.

```bash
# Make sure your Python venv is active
streamlit run dashboard/app.py
```

Opens at [http://localhost:8501](http://localhost:8501). The sidebar shows all CSV files found in `notebooks/` and `results/`.

**Tips:**
- For the 6-vertex CSV (36 GB), click **Build Parquet cache** once in the sidebar. All subsequent queries become ~10× faster.
- Click any row in the result table to render that graph visually.

### Jupyter notebooks

```bash
jupyter notebook
# or
jupyter lab
```

Select the `MajorityColoring` kernel (installed by `setup.sh`/`setup.ps1`) and open any notebook in `notebooks/`.

- `graph_analysis.ipynb` — 5-vertex results (chromatic distribution, property correlations)
- `graph_analysis_6vertex.ipynb` — 6-vertex analysis
- `graph_generation.ipynb` — walkthrough of how masks map to graphs

### Python analysis scripts

These scripts work on the 6-vertex CSV and produce plots in `results/visualizations/`.

```bash
# Make sure your venv is active
python scripts/analyze_6vertex.py
python scripts/comprehensive_analyze_6vertex.py
```

`analyze_6vertex.py` — quick log-scale chromatic distribution plot.

`comprehensive_analyze_6vertex.py` — full analysis: distribution plot, property boxplots, correlation heatmap, clique violin plot, and a `summary_stats.csv`.

Both scripts handle the 36 GB file in 1M-row chunks and never load the full table into memory.

---

## 8. Expected runtimes

| N | Total masks | Approximate time | Output size |
|---|---|---|---|
| 3 | 64 | < 1 second | 1.7 KB |
| 4 | 4,096 | ~5 seconds | 113 KB |
| 5 | 1,048,576 | ~30 seconds | 33 MB |
| 6 | 1,073,741,824 | ~10 hours | 36 GB |

Times measured with `-t 8` on an Intel Core i5-1235U (12th Gen, 6P+4E cores) with 30 GB RAM, using Gurobi. The 6-vertex run is significantly faster with `--filter-odd-cycles` since it skips ~99% of Gurobi calls.

For reference, pre-computed results are available:
- N=3, 4, 5: committed in `notebooks/`
- N=6 (full): too large to commit — run it yourself or request from maintainers
- N=6 (100k random sample): `notebooks/results_6vertex_max100k_random.csv`
- N=6 (chromatic=3 only): `tools/results_6vertex_chromatic3_stratified100000.csv`

---

## 9. Troubleshooting

**`julia: command not found`**
Julia is not on your PATH. Re-run the juliaup installer or add Julia's bin directory to your PATH manually.

**`ERROR: LoadError: ArgumentError: Package Gurobi not found`**
Run `julia --project -e 'using Pkg; Pkg.instantiate()'` from the repo root. If that succeeds but Gurobi still fails, check that your Gurobi licence is activated (`grbgetkey`) and `GUROBI_HOME` points to the correct directory.

**`GurobiError: No Gurobi licence found`**
Your Gurobi licence has not been activated or has expired. Visit [gurobi.com/academia](https://www.gurobi.com/academia/academic-program-and-licenses/) to request a free academic licence and re-run `grbgetkey`.

**Slow first run**
Julia precompiles packages the first time they are loaded. The `setup.sh` script runs `Pkg.precompile()` to do this upfront, but if you skipped setup just run it once:
```bash
julia --project -e 'using Pkg; Pkg.precompile()'
```

**Dashboard shows no datasets**
The dashboard looks for `results_*vertex.csv` files in `notebooks/` and `results/`. Run the enumeration for at least N=3 to generate `results/results_3vertex.csv`, or point the dashboard to an existing CSV using the file-path input in the sidebar.

**`ModuleNotFoundError` when running Python scripts**
Your virtual environment is not active. Run `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows) before running any Python command.

---

## Further reading

- `julia/README.md` — full function-by-function documentation of every Julia function
- `OPTIMIZATIONS.md` — technical notes on performance (sharded cache, producer-consumer architecture, canonical labelling)
- `dashboard/README.md` — dashboard layout and DuckDB memory management
- [arXiv:1911.01954](https://arxiv.org/pdf/1911.01954) — the paper whose Proposition 1 justifies the `--filter-odd-cycles` optimisation
