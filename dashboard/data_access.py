from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd


NUMERIC_COLS = ["num_edges", "connectivity_number", "stability_number", "clique_number"]
BOOLEAN_COLS = ["is_isomorphic", "is_cyclic", "has_hamiltonian_path"]
CATEGORICAL_COLS = ["chromatic_number"]


@dataclass(frozen=True)
class DatasetInfo:
    path: Path
    n_vertices: int
    size_bytes: int

    @property
    def parquet_path(self) -> Path:
        return self.path.with_suffix(".parquet")

    @property
    def label(self) -> str:
        size_mb = self.size_bytes / (1024 * 1024)
        if size_mb >= 1024:
            size_str = f"{size_mb / 1024:.1f} GB"
        else:
            size_str = f"{size_mb:.1f} MB"
        return f"N={self.n_vertices}  ({size_str})"


def discover_datasets(notebooks_dir: Path) -> list[DatasetInfo]:
    pattern = re.compile(r"results_(\d+)vertex\.csv$")
    out: list[DatasetInfo] = []
    for p in sorted(notebooks_dir.glob("results_*vertex.csv")):
        m = pattern.search(p.name)
        if not m:
            continue
        out.append(DatasetInfo(path=p, n_vertices=int(m.group(1)), size_bytes=p.stat().st_size))
    return out


