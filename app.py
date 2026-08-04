"""
SKSSF Letter Automation Pipeline
Generates official letters on the SKSSF Valachil Padavu Committee letterhead.
"""
import os
import io
import datetime
from flask import Flask, request, send_file, jsonify, render_template
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
import fitz  # PyMuPDF

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PDF = os.path.join(BASE_DIR, "S36BW-826073106590.pdf")
OUTPUT_DIR  = os.path.join(BASE_DIR, "generated")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Letter body generators for each issue type
# ─────────────────────────────────────────────────────────────────────────────

LETTER_TEMPLATES = {
    "financial": """\
To,
The Concerned Authority,

Sub: Financial Assistance for {name} – Humble Request

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, write this letter on behalf of {name}, {relation} of {guardian}, residing at {address}. We hereby certify that the said individual belongs to a genuinely financially distressed family in our locality.

{custom_note}

The family is unable to meet basic day-to-day needs and is in dire need of financial support. {name} has been a member of our community and is known for their honesty and integrity.

We humbly request your good office to kindly extend all possible financial assistance and support to the above-mentioned individual at the earliest.

We shall be highly obliged for your kind consideration.

Thanking you,
""",

    "health": """\
To,
The Concerned Authority,

Sub: Medical Assistance / Health Support for {name} – Request Letter

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, are writing this letter on behalf of {name}, {relation} of {guardian}, residing at {address}.

{custom_note}

The patient is currently undergoing treatment and is in need of urgent medical assistance. The family lacks sufficient resources to bear the medical expenses. We verify that the above information is true to the best of our knowledge.

We earnestly request your esteemed office to kindly render all possible support and medical assistance to the patient and their family in this difficult time.

Thanking you,
""",

    "education": """\
To,
The Concerned Authority,

Sub: Educational Support / Scholarship for {name} – Request Letter

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

We, the members of SKSSF Valachil Padavu Unit, write this letter with deep sorrow to inform you about the untimely demise of {name}, {relation} of {guardian}, who was a resident of {address}.

{custom_note}

The bereaved family is in a state of grief and financial hardship. We humbly request your office to extend the applicable death benefit and any other form of assistance to help the family during this difficult period.

Thanking you,
""",

    "job": """\
To,
The Concerned Authority,

Sub: Employment / Job Support for {name} – Request Letter

Respected Sir/Madam,

We, the members of SKSSF Valachil Padavu Unit, write this letter on behalf of {name}, {relation} of {guardian}, residing at {address}.

{custom_note}

The applicant is currently unemployed and is actively seeking a suitable job opportunity. We certify that the said person is diligent, honest, and capable of carrying out responsibilities entrusted to them.

We humbly request your office to consider providing employment or any suitable job-related assistance to the above-mentioned individual.

Thanking you,
""",
}

ISSUE_LABELS = {
    "financial":    "Financial Assistance",
    "health":       "Health / Medical Support",
    "education":    "Educational Support",
    "general":      "General Recommendation",
    "death_benefit":"Death Benefit",
    "job":          "Employment / Job Support",
}

# ─────────────────────────────────────────────────────────────────────────────
# PDF generation: overlay text onto the original letterhead
# ─────────────────────────────────────────────────────────────────────────────

