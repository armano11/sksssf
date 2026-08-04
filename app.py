"""
SKSSF Letter Automation Pipeline v3
Generates official letters on the SKSSF Valachil Padavu Committee letterhead.
- Fixed signature loading with fallback
- Real AI parsing via Mistral API
- Multi-issue: health, financial, education, death, marriage, general, other
- "Other" type: AI generates custom subject + body
- Fixed recipient (no UI field needed)
- AI Fix button to clean up rough notes
- Production-ready: gunicorn compatible, PORT env support
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

# ── Fixed recipient — same as shown in the reference letter ──
DEFAULT_RECIPIENT = "To,\nThe Concerned Authority,"

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
# Letter templates for each issue type
# Format matches the uploaded reference letter:
#   To,\n<recipient>\n\nSub: <subject>\n\nRespected Sir/Madam,\n\n<body>\n\nThanking you,
# ─────────────────────────────────────────────────────────────────────────────

LETTER_TEMPLATES = {
    "financial": """\
To,
The Concerned Authority,

Sub: Financial Assistance for {name} – Humble Request

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, write this letter on behalf of {name}, {relation} of {guardian}, residing at {address}. We hereby certify that the said individual belongs to a genuinely financially distressed family in our locality.

{custom_note}

Due to unforeseen circumstances, the family has fallen into severe financial hardship and is unable to meet basic day-to-day needs. {name} has been a member of our community and is known for their honesty and integrity.

We humbly request your good office to kindly extend all possible financial assistance and support to the above-mentioned individual at the earliest.

We shall be highly obliged for your kind consideration.

Thanking you,
""",

    "health": """\
To,
The Concerned Authority,

Sub: Post-Treatment Medical Assistance for {name} – Request Letter

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, are writing this letter on behalf of {name}, {relation} of {guardian}, residing at {address}.

{custom_note}

The patient has undergone treatment and the family has incurred significant medical expenses. They are now in need of financial assistance to recover from the burden of these costs. The family lacks sufficient resources to cope with the situation. We verify that the above information is true to the best of our knowledge.

We earnestly request your esteemed office to kindly render all possible support and medical assistance to the patient and their family in this difficult time.

Thanking you,
""",

    "education": """\
To,
The Concerned Authority,

Sub: Educational Assistance for {name} – Request Letter

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, humbly write this letter in support of {name}, {relation} of {guardian}, residing at {address}.

{custom_note}

The student is academically sincere and hardworking. However, due to the family's weak financial background, they are unable to continue their education without external support. We certify that all the above details are true and correct.

We kindly request your good office to provide the necessary educational assistance or scholarship to enable the student to pursue their studies without financial burden.

Thanking you,
""",

    "general": """\
To,
The Concerned Authority,

Sub: Letter of Support / Recommendation for {name}

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, are pleased to forward this letter of recommendation on behalf of {name}, {relation} of {guardian}, residing at {address}.

{custom_note}

We have known the above-mentioned individual as a member of our local community. They are of good character and moral standing. We request your kind consideration and support in the above-mentioned matter.

Thanking you,
""",

    "death_benefit": """\
To,
The Concerned Authority,

Sub: Death Benefit / Bereavement Support for the Family of {name}

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, write this letter with deep sorrow to inform you about the demise of {name}, {relation} of {guardian}, who was a resident of {address}.

{custom_note}

Following the passing of {name}, the bereaved family is in a state of grief and financial hardship. We humbly request your office to extend the applicable death benefit and any other form of assistance to help the family during this difficult period.

Thanking you,
""",

    "marriage": """\
To,
The Concerned Authority,

Sub: Post-Marriage Financial Assistance for {name} – Humble Request

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, write this letter on behalf of {name}, {relation} of {guardian}, residing at {address}.

{custom_note}

Following the marriage, the family is facing severe financial hardship and is struggling to meet basic day-to-day needs. We hereby certify that the above-mentioned individual genuinely belongs to a financially weaker section of our community.

