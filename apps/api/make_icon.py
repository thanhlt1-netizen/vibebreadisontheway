from PIL import Image, ImageDraw
S = 1024; im = Image.new("RGBA", (S, S), (12, 15, 18, 255)); d = ImageDraw.Draw(im)
b = 190; d.ellipse([b, b, S - b, S - b], outline=(39, 48, 58, 255), width=70)
d.arc([b, b, S - b, S - b], start=-90, end=40, fill=(124, 224, 195, 255), width=70)
d.polygon([(440, 360), (700, 512), (440, 664)], fill=(232, 228, 217, 255))
os_ = [256, 128, 64, 48, 32, 16]; im.save("assets/icon.ico", sizes=[(s, s) for s in os_]); print("icon OK")
