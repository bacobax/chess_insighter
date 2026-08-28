import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import sys
    import pathlib

    # Add repo root to sys.path so utils/ and train_encoder are importable
    _repo_root = str(pathlib.Path(".").resolve())
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

    import marimo as mo
    import numpy as np
    import pandas as pd
    import altair as alt
    import torch
    import chess
    import chess.svg
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    from sklearn.preprocessing import StandardScaler

    from utils.opening_feature_transformer import (
        load_opening_lines,
        replay_boards,
        MATCHER_COLUMNS_V2,
    )
    from train_encoder import board_to_tensor
    from utils.position_style_encoder import (
        PositionStyleEncoder,
        embed_positions,
        _get_device as get_device,
    )

    return (
        MATCHER_COLUMNS_V2,
        PCA,
        PositionStyleEncoder,
        StandardScaler,
        TSNE,
        alt,
        board_to_tensor,
        chess,
        embed_positions,
        get_device,
        load_opening_lines,
        mo,
        np,
        pathlib,
        pd,
        replay_boards,
        torch,
    )


@app.cell
def _(mo):
    mo.md("""
    # Opening Final-Position Embedding Explorer

    Two views of 3700+ chess opening lines plotted in 2D.
    Use the **k** slider to color dots by shared opening prefix (same first k half-moves → same color).
    **Click any dot** to see the opening's name, board position, and features.

    | Pane | Feature source |
    |---|---|
    | **NN Encoder** | 128-d L2-normalized embedding from the trained ResNet (`small_lr_high_warmup`) |
    | **CSV Features** | 9 calibrated style features from `opening_feature_vectors.csv` |
    """)
    return


@app.cell
def _(pathlib):
    ALL_TSV  = pathlib.Path("openings_dataset/all.tsv")
    CSV_PATH = pathlib.Path("openings_dataset/opening_feature_vectors.csv")

    # Swap RUN_NAME to use a different checkpoint; arch map keeps params in sync
    RUN_NAME = "small_lr_high_warmup"
    RUN_ARCH = {
        "small_lr_high_warmup": {"num_blocks": 4, "width": 64},
        "base_50ep":            {"num_blocks": 8, "width": 128},
        "lr_high_50ep":         {"num_blocks": 8, "width": 128},
        "small_50ep":           {"num_blocks": 4, "width": 64},
        "lr_low_50ep":          {"num_blocks": 8, "width": 128},
    }
    CHECKPOINT = pathlib.Path(f"data/runs/{RUN_NAME}/checkpoint.pt")
    return ALL_TSV, CHECKPOINT, CSV_PATH, RUN_ARCH, RUN_NAME


@app.cell
def _(ALL_TSV, chess, load_opening_lines, mo, pd, replay_boards):
    _lines = load_opening_lines(str(ALL_TSV))

    _rows = []
    for _line in _lines:
        if not _line.uci or not _line.uci.strip():
            continue
        try:
            _boards, _ = replay_boards(_line.uci)
            _fen = _boards[-1].fen()
            # Convert UCI moves to SAN for human-readable prefix display
            _b = chess.Board()
            _san_parts = []
            for _uci_tok in _line.uci.strip().split():
                _mv = chess.Move.from_uci(_uci_tok)
                _san_parts.append(_b.san(_mv))
                _b.push(_mv)
            _san_line = " ".join(_san_parts)
        except Exception:
            continue
        _rows.append({
            "name":       _line.name,
            "eco":        _line.eco,
            "eco_letter": _line.eco[0] if _line.eco else "?",
            "family":     _line.name.split(":")[0].strip(),
            "pgn":        _line.pgn,
            "uci":        _line.uci,
            "san_moves":  _san_line,
            "fen":        _fen,
            "nply":       len(_line.uci.strip().split()),
        })

    meta_df = pd.DataFrame(_rows)
    mo.md(f"✓ Loaded **{len(meta_df)}** opening lines from `{ALL_TSV}`")
    return (meta_df,)


