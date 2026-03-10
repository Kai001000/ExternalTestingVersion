import altair as alt
import pandas as pd

from .i18n import t


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
) -> alt.Chart:
    df = plot_df.copy()

    if time_title is None:
        time_title = t("axis_week")
    if sales_title is None:
        sales_title = t("col_sales")

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce").round(0)

    if sales_col in df.columns:
        df[sales_col] = pd.to_numeric(df[sales_col], errors="coerce")

    df = df[df[time_col].notna() & df["value"].notna()].copy()
    if df.empty:
        return alt.Chart(pd.DataFrame({"x": [], "y": []})).mark_line()

    if stable_col not in df.columns:
        df[stable_col] = True

    hover = alt.selection_point(
        fields=[time_col],
        nearest=True,
        on="mouseover",
        empty=False,
        clear="mouseout",
    )

    x_scale = None
    if x_domain is not None:
        start_ts, end_ts = x_domain
        start_ts = pd.to_datetime(start_ts)
        end_ts = pd.to_datetime(end_ts)
        if pd.notna(start_ts) and pd.notna(end_ts) and start_ts <= end_ts:
            x_scale = alt.Scale(domain=[start_ts, end_ts])

    x_enc = alt.X(
        f"{time_col}:T",
        title=time_title,
        axis=alt.Axis(format=time_format, labelOverlap=True),
        scale=x_scale if x_scale is not None else alt.Undefined,
    )

    v = df["value"].dropna()
    if v.empty:
        domain = None
    else:
        lo = float(v.quantile(0.01))
        hi = float(v.quantile(0.99))
        if lo == hi:
            pad = max(1.0, lo * 0.02)
            domain = [lo - pad, hi + pad]
        else:
            pad = (hi - lo) * 0.06
            domain = [lo - pad, hi + pad]

    y_enc = alt.Y(
        "value:Q",
        title=t("axis_price"),
        axis=alt.Axis(format=",.0f"),
        scale=alt.Scale(zero=False, domain=domain) if domain else alt.Scale(zero=False),
    )

    if level == "NSW":
        color_enc = alt.Color("series:N", title=None, legend=None)
        stroke_dash_enc = alt.StrokeDash(
            f"{stable_col}:N",
            scale=alt.Scale(
                domain=[True, False],
                range=[[], [5, 3]]
            ),
            legend=None
        )
    else:
        color_enc = alt.Color("region:N", title=t("col_region"), legend=alt.Legend(orient="top"))
        stroke_dash_enc = alt.StrokeDash(
            f"{stable_col}:N",
            scale=alt.Scale(
                domain=[True, False],
                range=[[], [5, 3]]
            ),
            legend=alt.Legend(title="稳定", orient="bottom")
        )

    line = alt.Chart(df).mark_line(strokeWidth=2).encode(
        x=x_enc,
        y=y_enc,
        color=color_enc,
        strokeDash=stroke_dash_enc,
        tooltip=[],
    )

    selectors = alt.Chart(df).mark_point(opacity=0).encode(
        x=x_enc,
        y=y_enc,
        tooltip=[],
    ).add_params(hover)

    rulers = alt.Chart(df).mark_rule(strokeDash=[3, 3], strokeWidth=1, color="gray").encode(
        x=x_enc,
        opacity=alt.condition(hover, alt.value(0.8), alt.value(0)),
        tooltip=[],
    ).transform_filter(hover)

    tooltip_fields = [
        alt.Tooltip(f"{time_col}:T", title=time_title, format="%b %d, %Y"),
        alt.Tooltip("region:N", title=t("col_region")),
        alt.Tooltip("value:Q", title=t("axis_price"), format=",.0f"),
    ]
    if include_sales and sales_col in df.columns:
        tooltip_fields.append(
            alt.Tooltip(f"{sales_col}:Q", title=sales_title, format=",d")
        )
    tooltip_fields.append(alt.Tooltip(f"{stable_col}:N", title="稳定"))

    hover_points = alt.Chart(df).mark_circle(size=80).encode(
        x=x_enc,
        y=y_enc,
        color=color_enc,
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=tooltip_fields,
    ).transform_filter(hover)

    chart = alt.layer(
        line,
        selectors,
        rulers,
        hover_points,
    ).properties(height=420).interactive()

    return chart


def build_band_chart(
    df: pd.DataFrame,
    value_col: str,
    time_col: str,
    band_col: str,
    sales_col: str,
    stable_col: str = "stable",
) -> alt.Chart:
    chart = alt.Chart(df).mark_line().encode(
        x=alt.X(f"{time_col}:T", title=t("axis_week"), axis=alt.Axis(format="%b %Y")),
        y=alt.Y(f"{value_col}:Q", title=t("axis_price"), scale=alt.Scale(zero=False)),
        color=alt.Color(f"{band_col}:N", title="价格区间"),
        strokeDash=alt.StrokeDash(
            f"{stable_col}:N",
            scale=alt.Scale(domain=[True, False], range=[[], [5, 3]]),
            legend=alt.Legend(title="稳定")
        ),
        tooltip=[
            alt.Tooltip(f"{time_col}:T", title="日期", format="%Y-%m-%d"),
            alt.Tooltip(f"{band_col}:N", title="价格区间"),
            alt.Tooltip(f"{value_col}:Q", title="中位价", format=",.0f"),
            alt.Tooltip(f"{sales_col}:Q", title="28天销量", format=",d"),
        ]
    ).properties(height=400).interactive()

    return chart