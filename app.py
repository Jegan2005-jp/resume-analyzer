from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

from werkzeug.utils import secure_filename
import os
import io
import re
from typing import Dict, Any, List, Tuple, Optional

from PyPDF2 import PdfReader
from docx import Document


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "docx"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

LAST_ANALYSIS: Optional[Dict[str, Any]] = None


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(file_stream: io.BytesIO) -> str:
    reader = PdfReader(file_stream)
    text_parts: List[str] = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def extract_text_from_docx(file_stream: io.BytesIO) -> str:
    document = Document(file_stream)
    paragraphs = [p.text for p in document.paragraphs]
    return "\n".join(paragraphs)


def clean_text(text: str) -> str:
    # Basic normalization for analysis
    text = text.replace("\u00ef\u00bf\u00bd", " ")  # common bad char replacement
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def infer_domain(lower: str) -> str:
    """
    Heuristic domain detection: pick the best-matching domain from resume content.
    Supports AI/Data, Web, Cloud/DevOps, Product, Marketing, Finance, Design, QA, Security, Mobile, etc.
    """
    domains_keywords: Dict[str, set] = {
        "ai_data": {
            "machine learning", "data science", "data scientist", "data analyst",
            "analytics", "regression", "classification", "pandas", "numpy",
            "scikit-learn", "tensorflow", "pytorch", "nlp", "computer vision",
            "deep learning", "neural network", "statistics", "visualization",
        },
        "web_fullstack": {
            "frontend", "backend", "full stack", "react", "angular", "vue",
            "javascript", "typescript", "html", "css", "node", "express",
            "django", "flask", "spring boot", "rest api", "responsive",
        },
        "cloud_devops": {
            "devops", "cloud engineer", "site reliability", "sre", "aws",
            "azure", "gcp", "kubernetes", "docker", "terraform", "ci/cd",
            "pipeline", "jenkins", "ansible", "monitoring",
        },
        "product_management": {
            "product manager", "product owner", "roadmap", "backlog",
            "agile", "scrum", "jira", "user story", "stakeholder",
            "prioritization", "product strategy", "go-to-market",
        },
        "marketing_digital": {
            "marketing", "digital marketing", "seo", "sem", "content",
            "social media", "campaign", "brand", "analytics", "crm",
            "growth", "conversion", "email marketing", "ppc",
        },
        "finance_accounting": {
            "finance", "accounting", "financial", "budget", "forecast",
            "reconciliation", "gaap", "audit", "tax", "treasury",
            "investment", "risk", "compliance", "cfa", "cpa",
        },
        "design_ux": {
            "ux design", "ui design", "user experience", "figma", "sketch",
            "wireframe", "prototype", "design system", "usability",
            "user research", "interaction design", "adobe xd",
        },
        "qa_testing": {
            "qa", "quality assurance", "testing", "test automation",
            "selenium", "junit", "pytest", "manual testing", "bug",
            "test case", "regression", "performance testing",
        },
        "cybersecurity": {
            "security", "cybersecurity", "penetration testing", "soc",
            "siem", "firewall", "encryption", "vulnerability", "compliance",
            "gdpr", "iso 27001", "incident response",
        },
        "mobile": {
            "android", "ios", "mobile app", "kotlin", "swift",
            "react native", "flutter", "mobile development",
        },
        "embedded_systems": {
            "embedded", "microcontroller", "arduino", "raspberry",
            "c/c++", "rtos", "iot", "firmware", "hardware",
        },
        "project_management": {
            "project manager", "pmp", "prince2", "waterfall", "agile",
            "timeline", "resource", "delivery", "scope", "pmbok",
        },
        "hr_talent": {
            "recruitment", "talent", "hr", "human resources", "hiring",
            "onboarding", "l&d", "learning and development", "workday",
        },
        "sales_business": {
            "sales", "business development", "b2b", "b2c", "revenue",
            "pipeline", "client", "account", "negotiation", "crm",
        },
    }

    def score_domain(keywords: set) -> int:
        return sum(1 for kw in keywords if kw in lower)

    scores = {d: score_domain(kw) for d, kw in domains_keywords.items()}
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "general"


