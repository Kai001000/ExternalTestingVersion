import pandas as pd
import plotly.graph_objects as go

from .i18n import t, tr


DISPLAY_MODE_DUAL = "dual"
DISPLAY_MODE_SHORT = "short"
DISPLAY_MODE_LONG = "long"


STABLE_COLOR = "#8f4e2e"
TREND_COLOR = "#2f6c83"
UNSTABLE_COLOR = "#c4b5a3"
GRID_COLOR = "#ebe1d5"
PLOT_BG = "rgba(0,0,0,0)"
PAPER_BG = "rgba(0,0,0,0)"
SERIES_COLORS = [
    "#8f4e2e",
    "#2f6c83",
    "#9b6b3f",
    "#58734b",
    "#705786",
    "#af5d46",
]
TREND_SERIES_COLORS = [
    "#2f6c83",
    "#5f7d5b",
    "#5d5f8c",
    "#8b5e4a",
    "#2d7f7a",
    "#6e5a9a",
]


def _base_layout(height: int, x_title: str, y_title: str, x_mode: str = "date") -> dict:
    return dict(
        height=height,
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        margin=dict(l=22, r=14, t=14, b=18),
        hovermode="x unified",
        hoverdistance=28,
        spikedistance=1000,
        hoverlabel=dict(
            bgcolor="#fffaf4",
            bordercolor="#d9ccb9",
            font=dict(color="#3c3026", size=12, family='"Manrope", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'),
        ),
        font=dict(
            family='"Manrope", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            color="#4f4338",
            size=12,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11, color="#6f6053"),
        ),
        xaxis=dict(
            title=x_title,
            type=x_mode,
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(size=12, color="#897a6c"),
            title_font=dict(size=12, color="#6f6053"),
            tickformat="%b\n%Y" if x_mode == "date" else None,
            spikesnap="cursor",
            showspikes=True,
            spikecolor="#d6c7b4",
            spikethickness=1,
            spikedash="solid",
        ),
        yaxis=dict(
            title=y_title,
            showgrid=True,
            gridcolor=GRID_COLOR,
            gridwidth=1,
            zeroline=False,
            tickfont=dict(size=12, color="#897a6c"),
            title_font=dict(size=12, color="#6f6053"),
            tickformat=",.0f",
        ),
    )


def _apply_y_range(fig: go.Figure, values: pd.Series):
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return
    lo = float(vals.min())
    hi = float(vals.max())
    if lo == hi:
        pad = max(abs(lo) * 0.02, 1.0)
        y_min = lo - pad
        y_max = hi + pad
    elif lo > 0:
        y_min = lo * 0.98
        y_max = hi * 1.02
    else:
        pad = max(abs(lo), abs(hi), 1.0) * 0.02
        y_min = lo - pad
        y_max = hi + pad
    fig.update_yaxes(range=[y_min, y_max])


def _status_label(stable: bool) -> str:
    return tr("稳定", "Stable") if stable else tr("非稳定尾段", "Unstable tail")


def _hover_template(series_label: str, time_title: str, sales_title: str | None, stable: bool) -> str:
    status_label = _status_label(stable)
    parts = [
        f"<b>%{{fullData.name}}</b>",
        f"{time_title}: %{{x|%Y-%m-%d}}",
        f"{series_label}: %{{customdata[0]}}",
        f"{t('axis_price')}: $%{{y:,.0f}}",
        f"{tr('状态', 'Status')}: {status_label}",
    ]
    if sales_title is not None:
        parts.append(f"{sales_title}: %{{customdata[1]:,.0f}}")
    return "<br>".join(parts) + "<extra></extra>"


def _trend_hover_template(series_label: str, time_title: str, sales_title: str | None, trend_label: str, tail: bool) -> str:
    parts = [
        f"<b>%{{fullData.name}}</b>",
        f"{time_title}: %{{x|%Y-%m-%d}}",
        f"{series_label}: %{{customdata[0]}}",
        f"{trend_label}: $%{{y:,.0f}}",
    ]
    if sales_title is not None:
        parts.append(f"{sales_title}: %{{customdata[1]:,.0f}}")
    if tail:
        parts.append(tr("尾段弱化", "Tail weakened"))
    return "<br>".join(parts) + "<extra></extra>"


def _add_separator_shape(fig: go.Figure, x_value):
    fig.add_vline(
        x=x_value,
        line_width=1,
        line_color="#ddd1c3",
        line_dash="dot",
        opacity=0.95,
    )


