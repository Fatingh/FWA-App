import os
import altair as alt
import pandas as pd
import streamlit as st
from flags import run_all, FLAG_NAMES
from explain import explain
from impact import render as render_impact
from report import build_provider_report

st.set_page_config(page_title="FWA Explainer", layout="wide")
st.title("FWA Explainer (synthetic data prototype)")
st.caption("Flags are produced by deterministic rules. The AI only explains them and suggests the next step.")


@st.cache_data(show_spinner="Computing flags on all loaded data...")
def load_and_flag(frames):
    """Flags are computed ONCE on ALL loaded data. Date filters are applied afterwards,
    so repeat-visit flags still see visits that fall outside the chosen period."""
    claims = pd.concat(frames, ignore_index=True)
    before = len(claims)
    claims = claims.drop_duplicates(subset="claim_id", keep="last")
    return claims, before - len(claims), run_all(claims)


with st.sidebar:
    ups = st.file_uploader("Claims CSV files (synthetic only)", type="csv", accept_multiple_files=True,
                           help="Upload one or more monthly files. They are combined, duplicates removed by claim_id.")
    frames = tuple(pd.read_csv(u) for u in ups) if ups else (pd.read_csv("data.csv"),)
    claims, dupes, res_all = load_and_flag(frames)
    if dupes:
        st.caption(f"{dupes} duplicate claim rows ignored.")

    lang = st.radio("Explanation language", ["English", "Arabic"])
    mode = st.selectbox("AI mode", ["none", "anthropic", "azure"],
                        help="none = offline template (no API cost)")
    os.environ["LLM_PROVIDER"] = mode
    picked = st.multiselect("Flags", list(FLAG_NAMES), default=list(FLAG_NAMES),
                            format_func=lambda k: f"{k} - {FLAG_NAMES[k]}")

    dmin, dmax = res_all.date_of_service.min(), res_all.date_of_service.max()
    rng = st.date_input("Date of service (period)", value=(dmin, dmax), min_value=dmin, max_value=dmax,
                        help="Flags are calculated on ALL data first, then filtered to this period.")
    start, end = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (dmin, dmax)

res = res_all[res_all.flag_id.isin(picked) & (res_all.date_of_service >= start) & (res_all.date_of_service <= end)]

tab_flags, tab_impact, tab_provider = st.tabs(["Flags & explainer", "Business impact", "Provider report"])

with tab_flags:
    st.caption(f"Showing flags with date of service {start:%d %b %Y} to {end:%d %b %Y}. "
               f"Calculated on all {len(claims):,} loaded claims.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Claims loaded", f"{len(claims):,}")
    c2.metric("Flagged rows (in period)", f"{len(res):,}")
    c3.metric("Flagged amount (in period)", f"{res.drop_duplicates('claim_id').amount.sum():,.0f}")

    counts = res.flag_id.value_counts().rename_axis("flag").reset_index(name="flagged rows")
    st.altair_chart(
        alt.Chart(counts).mark_bar().encode(
            x=alt.X("flag:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("flagged rows:Q", scale=alt.Scale(domainMin=0), title="Flagged rows"),
            tooltip=["flag", "flagged rows"],
        ).properties(height=300),
        use_container_width=True,
    )
    st.dataframe(res.drop(columns=["flag_name"]), width="stretch", hide_index=True)
    st.download_button("Download flags for this period (CSV)", res.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"flags_{start:%Y%m%d}_{end:%Y%m%d}.csv", mime="text/csv")

    st.subheader("Explain a flagged claim")
    if len(res):
        labels = res.apply(lambda r: f"{r.claim_id} | {r.flag_id} | {r.billing_provider}", axis=1).tolist()
        sel = st.selectbox("Pick a flag", labels)
        row = res.iloc[labels.index(sel)]
        st.info(row["evidence"])
        if st.button("Explain with AI"):
            with st.spinner("Generating..."):
                st.write(explain(row, lang))

with tab_impact:
    if len(res):
        render_impact(res, picked)
    else:
        st.info("No flags in the selected period.")

with tab_provider:
    st.subheader("Provider report (PDF)")
    if len(res):
        counts_p = res.groupby("billing_provider").claim_id.nunique().sort_values(ascending=False)
        prov = st.selectbox("Provider", counts_p.index.tolist(),
                            format_func=lambda p: f"{p}  ({counts_p[p]} flagged claims)")
        days = st.number_input("Ask the provider to respond within (days)", 1, 60, 7)
        sub = res[res.billing_provider == prov].sort_values(["flag_id", "date_of_service", "claim_id"])
        st.dataframe(sub.drop(columns=["flag_name", "billing_provider"]), width="stretch", hide_index=True)
        pdf = build_provider_report(res, prov, respond_days=days, flag_names=FLAG_NAMES, period=(start, end))
        st.download_button("Download PDF report", pdf, file_name=f"provider_report_{prov}.pdf",
                           mime="application/pdf")
    else:
        st.info("No flags in the selected period.")