def get_roles_and_skills_for_domain(
    detected_domain: str, seniority: str, score: float
) -> Tuple[List[str], List[str]]:
    """
    Return (suggested_roles, important_skills) for the detected domain.
    Roles are ordered best-fit (top) to lower-fit (low). Score 0–100 decides how many roles to suggest.
    """
    seniority_suffix = " – " + seniority if seniority and seniority != "Early Career" else " (Entry / Early)"

    # Each list: top = best fit for high score, bottom = safer / entry for low score (8–10 roles per domain)
    role_templates: Dict[str, Tuple[List[str], List[str]]] = {
        "ai_data": (
            [
                "Data Scientist",
                "Machine Learning Engineer",
                "AI / ML Engineer",
                "Research Scientist – ML",
                "Data Analyst",
                "Business Intelligence Analyst",
                "Analytics Engineer",
                "Data Engineer",
            ],
            ["Python", "SQL", "Pandas", "NumPy", "Scikit-learn", "Data Visualization", "Model Evaluation", "Cloud (AWS/Azure/GCP)"],
        ),
        "web_fullstack": (
            [
                "Senior Full Stack Developer",
                "Full Stack Developer",
                "Frontend Developer",
                "Backend Developer",
                "Web Developer",
                "Software Engineer – Web",
                "UI Developer",
                "Application Developer",
            ],
            ["HTML", "CSS", "JavaScript", "React or Angular or Vue", "REST APIs", "Git", "Responsive Design"],
        ),
        "cloud_devops": (
            [
                "Principal DevOps Engineer",
                "DevOps Engineer",
                "Cloud Engineer",
                "Site Reliability Engineer (SRE)",
                "Platform Engineer",
                "Infrastructure Engineer",
                "Cloud Solutions Architect",
                "Release Engineer",
            ],
            ["AWS/Azure/GCP", "Linux", "Docker", "Kubernetes", "CI/CD", "Infrastructure as Code", "Monitoring & Logging"],
        ),
        "product_management": (
            [
                "Senior Product Manager",
                "Product Manager",
                "Technical Product Manager",
                "Product Owner",
                "Associate Product Manager",
                "Product Analyst",
                "Growth Product Manager",
            ],
            ["Roadmap", "Agile/Scrum", "Stakeholder Management", "Data-Driven Decisions", "Jira", "User Stories"],
        ),
        "marketing_digital": (
            [
                "Head of Growth",
                "Growth Marketing Manager",
                "Digital Marketing Manager",
                "Digital Marketing Specialist",
                "Marketing Analyst",
                "Content Marketing Specialist",
                "SEO/SEM Specialist",
                "Brand Manager",
            ],
            ["SEO/SEM", "Analytics", "Content Strategy", "Campaign Management", "CRM", "Social Media"],
        ),
        "finance_accounting": (
            [
                "Senior Financial Analyst",
                "Financial Analyst",
                "Senior Accountant",
                "Accountant",
                "Audit Associate",
                "Treasury Analyst",
                "Financial Planning Analyst",
            ],
            ["Financial Modeling", "GAAP", "Excel", "ERP", "Reconciliation", "Compliance"],
        ),
        "design_ux": (
            [
                "Lead Product Designer",
                "Product Designer",
                "UX Designer",
                "UI Designer",
                "UX Researcher",
                "Interaction Designer",
                "Visual Designer",
            ],
            ["Figma", "Wireframing", "Prototyping", "User Research", "Design Systems", "Accessibility"],
        ),
        "qa_testing": (
            [
                "Staff SDET",
                "SDET",
                "QA Engineer",
                "Test Engineer",
                "Quality Assurance Analyst",
                "Automation Engineer",
                "Manual QA Analyst",
            ],
            ["Test Automation", "Selenium", "API Testing", "Manual Testing", "Bug Tracking", "CI/CD"],
        ),
        "cybersecurity": (
            [
                "Senior Cybersecurity Engineer",
                "Cybersecurity Engineer",
                "Security Analyst",
                "SOC Analyst",
                "Penetration Tester",
                "Security Consultant",
                "Compliance Analyst",
            ],
            ["SIEM", "Incident Response", "Vulnerability Assessment", "Compliance", "Network Security"],
        ),
        "mobile": (
            [
                "Senior Mobile Developer",
                "Mobile App Developer",
                "Android Developer",
                "iOS Developer",
                "Cross-Platform Developer (Flutter/React Native)",
                "Mobile Engineer",
            ],
            ["Kotlin/Java or Swift", "React Native or Flutter", "REST APIs", "App Store", "UI/UX for Mobile"],
        ),
        "embedded_systems": (
            [
                "Senior Embedded Engineer",
                "Embedded Software Engineer",
                "Firmware Engineer",
                "IoT Engineer",
                "Systems Software Engineer",
            ],
            ["C/C++", "RTOS", "Microcontrollers", "Hardware Interfaces", "Debugging"],
        ),
        "project_management": (
            [
                "Senior Program Manager",
                "Program Manager",
                "Project Manager",
                "Delivery Manager",
                "Technical Project Manager",
                "Scrum Master",
            ],
            ["Agile/Scrum", "Stakeholder Management", "Risk Management", "Jira", "Timeline & Budget"],
        ),
        "hr_talent": (
            [
                "HR Manager",
                "Talent Acquisition Lead",
                "Talent Acquisition Specialist",
                "HR Business Partner",
                "HR Specialist",
                "L&D Specialist",
                "Recruiter",
            ],
            ["Recruitment", "ATS", "Onboarding", "HRIS", "Employee Engagement"],
        ),
        "sales_business": (
            [
                "Senior Account Executive",
                "Account Executive",
                "Business Development Representative",
                "Sales Representative",
                "Sales Development Representative",
                "Partnership Manager",
            ],
            ["CRM", "Pipeline Management", "Negotiation", "Client Relationship", "Revenue Targets"],
        ),
    }

    base_roles, important_skills = role_templates.get(
        detected_domain,
        (
            ["General Professional", "Analyst", "Specialist", "Coordinator", "Associate"],
            ["Communication", "Problem Solving", "Relevant Tools", "Domain Knowledge", "Metrics & Impact"],
        ),
    )

    # Score 0–100: how many roles to suggest (more score = more roles, top to low range)
    if score >= 90:
        count = min(8, len(base_roles))
    elif score >= 80:
        count = min(6, len(base_roles))
    elif score >= 70:
        count = min(5, len(base_roles))
    elif score >= 60:
        count = min(4, len(base_roles))
    elif score >= 50:
        count = min(3, len(base_roles))
    else:
        count = min(2, len(base_roles))

    # Slice top-to-low: first role = best fit for this score band, last = safer/entry
    selected_base = base_roles[:count]
    selected_roles = [r + seniority_suffix for r in selected_base]
    return selected_roles, important_skills