@app.cell
def _(
    CHECKPOINT,
    PositionStyleEncoder,
    RUN_ARCH,
    RUN_NAME,
    board_to_tensor,
    embed_positions,
    get_device,
    meta_df,
    mo,
    np,
    torch,
):
    # Stack all final-position board tensors: (N, 18, 8, 8)
    _tensors = np.stack([board_to_tensor(fen) for fen in meta_df["fen"]])

    # Rebuild model with the correct architecture and load the checkpoint weights
    _arch = RUN_ARCH[RUN_NAME]
    _model = PositionStyleEncoder(
        mode="lightweight",
        embed_dim=128,
        width=_arch["width"],
        num_blocks=_arch["num_blocks"],
    )
    _ckpt = torch.load(str(CHECKPOINT), map_location="cpu")
    _model.load_state_dict(_ckpt["model_state_dict"])
    _model.eval()

    Z_nn = embed_positions(_model, _tensors, batch_size=512, device=get_device())
    _norms = np.linalg.norm(Z_nn, axis=1)
    mo.md(
        f"✓ NN embeddings: shape `{Z_nn.shape}` · "
        f"mean L2-norm `{_norms.mean():.4f}` (≈ 1.0 expected)"
    )
    return (Z_nn,)


@app.cell
def _(CSV_PATH, MATCHER_COLUMNS_V2, meta_df, mo, np, pd):
    _csv_df    = pd.read_csv(CSV_PATH)
    _feat_cols = list(MATCHER_COLUMNS_V2)

    _joined = (
        meta_df
        .merge(
            _csv_df[["opening_name"] + _feat_cols],
            left_on="name",
            right_on="opening_name",
            how="inner",
        )
        .drop(columns=["opening_name"])
        .reset_index(drop=True)
    )

    X_csv       = _joined[_feat_cols].values.astype(np.float32)
    meta_csv_df = _joined.copy()

    mo.md(
        f"✓ CSV join: **{len(meta_csv_df)}** / {len(meta_df)} lines matched"
        f" ({len(meta_df) - len(meta_csv_df)} dropped)"
    )
    return X_csv, meta_csv_df


@app.cell
def _(PCA, StandardScaler, TSNE, X_csv, Z_nn, meta_csv_df, meta_df, mo):
    def _reduce(X):
        _s    = StandardScaler().fit_transform(X)
        _pca  = PCA(n_components=2, random_state=42)
        _p_xy = _pca.fit_transform(_s)
        _t_xy = TSNE(
            n_components=2, init="pca", perplexity=30, random_state=42
        ).fit_transform(_s)
        return _p_xy, _t_xy, _pca.explained_variance_ratio_

    def _attach(xy, meta):
        _df      = meta.copy()
        _df["x"] = xy[:, 0]
        _df["y"] = xy[:, 1]
        return _df

    _nn_pca_xy,  _nn_tsne_xy,  nn_pca_var  = _reduce(Z_nn)
    _csv_pca_xy, _csv_tsne_xy, csv_pca_var = _reduce(X_csv)

    nn_pca_df   = _attach(_nn_pca_xy,   meta_df)
    nn_tsne_df  = _attach(_nn_tsne_xy,  meta_df)
    csv_pca_df  = _attach(_csv_pca_xy,  meta_csv_df)
    csv_tsne_df = _attach(_csv_tsne_xy, meta_csv_df)

    mo.md(
        f"✓ NN PCA: **{nn_pca_var[0]:.1%}** + **{nn_pca_var[1]:.1%}** var explained · "
        f"CSV PCA: **{csv_pca_var[0]:.1%}** + **{csv_pca_var[1]:.1%}**"
    )
    return (
        csv_pca_df,
        csv_pca_var,
        csv_tsne_df,
        nn_pca_df,
        nn_pca_var,
        nn_tsne_df,
    )


