import fitz

doc = fitz.open(r'c:\Users\ARMAN\OneDrive\Desktop\skssf\S36BW-826073106590.pdf')
page = doc[0]
r = page.rect
W, H = r.width, r.height
print(f"Page size: W={W:.2f}pt  H={H:.2f}pt")
print(f"At 150dpi pixmap would be: {W*150/72:.0f} x {H*150/72:.0f} px")

# The form is image-based, so let's render a calibration image with rulers
# showing coordinate positions
pix = page.get_pixmap(dpi=72)  # 1px = 1pt at 72dpi
print(f"Pixmap at 72dpi: {pix.width} x {pix.height}")

# Draw calibration marks on a copy
import PIL.Image, PIL.ImageDraw, io

img = PIL.Image.open(io.BytesIO(pix.tobytes("png")))
draw = PIL.ImageDraw.Draw(img)

# Draw horizontal lines at key depths from TOP (in pts = px at 72dpi)
marks = [80, 100, 110, 120, 130, 140, 150, 160, 170, 200]
for y_from_top in marks:
    y_px = y_from_top  # 1pt=1px at 72dpi
    draw.line([(0, y_px), (W, y_px)], fill=(255,0,0,180), width=1)
    draw.text((5, y_px+1), f"y_top={y_from_top}", fill=(255,0,0))

img.save(r'c:\Users\ARMAN\OneDrive\Desktop\skssf\calibration.png')
print("Saved calibration.png")
doc.close()
