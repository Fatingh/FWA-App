"""Business-impact tab: estimated review time/cost before vs after the AI assistant.
ALL numbers below are PLACEHOLDER ASSUMPTIONS. Replace them with measured values
(see the 'How to get real numbers' box in the app)."""
import altair as alt
import pandas as pd
import streamlit as st

# (manual minutes per flagged row, minutes with the AI assistant) - placeholders
DEFAULT_MINUTES = {
    "S1-F1": (10, 3),
    "S2-F2": (12, 4),
    "S5-F1": (8, 3),
    "S6-F1": (8, 3),
    "S21": (6, 2),
}


def render(res, flag_names):
    st.subheader("Business impact: before vs after")
    st.warning("The numbers below are assumptions, not measurements. Replace them with your own time "
               "study before presenting. Edit any value and the results update instantly.")

    c1, c2, c3, c4 = st.columns(4)
    monthly = c1.number_input("Flagged rows reviewed per month", 10, 1_000_000, 2000, step=100,
                              help="Total across all selected flags. Use your real monthly volume.")
    rate = c2.number_input("Cost per reviewer hour", 0.5, 1000.0, 10.0, step=0.5,
                           help="Use your own currency and loaded cost.")
    fte_hours = c3.number_input("Productive hours per FTE / month", 40, 220, 120, step=10)
    adoption = c4.slider("Reviews done with the AI assistant (%)", 0, 100, 80)

    flags_in = [f for f in flag_names if f in set(res.flag_id)] or list(flag_names)
    base = pd.DataFrame({
        "flag": flags_in,
        "manual_min": [DEFAULT_MINUTES.get(f, (8, 3))[0] for f in flags_in],
        "with_ai_min": [DEFAULT_MINUTES.get(f, (8, 3))[1] for f in flags_in],
    })
    st.markdown("**Minutes per review** (editable)")
    edited = st.data_editor(base, hide_index=True, width="stretch",
                            column_config={"flag": st.column_config.TextColumn(disabled=True),
                                           "manual_min": st.column_config.NumberColumn("Manual (min)", min_value=0.0),
                                           "with_ai_min": st.column_config.NumberColumn("With AI (min)", min_value=0.0)})

    mix = res.flag_id.value_counts(normalize=True)
    edited["share"] = edited.flag.map(mix).fillna(0)
    if edited.share.sum() == 0:
        edited["share"] = 1 / len(edited)
    edited["share"] = edited.share / edited.share.sum()
    a = adoption / 100
    edited["volume"] = monthly * edited.share
    edited["hours_before"] = edited.volume * edited.manual_min / 60
    edited["hours_after"] = edited.volume * (a * edited.with_ai_min + (1 - a) * edited.manual_min) / 60

    before, after = edited.hours_before.sum(), edited.hours_after.sum()
    saved = before - after
    pct = saved / before * 100 if before else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Review hours / month (before)", f"{before:,.0f}")
    m2.metric("Review hours / month (after)", f"{after:,.0f}", f"-{saved:,.0f} h")
    m3.metric("Time saved", f"{pct:.0f}%", f"{saved / fte_hours:.1f} FTE")
    m4.metric("Cost saved / year", f"{saved * rate * 12:,.0f}", f"{saved * rate:,.0f} / month")

    long = edited.melt(id_vars="flag", value_vars=["hours_before", "hours_after"],
                       var_name="scenario", value_name="hours")
    long["scenario"] = long.scenario.map({"hours_before": "Before (manual)", "hours_after": "After (AI-assisted)"})
    st.altair_chart(
        alt.Chart(long).mark_bar().encode(
            x=alt.X("flag:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            xOffset="scenario:N",
            y=alt.Y("hours:Q", scale=alt.Scale(domainMin=0), title="Review hours / month"),
            color=alt.Color("scenario:N", title=None),
            tooltip=["flag", "scenario", alt.Tooltip("hours:Q", format=",.0f")],
        ).properties(height=300),
        use_container_width=True,
    )

    with st.expander("How to get real numbers (recommended before presenting)"):
        st.markdown(
            "1. Pick 10 flagged rows per flag type (synthetic or an approved sample).\n"
            "2. Ask 2-3 reviewers to review them the current way and time each one.\n"
            "3. Ask the same reviewers to review similar rows using this tool and time them.\n"
            "4. Use the averages as *Manual* and *With AI*, and your real monthly volume.\n"
            "5. In the presentation, state clearly: *estimated, based on a small time study*."
        )
