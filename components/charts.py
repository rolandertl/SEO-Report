import plotly.graph_objects as go


def area_chart(
    df,
    x_col: str,
    y_col: str,
    line_color: str,
    fill_rgba: str,
    value_decimals: int = 2,
    y_tickformat: str | None = None,
):
    fig = go.Figure()

    # Hauptfläche
    fig.add_trace(
        go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="lines",
            line=dict(color=line_color, width=3),
            fill="tozeroy",
            fillcolor=fill_rgba,
            hovertemplate="%{y:.3f}<extra></extra>",
        )
    )

    # Start- und Endpunkt als Labels (PDF-tauglich)
    x_first = df[x_col].iloc[0]
    y_first = float(df[y_col].iloc[0])
    x_last = df[x_col].iloc[-1]
    y_last = float(df[y_col].iloc[-1])

    fig.add_trace(
        go.Scatter(
            x=[x_first],
            y=[y_first],
            mode="markers+text",
            marker=dict(color=line_color, size=8),
            text=[f"{y_first:.{value_decimals}f}"],
            textposition="top left",
            textfont=dict(color=line_color, size=12),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[x_last],
            y=[y_last],
            mode="markers+text",
            marker=dict(color=line_color, size=8),
            text=[f"{y_last:.{value_decimals}f}"],
            textposition="top right",
            textfont=dict(color=line_color, size=12),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.update_layout(
        height=380,
        margin=dict(l=22, r=12, t=18, b=72),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            automargin=True,
            tickfont=dict(size=12, color="#374151"),
            tickformat="%b %Y",
            tickangle=0,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(0,0,0,0.05)",
            zeroline=False,
            automargin=True,
            tickfont=dict(size=12, color="#374151"),
            tickformat=y_tickformat,
        ),
    )

    return fig

def donut_chart(labels: list[str], values: list[float], colors: list[str]):
    import plotly.graph_objects as go

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.65,
                marker=dict(colors=colors, line=dict(color="white", width=2)),
                textinfo="percent",
            )
        ]
    )

    fig.update_layout(
        height=380,
        margin=dict(l=0, r=34, t=10, b=10),
        showlegend=False,
        paper_bgcolor="white",
        plot_bgcolor="white",
    )

    return fig

import plotly.graph_objects as go


def dual_area_chart(
    df,
    x_col: str,
    y1_col: str,
    y2_col: str,
    label1: str,
    label2: str,
    color1: str,
    color2: str,
    fill1: str,
    fill2: str,
):
    fig = go.Figure()

    # Fläche 1 (Top-100)
    fig.add_trace(
        go.Scatter(
            x=df[x_col],
            y=df[y1_col],
            mode="lines+markers+text",
            name=label1,
            line=dict(color=color1, width=3),
            marker=dict(size=6, color=color1),
            fill="tozeroy",
            fillcolor=fill1,
            text=[""] * (len(df) - 1) + [str(int(df[y1_col].iloc[-1]))],  # Label nur am Ende
            textposition="top right",
            textfont=dict(color=color1, size=12),
            hovertemplate="%{y}<extra></extra>",
        )
    )

    # Fläche 2 (Top-10)
    fig.add_trace(
        go.Scatter(
            x=df[x_col],
            y=df[y2_col],
            mode="lines+markers+text",
            name=label2,
            line=dict(color=color2, width=3),
            marker=dict(size=6, color=color2),
            fill="tozeroy",
            fillcolor=fill2,
            text=[""] * (len(df) - 1) + [str(int(df[y2_col].iloc[-1]))],  # Label nur am Ende
            textposition="top right",
            textfont=dict(color=color2, size=12),
            hovertemplate="%{y}<extra></extra>",
        )
    )

    fig.update_layout(
        height=420,
        margin=dict(l=22, r=12, t=18, b=72),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=0.98,
            xanchor="left",
            x=0.02,
        ),
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            automargin=True,
            tickfont=dict(size=12, color="#374151"),
            tickformat="%b %Y",
            tickangle=0,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(0,0,0,0.05)",
            zeroline=False,
            automargin=True,
            tickfont=dict(size=12, color="#374151"),
        ),
    )

    return fig
import plotly.graph_objects as go


def _auto_table_column_widths(headers: list[str]) -> list[float] | None:
    n = len(headers)
    if n == 2:
        return [0.74, 0.26]
    if n == 3:
        return [0.56, 0.14, 0.30]
    if n == 5:
        return [0.58, 0.10, 0.10, 0.07, 0.15]
    return None


def table_chart(headers: list[str], rows: list[list[str]], column_widths: list[float] | None = None):
    row_count = len(rows)
    row_colors = ["#FFFFFF" if i % 2 == 0 else "#F7F9FC" for i in range(max(row_count, 1))]
    widths = column_widths or _auto_table_column_widths(headers)

    fig = go.Figure(
        data=[
            go.Table(
                columnwidth=widths,
                header=dict(
                    values=headers,
                    fill_color="#EEF2F7",
                    align="left",
                    font=dict(size=13, color="#1E293B"),
                    height=34,
                    line_color="#D7DEE8",
                ),
                cells=dict(
                    values=list(zip(*rows)) if rows else [[] for _ in headers],
                    align="left",
                    fill_color=[row_colors] * len(headers),
                    font=dict(size=12, color="#1F2937"),
                    height=30,
                    line_color="#E2E8F0",
                ),
            )
        ]
    )

    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="white",
        template="plotly_white",
    )
    return fig
