function plot_digraph(G;
    layout=circular_layout,
    node_color=colorant"skyblue",
    edge_color=colorant"black",
    labels=true,
    save_path=nothing
)

    ctx = gplot(
        G,
        layout=layout,
        nodelabel=labels ? (1:nv(G)) : nothing,
        nodefillc=fill(node_color, nv(G)),
        edgestrokec=edge_color,
        arrowlengthfrac=0.08
    )

    if save_path !== nothing
        draw(PNG(save_path, 800px, 800px), ctx)
    end

    return ctx
end