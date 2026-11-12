"""FWA flag rules (rule-based, deterministic). The LLM never decides flags,
it only explains them. Reference lists below are SYNTHETIC placeholders."""
import pandas as pd

# ---- Configurable reference data -------------------------------------------
GROUP_PROVIDERS = {"GRP-H01", "GRP-C02"}          # placeholder for the hospital group
QUALIFYING_PROCEDURES = {"P100", "P101", "P102", "P103"}
FALSIFYING_CODES = {"PH01", "PH02", "PH03"}
S6_EXCLUDED_CODES = {"9.02", "10.02", "11.02"}
SAME_PROVIDER_FOR_REPEAT = True   # ASSUMPTION: repeat visit = same member AND same provider

FLAG_NAMES = {
    "S1-F1": "Consultation & Procedure at the Same Day",
    "S2-F2": "Falsifying Diagnosis",
    "S5-F1": "Repeat Visit Within 7 Days - Free Follow-up",
    "S6-F1": "Repeat Visit After 8-26 Days - Repeat Consultation",
    "S21": "Consultation Specialty Upcoding",
}
KEY = ["life_code", "billing_provider", "date_of_service"]
COLS = ["claim_id", "flag_id", "flag_name", "life_code", "billing_provider",
        "date_of_service", "procedure_code", "amount", "evidence"]


def _fmt(out, flag_id):
    out = out.copy()
    out["flag_id"] = flag_id
    out["flag_name"] = FLAG_NAMES[flag_id]
    return out[COLS]


def _cons(df):
    return df[df.procedure_type == "Consultation"]


def s1(df):
    c = _cons(df)
    q = df[df.procedure_code.isin(QUALIFYING_PROCEDURES)][KEY + ["procedure_code"]]
    q = q.rename(columns={"procedure_code": "q_code"})
    m = c.merge(q, on=KEY)
    g = m.groupby("claim_id")["q_code"].apply(lambda s: ", ".join(sorted(set(s)))).reset_index()
    out = c.merge(g, on="claim_id")
    out["evidence"] = ("Consultation " + out.procedure_code + " billed on the same day, same member "
                       "and provider as qualifying procedure(s): " + out.q_code)
    return _fmt(out, "S1-F1")


def s2(df):
    p = df[(df.procedure_type == "Pharmaceuticals") & df.procedure_code.isin(FALSIFYING_CODES)].copy()
    p["n"] = p.groupby(KEY + ["procedure_code"])["claim_id"].transform("count")
    out = p[p.n > 1].copy()
    out["evidence"] = ("Pharmaceutical code " + out.procedure_code + " appears " + out.n.astype(str)
                       + " times on the same day for the same member and provider")
    return _fmt(out, "S2-F2")


def _gaps(df):
    c = _cons(df).sort_values(["life_code", "date_of_service", "claim_id"]).copy()
    grp = ["life_code"] + (["billing_provider"] if SAME_PROVIDER_FOR_REPEAT else [])
    c["prev_date"] = c.groupby(grp)["date_of_service"].shift()
    c["gap"] = (c.date_of_service - c.prev_date).dt.days
    c["is_group"] = c.billing_provider.isin(GROUP_PROVIDERS)
    return c.dropna(subset=["gap"])


def s5(df):
    c = _gaps(df)
    hi = c.is_group.map({True: 10, False: 7})
    out = c[(c.gap >= 1) & (c.gap <= hi)].copy()
    out["evidence"] = ("Consultation repeated " + out.gap.astype(int).astype(str) + " day(s) after the previous "
                       "one (window 1-" + hi[out.index].astype(str) + " days"
                       + out.is_group.map({True: ", hospital-group rule", False: ""}) + ")")
    return _fmt(out, "S5-F1")


def s6(df):
    c = _gaps(df)
    c = c[~c.procedure_code.isin(S6_EXCLUDED_CODES)]
    lo = c.is_group.map({True: 11, False: 8})
    hi = c.is_group.map({True: 30, False: 28})
    out = c[(c.gap >= lo) & (c.gap <= hi)].copy()
    out["evidence"] = ("Consultation repeated " + out.gap.astype(int).astype(str) + " days after the previous one "
                       "(window " + lo[out.index].astype(str) + "-" + hi[out.index].astype(str) + " days"
                       + out.is_group.map({True: ", hospital-group rule", False: ""}) + ")")
    return _fmt(out, "S6-F1")


def s21(df):
    c = _cons(df).copy()
    pid = c.procedure_code.str.split(".").str[0].astype(int)
    label = pid.map({9: "General Practitioner", 10: "Specialist", 11: "Consultant"})
    mask = ((pid == 11) & (c.clinician_specialty == "Specialist")) | \
           (pid.isin([10, 11]) & c.clinician_specialty.isin(["GP", "GEN"]))
    out = c[mask].copy()
    out["evidence"] = ("Billed as " + label[out.index] + " (procedure ID " + pid[out.index].astype(str)
                       + ") but clinician specialty is " + out.clinician_specialty)
    return _fmt(out, "S21")


def run_all(df):
    df = df.copy()
    df["date_of_service"] = pd.to_datetime(df["date_of_service"])
    res = pd.concat([f(df) for f in (s1, s2, s5, s6, s21)], ignore_index=True)
    res["date_of_service"] = res["date_of_service"].dt.date
    return res.sort_values(["flag_id", "claim_id"]).reset_index(drop=True)
