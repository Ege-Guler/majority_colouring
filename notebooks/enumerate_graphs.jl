"""
Enumerate all weakly connected directed graphs on N vertices and compute the minimum
number of colors required under the majority coloring rule.

Modular/Optimized Version:
  - Supports any N as command-line argument (default 5).
  - Producer-Consumer architecture with Channels.
  - Workers have private, local Gurobi environments.
  - Bitmask-based sharded caching.

Usage:
    julia --project -t auto notebooks/enumerate_graphs.jl [N]

Output:
    results_[N]vertex.csv
"""

using Pkg
Pkg.activate(joinpath(@__DIR__, ".."))

using JuMP, Gurobi, Graphs
using GraphPlot, Colors, Compose, Cairo
using Base.Threads
using Combinatorics

# --- Modular Vertices Setup ---
const VERTICES = parse(Int, get(ARGS, 1, "5"))
const ALL_EDGES = [(i, j) for i in 1:VERTICES for j in 1:VERTICES if i != j]
const NUM_EDGES = length(ALL_EDGES)
const TOTAL_MASKS = 2^NUM_EDGES

include("solve_majority_coloring_out.jl")

function mask_to_graph(mask::Int)::SimpleDiGraph
    G = SimpleDiGraph(VERTICES)
    for (k, (i, j)) in enumerate(ALL_EDGES)
        (mask >> (k - 1)) & 1 == 1 && add_edge!(G, i, j)
    end
    return G
end

# --- Graph property helpers ---

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

# --- Fast Bitmask-Based Canonical Labeling ---
const PERM_MAPS = Vector{Vector{Int}}()
let
    println("Precomputing $VERTICES-vertex permutation maps...")
    perms = collect(permutations(1:VERTICES))
    for p in perms
        pmap = Int[]
        for (i, j) in ALL_EDGES
            new_i, new_j = p[i], p[j]
            k_prime = findfirst(x -> x == (new_i, new_j), ALL_EDGES)
            push!(pmap, k_prime)
        end
        push!(PERM_MAPS, pmap)
    end
end

function get_canonical_mask(mask::Int)::UInt64
    min_mask = UInt64(mask)
    for pmap in PERM_MAPS
        curr = UInt64(0)
        for (k_idx, k_prime) in enumerate(pmap)
            if (mask >> (k_idx - 1)) & 1 == 1
                curr |= (UInt64(1) << (k_prime - 1))
            end
        end
        if curr < min_mask
            min_mask = curr
        end
    end
    return min_mask
end

const NUM_SHARDS = 256
const caches = [Dict{UInt64, Any}() for _ in 1:NUM_SHARDS]
const cache_locks = [ReentrantLock() for _ in 1:NUM_SHARDS]

function get_cached_result(cmask::UInt64)
    shard_idx = (cmask % NUM_SHARDS) + 1
    lock(cache_locks[shard_idx]) do
        return get(caches[shard_idx], cmask, nothing)
    end
end

function cache_result!(cmask::UInt64, res)
    shard_idx = (cmask % NUM_SHARDS) + 1
    lock(cache_locks[shard_idx]) do
        caches[shard_idx][cmask] = res
    end
end

# --- Setup output paths ---
notebooks_dir = @__DIR__
output_csv    = joinpath(notebooks_dir, "results_$(VERTICES)vertex.csv")
vis_dir       = joinpath(notebooks_dir, "visualizations")
mkpath(vis_dir)

# --- Timing & Statistics ---
const timer_keys = ["isomorphism_check", "solve_majority", "property_computation", "mask_to_graph"]
timers = Dict(k => Atomic{Float64}(0.0) for k in timer_keys)
counts = Dict{Int, Int}()

# --- Channels for Producer-Consumer ---
mask_chan       = Channel{Int}(1000)
results_chan    = Channel{Any}(1000)

# --- Implementation ---

println("Enumerating all $TOTAL_MASKS directed graphs on $VERTICES vertices...")
println("Threads (Julia): $(nthreads())")
println("CSV Output:      $output_csv")
flush(stdout)