def _resolve_trend_segments(frame: pd.DataFrame, stable_col: str, trend_tail_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if stable_col in frame.columns:
        stable_mask = frame[stable_col].fillna(False)
        return frame[stable_mask].copy(), frame[~stable_mask].copy()
    tail_mask = frame[trend_tail_col].fillna(False) if trend_tail_col in frame.columns else False
    return frame[~tail_mask].copy(), frame[tail_mask].copy()


def _normalize_display_mode(display_mode: str | None) -> str:
    value = str(display_mode or "").strip().lower()
    if value in {DISPLAY_MODE_DUAL, DISPLAY_MODE_SHORT, DISPLAY_MODE_LONG}:
        return value
    legacy_map = {
        "Both": DISPLAY_MODE_DUAL,
        "Dual": DISPLAY_MODE_DUAL,
        "双线": DISPLAY_MODE_DUAL,
        "Short-term only": DISPLAY_MODE_SHORT,
        "仅短期": DISPLAY_MODE_SHORT,
        "Long-term only": DISPLAY_MODE_LONG,
        "仅长期": DISPLAY_MODE_LONG,
    }
    return legacy_map.get(str(display_mode or "").strip(), DISPLAY_MODE_DUAL)


def build_interactive_chart(
    plot_df: pd.DataFrame,
    level: str,
    time_col: str = "event_week_start",
    time_title: str | None = None,
    time_format: str = "%b %Y",
    include_sales: bool = False,
    sales_col: str = "weekly_sales_count",
    sales_title: str | None = None,
    x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    stable_col: str = "stable",
    trend_col: str | None = None,
    trend_tail_col: str = "underlying_trend_tail",
    display_mode: str = "Both",
    anchor_points: pd.DataFrame | None = None,
) -> go.Figure:
    df = plot_df.copy()

    if time_title is None:
        time_title = t("axis_week")
    if sales_title is None:
        sales_title = t("col_sales")

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    if sales_col in df.columns:
        df[sales_col] = pd.to_numeric(df[sales_col], errors="coerce")
    if stable_col not in df.columns:
        df[stable_col] = True
    if trend_col is not None and trend_col in df.columns:
        df[trend_col] = pd.to_numeric(df[trend_col], errors="coerce")
    if trend_tail_col not in df.columns:
        df[trend_tail_col] = False

    df = df[df[time_col].notna() & df["value"].notna()].copy()
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_base_layout(380, time_title, t("axis_price")))
        return fig

    normalized_display_mode = _normalize_display_mode(display_mode)
    show_short = normalized_display_mode in {DISPLAY_MODE_DUAL, DISPLAY_MODE_SHORT}
    show_long = normalized_display_mode in {DISPLAY_MODE_DUAL, DISPLAY_MODE_LONG}
    group_col = "series" if level == "NSW" else "region"
    group_label = tr("线条", "Series") if level == "NSW" else t("col_region")
    if group_col not in df.columns:
        df[group_col] = tr("滚动中位价", "Rolling median")

    fig = go.Figure()
    series_values = sorted(df[group_col].astype(str).unique().tolist())

    for idx, series_name in enumerate(series_values):
        short_color = SERIES_COLORS[idx % len(SERIES_COLORS)] if level != "NSW" else STABLE_COLOR
        long_color = TREND_SERIES_COLORS[idx % len(TREND_SERIES_COLORS)] if level != "NSW" else TREND_COLOR
        series_df = df[df[group_col].astype(str) == series_name].sort_values(time_col).copy()
        stable_df = series_df[series_df[stable_col].fillna(False)].copy()
        unstable_df = series_df[~series_df[stable_col].fillna(False)].copy()

        if show_short and len(stable_df) >= 2:
            fig.add_trace(
                go.Scatter(
                    x=stable_df[time_col],
                    y=stable_df["value"],
                    mode="lines",
                    name=series_name,
                    line=dict(color=short_color, width=3.6),
                    fill="tozeroy" if level == "NSW" else None,
                    fillcolor="rgba(143, 78, 46, 0.10)" if level == "NSW" else None,
                    customdata=list(
                        zip(
                            stable_df[group_col].astype(str),
                            stable_df[sales_col] if include_sales and sales_col in stable_df.columns else [None] * len(stable_df),
                        )
                    ),
                    hovertemplate=_hover_template(group_label, time_title, sales_title if include_sales else None, True),
                )
            )
        elif show_short and len(stable_df) == 1:
            fig.add_trace(
                go.Scatter(
                    x=stable_df[time_col],
                    y=stable_df["value"],
                    mode="lines+markers",
                    name=series_name,
                    line=dict(color=short_color, width=3.6),
                    marker=dict(size=6, color=short_color),
                    customdata=list(
                        zip(
                            stable_df[group_col].astype(str),
                            stable_df[sales_col] if include_sales and sales_col in stable_df.columns else [None] * len(stable_df),
                        )
                    ),
                    hovertemplate=_hover_template(group_label, time_title, sales_title if include_sales else None, True),
                )
            )

        if show_short and not unstable_df.empty:
            if not stable_df.empty:
                _add_separator_shape(fig, stable_df[time_col].max())
            fig.add_trace(
                go.Scatter(
                    x=unstable_df[time_col],
                    y=unstable_df["value"],
                    mode="lines",
                    name=f"{series_name} · {_status_label(False)}",
                    line=dict(color=UNSTABLE_COLOR if level == "NSW" else short_color, width=2.6, dash="dash"),
                    opacity=0.9 if level == "NSW" else 0.55,
                    customdata=list(
                        zip(
                            unstable_df[group_col].astype(str),
                            unstable_df[sales_col] if include_sales and sales_col in unstable_df.columns else [None] * len(unstable_df),
                        )
                    ),
                    hovertemplate=_hover_template(group_label, time_title, sales_title if include_sales else None, False),
                    showlegend=False,
                )
            )

        if show_long and trend_col is not None and trend_col in series_df.columns:
            trend_df = series_df[series_df[trend_col].notna()].copy()
            stable_trend_df, tail_trend_df = _resolve_trend_segments(trend_df, stable_col, trend_tail_col)
            trend_label = tr("长期趋势", "Underlying trend")

            if not stable_trend_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=stable_trend_df[time_col],
                        y=stable_trend_df[trend_col],
                        mode="lines",
                        name=f"{series_name} · {trend_label}",
                        line=dict(color=long_color, width=2.4),
                        opacity=0.95 if level != "NSW" else 0.82,
                        customdata=list(
                            zip(
                                stable_trend_df[group_col].astype(str),
                                stable_trend_df[sales_col] if include_sales and sales_col in stable_trend_df.columns else [None] * len(stable_trend_df),
                            )
                        ),
                        hovertemplate=_trend_hover_template(group_label, time_title, sales_title if include_sales else None, trend_label, False),
                    )
                )

            if not tail_trend_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=tail_trend_df[time_col],
                        y=tail_trend_df[trend_col],
                        mode="lines",
                        name=f"{series_name} · {trend_label}",
                        line=dict(color=long_color, width=2.2, dash="dash"),
                        opacity=0.38 if level != "NSW" else 0.28,
                        customdata=list(
                            zip(
                                tail_trend_df[group_col].astype(str),
                                tail_trend_df[sales_col] if include_sales and sales_col in tail_trend_df.columns else [None] * len(tail_trend_df),
                            )
                        ),
                        hovertemplate=_trend_hover_template(group_label, time_title, sales_title if include_sales else None, trend_label, True),
                        showlegend=stable_trend_df.empty,
                    )
                )

    if anchor_points is not None and not anchor_points.empty:
        anchor_df = anchor_points.copy()
        anchor_df["x"] = pd.to_datetime(anchor_df["x"], errors="coerce")
        anchor_df["y"] = pd.to_numeric(anchor_df["y"], errors="coerce")
        anchor_df = anchor_df[anchor_df["x"].notna() & anchor_df["y"].notna()].copy()
        if not anchor_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=anchor_df["x"],
                    y=anchor_df["y"],
                    mode="markers",
                    name=tr("最新锚点", "Latest anchor"),
                    marker=dict(size=8, color="#1f2937", line=dict(color="#ffffff", width=1.5)),
                    customdata=list(anchor_df["label"].astype(str)) if "label" in anchor_df.columns else None,
                    hovertemplate=(
                        f"{group_label}: %{{customdata}}<br>{time_title}: %{{x|%Y-%m-%d}}<br>{t('axis_price')}: $%{{y:,.0f}}<extra></extra>"
                        if "label" in anchor_df.columns else
                        f"{time_title}: %{{x|%Y-%m-%d}}<br>{t('axis_price')}: $%{{y:,.0f}}<extra></extra>"
                    ),
                    showlegend=False,
                )
            )

    fig.update_layout(**_base_layout(360, time_title, t("axis_price")))
    if level == "NSW":
        fig.update_layout(showlegend=False)
    if x_domain is not None:
        fig.update_xaxes(range=[pd.to_datetime(x_domain[0]), pd.to_datetime(x_domain[1])])
    y_values = df["value"].copy()
    if show_long and trend_col is not None and trend_col in df.columns:
        y_values = pd.concat([y_values, pd.to_numeric(df[trend_col], errors="coerce")], ignore_index=True)
    _apply_y_range(fig, y_values)
    fig.update_traces(connectgaps=False)
    return fig


