"""
Enumerate all 2^20 directed graphs on 5 vertices and compute the minimum
number of colors required under the majority coloring rule.

Output:
  - results_5vertex.csv        : mask, num_edges, chromatic_number
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
# length(ALL_EDGES) == 20

function mask_to_graph(mask::Int)::SimpleDiGraph
    G = SimpleDiGraph(VERTICES)
    for (k, (i, j)) in enumerate(ALL_EDGES)
        (mask >> (k - 1)) & 1 == 1 && add_edge!(G, i, j)
    end
    return G
end

# --- Setup output paths ---
notebooks_dir = @__DIR__
output_csv    = joinpath(notebooks_dir, "results_5vertex.csv")
vis_dir       = joinpath(notebooks_dir, "visualizations")
mkpath(vis_dir)

# --- Main enumeration ---
total       = 2^20   # 1_048_576
MAX_IMAGES  = 200

counts      = Dict{Int,Int}()   
saved_count = Ref(0) # images saved so far 

println("Enumerating all $total directed graphs on $VERTICES vertices...")
println("CSV  → $output_csv")
println("Imgs → $vis_dir  (max $MAX_IMAGES)")
flush(stdout)

open(output_csv, "w") do f
    println(f, "mask,num_edges,chromatic_number")

    for mask in 0:(total - 1)
        if mask % 10_000 == 0
            pct = round(100.0 * mask / total; digits=1)
            println("Progress: $mask / $total  ($pct%)")
            flush(stdout)
            flush(f)
        end

        G = mask_to_graph(mask)
        ne_count = ne(G)

        _, _, y_val, coloring = solve_majority_coloring_out(G, true, true, true)

        chromatic = y_val === nothing ? -1 : sum(y_val)
        println(f, "$mask,$ne_count,$chromatic")

        counts[chromatic] = get(counts, chromatic, 0) + 1

        # Save visualization for graphs needing >= 3 colors
        if chromatic >= 3 && saved_count[] < MAX_IMAGES && coloring !== nothing
            img_path = joinpath(vis_dir, "mask_$(mask)_k$(chromatic).png")
            plot_advanced_digraph(G, coloring; save_path=img_path)
            saved_count[] += 1
        end
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