# 1. Start Writer Task
writer_task = @async begin
    open(output_csv, "w") do f
        println(f, "mask,num_edges,chromatic_number,is_isomorphic,is_cyclic,connectivity_number,stability_number,clique_number,has_hamiltonian_path")
        
        count = 0
        for res in results_chan
            count += 1
            if count % 20_000 == 0
                pct = round(100.0 * count / TOTAL_MASKS; digits=2)
                println("Progress: $count / $TOTAL_MASKS  ($pct%)")
                flush(stdout)
            end
            
            mask, ne_val, chromatic, iso, cyclic, conn, stability, clique, ham_path = res
            if chromatic != -1
                println(f, "$mask,$ne_val,$chromatic,$iso,$cyclic,$conn,$stability,$clique,$ham_path")
                counts[chromatic] = get(counts, chromatic, 0) + 1
            end
        end
    end
end

# 2. Start Worker Tasks
worker_tasks = []
for i in 1:nthreads()
    t = Threads.@spawn begin
        env = Gurobi.Env()
        Gurobi.GRBsetintparam(env, "OutputFlag", 0)
        Gurobi.GRBsetintparam(env, "Threads", 1)

        for mask in mask_chan
            t_iso = @elapsed cmask = get_canonical_mask(mask)
            atomic_add!(timers["isomorphism_check"], t_iso)
            
            cached_res = get_cached_result(cmask)
            
            if cached_res !== nothing
                chromatic, conn, stability, clique, ham_path, cyclic, wc = cached_res
                iso = true
                if !wc
                    put!(results_chan, (mask, count_ones(mask), -1, true, false, -1, -1, -1, false))
                    continue
                end
            else
                iso = false
                t_mask = @elapsed G = mask_to_graph(mask)
                atomic_add!(timers["mask_to_graph"], t_mask)
                
                wc = is_weakly_connected(G)
                if !wc
                    cache_result!(cmask, (-1, -1, -1, -1, false, false, false))
                    put!(results_chan, (mask, count_ones(mask), -1, false, false, -1, -1, -1, false))
                    continue
                end

                t_prop = @elapsed begin
                    cyclic    = is_cyclic(G)
                    conn      = compute_vertex_connectivity(G)
                    stability = compute_independence_number(G)
                    clique    = compute_clique_number(G)
                    ham_path  = has_hamiltonian_path(G)
                end
                atomic_add!(timers["property_computation"], t_prop)

                t_solve = @elapsed begin
                    # Retry mechanism for Gurobi license/network errors
                    max_retries = 3
                    retry_count = 0
                    success = false
                    y_val = nothing
                    
                    while !success && retry_count < max_retries
                        try
                            _, _, y_val, _ = solve_majority_coloring_out(G, env; strengthen_y=true, symmetry_break=true)
                            success = true
                        catch e
                            retry_count += 1
                            if retry_count < max_retries
                                @warn "Gurobi solver error (retry $retry_count/$max_retries): $e"
                                sleep(2) # Wait 2 seconds before retrying
                            else
                                @error "Gurobi solver failed after $max_retries attempts: $e"
                                chromatic = -1
                            end
                        end
                    end
                end
                atomic_add!(timers["solve_majority"], t_solve)
                chromatic = y_val === nothing ? -1 : sum(y_val)

                cache_result!(cmask, (chromatic, conn, stability, clique, ham_path, cyclic, true))
            end

            put!(results_chan, (mask, count_ones(mask), chromatic, iso, cyclic, conn, stability, clique, ham_path))
        end
    end
    push!(worker_tasks, t)
end

# 3. Start Producer
for mask in 0:(TOTAL_MASKS - 1)
    put!(mask_chan, mask)
end
close(mask_chan)

# 4. Wait for completion
wait.(worker_tasks)
close(results_chan)
wait(writer_task)

println("\nDone.")
println("\nTiming Summary (Cumulative Thread Time):")
total_processed = sum(values(counts))
sorted_timers = sort(collect(timers), by=x->x[2][], rev=true)

for (task, duration) in sorted_timers
    println("  $(rpad(task, 25)): $(round(duration[], digits=4)) seconds")
end

println("\nSummary by chromatic number for N=$VERTICES:")
for k in sort(collect(keys(counts)))
    label = k == -1 ? "skipped/error" : "$k color(s)"
    println("  $label : $(counts[k]) graphs")
end
println("Total graphs analyzed: $total_processed")
