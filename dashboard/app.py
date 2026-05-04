from __future__ import annotations

import gc
import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from data_access import (
    BOOLEAN_COLS,
    NUMERIC_COLS,
    DatasetInfo,
    GraphDataset,
    discover_datasets,
)
from visualize import render_graph

NOTEBOOKS_DIR = DASHBOARD_DIR.parent / "notebooks"

st.set_page_config(
    page_title="Majority Colouring — Graph Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner=False)
def _open_dataset(csv_path: str, parquet_present: bool) -> GraphDataset:
    # parquet_present is part of the key so we get a fresh handle after materialization
    del parquet_present
    info = next(
        i for i in discover_datasets(NOTEBOOKS_DIR) if str(i.path) == csv_path
    )
    return GraphDataset(info)


def get_dataset(info: DatasetInfo) -> GraphDataset:
    return _open_dataset(str(info.path), info.parquet_path.exists())


# ---------- sidebar ----------

datasets = discover_datasets(NOTEBOOKS_DIR)
if not datasets:
    st.error(f"No results_*vertex.csv files found in {NOTEBOOKS_DIR}.")
    st.stop()

st.sidebar.title("Dataset")
labels = [d.label for d in datasets]
default_idx = next((i for i, d in enumerate(datasets) if d.n_vertices == 5), 0)
chosen_label = st.sidebar.radio("Choose vertex count", labels, index=default_idx)
info = datasets[labels.index(chosen_label)]

ds = get_dataset(info)

source_kind = "Parquet cache" if ds.using_parquet() else "CSV (streamed)"
st.sidebar.caption(f"Source: **{source_kind}**")
st.sidebar.caption(f"Memory cap: {GraphDataset.MEMORY_LIMIT}, threads: {GraphDataset.THREADS}")

with st.sidebar.expander("Performance"):
    st.write(
        "Querying CSV directly is fine for this dashboard. Building a Parquet sibling "
        "speeds up repeat queries ~10×. For the 6-vertex CSV (~38 GB) the build can take "
        "a long time and will produce a ~few-GB Parquet file."
    )
    if not ds.using_parquet():
        if st.button("Build Parquet cache", type="secondary"):
            with st.spinner("Materializing Parquet…"):
                ds.materialize_parquet()
            _open_dataset.clear()
            st.rerun()
    else:
        st.caption(f"Parquet: {info.parquet_path.name}")

st.sidebar.divider()
st.sidebar.markdown(
    "Graph images are rendered **on demand** and dropped from memory after display. "
    "Nothing is written to disk."
)


# ---------- header ----------

st.title("Majority Colouring — Graph Dashboard")
st.caption(
    f"Properties of all enumerated directed graphs on N={info.n_vertices} vertices. "
    "Filter by any property and visualize a single graph."
)


# ---------- tabs ----------

tab_overview, tab_dist, tab_corr, tab_filter = st.tabs(
    ["Overview", "Distributions", "Correlations", "Filter & Visualize"]
)


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


with tab_overview:
    summary = ds.kpi_summary()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Graphs", f"{summary['total']:,}")
    c2.metric("Avg |E|", f"{summary['avg_num_edges']:.2f}")
    c3.metric("Canonical (iso)", _pct(summary["pct_isomorphic"]))
    c4.metric("Cyclic", _pct(summary["pct_cyclic"]))
    c5.metric("Has Hamiltonian", _pct(summary["pct_hamiltonian"]))

    st.subheader("Chromatic number distribution")
    chrom_df = ds.chromatic_distribution()
    log_y = st.toggle("Log scale", value=False)
    fig = px.bar(
        chrom_df,
        x="chromatic_number",
        y="count",
        text="count",
        labels={"chromatic_number": "Chromatic number", "count": "Graphs"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        yaxis_type="log" if log_y else "linear",
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
    )
    st.plotly_chart(fig, width='stretch')


with tab_dist:
    st.subheader("Numeric properties")
    rows = [NUMERIC_COLS[:2], NUMERIC_COLS[2:]]
    for row_cols in rows:
        cols = st.columns(len(row_cols))
        for col_name, slot in zip(row_cols, cols):
            with slot:
                df = ds.numeric_distribution(col_name)
                fig = px.bar(
                    df,
                    x="value",
                    y="count",
                    labels={"value": col_name, "count": "Graphs"},
                )
                fig.update_layout(
                    title=col_name.replace("_", " ").title(),
                    margin=dict(l=10, r=10, t=40, b=10),
                    height=320,
                )
                st.plotly_chart(fig, width='stretch')

    st.subheader("Boolean properties (split by chromatic number)")
    bool_cols_layout = st.columns(len(BOOLEAN_COLS))
    for col_name, slot in zip(BOOLEAN_COLS, bool_cols_layout):
        with slot:
            df = ds.boolean_split_by_chromatic(col_name)
            df = df.copy()
            df["value"] = df["value"].map({True: "true", False: "false"})
            fig = px.bar(
                df,
                x="chromatic_number",
                y="count",
                color="value",
                barmode="stack",
                labels={"chromatic_number": "Chromatic number", "count": "Graphs"},
                color_discrete_map={"true": "#2ca02c", "false": "#d62728"},
            )
            fig.update_layout(
                title=col_name.replace("_", " ").title(),
                margin=dict(l=10, r=10, t=40, b=10),
                height=320,
                legend_title_text="",
            )
            st.plotly_chart(fig, width='stretch')


with tab_corr:
    st.subheader("Mean chromatic number — pivot heatmap")
    c1, c2 = st.columns(2)
    pivot_options = NUMERIC_COLS
    x_default = "num_edges" if "num_edges" in pivot_options else pivot_options[0]
    y_default = "clique_number" if "clique_number" in pivot_options else pivot_options[-1]
    x_col = c1.selectbox("X axis", pivot_options, index=pivot_options.index(x_default))
    y_col = c2.selectbox(
        "Y axis",
        pivot_options,
        index=pivot_options.index(y_default) if y_default in pivot_options else 0,
    )
    if x_col == y_col:
        st.info("Pick two different columns for a meaningful pivot.")
    else:
        df = ds.pivot_chromatic(x_col, y_col)
        pivot = df.pivot(index="y", columns="x", values="mean_chromatic")
        fig = go.Figure(
            data=go.Heatmap(
                z=pivot.values,
                x=pivot.columns,
                y=pivot.index,
                colorscale="Viridis",
                colorbar=dict(title="mean χ"),
                hovertemplate=f"{x_col}=%{{x}}<br>{y_col}=%{{y}}<br>mean χ=%{{z:.3f}}<extra></extra>",
            )
        )
        fig.update_layout(
            xaxis_title=x_col,
            yaxis_title=y_col,
            margin=dict(l=10, r=10, t=10, b=10),
            height=460,
        )
        st.plotly_chart(fig, width='stretch')

    st.subheader("Numeric properties by chromatic number (quantile summary)")
    quant_cols = st.columns(2)
    for i, col_name in enumerate(NUMERIC_COLS):
        with quant_cols[i % 2]:
            q = ds.quantiles_by_chromatic(col_name)
            if q.empty:
                continue
            fig = go.Figure()
            for _, r in q.iterrows():
                fig.add_trace(
                    go.Box(
                        x=[str(int(r["chromatic_number"]))],
                        q1=[r["q1"]],
                        median=[r["median"]],
                        q3=[r["q3"]],
                        lowerfence=[r["q_min"]],
                        upperfence=[r["q_max"]],
                        mean=[r["mean"]],
                        name=f"χ={int(r['chromatic_number'])}",
                        boxpoints=False,
                    )
                )
            fig.update_layout(
                title=col_name.replace("_", " ").title(),
                xaxis_title="Chromatic number",
                yaxis_title=col_name,
                showlegend=False,
                margin=dict(l=10, r=10, t=40, b=10),
                height=360,
            )
            st.plotly_chart(fig, width='stretch')


with tab_filter:
    st.subheader("Filter graphs")

    # Slider ranges from min/max — bounded SQL queries
    ranges: dict[str, tuple[int, int]] = {
        c: ds.column_range(c) for c in NUMERIC_COLS
    }
    chrom_values = ds.distinct_values("chromatic_number")

    with st.form("filter_form", clear_on_submit=False):
        slider_cols = st.columns(2)
        slider_state: dict[str, tuple[int, int]] = {}
        for i, col_name in enumerate(NUMERIC_COLS):
            lo, hi = ranges[col_name]
            with slider_cols[i % 2]:
                if lo == hi:
                    st.write(f"**{col_name}**: fixed at {lo}")
                    slider_state[col_name] = (lo, hi)
                else:
                    slider_state[col_name] = st.slider(
                        col_name,
                        min_value=lo,
                        max_value=hi,
                        value=(lo, hi),
                    )

        chrom_pick = st.multiselect(
            "chromatic_number",
            options=chrom_values,
            default=chrom_values,
        )

        bool_cols = st.columns(len(BOOLEAN_COLS))
        bool_state: dict[str, object] = {}
        for col_name, slot in zip(BOOLEAN_COLS, bool_cols):
            with slot:
                choice = st.radio(
                    col_name,
                    options=["any", "true", "false"],
                    horizontal=True,
                    index=0,
                )
                bool_state[col_name] = (
                    True if choice == "true" else False if choice == "false" else None
                )

        submitted = st.form_submit_button("Apply filters", type="primary")

    if "filters" not in st.session_state or submitted:
        st.session_state.filters = {
            **slider_state,
            "chromatic_number": chrom_pick or chrom_values,
            **bool_state,
        }

    filters = st.session_state.filters
    match_count = ds.filter_count(filters)
    st.caption(f"**{match_count:,}** graphs match.")

    if match_count == 0:
        st.info("No graphs match these filters.")
    else:
        result_df = ds.filter_all(filters)

        event = st.dataframe(
            result_df,
            width='stretch',
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"filter_table_{info.n_vertices}",
        )

        selected_mask: int | None = None
        sel = getattr(event, "selection", None)
        if sel and sel.get("rows"):
            row_idx = sel["rows"][0]
            if 0 <= row_idx < len(result_df):
                selected_mask = int(result_df.iloc[row_idx]["mask"])

        st.divider()
        st.subheader("Visualize a graph")
        v1, v2 = st.columns([3, 1])
        with v1:
            mask_text = st.text_input(
                "Mask (decimal). Leave blank to use the row selected above.",
                value="",
            )
        with v2:
            do_render = st.button("Visualize", type="primary")

        if do_render:
            mask_to_use: int | None = None
            if mask_text.strip():
                try:
                    mask_to_use = int(mask_text.strip())
                except ValueError:
                    st.error("Mask must be an integer.")
            elif selected_mask is not None:
                mask_to_use = selected_mask
            else:
                st.warning("Type a mask or select a row first.")

            if mask_to_use is not None:
                row = ds.get_by_mask(mask_to_use)
                if row.empty:
                    st.warning(
                        f"Mask {mask_to_use} is not in this dataset. Rendering its graph anyway."
                    )
                else:
                    st.dataframe(row, width='stretch', hide_index=True)

                png_bytes = render_graph(mask_to_use, info.n_vertices)
                st.image(
                    png_bytes,
                    caption=f"mask={mask_to_use}, N={info.n_vertices}",
                    width='content',
                )
                # Hand the bytes to Streamlit and drop our reference. After this
                # rerun, nothing in user code holds the figure.
                del png_bytes
                gc.collect()
