from __future__ import annotations

import gc
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from graph_decode import mask_to_edges


def render_graph(mask: int, n: int) -> bytes:
    edges = mask_to_edges(mask, n)
    G = nx.DiGraph()
    G.add_nodes_from(range(1, n + 1))
    G.add_edges_from(edges)

    fig, ax = plt.subplots(figsize=(6, 6))
    pos = nx.circular_layout(G)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color="skyblue",
                           edgecolors="black", node_size=900)
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=12, font_weight="bold")
    nx.draw_networkx_edges(
        G, pos, ax=ax,
        edge_color="black",
        arrows=True,
        arrowsize=18,
        arrowstyle="-|>",
        connectionstyle="arc3,rad=0.12",
        node_size=900,
        width=1.2,
    )
    ax.set_title(f"Directed graph — N={n}, mask={mask}, |E|={len(edges)}")
    ax.set_axis_off()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    png_bytes = buf.getvalue()

    buf.close()
    plt.close(fig)
    del fig, ax, G, pos, edges, buf
    gc.collect()
    return png_bytes
