"""
Enumerate all weakly connected directed graphs on 5 vertices and compute the minimum
number of colors required under the majority coloring rule.

Output:
  - results_5vertex.csv        : mask, num_edges, chromatic_number, is_isomorphic,
                                  is_cyclic, connectivity_number, stability_number,
                                  clique_number, has_hamiltonian_path
  - visualizations/            : PNG plots for graphs with chromatic_number >= 3 (max 200)

Usage (from notebooks/ directory):
    julia enumerate_5vertex_graphs.jl
or from Julia REPL:
    include("enumerate_5vertex_graphs.jl")
"""

using Pkg
Pkg.activate(joinpath(@__DIR__, ".."))

using JuMP, HiGHS, Graphs
using GraphPlot, Colors, Compose, Cairo

include("solve_majority_coloring_out.jl")
include("plot_advanced_digraph.jl")

# --- Edge ordering (fixed, canonical) ---
const VERTICES = 5
const ALL_EDGES = [(i, j) for i in 1:VERTICES for j in 1:VERTICES if i != j]

function mask_to_graph(mask::Int)::SimpleDiGraph
    G = SimpleDiGraph(VERTICES)
    for (k, (i, j)) in enumerate(ALL_EDGES)
        (mask >> (k - 1)) & 1 == 1 && add_edge!(G, i, j)
    end
    return G
end

# --- Graph property helpers ---

# Vertex connectivity: minimum vertices to remove to weakly disconnect G (or leave ≤1 vertex).
function compute_vertex_connectivity(G::SimpleDiGraph)
    n = nv(G)
    n <= 1 && return 0
    for k in 1:n-1
        for removal_mask in 1:(2^n - 1)
            count_ones(removal_mask) == k || continue
            S = [v for v in 1:n if (removal_mask >> (v-1)) & 1 == 1]
            remaining = setdiff(1:n, S)
            if length(remaining) <= 1
                return k
            end
            H, _ = induced_subgraph(G, remaining)
            if !is_weakly_connected(H)
                return k
            end
        end
    end
    return n - 1
end

# Independence number (stability number): max independent set on underlying undirected graph.
function compute_independence_number(G::SimpleDiGraph)
    UG = SimpleGraph(G)
    n = nv(UG)
    best = 1
    for mask in 1:(2^n - 1)
        S = [v for v in 1:n if (mask >> (v-1)) & 1 == 1]
        if all(!has_edge(UG, u, v) for u in S for v in S if u < v)
            best = max(best, length(S))
        end
    end
    return best
end

# Clique number: max clique on underlying undirected graph.
function compute_clique_number(G::SimpleDiGraph)
    UG = SimpleGraph(G)
    n = nv(UG)
    best = 1
    for mask in 1:(2^n - 1)
        S = [v for v in 1:n if (mask >> (v-1)) & 1 == 1]
        if all(has_edge(UG, u, v) for u in S for v in S if u < v)
            best = max(best, length(S))
        end
    end
    return best
end

# Hamiltonian path: DFS backtracking over directed edges.
function has_hamiltonian_path(G::SimpleDiGraph)
    n = nv(G)
    visited = falses(n)
    function dfs(v, depth)
        depth == n && return true
        for u in outneighbors(G, v)
            if !visited[u]
                visited[u] = true
                dfs(u, depth + 1) && return true
                visited[u] = false
            end
        end
        return false
    end
    for start in 1:n
        fill!(visited, false)
        visited[start] = true
        dfs(start, 1) && return true
    end
    return false
end

# Isomorphism deduplication: returns true if G is isomorphic to a previously seen graph.
# Fingerprint-bucketed to avoid O(n²) VF2 comparisons.
const _iso_seen = Dict{Tuple, Vector{SimpleDiGraph}}()

function is_isomorphic_to_seen(G::SimpleDiGraph)::Bool
    fp = (Tuple(sort(indegree(G))), Tuple(sort(outdegree(G))), ne(G))
    candidates = get(_iso_seen, fp, nothing)
    if candidates !== nothing
        for H in candidates
            Graphs.Experimental.has_isomorph(G, H) && return true
        end
        push!(candidates, G)
    else
        _iso_seen[fp] = SimpleDiGraph[G]
    end
    return false
end

# --- Setup output paths ---
notebooks_dir = @__DIR__
output_csv    = joinpath(notebooks_dir, "results_5vertex.csv")
vis_dir       = joinpath(notebooks_dir, "visualizations")
mkpath(vis_dir)

# Reset isomorphism state on each run
empty!(_iso_seen)

# --- Main enumeration ---
total       = 2^20   # 1_048_576
MAX_IMAGES  = 200

counts      = Dict{Int,Int}()
saved_count = Ref(0)

println("Enumerating all $total directed graphs on $VERTICES vertices...")
println("CSV  → $output_csv")
println("Imgs → $vis_dir  (max $MAX_IMAGES)")
flush(stdout)

open(output_csv, "w") do f
    println(f, "mask,num_edges,chromatic_number,is_isomorphic,is_cyclic,connectivity_number,stability_number,clique_number,has_hamiltonian_path")

    for mask in 0:(total - 1)
        if mask % 10_000 == 0
            pct = round(100.0 * mask / total; digits=1)
            println("Progress: $mask / $total  ($pct%)")
            flush(stdout)
            flush(f)
        end

        G = mask_to_graph(mask)
        ne_count = ne(G)

        is_weakly_connected(G) || continue

        _, _, y_val, coloring = solve_majority_coloring_out(G, true, true, true)

        chromatic    = y_val === nothing ? -1 : sum(y_val)
        iso          = is_isomorphic_to_seen(G)
        cyclic       = is_cyclic(G)
        conn         = compute_vertex_connectivity(G)
        stability    = compute_independence_number(G)
        clique       = compute_clique_number(G)
        ham_path     = has_hamiltonian_path(G)

        println(f, "$mask,$ne_count,$chromatic,$iso,$cyclic,$conn,$stability,$clique,$ham_path")

        counts[chromatic] = get(counts, chromatic, 0) + 1

        # Save visualization for graphs needing >= 3 colors
        # if chromatic >= 3 && saved_count[] < MAX_IMAGES && coloring !== nothing
        #     img_path = joinpath(vis_dir, "mask_$(mask)_k$(chromatic).png")
        #     plot_advanced_digraph(G, coloring; save_path=img_path)
        #     saved_count[] += 1
        # end
    end
end

println("\nDone.")
println("Images saved: $(saved_count[])")
println("\nSummary by chromatic number:")
for k in sort(collect(keys(counts)))
    label = k == -1 ? "error/infeasible" : "$k color(s)"
    println("  $label : $(counts[k]) graphs")
end
println("Total graphs processed: $(sum(values(counts)))")

# run on all the graphs <= 5 vertices

# check isomorphic graphs -> check for libraries that can do this efficiently for directed graphs (e.g. nauty/traces, bliss, graph.julia)
#
# cyclic graphs, isomorphic graphs, hamiltonian cycles, density(#edges), connectivity number, stability number, clique number
#
# 10min -> 100K
# for 33M -> 3300min ~ 55hours -> maybe can be parallelized across multiple machines? (e.g. split by mask ranges)
#
