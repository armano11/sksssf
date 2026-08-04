"""
SKSSF Letter Automation Pipeline v4
Generates official letters on the SKSSF Valachil Padavu Committee letterhead.

Letter format (matches reference letter exactly):
  [Letterhead - pre-printed]
  Date: DD/MM/YYYY
  To
  [Recipient Name]
  [Recipient Organization]
  [Body - 4 paragraphs]
  Para 1: Introduction (name, place, situation)
  Para 2: Details (hospital/institution, diagnosis/issue, treatment, expenses)
  Para 3: Financial condition (income, employment, hardship)
  Para 4: Request for assistance (templated per issue type)
  For SKSSF Valachil Padavu Unit
  [Signature]
  Ibrahim Kaleel
  G. Secretary
"""
import os
import io
import json
import datetime
from flask import Flask, request, send_file, jsonify, render_template
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
import fitz  # PyMuPDF
import requests

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PDF = os.path.join(BASE_DIR, "S36BW-826073106590.pdf")
OUTPUT_DIR = os.path.join(BASE_DIR, "generated")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Fixed recipient and signatory ──
RECIPIENT = "To\nSKSSF Sahachari\nKendra Samithi"
ORG_NAME = "SKSSF Valachil Padavu Unit"
SIG_NAME = "Ibrahim Kaleel"
SIG_DESIGNATION = "G. Secretary"

# Signature — try multiple possible filenames, skip broken/placeholder files
SIG_CANDIDATES = [
    "ibrahim_kaleel_signature.png",
    "signature_ibrahim_kaleel.png",
]
SIG_PATH = None
for candidate in SIG_CANDIDATES:
    path = os.path.join(BASE_DIR, candidate)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        SIG_PATH = path
        break

# ─────────────────────────────────────────────────────────────────────────────
# Issue types and labels
# ─────────────────────────────────────────────────────────────────────────────

ISSUE_LABELS = {
    "health": "Health / Medical",
    "financial": "Financial Assistance",
    "education": "Education",
    "marriage": "Marriage Assistance",
    "death_benefit": "Death Benefit",
    "general": "General Recommendation",
    "other": "Other (AI Custom)",
}

# ─────────────────────────────────────────────────────────────────────────────
# Para 4 — Request paragraph (templated per issue type)
# Paras 1-3 are AI-generated, para 4 is fixed per issue type
# ─────────────────────────────────────────────────────────────────────────────

