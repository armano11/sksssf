import sys
sys.path.insert(0, r'c:\Users\ARMAN\OneDrive\Desktop\skssf')
from app import generate_letter_pdf
import fitz

data = {
    "name": "Mohammed Ashraf K",
    "relation": "S/o",
    "guardian": "Abdul Rahman",
    "address": "Valachil, Mangalore, DK District",
    "issue_type": "health",
    "custom_note": "The applicant is suffering from chronic kidney disease and requires dialysis twice a week. The family has no stable income.",
    "date": "04/08/2026"
}

pdf_bytes = generate_letter_pdf(data)

# Save PDF
with open(r'c:\Users\ARMAN\OneDrive\Desktop\skssf\test_output.pdf', 'wb') as f:
    f.write(pdf_bytes)
print("PDF saved.")

# Render to PNG for inspection
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
pix = doc[0].get_pixmap(dpi=100)
pix.save(r'c:\Users\ARMAN\OneDrive\Desktop\skssf\test_output.png')
print(f"PNG saved: {pix.width}x{pix.height}")
