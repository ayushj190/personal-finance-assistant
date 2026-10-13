import pandas as pd
import plotly.express as px
import streamlit as st

import ui.pages.investments
from services.portfolio import get_dimension_exposure_df
from ui.charts import ASSET_TYPE_COLORS, SECTOR_COLORS, build_investments_market_carpet
from ui.components import section_header
from ui.theme import render_chart


def render_exposure_visualizer(consolidated_df: pd.DataFrame) -> None:
    if consolidated_df.empty:
        return

    with section_header("Sector & Strategic Allocation", "Portfolio exposure heatmap and multi-dimension distribution"):
        with st.container(border=True, key="investments_exposure_heatmap_panel"):
            st.markdown("##### 🗺️ Portfolio Exposure Heatmap")
            carpet_fig = build_investments_market_carpet(consolidated_df, height=380)
            render_chart(carpet_fig, width="stretch", key="investments_market_carpet")

        dim_options = ["Sector", "Region", "Currency", "Nature"]
        selected_dim = st.pills(
            "Exposure Dimension",
            options=dim_options,
            default="Sector",
            key="portfolio_exposure_dim_pills",
            label_visibility="collapsed",
        ) or "Sector"

        dim_df = get_dimension_exposure_df(consolidated_df, selected_dim)
        col_donut, col_bar = st.columns([1, 1])

        with col_donut:
            with st.container(border=True):
                color_map = SECTOR_COLORS if selected_dim == "Sector" else None
                donut_fig = px.pie(
                    dim_df,
                    names="bucket",
                    values="value_eur",
                    hole=0.55,
                    color="bucket" if color_map else None,
                    color_discrete_map=color_map,
                    title=f"Allocation by {selected_dim}",
                )
                if ui.pages.investments.is_hidden():
                    donut_fig.update_traces(
                        texttemplate="%{label}<br>****%",
                        hovertemplate="Censored<extra></extra>",
                    )
                else:
                    donut_fig.update_traces(
                        texttemplate="%{label}<br>%{percent:.1%}",
                        hovertemplate="<b>%{label}</b><br>Value: €%{value:,.2f}<br>%{percent:.1%}<extra></extra>",
                    )
                donut_fig.update_layout(
                    showlegend=False,
                    margin=dict(t=40, l=10, r=10, b=10),
                    height=320,
                )
                render_chart(donut_fig, width="stretch")

        with col_bar:
            with st.container(border=True):
                bar_data = dim_df.sort_values(by="weight_pct", ascending=True)
                bar_fig = px.bar(
                    bar_data,
                    x="weight_pct",
                    y="bucket",
                    orientation="h",
                    text=bar_data["weight_pct"].map(
                        lambda x: "****%" if ui.pages.investments.is_hidden() else f"{x:.1f}%"
                    ),
                    color="bucket" if color_map else None,
                    color_discrete_map=color_map,
                    title=f"{selected_dim} Breakdown (%)",
                )
                if ui.pages.investments.is_hidden():
                    bar_fig.update_traces(hovertemplate="Censored<extra></extra>")
                else:
                    bar_fig.update_traces(
                        hovertemplate="<b>%{y}</b><br>Weight: %{x:.1f}%<extra></extra>"
                    )
                bar_fig.update_layout(
                    showlegend=False,
                    margin=dict(t=40, l=110, r=20, b=20),
                    height=320,
                    xaxis=dict(ticksuffix="%", automargin=True),
                    yaxis=dict(automargin=True),
                )
                render_chart(bar_fig, width="stretch")

        with st.expander("💼 Asset Class Breakdown (Stocks, ETFs, Crypto, Commodities)", expanded=False):
            ac_dim_df = get_dimension_exposure_df(consolidated_df, "Asset Class")
            ac_c1, ac_c2 = st.columns([1, 1])
            with ac_c1:
                with st.container(border=True):
                    ac_fig = px.pie(
                        ac_dim_df,
                        names="bucket",
                        values="value_eur",
                        hole=0.5,
                        color="bucket",
                        color_discrete_map=ASSET_TYPE_COLORS,
                        title="Asset Class Distribution",
                    )
                    ac_fig.update_layout(height=280, margin=dict(t=30, l=10, r=10, b=10))
                    render_chart(ac_fig, width="stretch")
            with ac_c2:
                table_ac = ac_dim_df.copy()
                if ui.pages.investments.is_hidden():
                    table_ac["Value (€)"] = "€****"
                    table_ac["Weight (%)"] = "****%"
                else:
                    table_ac["Value (€)"] = table_ac["value_eur"].map(lambda v: f"€{v:,.2f}")
                    table_ac["Weight (%)"] = table_ac["weight_pct"].map(lambda w: f"{w:.1f}%")
                table_ac.rename(columns={"bucket": "Asset Class"}, inplace=True)
                st.dataframe(
                    table_ac[["Asset Class", "Value (€)", "Weight (%)"]],
                    width="stretch",
                    hide_index=True,
                )

        with st.expander(f"📋 View {selected_dim} Details Table", expanded=False):
            table_df = dim_df.copy()
            if ui.pages.investments.is_hidden():
                table_df["Value (€)"] = "€****"
                table_df["Weight (%)"] = "****%"
            else:
                table_df["Value (€)"] = table_df["value_eur"].map(lambda v: f"€{v:,.2f}")
                table_df["Weight (%)"] = table_df["weight_pct"].map(lambda w: f"{w:.1f}%")
            table_df.rename(columns={"bucket": selected_dim}, inplace=True)
            st.dataframe(
                table_df[[selected_dim, "Value (€)", "Weight (%)"]],
                width="stretch",
                hide_index=True,
            )