REQUEST_PARAS = {
    "health": (
        "We earnestly request your esteemed office to kindly render all possible "
        "support and medical assistance to the patient and their family in this "
        "difficult time."
    ),
    "financial": (
        "We humbly request your good office to kindly extend all possible financial "
        "assistance and support to the above-mentioned individual at the earliest."
    ),
    "education": (
        "We kindly request your good office to provide the necessary educational "
        "assistance or scholarship to enable the student to pursue their studies "
        "without financial burden."
    ),
    "marriage": (
        "We humbly request your good office to kindly extend all possible "
        "post-marriage financial assistance and support to help the family "
        "recover from this difficult situation."
    ),
    "death_benefit": (
        "We humbly request your office to extend the applicable death benefit "
        "and any other form of assistance to help the family during this "
        "difficult period."
    ),
    "general": (
        "We request your kind consideration and support in the above-mentioned "
        "matter."
    ),
    "other": (
        "We humbly request your good office to kindly extend all possible "
        "assistance and support to the above-mentioned individual at the earliest."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# PDF generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_letter_pdf(data: dict) -> bytes:
    name = data.get("name", "").strip()
    relation = data.get("relation", "S/o").strip()
    guardian = data.get("guardian", "").strip()
    address = data.get("address", "").strip()
    issue_type = data.get("issue_type", "general")
    body_text = data.get("body", "").strip()
    date_str = data.get("date", datetime.date.today().strftime("%d/%m/%Y"))

    # Build the full letter body:
    # To + recipient + paras 1-3 (from body) + para 4 (templated)
    request_para = REQUEST_PARAS.get(issue_type, REQUEST_PARAS["general"])

    # If body is empty, use a placeholder
    if not body_text:
        body_text = (
            f"{name}, {relation} of {guardian if guardian else '—'}, residing at "
            f"{address if address else '—'}, is in need of assistance."
        )

    # Compose the full text that gets rendered on the PDF
    full_text = RECIPIENT + "\n\n" + body_text + "\n\n" + request_para

    # Open the original letterhead PDF as background image
    src_doc = fitz.open(TEMPLATE_PDF)
    src_page = src_doc[0]
    page_rect = src_page.rect
    W, H = page_rect.width, page_rect.height

    # Create a new PDF in memory
    out_buf = io.BytesIO()
    c = canvas.Canvas(out_buf, pagesize=(W, H))

    # ── Draw the original letterhead as background ──
    pix = src_page.get_pixmap(dpi=150)
    img_data = pix.tobytes("png")
    img_reader = ImageReader(io.BytesIO(img_data))
    c.drawImage(img_reader, 0, 0, width=W, height=H)

    # ── Date (right side, next to pre-printed "Date:" label) ──
    date_label_x = W * 0.595  # ≈ 364pt
    date_y = H - 154           # ≈ 638pt from bottom

    # White-out the old date area
    c.setFillColor(colors.white)
    c.rect(date_label_x - 2, date_y - 12, W * 0.38, 28, fill=1, stroke=0)

    # Draw clean date
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(date_label_x, date_y, f"Date: {date_str}")

    # ── Body text (To + recipient + 4 paragraphs) ──
    body_top_y = H - 185       # 185pt from top
    body_bottom_y = 195        # leave room for "For..." and signature
    left_margin = 42
    right_margin = W - 42
    body_width = right_margin - left_margin
    line_height = 14.5

    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.black)

    lines = full_text.split("\n")
    y = body_top_y
    for line in lines:
        if y < body_bottom_y:
            break
        words = line.split()
        if not words:
            # Blank line — paragraph break
            y -= line_height * 0.55
            continue
        current_line = ""
        for word in words:
            test_line = (current_line + " " + word).strip()
            if c.stringWidth(test_line, "Helvetica", 10.5) <= body_width:
                current_line = test_line
            else:
                c.drawString(left_margin, y, current_line)
                y -= line_height
                current_line = word
                if y < body_bottom_y:
                    break
        if y < body_bottom_y:
            break
        if current_line and y >= body_bottom_y:
            c.drawString(left_margin, y, current_line)
            y -= line_height

    # ── "For SKSSF Valachil Padavu Unit" — positioned dynamically after body ──
    # Place it 20pt below where the body text ended (y is already at next line position)
    for_y = y - 20
    # But don't go below 130pt from bottom (need room for signature below)
    for_y = max(for_y, 130)
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(colors.black)
    c.drawString(left_margin, for_y, f"For {ORG_NAME}")

    # ── Signature image (bottom right, on signature line) ──
    # Enlarged: 120pt wide for better visibility
    if SIG_PATH and os.path.exists(SIG_PATH):
        try:
            sig_img = ImageReader(SIG_PATH)
            sig_w = 120
            sig_h = sig_w / 2.44  # aspect-correct ≈ 49pt
            c.drawImage(sig_img, 400, 55, width=sig_w, height=sig_h, mask='auto')
        except Exception as e:
            print(f"Signature overlay warning: {e}")

    # ── Name and designation (below signature, right side) ──
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.black)
    c.drawString(400, 40, SIG_NAME)
    c.setFont("Helvetica", 9.5)
    c.setFillColor(colors.black)
    c.drawString(400, 26, SIG_DESIGNATION)

    c.save()
    src_doc.close()
    out_buf.seek(0)
    return out_buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# AI Parser — uses Mistral API
# Generates 3 paragraphs (intro, details, financial condition)
# ─────────────────────────────────────────────────────────────────────────────

def ai_parse_with_mistral(text: str) -> dict:
    """Parse raw text using Mistral API to extract structured letter fields."""
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not configured")

    issue_types = ", ".join(ISSUE_LABELS.keys())

    system_prompt = (
        "You are a letter parser for SKSSF, a community organization. "
        "Extract structured information from the given text about a person in need "
        "and return ONLY valid JSON. No explanation, no markdown."
    )

    user_prompt = f"""Extract the following fields from this text and return as JSON:
- name: full name of the person in need (string, empty if not found)
- relation: "S/o", "D/o", "W/o", or "H/o" — infer from gender/context (default "S/o")
- guardian: parent or husband name if mentioned (string, empty if not found)
- address: residence location if mentioned (string, empty if not found)
- issue_type: one of "{issue_types}". Classification rules (check in order):
  * "death_benefit" — if someone has died, expired, passed away, or demise is mentioned
  * "health" — if medical condition, hospital, disease, treatment, surgery, or illness is mentioned
  * "education" — if school, college, fees, student, study, or scholarship is mentioned
  * "marriage" — if marriage, wedding, or post-marriage financial hardship is mentioned
  * "financial" — if general financial hardship, debt, poverty, or money problems are mentioned (NOT covered by above)
  * "general" — for recommendation or general support letters
  * "other" — if the issue does NOT fit any of the above categories (e.g. house repair, accident, natural disaster)
- body: Three formal paragraphs separated by blank lines, suitable for an official community letter.
  Paragraph 1 (Introduction): Introduce the person — name, place, marital status if relevant, and the main condition/situation. 2-3 sentences.
  Paragraph 2 (Details): Explain the situation in detail. For health: hospital, diagnosis, treatment, expenses. For education: academic details, fees. For marriage: marriage details. For death: death details, date, cause. For financial: situation details, expenses. 2-3 sentences.
  Paragraph 3 (Financial condition): Explain the family's financial situation — income, employment status, economic hardship. 2-3 sentences.
  All paragraphs: third person, formal respectful tone, no greetings, no salutations, no first person pronouns (I, we, our). Do NOT use bracketed placeholders. Do NOT invent details not present in the text — use only what is stated.

Text: "{text}"

Return ONLY JSON with these exact keys. The "body" value must contain all 3 paragraphs separated by double newlines."""

    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    r = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Mistral API error: {r.status_code} — {r.text[:200]}")

    content = r.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)

    defaults = {
        "name": "",
        "relation": "S/o",
        "guardian": "",
        "address": "",
        "issue_type": "general",
        "body": "",
    }
    for key, default_val in defaults.items():
        val = parsed.get(key, default_val)
        if val is None:
            val = default_val
        defaults[key] = str(val).strip()

    if defaults["issue_type"] not in ISSUE_LABELS:
        defaults["issue_type"] = "other"

    return defaults


