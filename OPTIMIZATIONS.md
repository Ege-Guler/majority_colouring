# Algorithmic Optimizations for Majority Coloring Enumeration

This document details the optimizations implemented to `notebooks/enumerate_graphs.jl`.

## 1. Corrected Search Space
- **Issue**: The original script used `total = 2^25`, but a directed graph with 5 vertices has at most $5 \times (5-1) = 20$ directed edges (excluding self-loops) as defined in `ALL_EDGES`.
- **Mathematical Basis**:
    - For $n=5$ vertices, the number of possible directed edges between distinct vertices (excluding self-loops) is $n \times (n-1) = 20$.
    - Since each of these 20 edges can either exist or not, there are $2^{20} = 1,048,576$ total unique edge configurations.
    - Using $2^{25}$ would include $2^5 = 32$ redundant iterations for every unique graph, wasting significant computation time.
- **Implementation Detail**: 
    - The code explicitly excludes self-loops in the `ALL_EDGES` definition: `const ALL_EDGES = [(i, j) for i in 1:VERTICES for j in 1:VERTICES if i != j]`.
    - The `mask_to_graph` function iterates over this fixed list of 20 pairs, ensuring that no self-loops are ever added to the graph objects.
- **Optimization**: Reduced `total` to $2^{20}$. This ensures that each graph configuration is processed exactly once per mask.

## 2. Isomorphism-First Filtering with Result Caching
- **Issue**: The Majority Coloring problem was being solved via MILP (Gurobi) for every single weakly connected acyclic graph. Solving the same problem for isomorphic graphs is redundant.
- **Optimization**: 
    - We now check if a graph is isomorphic to one already processed *before* running the MILP solver.
    - Results (chromatic number, connectivity, stability number, clique number, Hamiltonian path) are cached for each unique isomorphism class.
    - This reduces the number of expensive MILP calls from ~1 million to a few thousand (or even just 292 if only DAGs are considered).

## 3. Parallelization
- **Optimization**: Enabled Julia's native multithreading using `Threads.@threads`.
- **Implementation**: 
    - The main enumeration loop now runs in parallel across all available CPU cores.
    - A `ReentrantLock` is used to ensure thread-safe access to the isomorphism cache and the output CSV file.
    - Atomic counters and thread-safe timing accumulation were added to maintain accurate performance statistics.

## 4. Redundancy Elimination
- **Optimization**: 
    - Optimized the `is_cyclic` and `is_weakly_connected` checks to avoid redundant calls.
    - Grouped all property computations into a single block that only runs for "new" (non-isomorphic) graphs.

## 5. Directed Odd-Cycle Pre-filter (`--filter-odd-cycles`)

- **Theoretical basis**: Proposition 1 of [arXiv:1911.01954](https://arxiv.org/pdf/1911.01954) states that every directed graph containing no directed cycle of odd length is majority 2-colourable. Such graphs can be resolved without any ILP solve.
- **Algorithm**: For a given graph $G$:
  1. Compute all strongly connected components (SCCs) via Tarjan's algorithm (`strongly_connected_components` from Graphs.jl, $O(V+E)$).
  2. For each non-trivial SCC (size ≥ 2), convert it to an undirected graph and run a BFS bipartiteness check ($O(V+E)$ per SCC).
  3. A directed odd cycle exists iff at least one SCC is non-bipartite. This is correct because: in a strongly connected digraph, all cycles are even iff the digraph has period 2, which is equivalent to the underlying undirected graph being bipartite.
- **Effect on the pipeline**: If no directed odd cycle is found, the graph is cached (marking `odd_cyc = false`) and skipped — property computation, Gurobi, and CSV output are all bypassed. Isomorphic copies consult the cache and are skipped without re-running the check.
- **Expected impact for N=6**: From the N=5 results, ~98.9 % of weakly connected graphs are chromatic 2, and a substantial portion of those will have no directed odd cycle and be eliminated here. This is the single largest lever for reducing the effective Gurobi workload of the $2^{30}$ mask run.
- **Output**: When the flag is active, results are written to `results_<N>vertex_odd_only.csv` (distinct from the full `results_<N>vertex.csv`) to avoid ambiguity.

## Impact Summary

| Optimization | Scope | Primary gain |
|---|---|---|
| Corrected search space | All runs | $2^{25} \to 2^{20}$ masks for N=5; correct $2^{N(N-1)}$ for any N |
| Isomorphism cache | All runs | Eliminates redundant Gurobi calls for isomorphic copies |
| Multithreading | All runs | Linear speedup with core count |
| Redundancy elimination | All runs | Single-pass property computation per canonical graph |
| Directed odd-cycle filter | `--filter-odd-cycles` | Eliminates Gurobi for ~majority of graphs via Prop. 1 of arXiv:1911.01954 |

Overall runtime without the filter: ~10 min for N=5, ~150+ hours for N=6 on a modern multi-core machine.
With `--filter-odd-cycles`: N=5 runtime drops significantly; N=6 becomes tractable depending on the fraction of graphs with odd cycles.
