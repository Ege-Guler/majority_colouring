# Julia Code Reference

Four files make up the Julia layer of this project. Two are standalone scripts you run directly; two are function libraries you `include` or call from a Julia session.

```
julia/
├── enumerate_graphs.jl          # main computation script (entry point)
├── solve_majority_coloring_out.jl  # MILP solver — included by enumerate_graphs.jl
├── plot_digraph.jl              # basic graph plotter
└── plot_advanced_digraph.jl     # coloring-aware graph plotter
```

---

## Quick-reference: available commands

```bash
# Enumerate all N-vertex digraphs and compute majority chromatic number
# Defaults to N=5 if omitted. Uses all available CPU threads.
julia --project -t auto julia/enumerate_graphs.jl
julia --project -t auto julia/enumerate_graphs.jl 4
julia --project -t auto julia/enumerate_graphs.jl 6

# Same, but skip graphs with no directed odd cycle (provably 2-colourable —
# saves ~99% of Gurobi calls for N≥5 at the cost of a less complete CSV)
julia --project -t auto julia/enumerate_graphs.jl 5 --filter-odd-cycles
julia --project -t auto julia/enumerate_graphs.jl 6 --filter-odd-cycles
```

Output is written to `results/results_<N>vertex.csv` (or `results_<N>vertex_odd_only.csv`).

The plot files and the solver file are not standalone scripts — they expose functions that you call from an interactive Julia session or from another script (see usage examples at the bottom of this file).

---

## File-by-file reference

---

### `enumerate_graphs.jl` — main script

This is the entry point. It enumerates every possible directed graph on N vertices (there are 2^(N*(N-1)) of them, one per bitmask) and writes one CSV row per weakly connected graph recording the majority chromatic number and several structural properties.

#### Constants and global setup (top of file)

| Constant | What it holds |
|---|---|
| `VERTICES` | Number of vertices (CLI arg 1, default 5) |
| `ALL_EDGES` | Ordered list of all possible directed edges `(i→j)` for i≠j |
| `NUM_EDGES` | `VERTICES*(VERTICES-1)` — length of `ALL_EDGES` |
| `TOTAL_MASKS` | `2^NUM_EDGES` — total graphs to test |
| `FILTER_ODD_CYCLES` | `true` if `--filter-odd-cycles` was passed |

`include("solve_majority_coloring_out.jl")` is called here, making `solve_majority_coloring_out` available.

A `let` block immediately after the constants **precomputes permutation maps** (`PERM_MAPS`) — see `get_canonical_mask` below.

#### Execution sequence

```
startup
 │
 ├─ parse VERTICES and FILTER_ODD_CYCLES from ARGS
 ├─ precompute PERM_MAPS (all N! vertex permutations → edge index remappings)
 ├─ set up results_dir and output_csv path
 │
 ├─ create mask_chan   (Channel{Int}, buffer 1000)  ← masks flow in
 ├─ create results_chan (Channel{Any}, buffer 1000)  ← result tuples flow out
 │
 ├─ [async] writer_task  — reads results_chan, writes CSV rows
 ├─ [threaded] worker_tasks (one per Julia thread) — reads mask_chan, does all computation
 ├─ [main thread] producer — pushes 0..(TOTAL_MASKS-1) into mask_chan, then closes it
 │
 ├─ wait for all worker_tasks to finish
 ├─ close results_chan
 ├─ wait for writer_task to finish
 │
 └─ print timing summary and chromatic number distribution
```

#### Worker loop (per mask, per thread)

For each integer `mask` received from `mask_chan`:

1. **Canonicalise** — compute `cmask = get_canonical_mask(mask)`.  This is the smallest bitmask reachable by relabelling vertices, and uniquely identifies the isomorphism class.
2. **Cache lookup** — call `get_cached_result(cmask)`.
   - **Cache hit**: the canonical representative was already processed. Copy its stored properties and mark `iso = true`. If the graph is not weakly connected, emit a skipped row and continue. If `--filter-odd-cycles` is active and the canonical copy has no odd cycle, skip silently.
   - **Cache miss**: this is the first time we see this isomorphism class. `iso = false`. Proceed to full computation.
3. **Build graph** — `mask_to_graph(mask)` → `SimpleDiGraph`.
4. **Connectivity check** — `is_weakly_connected(G)`. Not connected → cache a sentinel, emit a skipped row (`chromatic = -1`), continue.
5. **Odd-cycle filter** (only if `--filter-odd-cycles`) — `has_directed_odd_cycle(G)`. No odd cycle → cache as 2-colourable, skip (omit from CSV).
6. **Compute properties** — `is_cyclic`, `compute_vertex_connectivity`, `compute_independence_number`, `compute_clique_number`, `has_hamiltonian_path`.
7. **Solve MILP** — call `solve_majority_coloring_out(G, env)` (with up to 3 retries on Gurobi errors). `chromatic = sum(y_val)` = number of colors used.
8. **Cache** the full result tuple.
9. **Emit** the result tuple into `results_chan`.

