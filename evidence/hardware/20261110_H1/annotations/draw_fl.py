import sys
from PIL import Image, ImageDraw, ImageFont
S = 2
im = Image.open(sys.argv[1]).convert('RGB').resize((576*S, 768*S))
d = ImageDraw.Draw(im, 'RGBA')
font = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', 30, index=3)
big = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', 52, index=3)
p = lambda x, y: (x*S, y*S)
def text(xy, s, f=font, fill=(255,255,255), bg=(0,0,0,170)):
    b = d.textbbox(xy, s, font=f); d.rectangle((b[0]-6,b[1]-4,b[2]+6,b[3]+4), fill=bg); d.text(xy, s, font=f, fill=fill)
def arrow(a, b, col, w=8):
    import math
    d.line([a, b], fill=col, width=w)
    ang = math.atan2(b[1]-a[1], b[0]-a[0]); L = 30
    for s in (2.6, -2.6):
        d.line([b, (b[0]+L*math.cos(ang+s), b[1]+L*math.sin(ang+s))], fill=col, width=w)
# zones (board approx x127-378, y85-715 in source px)
for y0, y1, n in ((85,295,'A'), (295,505,'B'), (505,715,'C')):
    text(p(150, (y0+y1)/2-20), n, big, bg=(0,0,0,120))
d.line([p(127,295), p(378,295)], fill=(255,255,0,200), width=3)
d.line([p(127,505), p(378,505)], fill=(255,255,0,200), width=3)
RED, BLUE = (230,30,30), (20,90,255)
for bx, by in ((405,300), (410,490)):   # approximate base rotation centres
    c = p(bx, by)
    d.ellipse((c[0]-12,c[1]-12,c[0]+12,c[1]+12), fill=(255,255,0), outline=(0,0,0), width=3)
    arrow(c, (c[0]-200, c[1]), RED); text((c[0]-250, c[1]-60), 'F', big, fill=RED, bg=(255,255,255,200))
    arrow(c, (c[0], c[1]+150), BLUE); text((c[0]+18, c[1]+100), 'L', big, fill=BLUE, bg=(255,255,255,200))
text(p(10, 30), 'F：垂直長邊，指向場地／使用者（紅）', fill=RED, bg=(255,255,255,220))
text(p(10, 58), 'L：沿長邊，指向 B/C（手臂的左邊）（藍）', fill=BLUE, bg=(255,255,255,220))
text(p(10, 740), '← 使用者這側　　　　手臂底座這側 →')
text(p(300, 86), '黃點＝旋轉軸（位置為估計）', bg=(0,0,0,180))
im.save(sys.argv[2])
