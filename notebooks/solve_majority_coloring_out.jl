"""
Build + solve the Digraph Majority Coloring MILP.

Kwargs:
- strengthen_y::Bool = true  : add y[c] ≤ ∑_v x[v,c] (tightens MILP)
- symmetry_break::Bool = true: add small symmetry breakers
- silent::Bool = true        : silence solver output

Returns:
- model::Model
- x_val::Matrix{Int}  (n×K) assignment matrix (0/1)
- y_val::Vector{Int}  (K) used colors (0/1)
- coloring::Vector{Int} (n) color label 1..4 for each vertex
"""
function solve_majority_coloring_out(
    G::SimpleDiGraph,
    strengthen_y::Bool = true,
    symmetry_break::Bool = true,
    silent::Bool = true
)
    n = nv(G)
    K = 4

    model = Model(HiGHS.Optimizer)
    if silent
        set_silent(model)
    end

    @variable(model, x[1:n, 1:K], Bin)
    @variable(model, y[1:K], Bin)

    # A) Color assignment uniqueness
    @constraint(model, [v=1:n], sum(x[v,c] for c in 1:K) == 1)

    # B) Majority constraint on out-neighbors only
    for v in 1:n
        Nv = outneighbors(G, v)  # N⁺(v)
        dv = length(Nv)          # d⁺(v)
        if dv == 0
            continue
        end
        bound = fld(dv, 2)       # floor(d⁺(v)/2)

        for c in 1:K
            @constraint(model,
                sum(x[u,c] for u in Nv) <= bound + dv * (1 - x[v,c])
            )
        end
    end

    # C) Color usage linking
    @constraint(model, [v=1:n, c=1:K], x[v,c] <= y[c])

    # Optional strengthening
    if strengthen_y
        @constraint(model, [c=1:K], y[c] <= sum(x[v,c] for v in 1:n))
    end

    # Optional symmetry breaking
    if symmetry_break
        # force colors to be used in order: y1,y2..yN
        @constraint(model, [c=1:K-1], y[c] >= y[c+1])
        @constraint(model, x[1,1] == 1)
    end

    # Objective: minimize
    @objective(model, Min, sum(y[c] for c in 1:K))

    optimize!(model)

    # Extract optimal solution
    status = termination_status(model)
    if status != MOI.OPTIMAL && status != MOI.FEASIBLE_POINT
        return model, nothing, nothing, nothing
    end

    x_val = round.(Int, value.(x))
    y_val = round.(Int, value.(y))

    # Convert x to a color label per vertex
    coloring = zeros(Int, n)
    for v in 1:n
        for c in 1:K
            if x_val[v,c] == 1
                coloring[v] = c
                break
            end
        end
    end

    return model, x_val, y_val, coloring
end