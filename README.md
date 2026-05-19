# Majority Colouring

## 5 vertices graph results
https://github.com/Ege-Guler/majority_colouring/blob/main/notebooks/graph_analysis.ipynb

## Windows setup
1. Install Julia (e.g., via juliaup) and ensure `julia` is on your PATH.
2. (Optional) Install Jupyter: `pip install notebook` (or `pip install jupyterlab`).
3. Open PowerShell and run:
   `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
4. From the repository root, run:
   `.\setup.ps1` (optionally `.\setup.ps1 "KernelName"`).
5. Start Jupyter with `jupyter notebook` and select the `MajorityColoring` kernel (or your custom name).

## Linux setup
1. Install Julia (e.g., via juliaup) and ensure `julia` is on your PATH.
2. (Optional) Install Jupyter: `pip install notebook` (or `pip install jupyterlab`).
3. From the repository root, run:
   `./setup.sh` (optionally `./setup.sh "KernelName"`).
4. Start Jupyter with `jupyter notebook` and select the `MajorityColoring` kernel (or your custom name).

## Running the enumeration
To run the optimized graph enumeration with multithreading, use the `-t` (or `--threads`) flag. You can also specify the number of vertices $N$ as an argument (default is 5).

```bash
# Run for 5 vertices using all available CPU cores
julia --project -t auto notebooks/enumerate_graphs.jl 5

# Run for 6 vertices using 8 threads (Warning: 2^30 masks, will take several days)
julia --project -t 8 notebooks/enumerate_graphs.jl 6
```

### Flags

#### `--filter-odd-cycles`

By **Proposition 1 of [arXiv:1911.01954](https://arxiv.org/pdf/1911.01954)**, every directed graph that contains no directed cycle of odd length is majority 2-colourable. Passing this flag exploits that result as a pre-filter: before calling the Gurobi ILP solver, the script checks whether the graph has a directed odd cycle. If it does not, the graph is skipped entirely — it is not written to the CSV and Gurobi is never invoked for it.

```bash
# 5 vertices — filtered output
julia --project -t auto notebooks/enumerate_graphs.jl 5 --filter-odd-cycles

# 6 vertices — filtered output (recommended for the 38 GB run)
julia --project -t 8 notebooks/enumerate_graphs.jl 6 --filter-odd-cycles
```

Output file when the flag is set: `notebooks/results_<N>vertex_odd_only.csv`
Output file without the flag: `notebooks/results_<N>vertex.csv`

From the 5-vertex results, ~98.9 % of graphs have chromatic number 2; a large share of those will be eliminated by this filter without touching Gurobi, making the 6-vertex run substantially faster.

### Feedback & Monitoring
- **Threads:** When the script starts, it will print `Threads: X` to confirm how many CPU cores are being used.
- **Complexity:** For $N$ vertices, the script processes $2^{N(N-1)}$ masks.
  - $N=5 \implies 2^{20} \approx 10^6$ masks (~10 mins)
  - $N=6 \implies 2^{30} \approx 10^9$ masks (~150+ hours)
- **Progress:** A progress bar (percentage) is printed periodically.
- **Timing:** A detailed timing summary (total and average time per graph) is displayed at the end.
- **Optimizations:** See [OPTIMIZATIONS.md](./OPTIMIZATIONS.md) for technical details on the performance improvements.

## Python setup (charts)
1. Init & activate virtual env: `python3 -m venv .venv && source .venv/bin/activate`
2. Install requirements: `pip install -r requirements.txt`