We humbly request your good office to kindly extend all possible post-marriage financial assistance and support to help the family recover from this difficult situation.

We shall be highly obliged for your kind consideration.

Thanking you,
""",

    # "other" — AI generates the subject and body structure
    "other": """\
To,
The Concerned Authority,

Sub: {subject}

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, write this letter on behalf of {name}, {relation} of {guardian}, residing at {address}.

{custom_note}

We humbly request your good office to kindly extend all possible assistance and support to the above-mentioned individual at the earliest.

We shall be highly obliged for your kind consideration.

Thanking you,
""",
}

ISSUE_LABELS = {
    "financial": "Financial Assistance",
    "health": "Health / Medical",
    "education": "Education",
    "death_benefit": "Death Benefit",
    "marriage": "Marriage Assistance",
    "general": "General Recommendation",
    "other": "Other (AI Custom)",
}

# ─────────────────────────────────────────────────────────────────────────────
# PDF generation: overlay text onto the original letterhead
# Coordinates calibrated from the letterhead PDF and reference letter image
# ─────────────────────────────────────────────────────────────────────────────

def generate_letter_pdf(data: dict) -> bytes:
    name = data.get("name", "").strip()
    relation = data.get("relation", "S/o").strip()
    guardian = data.get("guardian", "").strip()
    address = data.get("address", "").strip()
    issue_type = data.get("issue_type", "general")
    custom_note = data.get("custom_note", "").strip()
    subject = data.get("subject", "").strip()
    date_str = data.get("date", datetime.date.today().strftime("%d/%m/%Y"))

    # Always use fixed recipient
    recipient = DEFAULT_RECIPIENT

    # Fill the template
    template = LETTER_TEMPLATES.get(issue_type, LETTER_TEMPLATES["general"])

    format_kwargs = dict(
        name=name,
        relation=relation,
        guardian=guardian if guardian else "—",
        address=address if address else "—",
        custom_note=custom_note if custom_note else "We hereby certify and support the above-mentioned individual's request.",
    )

    # "other" type needs a subject
    if issue_type == "other":
        format_kwargs["subject"] = subject if subject else f"Request for Assistance – {name}"

    raw_body = template.format(**format_kwargs)

    # Replace default "To, / The Concerned Authority," with fixed recipient
    body_lines = raw_body.split("\n")
    if body_lines and body_lines[0].startswith("To"):
        idx = 0
        while idx < len(body_lines) and (
            body_lines[idx].startswith("To") or
            body_lines[idx].strip() == "The Concerned Authority," or
            not body_lines[idx].strip()
        ):
            idx += 1
        body_text = recipient + "\n\n" + "\n".join(body_lines[idx:])
    else:
        body_text = raw_body

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

    # ── Date ──
    # "Date:" label is pre-printed at ~x=446pt, y=154pt from top
    # White-out the old date area and write clean date
    date_label_x = W * 0.595  # ≈ 364pt
    date_y = H - 154           # ≈ 638pt from bottom

    c.setFillColor(colors.white)
    c.rect(date_label_x - 2, date_y - 12, W * 0.38, 28, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(date_label_x, date_y, f"Date: {date_str}")

    # ── Signature Overlay ──
    # Signature placed at bottom-right, above the pre-printed signature line
    if SIG_PATH and os.path.exists(SIG_PATH):
        try:
            sig_img = ImageReader(SIG_PATH)
            # Aspect-correct: original 254x104px, ratio ~2.44
            sig_w = 100
            sig_h = sig_w / 2.44  # ≈ 41pt
            c.drawImage(sig_img, 420, 52, width=sig_w, height=sig_h, mask='auto')
        except Exception as e:
            print(f"Signature overlay warning: {e}")

    # ── Letter body ──
    # Body starts at 185pt from top (below header), ends at 160pt from bottom (above footer)
    body_top_y = H - 185
    body_bottom_y = 160
    left_margin = 42
    right_margin = W - 42
    body_width = right_margin - left_margin
    line_height = 14.5

    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.black)

    lines = body_text.split("\n")
    y = body_top_y
    for line in lines:
        if y < body_bottom_y:
            break
        words = line.split()
        if not words:
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

    c.save()
    src_doc.close()
    out_buf.seek(0)
    return out_buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# AI Parser — uses Mistral API for real NLP extraction
# ─────────────────────────────────────────────────────────────────────────────

def ai_parse_with_mistral(text: str) -> dict:
    """Parse raw text using Mistral API to extract structured letter fields."""
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not configured")

    system_prompt = (
        "You are a letter parser for SKSSF, a community organization. "
        "Extract structured information from the given text about a person in need "
        "and return ONLY valid JSON. No explanation, no markdown."
    )

    issue_types = ", ".join(ISSUE_LABELS.keys())

    user_prompt = f"""Extract the following fields from this text and return as JSON:
