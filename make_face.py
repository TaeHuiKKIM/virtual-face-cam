"""Generate a simple illustrated face (face.jpg) for testing.

Rendered at high resolution with supersampling for smooth edges.
For a photorealistic face instead, use a stock/AI-generated photo.
"""
from PIL import Image, ImageDraw

OUT = 720            # 최종 해상도
SS = 3               # 슈퍼샘플링 배율 (안티에일리어싱용)
S = SS               # 모든 좌표/두께에 곱할 스케일
W = H = OUT * SS

img = Image.new("RGB", (W, H), (235, 238, 242))
d = ImageDraw.Draw(img)

cx, cy = W // 2, H // 2 + 20 * S
skin = (238, 200, 170)
skin_shadow = (222, 182, 152)


def box(x0, y0, x1, y1):
    return [cx + x0 * S, cy + y0 * S, cx + x1 * S, cy + y1 * S]


# 목 / 상체
d.rectangle(box(-55, 120, 55, 260), fill=skin_shadow)
d.ellipse(box(-200, 230, 200, 520), fill=(70, 90, 130))

# 얼굴
d.ellipse(box(-130, -175, 130, 150), fill=skin)

# 귀
d.ellipse(box(-148, -20, -108, 55), fill=skin)
d.ellipse(box(108, -20, 148, 55), fill=skin)

# 머리카락
d.chord(box(-135, -200, 135, 40), 180, 360, fill=(60, 45, 40))
d.rectangle(box(-135, -90, -118, 10), fill=(60, 45, 40))
d.rectangle(box(118, -90, 135, 10), fill=(60, 45, 40))

# 눈썹
d.line([cx - 85 * S, cy - 45 * S, cx - 30 * S, cy - 50 * S], fill=(70, 50, 40), width=7 * S)
d.line([cx + 30 * S, cy - 50 * S, cx + 85 * S, cy - 45 * S], fill=(70, 50, 40), width=7 * S)

# 눈
for ex in (-58, 58):
    d.ellipse(box(ex - 32, -25, ex + 32, 10), fill=(255, 255, 255))
    d.ellipse(box(ex - 15, -20, ex + 15, 8), fill=(90, 60, 40))
    d.ellipse(box(ex - 7, -12, ex + 7, 2), fill=(20, 20, 20))
    d.ellipse(box(ex - 3, -12, ex + 3, -6), fill=(255, 255, 255))

# 코
d.polygon([(cx, cy - 5 * S), (cx - 18 * S, cy + 55 * S), (cx + 18 * S, cy + 55 * S)],
          fill=skin_shadow)
d.ellipse(box(-20, 45, 20, 68), fill=skin_shadow)

# 입
d.chord(box(-45, 78, 45, 128), 10, 170, fill=(180, 90, 90))
d.line([cx - 40 * S, cy + 90 * S, cx + 40 * S, cy + 90 * S], fill=(150, 70, 70), width=4 * S)

# 슈퍼샘플링 축소 → 매끄러운 가장자리
img = img.resize((OUT, OUT), Image.LANCZOS)
img.save("face.jpg", quality=95)
print("저장 완료: face.jpg", f"({OUT}x{OUT})")