@app.cell
def _(mo):
    get_seq, set_seq = mo.state([])
    return get_seq, set_seq


@app.cell
def _(get_seq):
    filter_seq = list(get_seq())
    return (filter_seq,)


@app.cell
def _(filter_seq, mo):
    _dummy = filter_seq  # static dependency — re-executes (clearing field) on every sequence change
    move_input = mo.ui.text(placeholder="e.g. e4")
    return (move_input,)


@app.cell
def _(chess, get_seq, meta_df, mo, move_input, set_seq):
    _seq = get_seq()

    def _on_add(_):
        mv = move_input.value.strip()
        if mv:
            set_seq(get_seq() + [mv])

    def _on_undo(_):
        if get_seq():
            set_seq(get_seq()[:-1])

    def _on_reset(_):
        set_seq([])

    _add_btn   = mo.ui.button(label="Add →",    on_click=_on_add,   kind="success")
    _undo_btn  = mo.ui.button(label="← Undo",   on_click=_on_undo)
    _reset_btn = mo.ui.button(label="Clear all", on_click=_on_reset)

    def _fmt(moves):
        if not moves:
            return "*(empty — all openings shown)*"
        parts = []
        for i, m in enumerate(moves):
            if i % 2 == 0:
                parts.append(f"{i // 2 + 1}. {m}")
            else:
                parts.append(m)
        return " ".join(parts)

    _board = chess.Board()
    _board_ok = True
    for _mv in _seq:
        try:
            _board.push_san(_mv)
        except Exception:
            _board_ok = False
            break
    _svg = chess.svg.board(_board, size=220) if _seq and _board_ok else ""

    _n = sum(
        1 for s in meta_df["san_moves"]
        if str(s).strip().split()[: len(_seq)] == list(_seq)
    )
    _pct = f" ({_n / len(meta_df):.0%} of all lines)" if _seq else ""

    mo.vstack([
        mo.md("---"),
        mo.md("## Move Sequence Explorer"),
        mo.md(
            "Enter moves one by one to narrow down openings. "
            "Both scatter plots update to highlight only lines that start with your sequence."
        ),
        mo.hstack(
            [mo.md("**Next move:**"), move_input, _add_btn, _undo_btn, _reset_btn],
            align="center",
        ),
        mo.hstack([
            mo.vstack([
                mo.md(f"**Sequence:** {_fmt(_seq)}"),
                mo.md(f"**Matching lines:** {_n}{_pct}"),
                mo.md("*(invalid move — board shows last valid position)*") if _seq and not _board_ok else mo.md(""),
            ]),
            mo.Html(_svg) if _svg else mo.md(""),
        ]),
        mo.md("---"),
    ])
    return


@app.cell
def _(mo):
    k_slider = mo.ui.slider(
        start=1, stop=8, value=2,
        label="k — color by first k half-moves (plies)",
        full_width=True,
    )
    mo.vstack([
        mo.md("## NN Encoder (128-d embedding)"),
        mo.md(
            "Openings sharing the same first **k** half-moves get the same color. "
            "k=1 → white's first move only; k=2 → white's first move + black's first reply; …"
        ),
        k_slider,
    ])
    return (k_slider,)


