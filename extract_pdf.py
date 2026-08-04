import pdfplumber

pdf = pdfplumber.open(r"C:\Users\ARMAN\OneDrive\Desktop\skssf\S36BW-826073106590.pdf")
print(f"Pages: {len(pdf.pages)}")
for i, page in enumerate(pdf.pages):
    text = page.extract_text()
    print(f"--- Page {i+1} ---")
    print(text if text else "(no text extracted)")
pdf.close()