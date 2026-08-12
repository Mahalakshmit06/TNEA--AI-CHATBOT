from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import pandas as pd
import sqlite3
import re
import unicodedata

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "Final_TNEA_dataset.csv"
DB_PATH = BASE_DIR / "campus_ai.db"

app = FastAPI(
    title="Campus AI - TNEA Counselling Recommendation System",
    version="2.0.0",
)

# Local development + Vercel. In production, set CORS_ORIGINS to a comma-separated list.
origins = [x.strip() for x in __import__("os").getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

COMMUNITIES = ["OC", "BC", "BCM", "MBC", "SC", "SCA", "ST"]

BRANCH_ALIASES = {
    "cse": "COMPUTER SCIENCE AND ENGINEERING",
    "cs": "COMPUTER SCIENCE AND ENGINEERING",
    "computer science": "COMPUTER SCIENCE AND ENGINEERING",
    "ece": "ELECTRONICS AND COMMUNICATION ENGINEERING",
    "ec": "ELECTRONICS AND COMMUNICATION ENGINEERING",
    "eee": "ELECTRICAL AND ELECTRONICS ENGINEERING",
    "it": "INFORMATION TECHNOLOGY",
    "information technology": "INFORMATION TECHNOLOGY",
    "ai ds": "Artificial Intelligence and Data Science",
    "aids": "Artificial Intelligence and Data Science",
    "ai&ds": "Artificial Intelligence and Data Science",
    "ai and ds": "Artificial Intelligence and Data Science",
    "ai ml": "Artificial Intelligence and Machine Learning",
    "aiml": "Artificial Intelligence and Machine Learning",
    "ai and ml": "Artificial Intelligence and Machine Learning",
    "cyber security": "Computer Science and Engineering (Cyber Security)",
    "cyber": "Computer Science and Engineering (Cyber Security)",
    "mech": "MECHANICAL ENGINEERING",
    "mechanical": "MECHANICAL ENGINEERING",
    "civil": "CIVIL ENGINEERING",
    "aero": "AERONAUTICAL ENGINEERING",
    "aeronautical": "AERONAUTICAL ENGINEERING",
    "biotech": "BIO TECHNOLOGY",
    "biotechnology": "BIO TECHNOLOGY",
    "biomedical": "BIO MEDICAL ENGINEERING",
    "bme": "BIO MEDICAL ENGINEERING",
    "mechatronics": "Mechatronics Engineering",
    "robotics": "ROBOTICS AND AUTOMATION",
    "chemical": "CHEMICAL ENGINEERING",
    "vlsi": "Electronics Engineering (VLSI Design and Technology)",
    "ece vlsi": "Electronics Engineering (VLSI Design and Technology)",
}

DISTRICT_ALIASES = {
    "madras": "CHENNAI",
    "chennai city": "CHENNAI",
    "kovai": "COIMBATORE",
    "coimbatore city": "COIMBATORE",
    "trichy": "TIRUCHIRAPPALLI",
    "tiruchirapalli": "TIRUCHIRAPPALLI",
    "nellai": "TIRUNELVELI",
    "tuticorin": "THOOTHUKUDI",
    "thoothukudi": "THOOTHUKUDI",
    "tanjore": "THANJAVUR",
}

STOPWORDS = {
    "college", "colleges", "engineering", "engg", "branch", "branches",
    "course", "courses", "in", "at", "the", "for", "with", "my",
    "cutoff", "mark", "marks", "show", "suggest", "find", "which",
    "can", "i", "get", "give", "me", "is", "are", "offer", "offers",
    "good", "best", "near", "nearby", "district"
}


def clean_text(value):
    if value is None or pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", " ", value)


def norm(value):
    s = clean_text(value).upper()
    s = re.sub(r"[^A-Z0-9&]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_district(value):
    n = norm(value)
    n = re.sub(r"\s+(FR|F)$", "", n)
    if n in {"", "637018"}:
        return "UNKNOWN"
    if n in {norm(k): v for k, v in DISTRICT_ALIASES.items()}:
        return {norm(k): v for k, v in DISTRICT_ALIASES.items()}[n]
    return n


def normalize_branch(value):
    text = clean_text(value)
    n = norm(text)
    for alias, target in BRANCH_ALIASES.items():
        if n == norm(alias):
            return target
    return text


# Load and normalize the supplied dataset once at startup.
df = pd.read_csv(DATA_PATH)
df["DistrictClean"] = df["District"].apply(normalize_district)
df["BranchClean"] = df["Branch Name"].apply(normalize_branch)
df["CollegeClean"] = df["College Name"].apply(clean_text)
for community in COMMUNITIES:
    df[community] = pd.to_numeric(df[community], errors="coerce")


def db_connection():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    con = db_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_key TEXT NOT NULL,
            name TEXT NOT NULL,
            community TEXT,
            cutoff REAL,
            district TEXT,
            branch TEXT,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    columns = {row[1] for row in con.execute("PRAGMA table_info(chat_history)").fetchall()}
    for column, sql_type in (("district", "TEXT"), ("branch", "TEXT")):
        if column not in columns:
            con.execute(f"ALTER TABLE chat_history ADD COLUMN {column} {sql_type}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chat_profile ON chat_history(profile_key, id)")
    con.commit()
    con.close()


init_db()


class CutoffRequest(BaseModel):
    mathematics: float = Field(ge=0, le=100)
    physics: float = Field(ge=0, le=100)
    chemistry: float = Field(ge=0, le=100)


class RecommendRequest(BaseModel):
    name: str = "Student"
    cutoff: float = Field(ge=0, le=200)
    community: str = "OC"
    district: str = "ALL"
    branch: str = "ALL"
    limit: int = Field(default=300, ge=1, le=500)


class ChatRequest(BaseModel):
    name: str = ""
    community: Optional[str] = None
    cutoff: Optional[float] = Field(default=None, ge=0, le=200)
    district: Optional[str] = None
    branch: Optional[str] = None
    message: str = Field(min_length=1, max_length=1200)


def profile_key(name, community, cutoff):
    return f"{norm(name)}|{norm(community or '')}|{round(float(cutoff), 1) if cutoff is not None else ''}"


def save_message(profile, role, message):
    con = db_connection()
    con.execute(
        """INSERT INTO chat_history
        (profile_key,name,community,cutoff,district,branch,role,message)
        VALUES (?,?,?,?,?,?,?,?)""",
        (
            profile_key(profile.get("name", ""), profile.get("community"), profile.get("cutoff")),
            profile.get("name", "Student"), profile.get("community"), profile.get("cutoff"),
            profile.get("district"), profile.get("branch"), role, message,
        ),
    )
    con.commit()
    con.close()


def get_history(profile):
    key = profile_key(profile.get("name", ""), profile.get("community"), profile.get("cutoff"))
    con = db_connection()
    rows = con.execute(
        "SELECT role,message,created_at FROM chat_history WHERE profile_key=? ORDER BY id DESC LIMIT 60",
        (key,),
    ).fetchall()
    con.close()
    rows.reverse()
    return [{"role": r[0], "message": r[1], "created_at": r[2]} for r in rows]


def extract_cutoff(text):
    patterns = [
        r"(?:cutoff|cut off|score|mark|marks)\s*(?:is|of|=|:)?\s*(\d{2,3}(?:\.\d+)?)",
        r"\b(\d{2,3}(?:\.\d+)?)\s*(?:cutoff|cut off|marks?)\b",
        r"\b(?:between|from)\s*(\d{2,3}(?:\.\d+)?)\s*(?:to|and|-)\s*(\d{2,3}(?:\.\d+)?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = float(match.group(1))
            if 0 <= value <= 200:
                return value
    return None


def extract_cutoff_range(text):
    match = re.search(r"\b(\d{2,3}(?:\.\d+)?)\s*(?:to|-|–)\s*(\d{2,3}(?:\.\d+)?)\b", text, re.I)
    if match:
        a, b = float(match.group(1)), float(match.group(2))
        if 0 <= a <= 200 and 0 <= b <= 200:
            return min(a, b), max(a, b)
    return None


def detect_community(text):
    n = norm(text)
    for community in COMMUNITIES:
        if re.search(rf"\b{re.escape(community)}\b", n):
            return community
    aliases = {
        "GENERAL": "OC", "OPEN": "OC", "OPEN CATEGORY": "OC",
        "GENERAL CATEGORY": "OC", "MBC DNC": "MBC", "MBC DNC CATEGORY": "MBC",
    }
    for alias, community in aliases.items():
        if alias in n:
            return community
    return None


def detect_district(text):
    n = norm(text)
    if re.search(r"\b(ALL|ANY|ANYWHERE)\s+(DISTRICTS?|DISTRICT)\b", n) or "ANY DISTRICT" in n:
        return "ALL"
    for alias, district in sorted(DISTRICT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if norm(alias) in n:
            return district
    districts = sorted([x for x in df["DistrictClean"].dropna().unique() if x != "UNKNOWN"], key=len, reverse=True)
    for district in districts:
        if re.search(rf"\b{re.escape(district)}\b", n):
            return district
    return None


def detect_branch(text):
    n = norm(text)
    if re.search(r"\b(ALL|ANY)\s+BRANCH(?:ES)?\b", n):
        return "ALL"
    for alias, target in sorted(BRANCH_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        a = norm(alias)
        if re.search(rf"(?<![A-Z0-9]){re.escape(a)}(?![A-Z0-9])", n):
            return target
    branches = sorted(df["BranchClean"].dropna().unique(), key=len, reverse=True)
    for branch in branches:
        bn = norm(branch)
        if bn and re.search(rf"(?<![A-Z0-9]){re.escape(bn)}(?![A-Z0-9])", n):
            return branch
    return None


def is_greeting(text):
    return bool(re.search(r"\b(hi|hii|hiii|hello|hey|good morning|good afternoon|good evening)\b", text, re.I))


def recommendation_frame(cutoff, community, district="ALL", branch="ALL", college=None, min_cutoff=None):
    community = community if community in COMMUNITIES else "OC"
    work = df.copy()
    if district and district != "ALL":
        work = work[work["DistrictClean"] == normalize_district(district)]
    if branch and branch != "ALL":
        target = norm(normalize_branch(branch))
        work = work[work["BranchClean"].apply(lambda x: norm(x) == target or target in norm(x) or norm(x) in target)]
    if college:
        q = norm(college)
        work = work[work["CollegeClean"].apply(lambda x: q in norm(x))]
    work["closing"] = work[community]
    work = work[work["closing"].notna()]
    if min_cutoff is None:
        work = work[work["closing"] <= cutoff]
    else:
        work = work[(work["closing"] <= cutoff) & (work["closing"] >= min_cutoff)]
    work["margin"] = cutoff - work["closing"]
    work["status"] = work["margin"].apply(lambda x: "Strong" if x >= 10 else ("Possible" if x >= 3 else "Edge"))
    work["DistrictDisplay"] = work["DistrictClean"].replace({"UNKNOWN": "District not specified"})
    return work.sort_values(["closing", "CollegeClean"], ascending=[False, True])


def format_records(work, limit=50):
    records = []
    for _, row in work.head(limit).iterrows():
        code = row.get("College Code")
        try:
            code = int(code) if pd.notna(code) else ""
        except Exception:
            code = clean_text(code)
        records.append({
            "college_code": code,
            "college_name": row["CollegeClean"],
            "district": row.get("DistrictDisplay", row["DistrictClean"]),
            "branch": clean_text(row["Branch Name"]),
            "branch_code": clean_text(row["Branch Code"]),
            "closing_cutoff": float(row["closing"]) if pd.notna(row["closing"]) else None,
            "margin": round(float(row["margin"]), 1),
            "status": row["status"],
        })
    return records


def find_college_names(text):
    query_tokens = {t for t in norm(text).split() if t not in STOPWORDS and len(t) >= 3}
    if not query_tokens:
        return []
    candidates = []
    for name in df["CollegeClean"].dropna().unique():
        tokens = {t for t in norm(name).split() if t not in STOPWORDS and len(t) >= 3}
        overlap = len(query_tokens & tokens)
        if overlap >= 2 or (overlap == 1 and len(query_tokens) <= 2):
            score = overlap / max(1, len(tokens)) + min(overlap, 6) * 0.04
            candidates.append((score, name))
    candidates.sort(reverse=True)
    return [name for _, name in candidates[:5]]


def counselling_answer(text):
    n = norm(text)
    if any(k in n for k in ["DOCUMENT", "CERTIFICATE", "WHAT TO BRING", "NEEDED FOR COUNSELLING", "DOCUMENTS"]):
        return (
            "For counselling preparation, keep the academic, identity and category/community documents requested in your counselling instructions ready. "
            "Keep clear copies/scans where applicable, and make sure the information in your application matches the supporting documents. "
            "For the exact checklist and submission requirements, use the official TNEA instructions."
        )
    if any(k in n for k in ["COUNSELLING PROCEDURE", "HOW COUNSELLING WORKS", "COUNSELLING PROCESS", "HOW DOES TNEA", "STEPS OF COUNSELLING"]):
        return (
            "The counselling flow generally involves application/registration, verification of submitted information, rank-related processing, "
            "choice filling, processing of choices, allotment and the required joining/reporting steps. "
            "Follow the official TNEA instructions for the applicable schedule and exact rules."
        )
    if any(k in n for k in ["BEFORE COUNSELLING", "WHAT SHOULD I KNOW", "PREPARE FOR COUNSELLING", "COUNSELLING TIPS"]):
        return (
            "Before counselling, keep your cutoff and community details ready, prepare a realistic list of preferred branches and colleges, "
            "check the available options carefully, keep required documents ready, and review each choice before submitting it."
        )
    if "COMMUNITY" in n or "CATEGORY" in n:
        return (
            "Community is important because the dataset stores a separate closing-cutoff value for each community. "
            "For recommendations, select the community that matches your counselling application details."
        )
    if "CUTOFF" in n and any(k in n for k in ["WHAT", "MEAN", "CALCULATE", "FORMULA"]):
        return "The project cutoff formula is Mathematics + Physics/2 + Chemistry/2, with a maximum calculated cutoff of 200."
    if "FEE" in n or "FEES" in n:
        return "Fee information is not part of the supplied recommendation dataset, so I will not invent a fee figure. Check the official college/TNEA information for current fees."
    if "HOSTEL" in n or "TRANSPORT" in n:
        return "Hostel and transport details are not fields in the supplied recommendation dataset. For a specific college, check its official information."
    if "PLACEMENT" in n:
        return "Placement statistics are not fields in the supplied recommendation dataset. I can still recommend colleges using your cutoff, community, district and branch without inventing placement figures."
    return None


def phase(profile):
    if not clean_text(profile.get("name")):
        return "name"
    if profile.get("cutoff") is None:
        return "cutoff"
    if not profile.get("community"):
        return "community"
    if not profile.get("district"):
        return "district"
    if not profile.get("branch"):
        return "branch"
    return "ready"


def onboarding_reply(current_phase, profile):
    prompts = {
        "name": "Hello! I’m Campus AI. What’s your name?",
        "cutoff": f"Nice to meet you, {profile['name']}. What is your cutoff mark?",
        "community": "Got it. Which community should I use? Choose OC, BC, BCM, MBC, SC, SCA or ST.",
        "district": "Which district are you looking for? You can enter a district name or say “all districts”.",
        "branch": "Which branch are you interested in? You can enter CSE, ECE, EEE, IT, AI & DS or say “all branches”.",
    }
    return prompts[current_phase]


def is_name_candidate(text):
    if len(text.split()) > 5 or any(ch.isdigit() for ch in text):
        return False
    blocked = ["college", "cutoff", "community", "district", "branch", "counselling", "cse", "ece", "eee"]
    return not any(word in norm(text).split() for word in blocked)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "campus-ai"}


@app.get("/api/meta")
def meta():
    districts = sorted(x for x in df["DistrictClean"].dropna().unique() if x != "UNKNOWN")
    branches = sorted(clean_text(x) for x in df["Branch Name"].dropna().unique())
    return {
        "project": "Campus AI - TNEA Counselling Recommendation System",
        "records": int(len(df)),
        "colleges": int(df["College Name"].nunique()),
        "districts": districts,
        "branches": branches,
        "communities": COMMUNITIES,
        "formula": "Mathematics + Physics/2 + Chemistry/2",
    }


@app.post("/api/calculate-cutoff")
def calculate_cutoff(req: CutoffRequest):
    cutoff = req.mathematics + req.physics / 2 + req.chemistry / 2
    return {"cutoff": round(cutoff, 2)}


@app.post("/api/recommend")
def recommend(req: RecommendRequest):
    community = req.community.upper().strip()
    if community not in COMMUNITIES:
        raise HTTPException(400, "Please select a supported community.")
    work = recommendation_frame(req.cutoff, community, req.district, req.branch)
    records = format_records(work, req.limit)
    return {"count": len(work), "showing": len(records), "records": records, "profile": req.model_dump()}


@app.get("/api/history/{name}")
def history(name: str, community: Optional[str] = None, cutoff: Optional[float] = None):
    return {"messages": get_history({"name": name, "community": community, "cutoff": cutoff})}


@app.post("/api/chat")
def chat(req: ChatRequest):
    profile = {
        "name": clean_text(req.name),
        "cutoff": req.cutoff,
        "community": req.community.upper().strip() if req.community else None,
        "district": req.district,
        "branch": req.branch,
    }
    text = clean_text(req.message)
    save_message(profile, "user", text)

    current = phase(profile)
    detected_cutoff = extract_cutoff(text)
    detected_community = detect_community(text)
    detected_district = detect_district(text)
    detected_branch = detect_branch(text)
    records = []
    intent = "conversation"

    # Strict, one-question-at-a-time onboarding.
    if current == "name":
        if is_greeting(text):
            reply = onboarding_reply("name", profile)
        elif is_name_candidate(text):
            profile["name"] = text
            reply = onboarding_reply("cutoff", profile)
            current = "cutoff"
        else:
            reply = "Please enter your name so I can create your recommendation profile."
        save_message(profile, "assistant", reply)
        return {"reply": reply, "intent": "onboarding", "profile": profile, "detected": {}, "records": [], "history": get_history(profile)}

    if current == "cutoff":
        if detected_cutoff is None:
            standalone = re.fullmatch(r"\s*(\d{2,3}(?:\.\d+)?)\s*", text)
            if standalone:
                value = float(standalone.group(1))
                detected_cutoff = value if 0 <= value <= 200 else None
        if detected_cutoff is None:
            reply = "Please enter a valid cutoff between 0 and 200, for example 180 or 172.5."
        else:
            profile["cutoff"] = detected_cutoff
            reply = onboarding_reply("community", profile)
        save_message(profile, "assistant", reply)
        return {"reply": reply, "intent": "onboarding", "profile": profile, "detected": {"cutoff": detected_cutoff}, "records": [], "history": get_history(profile)}

    if current == "community":
        if detected_community is None:
            reply = "Please choose one of OC, BC, BCM, MBC, SC, SCA or ST."
        else:
            profile["community"] = detected_community
            reply = onboarding_reply("district", profile)
        save_message(profile, "assistant", reply)
        return {"reply": reply, "intent": "onboarding", "profile": profile, "detected": {"community": detected_community}, "records": [], "history": get_history(profile)}

    if current == "district":
        if detected_district is None:
            reply = "Please enter a district name, or say “all districts” if you want recommendations across districts."
        else:
            profile["district"] = detected_district
            reply = onboarding_reply("branch", profile)
        save_message(profile, "assistant", reply)
        return {"reply": reply, "intent": "onboarding", "profile": profile, "detected": {"district": detected_district}, "records": [], "history": get_history(profile)}

    if current == "branch":
        if detected_branch is None:
            reply = "Please enter a branch such as CSE, ECE, EEE, IT, AI & DS, or say “all branches”."
        else:
            profile["branch"] = detected_branch
            work = recommendation_frame(profile["cutoff"], profile["community"], profile["district"], profile["branch"])
            records = format_records(work, 300)
            intent = "recommendation"
            reply = (
                f"Thanks, {profile['name']}. I matched your profile using cutoff {profile['cutoff']:g}, "
                f"{profile['community']}, {profile['district'].title() if profile['district'] != 'ALL' else 'all districts'}, "
                f"and {profile['branch'] if profile['branch'] != 'ALL' else 'all branches'}. "
                f"I found {len(work)} matching college-branch records."
            )
        save_message(profile, "assistant", reply)
        return {"reply": reply, "intent": intent, "profile": profile, "detected": {"branch": detected_branch}, "records": records, "history": get_history(profile)}

    # Ready state: natural follow-up questions and fresh recommendation queries.
    if detected_cutoff is not None:
        profile["cutoff"] = detected_cutoff
    if detected_community:
        profile["community"] = detected_community
    if detected_district:
        profile["district"] = detected_district
    if detected_branch:
        profile["branch"] = detected_branch

    counselling = counselling_answer(text)
    college_names = find_college_names(text)
    range_values = extract_cutoff_range(text)
    n = norm(text)

    if is_greeting(text):
        reply = f"Hello {profile['name']}! How can I help with your college recommendation or TNEA counselling question?"
        intent = "greeting"
    elif counselling:
        reply = counselling
        intent = "counselling"
    elif "SAFE" in n:
        work = recommendation_frame(profile["cutoff"], profile["community"], profile.get("district") or "ALL", profile.get("branch") or "ALL")
        work = work[work["margin"] >= 10]
        records = format_records(work, 300)
        reply = f"Here are the stronger-margin choices from the matching records for your cutoff of {profile['cutoff']:g}."
        intent = "safe_recommendation"
    elif range_values:
        low, high = range_values
        work = recommendation_frame(high, profile["community"], profile.get("district") or "ALL", profile.get("branch") or "ALL", min_cutoff=low)
        records = format_records(work, 300)
        reply = f"Here are the matching college-branch records with community closing cutoffs from {low:g} to {high:g}."
        intent = "cutoff_range"
    elif college_names:
        college = college_names[0]
        work = recommendation_frame(profile["cutoff"], profile["community"], profile.get("district") or "ALL", profile.get("branch") or "ALL", college=college)
        records = format_records(work, 300)
        if records:
            reply = f"Here are the records for {college} that match your current profile."
        else:
            # Show the college's community records so the user gets a useful answer without falsely claiming eligibility.
            base = df[df["CollegeClean"].str.upper() == college.upper()].copy()
            if profile.get("district") and profile["district"] != "ALL":
                base = base[base["DistrictClean"] == profile["district"]]
            if profile.get("branch") and profile["branch"] != "ALL":
                target = norm(profile["branch"])
                base = base[base["BranchClean"].apply(lambda x: target in norm(x) or norm(x) in target)]
            base["closing"] = base[profile["community"]]
            base = base.dropna(subset=["closing"])
            base["margin"] = profile["cutoff"] - base["closing"]
            base["status"] = base["margin"].apply(lambda x: "Eligible range" if x >= 0 else "Above cutoff")
            base["DistrictDisplay"] = base["DistrictClean"].replace({"UNKNOWN": "District not specified"})
            records = format_records(base, 300)
            reply = f"I found {college} in the supplied college records. The table shows the community closing-cutoff records so you can compare them with your cutoff."
        intent = "college"
    elif any(k in n for k in ["COLLEGE", "COLLEGES", "BRANCH", "DISTRICT", "CSE", "ECE", "EEE", "AIDS", "AI DS", "AIML"]):
        work = recommendation_frame(profile["cutoff"], profile["community"], profile.get("district") or "ALL", profile.get("branch") or "ALL")
        records = format_records(work, 300)
        reply = f"I found {len(work)} matching college-branch records using your profile."
        intent = "recommendation"
    else:
        reply = (
            "I can recommend colleges from your profile and answer questions about cutoff, community, district, branch, "
            "specific colleges and counselling preparation. For example: “Which colleges can I get with my cutoff?”, "
            "“Which colleges offer CSE?”, or “Suggest colleges in Chennai.”"
        )
        intent = "help"

    save_message(profile, "assistant", reply)
    return {
        "reply": reply,
        "intent": intent,
        "profile": profile,
        "detected": {
            "cutoff": detected_cutoff,
            "community": detected_community,
            "district": detected_district,
            "branch": detected_branch,
        },
        "records": records,
        "history": get_history(profile),
    }
