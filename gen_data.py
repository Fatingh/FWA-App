"""Generates a SYNTHETIC claims file (data.csv). No real data is used."""
import random
from datetime import date, timedelta
import pandas as pd

random.seed(7)
GROUP = ["GRP-H01", "GRP-C02"]          # fake "hospital group" providers
OTHER = ["PRV-A10", "PRV-B20", "PRV-C30", "PRV-D40"]
rows, cid = [], 0
D0 = date(2026, 1, 1)


def add(life, prov, d, code, ptype, spec, amt):
    global cid
    cid += 1
    rows.append(dict(claim_id=f"CLM{cid:04d}", life_code=life, billing_provider=prov,
                     date_of_service=d, procedure_code=code, procedure_type=ptype,
                     clinician_specialty=spec, amount=amt))


def spec_for(code):
    pid = int(code.split(".")[0])
    return {9: random.choice(["GP", "GEN"]), 10: "Specialist", 11: "Consultant"}[pid]


def rd(): return D0 + timedelta(days=random.randint(0, 120))


# ---- Background (clean) claims: one consultation per member, no overlaps
for i in range(1, 61):
    code = random.choice(["9.01", "10.01", "11.01"])
    add(f"L{i:03d}", random.choice(OTHER + GROUP), rd(), code, "Consultation",
        spec_for(code), random.randint(150, 600))
for i in range(61, 101):
    add(f"L{i:03d}", random.choice(OTHER), rd(), random.choice(["PH10", "PH11", "PH12"]),
        "Pharmaceuticals", "GP", random.randint(20, 200))

# ---- Injected: S1 consultation + qualifying procedure, same day
for i in range(200, 205):
    d, p = rd(), random.choice(OTHER)
    add(f"L{i}", p, d, "9.01", "Consultation", "GP", 300)
    add(f"L{i}", p, d, random.choice(["P100", "P101", "P102"]), "Procedure", "GP", 450)

# ---- Injected: S2 repeated falsifying-diagnosis pharma code same day
for i in range(210, 215):
    d, p = rd(), random.choice(OTHER)
    code = random.choice(["PH01", "PH02", "PH03"])
    for _ in range(random.choice([2, 3])):
        add(f"L{i}", p, d, code, "Pharmaceuticals", "GP", 90)

# ---- Injected: S5 repeat visit within 7 days (10 for group providers)
for i, (prov, gap) in enumerate([(OTHER[0], 3), (OTHER[1], 6), (GROUP[0], 9),
                                 (GROUP[1], 5), (OTHER[2], 1)]):
    d = rd()
    add(f"L{220+i}", prov, d, "9.01", "Consultation", "GP", 300)
    add(f"L{220+i}", prov, d + timedelta(days=gap), "9.01", "Consultation", "GP", 300)

# ---- Injected: S6 repeat visit after 8-28 days (11-30 for group providers)
for i, (prov, gap) in enumerate([(OTHER[0], 14), (OTHER[3], 25), (GROUP[0], 20),
                                 (GROUP[1], 12), (OTHER[1], 9)]):
    d = rd()
    add(f"L{230+i}", prov, d, "10.01", "Consultation", "Specialist", 500)
    add(f"L{230+i}", prov, d + timedelta(days=gap), "10.01", "Consultation", "Specialist", 500)

# ---- Injected: S21 specialty upcoding
for i, (code, spec) in enumerate([("11.01", "Specialist"), ("10.01", "GP"),
                                  ("11.01", "GEN"), ("10.01", "GEN"), ("11.01", "GP")]):
    add(f"L{240+i}", random.choice(OTHER), rd(), code, "Consultation", spec, 700)

df = pd.DataFrame(rows)
df.to_csv("data.csv", index=False)
print(f"data.csv written: {len(df)} synthetic claims")