The writer task reads from `results_chan` and writes one CSV line per non-skipped graph. Progress is printed every 20,000 rows.

---

#### `mask_to_graph(mask::Int) → SimpleDiGraph`

Decodes an integer bitmask into a directed graph.

Each bit position `k` corresponds to the `k`-th entry in `ALL_EDGES`. If bit `k` is set, edge `ALL_EDGES[k]` is added to the graph.

```
mask = 0b0101  →  edges ALL_EDGES[1] and ALL_EDGES[3] are present
```

---

#### `compute_vertex_connectivity(G::SimpleDiGraph) → Int`

Returns the vertex connectivity κ(G): the minimum number of vertices whose removal disconnects the graph (or leaves fewer than 2 vertices).

Brute-force: iterates over all subsets S of size k=1,2,… and checks whether removing S makes the induced subgraph on the remaining vertices weakly disconnected. Returns the first k that works, or n-1 if none does.

Feasible only for small N (≤6). Time: O(2^N · N).

---

#### `compute_independence_number(G::SimpleDiGraph) → Int`

Returns the independence number α(G): the size of the largest set of vertices with no edge between any pair in the *underlying undirected graph*.

Brute-force over all 2^N subsets. Time: O(2^N · N²).

---

#### `compute_clique_number(G::SimpleDiGraph) → Int`

Returns the clique number ω(G): the size of the largest clique in the underlying undirected graph.

Same brute-force structure as independence number but tests that every pair in the subset *is* connected. Time: O(2^N · N²).

---

#### `has_directed_odd_cycle(G::SimpleDiGraph) → Bool`

Returns `true` if G contains at least one directed cycle of odd length.

Algorithm: decompose G into strongly connected components (SCCs). For each SCC with ≥2 vertices, convert it to an undirected graph and check bipartiteness. A strongly connected digraph has a directed odd cycle if and only if its undirected version is not bipartite (because non-bipartiteness ↔ odd cycle, and in a strongly connected digraph every undirected cycle corresponds to a combination of directed cycles).

Used as a fast pre-filter: any graph failing this check is provably majority 2-colourable (Proposition 1, arXiv:1911.01954) and can skip the expensive Gurobi solve.

---

#### `has_hamiltonian_path(G::SimpleDiGraph) → Bool`

Returns `true` if there exists a path that visits every vertex exactly once.

DFS with backtracking, tried from every possible start vertex. `visited` is a shared `BitArray` that is reset before each starting vertex. Time: O(N · N!) worst case.

---

#### `get_canonical_mask(mask::Int) → UInt64`

Returns the canonical (minimum) bitmask over all N! relabellings of the vertices.

For each permutation p of 1..N, every edge (i→j) in the original graph maps to (p[i]→p[j]). The bitmask of the permuted graph is computed directly from `PERM_MAPS` (precomputed index remappings) without rebuilding the graph. The minimum such bitmask is returned.

Two masks with the same canonical mask are isomorphic. This is the core isomorphism-detection mechanism.

---

#### `get_or_claim_cached_result(cmask::UInt64) → (:hit, result) | (:claimed, nothing) | (:pending, nothing)`  
#### `cache_result!(cmask::UInt64, res)`

Thread-safe, race-free read/claim/write to a sharded dictionary cache.

256 shards, each with its own `ReentrantLock`. A mask is routed to shard `(cmask % 256) + 1`.

`get_or_claim_cached_result` does a single atomic lock-protected operation:
- **`:hit`** — result already stored by another thread; caller uses it and marks `iso = true`.
- **`:claimed`** — entry was empty; caller now owns it, must compute and call `cache_result!`.
- **`:pending`** — another thread claimed it but hasn't written the result yet; caller `yield()`s and retries.

This prevents the race condition where two threads process isomorphic graphs simultaneously, both see an empty cache, and both write `iso = false`. With the claim/pending protocol only one thread can own a canonical mask at a time.

The stored tuple is `(chromatic, conn, stability, clique, ham_path, cyclic, weakly_connected, has_odd_cycle)`.

---

### `solve_majority_coloring_out.jl` — MILP solver

Included by `enumerate_graphs.jl`. Exposes one function.

#### `solve_majority_coloring_out(G, env; strengthen_y, symmetry_break) → (model, x_val, y_val, coloring)`

Builds and solves a Mixed-Integer Linear Program that finds the minimum number of colors for which a majority coloring of G exists.