class GraphDataset:
    """DuckDB-backed view over a results_<n>vertex.csv (or its Parquet sibling).

    All queries are SQL aggregates; the underlying file is never fully loaded.
    Memory is hard-capped via SET memory_limit, keeping process RSS well below 5 GB.
    """

    MEMORY_LIMIT = "4GB"
    THREADS = 4

    def __init__(self, info: DatasetInfo):
        self.info = info
        self._con = duckdb.connect(":memory:")
        self._con.execute(f"SET memory_limit='{self.MEMORY_LIMIT}'")
        self._con.execute(f"SET threads={self.THREADS}")
        self._setup_views()

    def close(self) -> None:
        self._con.close()

    def _source_path(self) -> Path:
        if self.info.parquet_path.exists():
            return self.info.parquet_path
        return self.info.path

    def using_parquet(self) -> bool:
        return self.info.parquet_path.exists()

    def _setup_views(self) -> None:
        src = self._source_path()
        # DDL can't use prepared params; quote-escape the path literal instead.
        src_lit = "'" + str(src).replace("'", "''") + "'"
        if src.suffix == ".parquet":
            self._con.execute(
                f"CREATE OR REPLACE VIEW raw AS SELECT * FROM read_parquet({src_lit})"
            )
        else:
            self._con.execute(
                f"CREATE OR REPLACE VIEW raw AS "
                f"SELECT * FROM read_csv_auto({src_lit}, HEADER=TRUE, SAMPLE_SIZE=-1)"
            )
        self._con.execute(
            """
            CREATE OR REPLACE VIEW graphs AS
            SELECT
              CAST(mask AS BIGINT)                                          AS mask,
              CAST(num_edges AS INTEGER)                                    AS num_edges,
              CAST(chromatic_number AS INTEGER)                             AS chromatic_number,
              (LOWER(CAST(is_isomorphic         AS VARCHAR)) = 'true')      AS is_isomorphic,
              (LOWER(CAST(is_cyclic             AS VARCHAR)) = 'true')      AS is_cyclic,
              CAST(connectivity_number AS INTEGER)                          AS connectivity_number,
              CAST(stability_number    AS INTEGER)                          AS stability_number,
              CAST(clique_number       AS INTEGER)                          AS clique_number,
              (LOWER(CAST(has_hamiltonian_path  AS VARCHAR)) = 'true')      AS has_hamiltonian_path
            FROM raw
            """
        )

    def materialize_parquet(self, progress=None) -> Path:
        target = self.info.parquet_path
        if target.exists():
            return target
        if progress:
            progress(f"Building Parquet cache at {target.name}…")
        src_lit = "'" + str(self.info.path).replace("'", "''") + "'"
        tgt_lit = "'" + str(target).replace("'", "''") + "'"
        self._con.execute(
            f"COPY (SELECT * FROM read_csv_auto({src_lit}, HEADER=TRUE, SAMPLE_SIZE=-1)) "
            f"TO {tgt_lit} (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        self._setup_views()
        return target

    # --- aggregates for charts/KPIs ---

    def total_count(self) -> int:
        return int(self._con.execute("SELECT COUNT(*) FROM graphs").fetchone()[0])

    def kpi_summary(self) -> dict:
        row = self._con.execute(
            """
            SELECT
              COUNT(*)                                     AS total,
              AVG(CASE WHEN is_isomorphic       THEN 1 ELSE 0 END) AS pct_iso,
              AVG(CASE WHEN is_cyclic           THEN 1 ELSE 0 END) AS pct_cyclic,
              AVG(CASE WHEN has_hamiltonian_path THEN 1 ELSE 0 END) AS pct_hamil,
              AVG(num_edges) AS avg_edges
            FROM graphs
            """
        ).fetchone()
        return {
            "total": int(row[0]),
            "pct_isomorphic": float(row[1] or 0.0),
            "pct_cyclic": float(row[2] or 0.0),
            "pct_hamiltonian": float(row[3] or 0.0),
            "avg_num_edges": float(row[4] or 0.0),
        }

    def chromatic_distribution(self) -> pd.DataFrame:
        return self._con.execute(
            "SELECT chromatic_number, COUNT(*) AS count "
            "FROM graphs GROUP BY chromatic_number ORDER BY chromatic_number"
        ).df()

    def numeric_distribution(self, col: str) -> pd.DataFrame:
        if col not in NUMERIC_COLS:
            raise ValueError(f"unknown numeric column: {col}")
        return self._con.execute(
            f"SELECT {col} AS value, COUNT(*) AS count "
            f"FROM graphs GROUP BY {col} ORDER BY {col}"
        ).df()

    def boolean_split_by_chromatic(self, col: str) -> pd.DataFrame:
        if col not in BOOLEAN_COLS:
            raise ValueError(f"unknown boolean column: {col}")
        return self._con.execute(
            f"SELECT chromatic_number, {col} AS value, COUNT(*) AS count "
            f"FROM graphs GROUP BY chromatic_number, {col} "
            f"ORDER BY chromatic_number, {col}"
        ).df()

    def pivot_chromatic(self, x: str, y: str) -> pd.DataFrame:
        for c in (x, y):
            if c not in NUMERIC_COLS + CATEGORICAL_COLS:
                raise ValueError(f"unknown pivot column: {c}")
        return self._con.execute(
            f"SELECT {x} AS x, {y} AS y, AVG(chromatic_number) AS mean_chromatic, COUNT(*) AS n "
            f"FROM graphs GROUP BY {x}, {y} ORDER BY {x}, {y}"
        ).df()

    def quantiles_by_chromatic(self, col: str) -> pd.DataFrame:
        if col not in NUMERIC_COLS:
            raise ValueError(f"unknown numeric column: {col}")
        return self._con.execute(
            f"""
            SELECT
              chromatic_number,
              MIN({col})                                 AS q_min,
              approx_quantile({col}, 0.25)               AS q1,
              approx_quantile({col}, 0.50)               AS median,
              approx_quantile({col}, 0.75)               AS q3,
              MAX({col})                                 AS q_max,
              AVG({col})                                 AS mean,
              COUNT(*)                                   AS n
            FROM graphs
            GROUP BY chromatic_number
            ORDER BY chromatic_number
            """
        ).df()

    def column_range(self, col: str) -> tuple[int, int]:
        row = self._con.execute(f"SELECT MIN({col}), MAX({col}) FROM graphs").fetchone()
        lo, hi = row
        return int(lo if lo is not None else 0), int(hi if hi is not None else 0)

    def distinct_values(self, col: str) -> list[int]:
        rows = self._con.execute(
            f"SELECT DISTINCT {col} FROM graphs ORDER BY {col}"
        ).fetchall()
        return [int(r[0]) for r in rows if r[0] is not None]

    # --- filtered listing ---

    def _build_where(self, filters: dict) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        for col in NUMERIC_COLS:
            rng = filters.get(col)
            if rng is not None:
                clauses.append(f"{col} BETWEEN ? AND ?")
                params.extend([int(rng[0]), int(rng[1])])
        chrom = filters.get("chromatic_number")
        if chrom:
            placeholders = ",".join("?" for _ in chrom)
            clauses.append(f"chromatic_number IN ({placeholders})")
            params.extend([int(v) for v in chrom])
        for col in BOOLEAN_COLS:
            v = filters.get(col)
            if v is True or v is False:
                clauses.append(f"{col} = ?")
                params.append(bool(v))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def filter_count(self, filters: dict) -> int:
        where, params = self._build_where(filters)
        sql = f"SELECT COUNT(*) FROM graphs{where}"
        return int(self._con.execute(sql, params).fetchone()[0])

    def filter_page(self, filters: dict, limit: int, offset: int) -> pd.DataFrame:
        where, params = self._build_where(filters)
        sql = f"SELECT * FROM graphs{where} ORDER BY mask LIMIT ? OFFSET ?"
        return self._con.execute(sql, params + [int(limit), int(offset)]).df()

    def get_by_mask(self, mask: int) -> pd.DataFrame:
        return self._con.execute(
            "SELECT * FROM graphs WHERE mask = ? LIMIT 1", [int(mask)]
        ).df()
