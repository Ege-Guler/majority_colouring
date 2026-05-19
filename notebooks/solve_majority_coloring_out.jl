"""
Build + solve the Digraph Majority Coloring MILP.

Arguments:
- G::SimpleDiGraph : The graph to color
- env::Gurobi.Env  : The Gurobi environment (must be thread-local for parallel use)

Kwargs:
- strengthen_y::Bool = true  : add y[c] ≤ ∑_v x[v,c] (tightens MILP)
- symmetry_break::Bool = true: add small symmetry breakers

Returns:
- model::Model
- x_val::Matrix{Int}  (n×K) assignment matrix (0/1)
- y_val::Vector{Int}  (K) used colors (0/1)
- coloring::Vector{Int} (n) color label 1..4 for each vertex
"""
function solve_majority_coloring_out(
    G::SimpleDiGraph,
    env::Gurobi.Env;
    strengthen_y::Bool = true,
    symmetry_break::Bool = true
)
    n = nv(G)
    K = 4

    # Use the provided thread-local environment
    model = Model(() -> Gurobi.Optimizer(env))
    
    set_optimizer_attribute(model, "OutputFlag", 0)
    set_optimizer_attribute(model, "Threads", 1)

    @variable(model, x[1:n, 1:K], Bin)
    @variable(model, y[1:K], Bin)

    @constraint(model, [v=1:n], sum(x[v,c] for c in 1:K) == 1)

    for v in 1:n
        Nv = outneighbors(G, v)
        dv = length(Nv)
        if dv == 0
            continue
        end
        bound     = fld(dv, 2)
        big_m     = cld(dv, 2)

        for c in 1:K
            @constraint(model,
                sum(x[u,c] for u in Nv) <= bound + big_m * (1 - x[v,c])
            )
        end
    end

    @constraint(model, [v=1:n, c=1:K], x[v,c] <= y[c])

    if strengthen_y
        @constraint(model, [c=1:K], y[c] <= sum(x[v,c] for v in 1:n))
    end

    if symmetry_break
        @constraint(model, [c=1:K-1], y[c] >= y[c+1])
        @constraint(model, x[1,1] == 1)
    end

    @objective(model, Min, sum(y[c] for c in 1:K))

    optimize!(model)

    status = termination_status(model)
    if status != MOI.OPTIMAL && status != MOI.FEASIBLE_POINT
        return model, nothing, nothing, nothing
    end

    x_val = round.(Int, value.(x))
    y_val = round.(Int, value.(y))

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