**Decision variables:**
- `x[v, c] ∈ {0,1}` — vertex `v` is assigned color `c`
- `y[c] ∈ {0,1}` — color `c` is used by at least one vertex

**Objective:** minimise `∑_c y[c]` (total colors used)

**Constraints:**

| Constraint | Meaning |
|---|---|
| `∑_c x[v,c] = 1` for all v | every vertex gets exactly one color |
| `∑_{u∈N⁺(v)} x[u,c] ≤ ⌊d⁺(v)/2⌋ + ⌈d⁺(v)/2⌉·(1 - x[v,c])` | majority rule: if v has color c, at most half its out-neighbors may also have color c |
| `x[v,c] ≤ y[c]` | a color can only be used if it is "active" |
| `y[c] ≤ ∑_v x[v,c]` *(if strengthen_y)* | a color is only active if some vertex uses it (LP relaxation tightener) |
| `y[c] ≥ y[c+1]` *(if symmetry_break)* | colors are used in order (breaks permutation symmetry) |
| `x[1,1] = 1` *(if symmetry_break)* | vertex 1 always gets color 1 (further symmetry reduction) |

The majority rule constraint is linearised with a big-M formulation. When `x[v,c]=0` the right-hand side becomes `⌊d/2⌋ + ⌈d/2⌉ = d`, which is trivially satisfied (at most d out-neighbors can have any color). When `x[v,c]=1` it tightens to `⌊d/2⌋`.

**Returns:**
- `model` — the JuMP model (useful for inspecting dual values etc.)
- `x_val` — N×4 integer matrix, `x_val[v,c]=1` means vertex v has color c
- `y_val` — length-4 integer vector, `sum(y_val)` is the chromatic number
- `coloring` — length-N vector, `coloring[v]` is the color label (1..4) assigned to vertex v

Returns `(model, nothing, nothing, nothing)` if Gurobi does not find an optimal or feasible solution.

---

### `plot_digraph.jl` — basic plotter

Not a standalone script. Include it in a Julia session alongside the Graphs/GraphPlot packages.

#### `plot_digraph(G; layout, node_color, edge_color, labels, save_path) → Compose.Context`

Renders a directed graph using GraphPlot.

| Parameter | Default | Description |
|---|---|---|
| `layout` | `circular_layout` | Layout algorithm (e.g. `spring_layout`, `spectral_layout`) |
| `node_color` | `colorant"skyblue"` | Fill color for all nodes |
| `edge_color` | `colorant"black"` | Color for all edges |
| `labels` | `true` | Show vertex ID labels |
| `save_path` | `nothing` | If set, saves an 800×800 PNG to this path |

Returns the Compose context so it can be displayed inline in a Jupyter notebook or composed with other elements.

---

### `plot_advanced_digraph.jl` — coloring-aware plotter

Not a standalone script. Requires a coloring vector from `solve_majority_coloring_out`.

#### `plot_advanced_digraph(G, coloring; layout, save_path) → Compose.Context`

Renders a majority-coloring result visually.

| Parameter | Default | Description |
|---|---|---|
| `coloring` | required | Length-N vector of color labels 1..4 (from solver) |
| `layout` | `circular_layout` | Layout algorithm |
| `save_path` | `nothing` | If set, saves a 1000×1000 PNG to this path |

Each node is filled with a distinct color from a `distinguishable_colors` palette. Text color is chosen automatically for contrast (white on dark backgrounds, black on light ones) using CIE Lab luminance.

Node labels show `"ID\nconflicts/limit"` where:
- `conflicts` = number of out-neighbors that share this vertex's color
- `limit` = `⌊d⁺/2⌋` = the majority threshold (must have `conflicts ≤ limit` for a valid coloring)

---

## Usage examples (interactive session)

```julia
# From the repo root:
julia --project

# Load everything
include("julia/solve_majority_coloring_out.jl")
include("julia/plot_digraph.jl")
include("julia/plot_advanced_digraph.jl")

using JuMP, Gurobi, Graphs, GraphPlot, Colors, Compose, Cairo

# Build a small test graph
G = SimpleDiGraph(4)
add_edge!(G, 1, 2); add_edge!(G, 1, 3); add_edge!(G, 2, 4)
add_edge!(G, 3, 4); add_edge!(G, 4, 1)

# Basic plot (displays inline in Jupyter, or save to file)
plot_digraph(G)
plot_digraph(G; save_path="graph.png")

# Solve and plot with coloring
env = Gurobi.Env()
_, _, y_val, coloring = solve_majority_coloring_out(G, env)
println("Colors needed: ", sum(y_val))   # e.g. 2

plot_advanced_digraph(G, coloring)
plot_advanced_digraph(G, coloring; save_path="colored.png")
```