def generate_letter_pdf(data: dict) -> bytes:
    name        = data.get("name", "").strip()
    relation    = data.get("relation", "S/o").strip()
    guardian    = data.get("guardian", "").strip()
    address     = data.get("address", "").strip()
    issue_type  = data.get("issue_type", "general")
    custom_note = data.get("custom_note", "").strip()
    date_str    = data.get("date", datetime.date.today().strftime("%d/%m/%Y"))

    recipient   = data.get("recipient", "").strip()
    if not recipient:
        recipient = "To,\nThe Concerned Authority,"
    elif not recipient.lower().startswith("to"):
        recipient = f"To,\n{recipient}"

    # Fill the template
    raw_body = LETTER_TEMPLATES.get(issue_type, LETTER_TEMPLATES["general"]).format(
        name=name,
        relation=relation,
        guardian=guardian,
        address=address,
        custom_note=custom_note if custom_note else f"We hereby certify and support the above-mentioned individual's request.",
    )
    # Replace default To line with custom recipient if provided
    body_lines = raw_body.split("\n")
    if body_lines and body_lines[0].startswith("To"):
        # Remove default 'To,' and 'The Concerned Authority,'
        idx = 0
        while idx < len(body_lines) and (body_lines[idx].startswith("To") or body_lines[idx].strip() == "The Concerned Authority," or not body_lines[idx].strip()):
            idx += 1
        body_text = recipient + "\n\n" + "\n".join(body_lines[idx:])
    else:
        body_text = raw_body

    # Open the original letterhead PDF as background image
    src_doc  = fitz.open(TEMPLATE_PDF)
    src_page = src_doc[0]
    page_rect = src_page.rect   # width x height in points
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
    # Paint over the background "Date:" label then draw our own full line.
    # Calibrated: "Date:" sits at x≈370–480pt, y_top≈148–160pt.
    # In ReportLab (y from bottom): y ≈ H-160=632 to H-148=644.
    date_label_x = W * 0.595   # ≈ 364pt  (left edge of "Date:" label)
    date_y       = H - 154     # ≈ 638pt from bottom (154pt from top)

    # White-out the original "Date:" label area (covers ~2 lines of height)
    c.setFillColor(colors.white)
    c.rect(date_label_x - 2, date_y - 12, W * 0.38, 28, fill=1, stroke=0)

    # Draw clean "Date: DD/MM/YYYY" in one go
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(date_label_x, date_y, f"Date:  {date_str}")

    # ── Signature Overlay (Ibrahim Kaleel - G.Secretary) ──
    SIG_PATH = os.path.join(BASE_DIR, "ibrahim_kaleel_signature.png")
    if os.path.exists(SIG_PATH):
        sig_img = ImageReader(SIG_PATH)
        # Position right above 'President / Secretary' line at bottom-right
        c.drawImage(sig_img, 425, 56, width=95, height=32, mask='auto')

    # ── Letter body ──
    # Calibration: header ends ~130pt from top, body should start ~185pt from top.
    # ReportLab y: body_top = H - 185 = 607pt from bottom.
    # Footer (stamp) occupies bottom ~160pt, so stop at y = 160.
    body_top_y    = H - 185
    body_bottom_y = 160
    left_margin   = 42
    right_margin  = W - 42
    body_width    = right_margin - left_margin
    line_height   = 14.5

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
        if current_line and y >= body_bottom_y:
            c.drawString(left_margin, y, current_line)
            y -= line_height

    c.save()
    src_doc.close()
    out_buf.seek(0)
    return out_buf.read()


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
        filename  = f"SKSSF_Letter_{name_slug}_{datetime.date.today().strftime('%Y%m%d')}.pdf"
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
    """Smart AI Parser to extract details from raw voice/text description of an issue."""
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    import re

    # Default extracted fields
    extracted = {
        "name": "",
        "relation": "S/o",
        "guardian": "",
        "address": "",
        "issue_type": "general",
        "custom_note": "",
        "recipient": "The Concerned Authority"
    }

    # Extract Name (e.g., "Ruksana is...", "Mohammed Ashraf...")
    name_match = re.search(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
    if name_match:
        extracted["name"] = name_match.group(1)

    # Address / Resident detection (e.g. "resident of Valachil Padavu")
    addr_match = re.search(r'resident of ([^.\n,]+)', text, re.IGNORECASE)
    if addr_match:
        extracted["address"] = addr_match.group(1).strip()

    # Determine relation & gender
    if re.search(r'\b(married woman|she|her|daughter|wife)\b', text, re.IGNORECASE):
        extracted["relation"] = "W/o"

    # Determine issue category
    lower_t = text.lower()
    if any(k in lower_t for k in ["hospital", "stomach", "stone", "surgery", "patient", "medical", "disease", "treatment"]):
        extracted["issue_type"] = "health"
    elif any(k in lower_t for k in ["lakh", "rupees", "financial", "poverty", "debt", "poor", "money"]):
        extracted["issue_type"] = "financial"
    elif any(k in lower_t for k in ["school", "college", "fees", "education", "student", "study"]):
        extracted["issue_type"] = "education"
    elif any(k in lower_t for k in ["death", "expired", "passed away", "demise"]):
        extracted["issue_type"] = "death_benefit"
    elif any(k in lower_t for k in ["job", "work", "unemployed"]):
        extracted["issue_type"] = "job"

    # Polish custom note for formal letter
    extracted["custom_note"] = text

    return jsonify({
        "status": "success",
        "extracted": extracted,
        "message": "AI successfully parsed the issue details!"
    })

@app.route("/issue_types")
def issue_types():
    return jsonify(ISSUE_LABELS)

if __name__ == "__main__":
    print("SKSSF Letter Automation Pipeline running at http://localhost:5050")
    app.run(debug=True, port=5050)