def ai_fix_body_with_mistral(text: str, issue_type: str, name: str) -> str:
    """Use Mistral to clean up / formalize the body text into 3 proper paragraphs."""
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not configured")

    issue_label = ISSUE_LABELS.get(issue_type, "general")

    user_prompt = f"""Rewrite the following rough text into 3 clean, formal paragraphs for an official letter.

STRICT RULES — VIOLATION = FAILURE:
- Use ONLY information present in the rough text. Do NOT invent, assume, or add ANY detail not explicitly stated.
- Do NOT add city names, dates, medical terms, amounts, or conditions that are not in the original text.
- Do NOT use placeholders like [City], [Date], [Name] — if a detail is missing, simply omit it.
- Only rephrase and formalize what is already written. You are cleaning up grammar and tone, NOT adding content.
- Keep it in third person. No greetings, no salutations, no first person pronouns (I, we, our).
- Separate the 3 paragraphs with a blank line. Each paragraph: 2-3 sentences.

Paragraph structure:
1. Introduction: Who is the person, where do they live, what is their situation (ONLY from the text).
2. Details: What happened, where, what costs (ONLY from the text).
3. Financial condition: Income, employment, hardship (ONLY from the text).

Issue type: {issue_label}
Person name: {name}

Rough text: "{text}"

Return ONLY the 3 paragraphs. No quotes, no JSON, no explanation."""

    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": "You are a professional letter writer for a community organization. Return only the rewritten text."},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }

    r = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Mistral API error: {r.status_code}")

    content = r.json()["choices"][0]["message"]["content"].strip()
    if content.startswith('"') and content.endswith('"'):
        content = content[1:-1]
    return content


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    try:
        pdf_bytes = generate_letter_pdf(data)
        name_slug = data["name"].replace(" ", "_")
        filename = f"SKSSF_Letter_{name_slug}_{datetime.date.today().strftime('%Y%m%d')}.pdf"
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/preview", methods=["POST"])
def preview():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = generate_letter_pdf(data)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=False,
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/ai_parse", methods=["POST"])
def ai_parse():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        extracted = ai_parse_with_mistral(text)
        return jsonify({
            "status": "success",
            "extracted": extracted,
            "message": "AI successfully parsed the issue details!",
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "message": "AI parsing failed. You can still fill the form manually.",
        }), 500


@app.route("/ai_fix", methods=["POST"])
def ai_fix():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    issue_type = data.get("issue_type", "general")
    name = data.get("name", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        fixed = ai_fix_body_with_mistral(text, issue_type, name)
        return jsonify({
            "status": "success",
            "fixed_body": fixed,
            "message": "AI cleaned up the letter body!",
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "message": "AI fix failed.",
        }), 500


@app.route("/issue_types")
def issue_types():
    return jsonify(ISSUE_LABELS)


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "signature_loaded": SIG_PATH is not None,
        "signature_path": os.path.basename(SIG_PATH) if SIG_PATH else None,
        "template_pdf_exists": os.path.exists(TEMPLATE_PDF),
        "ai_configured": bool(os.environ.get("MISTRAL_API_KEY")),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    sig_status = "loaded" if SIG_PATH else "NOT FOUND"
    print(f"SKSSF Letter Automation v4 — http://localhost:{port}")
    print(f"  Signature: {sig_status}")
    print(f"  Letterhead: {'loaded' if os.path.exists(TEMPLATE_PDF) else 'NOT FOUND'}")
    print(f"  AI Parser: Mistral API {'configured' if os.environ.get('MISTRAL_API_KEY') else 'NOT configured'}")
    app.run(debug=False, host="0.0.0.0", port=port)