@app.cell
def _(alt, filter_seq, k_slider, mo, nn_pca_df, nn_pca_var, nn_tsne_df):
    def _san_prefix(san_moves, k):
        tokens = str(san_moves).strip().split()
        return " ".join(tokens[:k]) if tokens else ""

    _k = k_slider.value
    _filter_seq = filter_seq

    def _color_by_prefix(df):
        _df = df.copy()
        _df["opening_prefix"] = _df["san_moves"].apply(lambda s: _san_prefix(s, _k))
        if _filter_seq:
            _df["seq_match"] = _df["san_moves"].apply(
                lambda s: str(s).strip().split()[: len(_filter_seq)] == _filter_seq
            )
        return _df

    def _scatter(df, title):
        _label = f"First {_k} half-move{'s' if _k != 1 else ''}"
        _x = alt.X("x:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
        _y = alt.Y("y:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
        _color_full = alt.Color("opening_prefix:N", legend=alt.Legend(title=_label, symbolLimit=40))
        _tip = ["name:N", "eco:N", "family:N", "opening_prefix:N"]
        if _filter_seq:
            _match = df[df["seq_match"]]
            _other = df[~df["seq_match"]]
            _bg = (
                alt.Chart(_other)
                .mark_circle(size=10, opacity=0.01)
                .encode(x=_x, y=_y, color=alt.Color("opening_prefix:N", legend=None))
            )
            _fg = (
                alt.Chart(_match)
                .mark_circle(size=46, opacity=0.92)
                .encode(x=_x, y=_y, color=_color_full, tooltip=_tip)
            )
            return (_bg + _fg).properties(title=title, width=430, height=350)
        else:
            _legend_sel = alt.selection_point(fields=["opening_prefix"], bind="legend")
            return (
                alt.Chart(df)
                .mark_circle(size=28)
                .encode(
                    x=_x, y=_y,
                    color=_color_full,
                    opacity=alt.condition(_legend_sel, alt.value(0.85), alt.value(0.08)),
                    tooltip=_tip,
                )
                .properties(title=title, width=430, height=350)
                .add_params(_legend_sel)
            )

    nn_pca_plot_df  = _color_by_prefix(nn_pca_df)
    nn_tsne_plot_df = _color_by_prefix(nn_tsne_df)

    _nn_pca_base  = _scatter(
        nn_pca_plot_df,
        f"NN Encoder — PCA  ({nn_pca_var[0]:.1%} + {nn_pca_var[1]:.1%})",
    )
    _nn_tsne_base = _scatter(nn_tsne_plot_df, "NN Encoder — t-SNE")

    nn_pca_chart  = mo.ui.altair_chart(_nn_pca_base,  legend_selection=False)
    nn_tsne_chart = mo.ui.altair_chart(_nn_tsne_base, legend_selection=False)

    mo.hstack([nn_pca_chart, nn_tsne_chart])
    return nn_pca_chart, nn_pca_plot_df, nn_tsne_chart, nn_tsne_plot_df


@app.cell
def _(
    RUN_NAME,
    chess,
    mo,
    nn_pca_chart,
    nn_pca_plot_df,
    nn_tsne_chart,
    nn_tsne_plot_df,
    pd,
):
    _pca_sel  = nn_pca_chart.apply_selection(nn_pca_plot_df)
    _tsne_sel = nn_tsne_chart.apply_selection(nn_tsne_plot_df)
    _parts    = [_df for _df in [_pca_sel, _tsne_sel] if len(_df) > 0]

    mo.stop(
        len(_parts) == 0,
        mo.md("*Click a dot in the NN charts above to see opening details.*"),
    )

    _sel   = pd.concat(_parts).drop_duplicates(subset=["name"]).iloc[0]
    _board = chess.Board(_sel["fen"])
    _svg   = chess.svg.board(_board, size=290)

    mo.hstack([
        mo.Html(_svg),
        mo.vstack([
            mo.md(f"### {_sel['name']}"),
            mo.md(f"**ECO:** {_sel['eco']} · **Family:** {_sel['family']}"),
            mo.md(f"**PGN:** {_sel['pgn']}"),
            mo.md(f"**FEN:** `{_sel['fen']}`"),
            mo.md(f"**UCI:** `{_sel['uci']}`"),
            mo.md(f"*Checkpoint: `{RUN_NAME}`*"),
        ]),
    ])
    return


@app.cell
def _(mo):
    kp_slider = mo.ui.slider(
        start=1, stop=8, value=2,
        label="k′ — color by first k′ half-moves (plies)",
        full_width=True,
    )
    mo.vstack([
        mo.md("## CSV Calibrated Features (9-d)"),
        mo.md(
            "Openings sharing the same first **k′** half-moves get the same color. "
            "k′=1 → white's first move only; k′=2 → white's first move + black's first reply; …"
        ),
        kp_slider,
    ])
    return (kp_slider,)


@app.cell
def _(alt, csv_pca_df, csv_pca_var, csv_tsne_df, filter_seq, kp_slider, mo):
    def _san_prefix(san_moves, k):
        tokens = str(san_moves).strip().split()
        return " ".join(tokens[:k]) if tokens else ""

    _kp = kp_slider.value
    _filter_seqp = filter_seq

    def _color_by_prefix(df):
        _df = df.copy()
        _df["opening_prefix"] = _df["san_moves"].apply(lambda s: _san_prefix(s, _kp))
        if _filter_seqp:
            _df["seq_match"] = _df["san_moves"].apply(
                lambda s: str(s).strip().split()[: len(_filter_seqp)] == _filter_seqp
            )
        return _df

    def _scatter(df, title):
        _label = f"First {_kp} half-move{'s' if _kp != 1 else ''}"
        _x = alt.X("x:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
        _y = alt.Y("y:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
        _color_full = alt.Color("opening_prefix:N", legend=alt.Legend(title=_label, symbolLimit=40))
        _tip = ["name:N", "eco:N", "family:N", "opening_prefix:N"]
        if _filter_seqp:
            _match = df[df["seq_match"]]
            _other = df[~df["seq_match"]]
            _bg = (
                alt.Chart(_other)
                .mark_circle(size=10, opacity=0.01)
                .encode(x=_x, y=_y, color=alt.Color("opening_prefix:N", legend=None))
            )
            _fg = (
                alt.Chart(_match)
                .mark_circle(size=46, opacity=0.92)
                .encode(x=_x, y=_y, color=_color_full, tooltip=_tip)
            )
            return (_bg + _fg).properties(title=title, width=430, height=350)
        else:
            _legend_sel = alt.selection_point(fields=["opening_prefix"], bind="legend")
            return (
                alt.Chart(df)
                .mark_circle(size=28)
                .encode(
                    x=_x, y=_y,
                    color=_color_full,
                    opacity=alt.condition(_legend_sel, alt.value(0.85), alt.value(0.08)),
                    tooltip=_tip,
                )
                .properties(title=title, width=430, height=350)
                .add_params(_legend_sel)
            )

    csv_pca_plot_df  = _color_by_prefix(csv_pca_df)
    csv_tsne_plot_df = _color_by_prefix(csv_tsne_df)

    _csv_pca_base  = _scatter(
        csv_pca_plot_df,
        f"CSV Features — PCA  ({csv_pca_var[0]:.1%} + {csv_pca_var[1]:.1%})",
    )
    _csv_tsne_base = _scatter(csv_tsne_plot_df, "CSV Features — t-SNE")

    csv_pca_chart  = mo.ui.altair_chart(_csv_pca_base,  legend_selection=False)
    csv_tsne_chart = mo.ui.altair_chart(_csv_tsne_base, legend_selection=False)

    mo.hstack([csv_pca_chart, csv_tsne_chart])
    return csv_pca_chart, csv_pca_plot_df, csv_tsne_chart, csv_tsne_plot_df


@app.cell
def _(
    MATCHER_COLUMNS_V2,
    chess,
    csv_pca_chart,
    csv_pca_plot_df,
    csv_tsne_chart,
    csv_tsne_plot_df,
    mo,
    pd,
):
    _pca_sel  = csv_pca_chart.apply_selection(csv_pca_plot_df)
    _tsne_sel = csv_tsne_chart.apply_selection(csv_tsne_plot_df)
    _parts    = [_df for _df in [_pca_sel, _tsne_sel] if len(_df) > 0]

    mo.stop(
        len(_parts) == 0,
        mo.md("*Click a dot in the CSV charts above to see opening details.*"),
    )

    _sel   = pd.concat(_parts).drop_duplicates(subset=["name"]).iloc[0]
    _board = chess.Board(_sel["fen"])
    _svg   = chess.svg.board(_board, size=290)

    _feat_md = "\n".join(
        f"- **{feat}**: {_sel[feat]:.4f}"
        for feat in MATCHER_COLUMNS_V2
        if feat in _sel.index
    )

    mo.hstack([
        mo.Html(_svg),
        mo.vstack([
            mo.md(f"### {_sel['name']}"),
            mo.md(f"**ECO:** {_sel['eco']} · **Family:** {_sel['family']}"),
            mo.md(f"**PGN:** {_sel['pgn']}"),
            mo.md(f"**FEN:** `{_sel['fen']}`"),
            mo.md(f"**UCI:** `{_sel['uci']}`"),
            mo.md(f"**Calibrated features:**\n{_feat_md}"),
        ]),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ---
    # 🔬 Encoder Diagnostics

    The scatter plots above are colored by **opening prefix** — something the
    encoder was *never trained to encode*. Its real targets are **style** (9
    features), **phase**, and **tactics**. These four cells evaluate what the
    embedding actually captures.

    **TL;DR from the data:** PC1 (45.9% var) is dominated by line *depth*
    (`nply`, r ≈ −0.69, driven by the fullmove-number input plane), so the two
    big regions are short vs. deep lines — not a style split. The style signal
    the model learned lives mostly on **PC2** (quiet/castled/endgame ↔
    tactical/sharp).
    """)
    return


@app.cell
def _(alt, mo, nn_pca_df, nn_pca_var):
    # ── 1 · Color the NN PCA by line depth (nply) ───────────────────────────────
    _x = alt.X("x:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
    _y = alt.Y("y:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
    _chart = (
        alt.Chart(nn_pca_df)
        .mark_circle(size=30, opacity=0.75)
        .encode(
            x=_x, y=_y,
            color=alt.Color(
                "nply:Q",
                scale=alt.Scale(scheme="viridis"),
                legend=alt.Legend(title="line depth (plies)"),
            ),
            tooltip=["name:N", "eco:N", "family:N", "nply:Q"],
        )
        .properties(
            title=f"NN PCA — colored by line depth  ({nn_pca_var[0]:.1%} + {nn_pca_var[1]:.1%})",
            width=560, height=390,
        )
    )
    mo.vstack([
        mo.md("## 1 · Color by line depth (`nply`)"),
        mo.md(
            "PC1 correlates **−0.69** with the number of half-moves in the line. "
            "If the two regions are a depth artifact (driven by the fullmove-number "
            "input plane #17), they separate cleanly along this gradient — confirming "
            "the dominant axis is *how deep the line goes*, not opening identity."
        ),
        mo.ui.altair_chart(_chart),
    ])
    return


@app.cell
def _(MATCHER_COLUMNS_V2, mo):
    # Dropdown lives in its own cell so its .value is reactive downstream.
    feat_dropdown = mo.ui.dropdown(
        options=list(MATCHER_COLUMNS_V2),
        value="quiet_position_density",
        label="style feature",
    )
    return (feat_dropdown,)


@app.cell
def _(CSV_PATH, MATCHER_COLUMNS_V2, alt, feat_dropdown, mo, nn_pca_df, pd):
    # ── 2 · Color the NN PCA by a chosen calibrated style feature ───────────────
    # Family-level CSV feature, averaged per opening name, joined onto NN points.
    _csv = pd.read_csv(CSV_PATH)
    _feat_lookup = (
        _csv.groupby("opening_name")[list(MATCHER_COLUMNS_V2)]
        .mean()
        .reset_index()
    )
    _df = nn_pca_df.merge(
        _feat_lookup, left_on="name", right_on="opening_name", how="inner"
    )

    _feat = feat_dropdown.value
    _x = alt.X("x:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
    _y = alt.Y("y:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
    _chart = (
        alt.Chart(_df)
        .mark_circle(size=30, opacity=0.8)
        .encode(
            x=_x, y=_y,
            color=alt.Color(
                f"{_feat}:Q",
                scale=alt.Scale(scheme="turbo"),
                legend=alt.Legend(title=_feat),
            ),
            tooltip=["name:N", "eco:N", f"{_feat}:Q"],
        )
        .properties(
            title=f"NN PCA — colored by {_feat}  (n={len(_df)})",
            width=560, height=390,
        )
    )
    mo.vstack([
        mo.md("## 2 · Color by a calibrated style feature"),
        mo.md(
            "Pick a style dimension and watch the gradient. Features like "
            "`quiet_position_density`, `early_castling_tendency`, and "
            "`endgame_likelihood_proxy` track **PC2**; `tactical_density` / "
            "`pawn_structure_sharpness` run the opposite way — that's the style "
            "axis the encoder learned."
        ),
        feat_dropdown,
        mo.ui.altair_chart(_chart),
    ])
    return


@app.cell
def _(meta_df, mo):
    # Depth selector for the fixed-depth PCA below (own cell → reactive .value).
    _depths = sorted(d for d in meta_df["nply"].unique() if d >= 2)
    _common = [d for d in _depths if (meta_df["nply"] == d).sum() >= 40]
    depth_select = mo.ui.dropdown(
        options=[str(d) for d in _common],
        value=str(_common[len(_common) // 2]) if _common else None,
        label="fix line depth to (plies)",
    )
    return (depth_select,)


@app.cell
def _(
    CSV_PATH,
    MATCHER_COLUMNS_V2,
    PCA,
    StandardScaler,
    Z_nn,
    alt,
    depth_select,
    feat_dropdown,
    meta_df,
    mo,
    np,
    pd,
):
    # ── 3 · Fixed-depth PCA: remove the depth axis, let style dominate ──────────
    _d = int(depth_select.value)
    _mask = (meta_df["nply"] == _d).values
    _n = int(_mask.sum())

    mo.stop(
        _n < 10,
        mo.md(f"*Only {_n} lines at depth {_d} — pick another depth.*"),
    )

    _Z = Z_nn[_mask]
    _scaled = StandardScaler().fit_transform(_Z)
    _pca = PCA(n_components=2, random_state=42)
    _xy = _pca.fit_transform(_scaled)
    _var = _pca.explained_variance_ratio_

    _sub = meta_df[_mask].copy().reset_index(drop=True)
    _sub["x"], _sub["y"] = _xy[:, 0], _xy[:, 1]

    _csv = pd.read_csv(CSV_PATH)
    _lk = _csv.groupby("opening_name")[list(MATCHER_COLUMNS_V2)].mean().reset_index()
    _sub = _sub.merge(_lk, left_on="name", right_on="opening_name", how="left")

    _feat = feat_dropdown.value
    _x = alt.X("x:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
    _y = alt.Y("y:Q", axis=alt.Axis(labels=False, ticks=False, title=""))
    _chart = (
        alt.Chart(_sub)
        .mark_circle(size=46, opacity=0.85)
        .encode(
            x=_x, y=_y,
            color=alt.Color(
                f"{_feat}:Q",
                scale=alt.Scale(scheme="turbo"),
                legend=alt.Legend(title=_feat),
            ),
            tooltip=["name:N", "eco:N", f"{_feat}:Q"],
        )
        .properties(
            title=f"NN PCA @ depth {_d}  ({_var[0]:.1%} + {_var[1]:.1%}) · n={_n}",
            width=560, height=390,
        )
    )
    # Correlation of each style feature with this subset's PC1 — what now drives it?
    _corrs = []
    for _c in MATCHER_COLUMNS_V2:
        _v = _sub[_c].values.astype(float)
        if np.isfinite(_v).sum() > 3 and np.nanstd(_v) > 1e-9:
            _r = np.corrcoef(_sub["x"], np.nan_to_num(_v, nan=float(np.nanmean(_v))))[0, 1]
            _corrs.append((_c, _r))
    _corrs.sort(key=lambda t: -abs(t[1]))
    _corr_md = "\n".join(f"- `{c}`: PC1 r = {r:+.2f}" for c, r in _corrs[:4])

    mo.vstack([
        mo.md("## 3 · Fixed-depth PCA (depth removed)"),
        mo.md(
            "Restricting to lines of a single length removes the dominant depth axis. "
            "With it gone, the **style features should organize PC1**. Uses the same "
            "feature dropdown as section 2."
        ),
        depth_select,
        mo.md(f"**Top style features driving PC1 at depth {_d}:**\n{_corr_md}"),
        mo.ui.altair_chart(_chart),
    ])
    return


@app.cell
def _(
    CHECKPOINT,
    PositionStyleEncoder,
    RUN_ARCH,
    RUN_NAME,
    Z_nn,
    meta_df,
    mo,
    np,
    pd,
    torch,
):
    # ── 4 · Style-head R²: does the head reconstruct its training target? ───────
    # Ground truth = the engine-free per-position labels the head was trained on.
    from utils.position_label_builder import _lightweight_labels_for_position, STYLE_COLS

    _y_true = np.array([
        [
            _lightweight_labels_for_position(_fen, int(_ply), None)[f"style_{_c}"]
            for _c in STYLE_COLS
        ]
        for _fen, _ply in zip(meta_df["fen"], meta_df["nply"])
    ], dtype=np.float32)

    # Reload model and push embeddings through the style head (sigmoid → [0,1]).
    _arch = RUN_ARCH[RUN_NAME]
    _model = PositionStyleEncoder(
        mode="lightweight", embed_dim=128,
        width=_arch["width"], num_blocks=_arch["num_blocks"],
    )
    _model.load_state_dict(torch.load(str(CHECKPOINT), map_location="cpu")["model_state_dict"])
    _model.eval()
    with torch.no_grad():
        _y_pred = torch.sigmoid(
            _model.head_style(torch.from_numpy(Z_nn.astype(np.float32)))
        ).numpy()

    def _r2(t, p):
        _ss_res = float(np.sum((t - p) ** 2))
        _ss_tot = float(np.sum((t - t.mean()) ** 2))
        return 1.0 - _ss_res / _ss_tot if _ss_tot > 1e-12 else float("nan")

    _rows = []
    for _i, _c in enumerate(STYLE_COLS):
        _t, _p = _y_true[:, _i], _y_pred[:, _i]
        _rows.append({
            "feature": _c,
            "R²":   round(_r2(_t, _p), 3),
            "Pearson r": round(float(np.corrcoef(_t, _p)[0, 1]), 3),
            "MAE":  round(float(np.mean(np.abs(_t - _p))), 3),
            "label_std": round(float(_t.std()), 3),
        })
    _table = pd.DataFrame(_rows).sort_values("R²", ascending=False)
    _mean_r2 = _table["R²"].mean()

    mo.vstack([
        mo.md("## 4 · Style-head reconstruction (R² vs. training target)"),
        mo.md(
            "The direct, numeric test of *did it learn the features*: push each "
            "embedding `z` through `head_style` (+sigmoid) and compare to the "
            "engine-free per-position label it was trained on. High R²/Pearson = the "
            "embedding genuinely carries that feature. `label_std` near 0 means the "
            "feature barely varies across these opening final-positions, so a low R² "
            "there is uninformative."
        ),
        mo.md(f"**Mean R² across 9 features: {_mean_r2:.3f}**"),
        mo.ui.table(_table, selection=None),
    ])
    return


if __name__ == "__main__":
    app.run()
