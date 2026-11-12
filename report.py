"""Builds a provider-facing PDF: summary, what is requested from the provider, and a sorted case table.
Wording is deliberately neutral: flags are indicators for review, not findings of fraud."""
from datetime import date, timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY, TEAL, LIGHT, GRID = colors.HexColor("#0F2A3D"), colors.HexColor("#136F7C"), colors.HexColor("#EEF3F2"), colors.HexColor("#C9D3D0")

# What we ask the provider to do, per flag (edit to match your real process)
REQUESTED = {
    "S1-F1": "Confirm whether the consultation is separately billable alongside the procedure on the same day. "
             "Provide the medical report and the invoice breakdown.",
    "S2-F2": "Provide the prescriptions and the clinical justification for the repeated pharmaceutical item(s).",
    "S5-F1": "Confirm whether the visit is a free follow-up under the contract. If so, withdraw the consultation "
             "fee; otherwise provide the clinical reason for the new consultation.",
    "S6-F1": "Provide the clinical reason for the repeat consultation and confirm whether it is a new episode of care.",
    "S21": "Confirm the clinician's registered specialty and the consultation level billed. "
           "Re-submit the claim with the correct level if needed.",
}

_ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=11)
HEAD = ParagraphStyle("head", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=NAVY,
                    spaceBefore=10, spaceAfter=6)
TITLE = ParagraphStyle("title", parent=_ss["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=NAVY,
                       alignment=0, spaceAfter=4)


def _p(text, style=CELL):
    return Paragraph(escape(str(text)), style)


def _footer(note):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#566472"))
        canvas.drawString(15 * mm, 8 * mm, note)
        canvas.drawRightString(landscape(A4)[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def build_provider_report(res, provider, respond_days=7, flag_names=None, period=None,
                          footer_note="Prototype report generated from synthetic data. "
                                      "Flags are indicators for review, not findings of fraud."):
    flag_names = flag_names or {}
    df = res[res.billing_provider == provider].sort_values(["flag_id", "date_of_service", "claim_id"]).reset_index(drop=True)
    today = date.today()
    deadline = today + timedelta(days=int(respond_days))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm, title=f"Provider review report - {provider}")
    s = [Paragraph("Provider Review Report", TITLE),
         Paragraph(f"<b>Provider:</b> {escape(str(provider))} &nbsp;&nbsp; <b>Report date:</b> {today:%d %b %Y} "
                   f"&nbsp;&nbsp; <b>Please respond by:</b> {deadline:%d %b %Y}"
                   + (f"<br/><b>Period (date of service):</b> {period[0]:%d %b %Y} to {period[1]:%d %b %Y}"
                      if period else ""), BODY),
         Spacer(1, 4),
         Paragraph("The claims below were selected by our automated review rules for further checking. "
                   "A flag is an indicator only and does not mean that any wrongdoing occurred. "
                   "Please review each case and send the requested information.", BODY)]

    # ---- Summary per flag
    s.append(Paragraph("Summary", H2))
    uniq_amount = df.drop_duplicates("claim_id").amount.sum()
    rows = [[_p("Flag", HEAD), _p("Description", HEAD), _p("Cases", HEAD), _p("Amount", HEAD)]]
    for fid, g in df.groupby("flag_id"):
        rows.append([_p(fid), _p(flag_names.get(fid, fid)), _p(len(g)), _p(f"{g.amount.sum():,.0f}")])
    rows.append([_p("Total", HEAD), _p(f"{df.claim_id.nunique()} distinct claims", HEAD), _p(len(df), HEAD),
                 _p(f"{uniq_amount:,.0f}", HEAD)])
    t = Table(rows, colWidths=[25 * mm, 150 * mm, 25 * mm, 35 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("BACKGROUND", (0, -1), (-1, -1), TEAL),
                           ("GRID", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT])]))
    s.append(t)

    # ---- What we need from the provider
    s.append(Paragraph("What we need from you", H2))
    need = [[_p("Flag", HEAD), _p("Requested action", HEAD)]]
    for fid in sorted(df.flag_id.unique()):
        need.append([_p(f"{fid}\n{flag_names.get(fid, '')}"), _p(REQUESTED.get(fid, "Please review and respond."))])
    t = Table(need, colWidths=[75 * mm, 160 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]))
    s.append(t)

    # ---- Detailed case table
    s.append(Paragraph("Cases (sorted by flag, then date of service)", H2))
    head = ["#", "Claim ID", "Member", "Date", "Procedure", "Amount", "Flag", "Why it was flagged"]
    data = [[_p(h, HEAD) for h in head]]
    for i, r in df.iterrows():
        data.append([_p(i + 1), _p(r.claim_id), _p(r.life_code), _p(r.date_of_service), _p(r.procedure_code),
                     _p(f"{r.amount:,.0f}"), _p(r.flag_id), _p(r.evidence)])
    t = Table(data, colWidths=[8 * mm, 24 * mm, 22 * mm, 24 * mm, 22 * mm, 22 * mm, 20 * mm, 125 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]))
    s.append(t)

    doc.build(s, onFirstPage=_footer(footer_note), onLaterPages=_footer(footer_note))
    return buf.getvalue()
