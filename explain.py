"""Turns a rule-based flag into a plain-language explanation + next step.
LLM_PROVIDER env var: none (default, offline template) | anthropic | azure"""
import os

NEXT_STEP = {
    "S1-F1": "Check whether the consultation is already included in the procedure fee; request the medical report.",
    "S2-F2": "Review the prescriptions against the diagnosis and confirm the repeated item was clinically justified.",
    "S5-F1": "Verify whether this visit is a free follow-up under the provider contract; reject the consultation fee if so.",
    "S6-F1": "Check the clinical reason for the repeat visit and whether it is a new episode of care.",
    "S21": "Compare the billed consultation level with the clinician's registered specialty; request a re-grade if mismatched.",
}

SYSTEM = ("You assist medical claims reviewers in Fraud, Waste & Abuse. Explain in 3-4 short sentences why the "
          "claim was flagged, using ONLY the evidence given. Do not invent facts or accuse anyone of fraud; "
          "use wording like 'may indicate'. End with one recommended next step. Reply in the requested language.")


def template_explain(row, lang="English"):
    step = NEXT_STEP[row["flag_id"]]
    if lang == "Arabic":
        return (f"تم تعليم المطالبة {row['claim_id']} بـ ({row['flag_name']}). السبب: {row['evidence']}. "
                f"هذا قد يشير إلى فوترة مكررة أو غير مبررة ويحتاج مراجعة.\n\nالخطوة المقترحة: {step}")
    return (f"Claim {row['claim_id']} was flagged: {row['flag_name']}. Reason: {row['evidence']}. "
            f"This may indicate duplicate or unjustified billing and needs review.\n\nSuggested next step: {step}")


def _prompt(row, lang):
    return (f"Language: {lang}\nFlag: {row['flag_id']} - {row['flag_name']}\nClaim: {row['claim_id']}\n"
            f"Procedure code: {row['procedure_code']}\nAmount: {row['amount']}\nEvidence: {row['evidence']}\n"
            f"Suggested next step (rephrase): {NEXT_STEP[row['flag_id']]}")


def explain(row, lang="English"):
    provider = os.getenv("LLM_PROVIDER", "none").lower()
    try:
        if provider == "anthropic":
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"), max_tokens=400,
                system=SYSTEM, messages=[{"role": "user", "content": _prompt(row, lang)}])
            return msg.content[0].text
        if provider == "azure":
            from openai import AzureOpenAI
            client = AzureOpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"],
                                 azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                                 api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01"))
            r = client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": _prompt(row, lang)}])
            return r.choices[0].message.content
    except Exception as e:  # never break the demo
        return template_explain(row, lang) + f"\n\n(LLM unavailable, template used: {e})"
    return template_explain(row, lang)
