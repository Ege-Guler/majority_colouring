# Algorithmic Optimizations for Majority Coloring Enumeration

This document details the optimizations implemented to the `enumerate_5vertex_graphs.jl` script to improve its performance and efficiency.

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

## Impact
- **Runtime**: Expected reduction from ~310 hours (estimated) to less than 10 minutes on a modern multi-core machine.
- **Accuracy**: Maintained the same CSV output format and property calculation logic to ensure compatibility with existing analysis notebooks.