def infer_seniority(lower: str) -> str:
    """
    Rough seniority inference from wording.
    """
    if any(w in lower for w in ["intern", "trainee", "fresher"]):
        return "Entry / Intern"
    if "junior" in lower or "graduate" in lower:
        return "Junior"
    if any(w in lower for w in ["senior", "sr.", "sr "]):
        return "Senior"
    if any(w in lower for w in ["lead", "principal"]):
        return "Lead"
    if any(w in lower for w in ["manager", "head of", "director"]):
        return "Manager / Director"
    # Default for generic resumes without explicit titles
    return "Early Career"


def analyse_resume(text: str) -> Dict[str, Any]:
    """
    Heuristic TALENTX-style ATS analysis and scoring.
    """
    original_text = text
    text = clean_text(text)
    lower = text.lower()

    # All-domain keyword union for fair scoring across any role
    all_domain_keywords: set = set()
    for kw_set in (
        {"python", "sql", "machine learning", "data analysis", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch"},
        {"html", "css", "javascript", "react", "angular", "vue", "node", "express", "flask", "django", "rest api", "full stack"},
        {"aws", "azure", "gcp", "cloud", "docker", "kubernetes", "devops", "terraform", "ci/cd"},
        {"product", "roadmap", "agile", "scrum", "stakeholder", "jira"},
        {"marketing", "seo", "campaign", "analytics", "crm", "content"},
        {"finance", "accounting", "budget", "forecast", "gaap", "audit"},
        {"ux", "ui", "figma", "design", "wireframe", "prototype"},
        {"qa", "testing", "selenium", "test automation", "quality"},
        {"security", "cybersecurity", "encryption", "compliance"},
        {"android", "ios", "mobile", "flutter", "react native"},
        {"embedded", "iot", "firmware", "c++", "microcontroller"},
        {"project", "pmp", "delivery", "timeline"},
        {"hr", "recruitment", "talent", "hiring"},
        {"sales", "business development", "b2b", "revenue", "client"},
    ):
        all_domain_keywords |= kw_set

    action_verbs = {
        "developed", "built", "designed", "led", "managed", "implemented",
        "optimized", "improved", "created", "delivered", "deployed", "architected",
        "analysed", "analyzed", "collaborated", "owned"
    }

    # Content relevance: based on broad keyword coverage (any role)
    base_hits = sum(1 for kw in all_domain_keywords if kw in lower)
    content_relevance_score = min(40, base_hits * 2)

    # Domain / specialization auto-detection (all roles)
    detected_domain = infer_domain(lower)
    seniority = infer_seniority(lower)

    # Domain-specific keywords for keyword optimization
    specialization_keywords_map = {
        "ai_data": all_domain_keywords,  # keep broad for scoring
        "web_fullstack": all_domain_keywords,
        "cloud_devops": all_domain_keywords,
        "product_management": all_domain_keywords,
        "marketing_digital": all_domain_keywords,
        "finance_accounting": all_domain_keywords,
        "design_ux": all_domain_keywords,
        "qa_testing": all_domain_keywords,
        "cybersecurity": all_domain_keywords,
        "mobile": all_domain_keywords,
        "embedded_systems": all_domain_keywords,
        "project_management": all_domain_keywords,
        "hr_talent": all_domain_keywords,
        "sales_business": all_domain_keywords,
        "general": all_domain_keywords,
    }
    spec_keywords = specialization_keywords_map.get(detected_domain, all_domain_keywords)
    spec_hits = sum(1 for kw in spec_keywords if kw in lower)
    keyword_optimization_score = min(30, spec_hits * 1.5)

    # Structural integrity: heuristic – penalize very short or very long resumes
    word_count = max(1, len(text.split()))
    page_estimate = word_count / 550.0  # rough pages based on words
    structural_score = 20
    if word_count < 150:
        structural_score -= 6
    if page_estimate > 3:
        structural_score -= 4

    # STAR / impact score: based on action verbs and numbers
    verb_hits = sum(len(re.findall(rf"\b{re.escape(v)}\b", lower)) for v in action_verbs)
    number_hits = len(re.findall(r"\b\d+(\.\d+)?%?", original_text))
    star_score = min(10, verb_hits + number_hits * 0.5)

    total_score = round(content_relevance_score +
                        keyword_optimization_score +
                        structural_score +
                        star_score, 1)

    # Impact density: metrics per 100 words
    impact_density = round((number_hits / word_count) * 100, 2)

    # Classification level
    if total_score >= 90:
        market_level = "Elite Tier"
    elif total_score >= 80:
        market_level = "Highly Competitive"
    elif total_score >= 65:
        market_level = "Competitive"
    else:
        market_level = "Below Market"

    # Career mapping gate
    allow_career_mapping = total_score >= 80

    # Roles and skills based on detected domain (all roles from resume)
    roles, important_skills_all = get_roles_and_skills_for_domain(detected_domain, seniority, total_score)

    # Human-readable score band for role range (0–100)
    if total_score >= 90:
        roles_score_band = "Score 90–100: Top roles (best fit → lower fit)"
    elif total_score >= 80:
        roles_score_band = "Score 80–89: Strong fit roles (top → low)"
    elif total_score >= 70:
        roles_score_band = "Score 70–79: Good fit range (top → low)"
    elif total_score >= 60:
        roles_score_band = "Score 60–69: Moderate fit (top → low)"
    elif total_score >= 50:
        roles_score_band = "Score 50–59: Entry-strong roles (top → low)"
    else:
        roles_score_band = "Score 0–49: Safer / entry roles (top → low)"

    # Split important skills into ones detected in the resume vs missing
    present_skills = [s for s in important_skills_all if s.lower() in lower]
    missing_skills = [s for s in important_skills_all if s.lower() not in lower]

    # Optimization vs career-mapping payloads

    if allow_career_mapping:
        mode = "career_mapping"
        optimization_blueprint: Dict[str, Any] = {}
    else:
        mode = "optimization"
        optimization_blueprint = {
            "recommended_actions": [
                "Strengthen domain-specific keywords and tools for your detected domain.",
                "Add more quantified outcomes (numbers, percentages, ranges) to project and experience bullets.",
                "Standardize structure with clear sections (Summary, Skills, Experience, Projects, Education).",
            ],
            "missing_important_skills": missing_skills,
        }

    # Simple ethical AI & readiness heuristics
    has_dob = bool(re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", original_text))
    has_gender_terms = any(g in lower for g in ["male", "female"])
    has_photo_hint = any(w in lower for w in ["photo", "photograph", "passport size"])

    diversity_score = 100
    if has_dob:
        diversity_score -= 10
    if has_gender_terms:
        diversity_score -= 10
    if has_photo_hint:
        diversity_score -= 5

    if market_level in ("Elite Tier", "Highly Competitive"):
        readiness_level = "International Ready"
    elif market_level == "Competitive":
        readiness_level = "Regional Competitive"
    else:
        readiness_level = "Domestic Only"

    return {
        "score": total_score,
        "breakdown": {
            "content_relevance": round(content_relevance_score, 1),
            "keyword_optimization": round(keyword_optimization_score, 1),
            "structural_integrity": round(structural_score, 1),
            "star_impact": round(star_score, 1),
        },
        "impact_density_per_100_words": impact_density,
        "market_competitiveness": market_level,
        "mode": mode,
        "allow_career_mapping": allow_career_mapping,
        "detected_domain": detected_domain,
        "seniority_level": seniority,
        "suggested_roles": roles,
        "roles_score_band": roles_score_band,
        "important_skills": present_skills,
        "missing_important_skills": missing_skills,
        "optimization_blueprint": optimization_blueprint,
        "diversity_inclusion_score": diversity_score,
        "global_hiring_readiness": readiness_level,
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    global LAST_ANALYSIS
    if "resume" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["resume"]

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type"}), 400

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower()

    # Read into memory for parsing
    file_bytes = io.BytesIO(file.read())

    try:
        if ext == "pdf":
            text = extract_text_from_pdf(file_bytes)
        elif ext == "docx":
            text = extract_text_from_docx(file_bytes)
        else:
            return jsonify({"error": "Unsupported file type"}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {e}"}), 500

    if not text.strip():
        return jsonify({"error": "Could not extract any text from the file."}), 400

    result = analyse_resume(text)
    LAST_ANALYSIS = result
    return jsonify(result)


@app.route("/chat", methods=["POST"])
def chat():
    """
    Lightweight AI-style coach that answers questions based on
    the latest analysed resume and ATS scores.
    """
    global LAST_ANALYSIS
    if LAST_ANALYSIS is None:
        return jsonify({"error": "Please upload and analyse a resume first."}), 400

    if not request.is_json:
        return jsonify({"error": "Expected JSON payload."}), 400

    data = request.get_json(silent=True) or {}
    message_raw = data.get("message", "")
    if not isinstance(message_raw, str) or not message_raw.strip():
        return jsonify({"error": "Message is required."}), 400

    message = message_raw.lower()
    analysis = LAST_ANALYSIS

    score = analysis.get("score", 0)
    breakdown = analysis.get("breakdown", {})
    detected_domain = analysis.get("detected_domain", "ai_data")
    seniority = analysis.get("seniority_level", "Early Career")
    mode = analysis.get("mode", "optimization")
    important_skills = analysis.get("important_skills", [])
    missing_skills = analysis.get("missing_important_skills", [])
    blueprint = analysis.get("optimization_blueprint", {}) or {}

    parts: list[str] = []

    # Domain label (all roles)
    DOMAIN_LABELS = {
        "ai_data": "AI / Data Science",
        "web_fullstack": "Web / Full Stack",
        "cloud_devops": "Cloud / DevOps",
        "product_management": "Product Management",
        "marketing_digital": "Marketing / Digital",
        "finance_accounting": "Finance / Accounting",
        "design_ux": "Design / UX",
        "qa_testing": "QA / Testing",
        "cybersecurity": "Cybersecurity",
        "mobile": "Mobile Development",
        "embedded_systems": "Embedded / IoT",
        "project_management": "Project Management",
        "hr_talent": "HR / Talent",
        "sales_business": "Sales / Business Development",
        "general": "General / Cross-functional",
    }
    domain_label = DOMAIN_LABELS.get(detected_domain, detected_domain.replace("_", " ").title())

    # Improve score / reach 80+
    if any(k in message for k in ["improve", "80", "ats", "score", "boost"]):
        parts.append(
            f"Your current ATS score is {score}/100 for a {domain_label} profile at {seniority} level."
        )
        cr = breakdown.get("content_relevance", 0)
        ko = breakdown.get("keyword_optimization", 0)
        st = breakdown.get("structural_integrity", 0)
        si = breakdown.get("star_impact", 0)
        parts.append(
            "To move above 80, focus on three areas:\n"
            f"- Content relevance: currently {cr}/40 – add more domain-specific projects and responsibilities.\n"
            f"- Keyword optimization: currently {ko}/30 – explicitly mention core tools and platforms used in this domain.\n"
            f"- STAR impact: currently {si}/10 – rewrite bullets with quantified impact (numbers, % improvements, ranges)."
        )
        if missing_skills:
            parts.append(
                "Add at least 2–3 of these missing core skills into real projects and your resume: "
                + ", ".join(missing_skills)
                + "."
            )
        recs = blueprint.get("recommended_actions") or []
        if recs:
            parts.append("High-impact actions based on your last analysis:")
            for r in recs:
                parts.append(f"- {r}")

    # Skills / learning plan
    elif any(k in message for k in ["skill", "learn", "upskill", "course"]):
        parts.append(
            f"For a {domain_label} path at {seniority} level, core skills to deepen are:"
        )
        if important_skills:
            parts.append("- Core stack: " + ", ".join(important_skills) + ".")
        if missing_skills:
            parts.append(
                "- Priority gaps to close: " + ", ".join(missing_skills) + "."
            )
        parts.append(
            "Use a three-step plan: 1) complete 1–2 structured courses, 2) build at least two end-to-end projects using these tools, "
            "3) publish code and summarize outcomes with metrics on your resume."
        )

    # Role / career questions
    elif any(k in message for k in ["role", "job", "career", "position"]):
        roles = analysis.get("suggested_roles", [])
        if mode == "career_mapping" and roles:
            parts.append(
                "Based on your profile and score, you are best aligned to these global roles:"
            )
            for r in roles:
                parts.append(f"- {r}")
        else:
            parts.append(
                "Career mapping is currently locked because your ATS score is below 80."
            )
            if roles := analysis.get("suggested_roles", []):
                parts.append(
                    "Once you cross 80, these roles will be realistic entry points:"
                )
                for r in roles:
                    parts.append(f"- {r}")
        parts.append(
            "Focus on one target title first and align your projects, skills, and keywords directly to typical job descriptions for that role."
        )

    # Resume structure / format questions
    elif any(k in message for k in ["resume", "format", "structure", "section"]):
        st = breakdown.get("structural_integrity", 0)
        parts.append(
            f"Your structural integrity score is {st}/20. Aim for a clean one-page layout with clear sections and no tables or graphics."
        )
        parts.append(
            "Use this section order: Summary, Skills, Experience, Projects, Education, Certifications. "
            "Keep bullets short, action-led, and make sure each role or project has dates and location."
        )

    # Default guidance
    else:
        parts.append(
            f"Detected profile: {domain_label}, {seniority} level, ATS score {score}/100."
        )
        if mode == "career_mapping":
            parts.append(
                "You are already above 80 – focus on deepening domain expertise and adding more measurable impact to move towards elite tier."
            )
        else:
            parts.append(
                "You are below 80 – prioritize closing core skill gaps and rewriting bullets with STAR-style impact before applying widely."
            )
        if missing_skills:
            parts.append(
                "Start with these missing skills: " + ", ".join(missing_skills) + "."
            )

    answer = "\n".join(parts)
    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

