import sys
sys.path.insert(0, r'c:\Users\ARMAN\OneDrive\Desktop\skssf')
from app import generate_letter_pdf
import fitz

data = {
    "name": "Ruksana",
    "relation": "W/o",
    "guardian": "Mohammed",
    "address": "Valachil Padavu",
    "recipient": "SKSSF Sahachari\nKendra Samithi",
    "issue_type": "health",
    "custom_note": "Ruksana is the resident of Valachil Padavu. She is a married woman who started severe stomach pain. She was diagnosed and admitted for stone in the uterus and womb at Father Muller Hospital. The medical treatment costed more than 3 Lakh rupees. Their financial background is very weak.",
    "date": "30/09/2025"
}

pdf_bytes = generate_letter_pdf(data)

# Save PDF
with open(r'c:\Users\ARMAN\OneDrive\Desktop\skssf\test_ruksana.pdf', 'wb') as f:
    f.write(pdf_bytes)

# Render PNG
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
pix = doc[0].get_pixmap(dpi=100)
pix.save(r'c:\Users\ARMAN\OneDrive\Desktop\skssf\test_ruksana.png')
print("Generated test_ruksana.png successfully!")