- name: full name of the person in need (string, empty if not found)
- relation: "S/o", "D/o", "W/o", or "H/o" — infer from gender/context (default "S/o")
- guardian: parent or husband name if mentioned (string, empty if not found)
- address: residence location if mentioned (string, empty if not found)
- issue_type: one of "{issue_types}" — use "other" if it doesn't fit any category
- subject: a concise formal subject line for the letter (e.g. "Medical Assistance for {text.split(',')[0] if ',' in text else 'Applicant'} – Request Letter"). Only needed for "other" type, but always provide it.
- custom_note: a formal 2-3 sentence summary of the situation, written in a respectful tone suitable for an official community letter. Use third person. Do not use first person pronouns.

Text: "{text}"

Return ONLY JSON with these exact keys."""

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

    # Validate and fill defaults
    defaults = {
        "name": "",
        "relation": "S/o",
        "guardian": "",
        "address": "",
        "issue_type": "general",
        "subject": "",
        "custom_note": "",
    }
    for key, default_val in defaults.items():
        val = parsed.get(key, default_val)
        if val is None:
            val = default_val
        defaults[key] = str(val).strip()

    # Validate issue_type
    if defaults["issue_type"] not in ISSUE_LABELS:
        defaults["issue_type"] = "other"

    return defaults


def ai_fix_note_with_mistral(text: str, issue_type: str, name: str) -> str:
    """Use Mistral to clean up / formalize a rough custom note."""
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not configured")

    issue_label = ISSUE_LABELS.get(issue_type, "general")

    user_prompt = f"""You are writing for an official community organization letter.
Rewrite the following rough note into a clean, formal 2-4 sentence paragraph suitable for an official letter.
- Keep it in third person
- Maintain all factual details (amounts, hospital names, conditions, dates)
- Use respectful, formal tone
- Do NOT add any greeting or salutation — just the paragraph
- Do NOT use first person pronouns (I, we, our)

Issue type: {issue_label}
Person name: {name}

Rough note: "{text}"

Return ONLY the rewritten paragraph, no quotes, no JSON, no explanation."""

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
    """Return PDF inline for browser preview."""
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
    """AI Parser — extracts structured details from raw voice/text using Mistral."""
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
    """AI Fix — cleans up / formalizes a rough custom note using Mistral."""
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    issue_type = data.get("issue_type", "general")
    name = data.get("name", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        fixed = ai_fix_note_with_mistral(text, issue_type, name)
        return jsonify({
            "status": "success",
            "fixed_note": fixed,
            "message": "AI cleaned up the note!",
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
    print(f"SKSSF Letter Automation v3 — http://localhost:{port}")
    print(f"  Signature: {sig_status}")
    print(f"  Letterhead: {'loaded' if os.path.exists(TEMPLATE_PDF) else 'NOT FOUND'}")
    print(f"  AI Parser: Mistral API {'configured' if os.environ.get('MISTRAL_API_KEY') else 'NOT configured'}")
    app.run(debug=False, host="0.0.0.0", port=port)
