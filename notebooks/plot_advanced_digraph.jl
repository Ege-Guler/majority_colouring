function plot_advanced_digraph(G, coloring::Vector{Int}; 
                               layout=circular_layout, 
                               save_path=nothing)
    
    K = 4
    palette = distinguishable_colors(K, [colorant"white", colorant"black"], dropseed=true)
    node_fill_colors = [palette[c] for c in coloring]


    # select text color based on node color
    function get_contrast_color(c)
        return Lab(c).l < 50 ? colorant"white" : colorant"black"
    end
    node_label_colors = [get_contrast_color(c) for c in node_fill_colors]

    # labels
    node_labels = String[]
    for v in 1:nv(G)
        d_out = length(outneighbors(G, v))
        limit = floor(Int, d_out / 2)
        c_v = coloring[v]
        conflicts = count(u -> coloring[u] == c_v, outneighbors(G, v))
        
        # set format "ID: Conflicts/Limit"
        push!(node_labels, "$v\n$conflicts/$limit")
    end


    ctx = gplot(
        G,
        layout=layout,
        nodelabel=node_labels,
        nodefillc=node_fill_colors,
        nodelabelc=node_label_colors,
        edgestrokec=colorant"gray60",
        arrowlengthfrac=0.08,
        
        NODESIZE=0.10,
        NODELABELSIZE=3.0
    )

    if save_path !== nothing
        draw(PNG(save_path, 1000px, 1000px), ctx)
    end

    return ctx
end