def build_band_chart(
    df: pd.DataFrame,
    value_col: str,
    time_col: str,
    band_col: str,
    sales_col: str,
    stable_col: str = "stable",
    trend_col: str | None = None,
    trend_tail_col: str = "underlying_trend_tail",
    display_mode: str = "Both",
) -> go.Figure:
    frame = df.copy()
    frame[time_col] = pd.to_datetime(frame[time_col], errors="coerce")
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame[sales_col] = pd.to_numeric(frame[sales_col], errors="coerce")
    if stable_col not in frame.columns:
        frame[stable_col] = True
    if trend_col is not None and trend_col in frame.columns:
        frame[trend_col] = pd.to_numeric(frame[trend_col], errors="coerce")
    if trend_tail_col not in frame.columns:
        frame[trend_tail_col] = False
    frame = frame[frame[time_col].notna() & frame[value_col].notna()].copy()

    fig = go.Figure()
    if frame.empty:
        fig.update_layout(**_base_layout(340, t("axis_week"), t("axis_price")))
        return fig

    normalized_display_mode = _normalize_display_mode(display_mode)
    show_short = normalized_display_mode in {DISPLAY_MODE_DUAL, DISPLAY_MODE_SHORT}
    show_long = normalized_display_mode in {DISPLAY_MODE_DUAL, DISPLAY_MODE_LONG}
    bands = sorted(frame[band_col].astype(str).unique().tolist())
    for idx, band_name in enumerate(bands):
        short_color = SERIES_COLORS[idx % len(SERIES_COLORS)]
        long_color = TREND_SERIES_COLORS[idx % len(TREND_SERIES_COLORS)]
        band_df = frame[frame[band_col].astype(str) == band_name].sort_values(time_col).copy()
        stable_df = band_df[band_df[stable_col].fillna(False)].copy()
        unstable_df = band_df[~band_df[stable_col].fillna(False)].copy()

        if show_short and not stable_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=stable_df[time_col],
                    y=stable_df[value_col],
                    mode="lines",
                    name=band_name,
                    line=dict(color=short_color, width=3.2),
                    customdata=list(zip(stable_df[band_col].astype(str), stable_df[sales_col])),
                    hovertemplate=_hover_template(tr("价格区间", "Price band"), tr("日期", "Date"), tr("28天销量", "28-day sales"), True),
                )
            )

        if show_short and not unstable_df.empty:
            if not stable_df.empty:
                _add_separator_shape(fig, stable_df[time_col].max())
            fig.add_trace(
                go.Scatter(
                    x=unstable_df[time_col],
                    y=unstable_df[value_col],
                    mode="lines",
                    name=f"{band_name} · {_status_label(False)}",
                    line=dict(color=short_color, width=2.4, dash="dash"),
                    opacity=0.42,
                    customdata=list(zip(unstable_df[band_col].astype(str), unstable_df[sales_col])),
                    hovertemplate=_hover_template(tr("价格区间", "Price band"), tr("日期", "Date"), tr("28天销量", "28-day sales"), False),
                    showlegend=False,
                )
            )

        if show_long and trend_col is not None and trend_col in band_df.columns:
            trend_df = band_df[band_df[trend_col].notna()].copy()
            stable_trend_df, tail_trend_df = _resolve_trend_segments(trend_df, stable_col, trend_tail_col)
            trend_label = tr("长期趋势", "Underlying trend")

            if not stable_trend_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=stable_trend_df[time_col],
                        y=stable_trend_df[trend_col],
                        mode="lines",
                        name=f"{band_name} · {trend_label}",
                        line=dict(color=long_color, width=2.2),
                        opacity=0.82,
                        customdata=list(zip(stable_trend_df[band_col].astype(str), stable_trend_df[sales_col])),
                        hovertemplate=_trend_hover_template(tr("价格区间", "Price band"), tr("日期", "Date"), tr("28天销量", "28-day sales"), trend_label, False),
                    )
                )

            if not tail_trend_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=tail_trend_df[time_col],
                        y=tail_trend_df[trend_col],
                        mode="lines",
                        name=f"{band_name} · {trend_label}",
                        line=dict(color=long_color, width=2.0, dash="dash"),
                        opacity=0.28,
                        customdata=list(zip(tail_trend_df[band_col].astype(str), tail_trend_df[sales_col])),
                        hovertemplate=_trend_hover_template(tr("价格区间", "Price band"), tr("日期", "Date"), tr("28天销量", "28-day sales"), trend_label, True),
                        showlegend=stable_trend_df.empty,
                    )
                )

    fig.update_layout(**_base_layout(340, t("axis_week"), t("axis_price")))
    y_values = frame[value_col].copy()
    if show_long and trend_col is not None and trend_col in frame.columns:
        y_values = pd.concat([y_values, pd.to_numeric(frame[trend_col], errors="coerce")], ignore_index=True)
    _apply_y_range(fig, y_values)
    fig.update_traces(connectgaps=False)
    return fig
