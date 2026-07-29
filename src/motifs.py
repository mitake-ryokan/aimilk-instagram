"""季節モチーフの描画部品。

写真がなくても季節感のある投稿画像を作るための、イラスト描画関数を集めたもの。
すべて「指定した高さの帯（バンド）」に描く形に統一してあるので、
スライドの上部にそのまま貼れる。
"""
from PIL import Image, ImageDraw, ImageFilter
import math

W = 1080


def _grad(w, h, top, bottom):
    """上から下へのグラデーション画像を作る"""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def _rot(pts, cx, cy, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + (x - cx) * ca - (y - cy) * sa,
             cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


# ---------------------------------------------------------------- 春：桜
def sakura(h=520, seed=7):
    img = _grad(W, h, (255, 240, 244), (252, 226, 232))
    d = ImageDraw.Draw(img, "RGBA")
    r = seed

    def petal(cx, cy, size, ang, col):
        pts = []
        for i in range(24):
            t = 2 * math.pi * i / 24
            rr = size * (1 - 0.35 * abs(math.cos(t * 0.5)))
            pts.append((cx + math.cos(t) * rr * 0.62, cy + math.sin(t) * rr))
        d.polygon(_rot(pts, cx, cy, ang), fill=col)

    def flower(cx, cy, size, col, core):
        for i in range(5):
            a = 2 * math.pi * i / 5
            petal(cx + math.cos(a - math.pi / 2) * size * 0.62,
                  cy + math.sin(a - math.pi / 2) * size * 0.62,
                  size * 0.72, a, col)
        d.ellipse([cx - size * .2, cy - size * .2, cx + size * .2, cy + size * .2], fill=core)

    # 枝
    d.line([(-20, 90), (300, 70), (620, 130), (1100, 60)], fill=(120, 88, 74), width=14, joint="curve")
    d.line([(160, 78), (200, 190), (170, 300)], fill=(120, 88, 74), width=8, joint="curve")
    d.line([(760, 108), (820, 210)], fill=(120, 88, 74), width=7, joint="curve")

    spots = [(120, 70, 52), (250, 96, 44), (400, 78, 58), (560, 112, 46),
             (700, 96, 54), (860, 78, 48), (1000, 66, 56), (196, 196, 40),
             (176, 300, 36), (826, 214, 38)]
    for cx, cy, s in spots:
        flower(cx, cy, s, (255, 190, 205, 255), (250, 224, 150, 255))

    # 舞う花びら
    for i in range(34):
        r = (r * 1103515245 + 12345) % 2147483648
        x = r % W
        r = (r * 1103515245 + 12345) % 2147483648
        y = 120 + r % (h - 140)
        r = (r * 1103515245 + 12345) % 2147483648
        a = (r % 628) / 100
        petal(x, y, 13 + (i % 4) * 3, a, (255, 205, 216, 210))
    return img


# ---------------------------------------------------------------- 夏：青空と入道雲
def natsu(h=520, seed=3):
    img = _grad(W, h, (108, 176, 236), (196, 226, 246))
    d = ImageDraw.Draw(img, "RGBA")

    def cloud(cx, cy, s):
        blobs = [(0, 0, 1.0), (-0.75, 0.18, .72), (0.78, 0.2, .68),
                 (-0.36, -0.5, .66), (0.4, -0.46, .6), (0.05, -0.86, .5),
                 (-1.3, 0.42, .5), (1.32, 0.44, .48)]
        for dx, dy, rs in blobs:
            rr = s * rs
            d.ellipse([cx + dx * s - rr, cy + dy * s - rr,
                       cx + dx * s + rr, cy + dy * s + rr], fill=(255, 255, 255, 246))

    cloud(250, 330, 130)
    cloud(720, 300, 155)
    cloud(980, 380, 95)
    # 太陽
    d.ellipse([840, 60, 990, 210], fill=(255, 244, 196, 235))
    return img


# ---------------------------------------------------------------- 夏夜：花火
def hanabi(h=520, seed=11):
    img = _grad(W, h, (24, 30, 58), (48, 56, 96))
    d = ImageDraw.Draw(img, "RGBA")
    GOLD = (240, 196, 92)
    for i in range(160):
        x = (i * 137) % W
        y = (i * 61) % h
        s = 1 + (i % 3)
        d.ellipse([x, y, x + s, y + s], fill=(120, 132, 174, 200))

    def fw(cx, cy, R, cols, n=30):
        for i in range(n):
            a = 2 * math.pi * i / n
            col = cols[i % len(cols)]
            for t in range(6, 11):
                rr = R * t / 10
                px, py = cx + math.cos(a) * rr, cy + math.sin(a) * rr
                s = 3 if t < 9 else 5
                d.ellipse([px - s, py - s, px + s, py + s], fill=col)
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(255, 255, 255))

    fw(300, 200, 155, [(255, 120, 100), GOLD, (255, 200, 190)])
    fw(770, 140, 115, [GOLD, (150, 200, 255), (255, 255, 255)])
    fw(600, 350, 85, [(255, 150, 190), GOLD])
    return img


# ---------------------------------------------------------------- 秋：すすき
def susuki(h=520, seed=5):
    img = _grad(W, h, (255, 214, 158), (255, 176, 122))
    d = ImageDraw.Draw(img, "RGBA")
    # 夕日
    d.ellipse([760, 90, 970, 300], fill=(255, 152, 96, 235))
    # 遠景の山（台ヶ岳のイメージ）
    d.polygon([(-40, h), (180, 300), (420, h)], fill=(206, 140, 110, 210))
    d.polygon([(300, h), (620, 250), (940, h)], fill=(186, 122, 98, 220))

    # 穂は別レイヤーに描いてからぼかす。線のままだと硬く見えるため
    over = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(over, "RGBA")

    def stalk(x, base, top_y, lean, col, plume, sd=1):
        # 茎
        pts = [(x, base), (x + lean * .4, (base + top_y) / 2), (x + lean, top_y)]
        d.line(pts, fill=col, width=5, joint="curve")
        # 穂：細長い袋状のかたまり＋無数の点で「ふわっ」とした綿毛を作る
        tx, ty = x + lean, top_y + 155   # ty = 穂の付け根（下端）
        PH, HW = 155, 25                 # 穂の高さ / 最大半幅

        def half_w(t):
            # t=0 付け根, t=1 穂先。中ほどが一番ふくらむ
            return HW * (math.sin(min(max(t, 0), 1) ** 0.8 * math.pi) ** 0.75)

        body = []
        for i in range(24):
            t = i / 23
            body.append((tx - half_w(t) * .8, ty - PH * t))
        for i in range(24):
            t = 1 - i / 23
            body.append((tx + half_w(t) * .8, ty - PH * t))
        od.polygon(body, fill=plume[:3] + (int(plume[3] * .55),))

        st = sd * 2654435761
        for i in range(320):
            st = (st * 1103515245 + 12345) % 2147483648
            t = (st % 1000) / 1000
            st = (st * 1103515245 + 12345) % 2147483648
            u = ((st % 2000) / 1000) - 1.0          # -1..1
            hw = half_w(t)
            px = tx + u * hw * 1.25
            py = ty - PH * t + abs(u) * 10          # 端ほど少し下がる＝垂れ感
            r0 = 1 + (i % 3)
            od.ellipse([px - r0, py - r0, px + r0, py + r0], fill=plume)

    r = seed
    for i in range(26):
        r = (r * 1103515245 + 12345) % 2147483648
        x = (r % (W + 120)) - 60
        r = (r * 1103515245 + 12345) % 2147483648
        top = 120 + r % 190
        r = (r * 1103515245 + 12345) % 2147483648
        lean = (r % 90) - 45
        far = i % 3 == 0
        stalk(x, h + 20, top, lean,
              (176, 132, 92, 230) if far else (150, 108, 70, 245),
              (255, 234, 206, 175) if far else (255, 248, 232, 215), sd=i + 1)

    soft = over.filter(ImageFilter.GaussianBlur(2.6))
    img = Image.alpha_composite(img.convert("RGBA"), soft)
    img = Image.alpha_composite(img, over)
    return img.convert("RGB")


# ---------------------------------------------------------------- 秋：紅葉
def momiji(h=520, seed=9):
    img = _grad(W, h, (255, 232, 200), (250, 206, 168))
    d = ImageDraw.Draw(img, "RGBA")

    def leaf(cx, cy, s, ang, col):
        pts = []
        for i in range(5):
            a = -math.pi / 2 + (i - 2) * 0.62
            pts.append((cx + math.cos(a) * s, cy + math.sin(a) * s))
            pts.append((cx + math.cos(a + .31) * s * .42, cy + math.sin(a + .31) * s * .42))
        pts.append((cx, cy + s * .52))
        d.polygon(_rot(pts, cx, cy, ang), fill=col)
        d.line(_rot([(cx, cy), (cx, cy + s * .74)], cx, cy, ang), fill=(150, 60, 40, 180), width=3)

    d.line([(-20, 70), (340, 96), (700, 60), (1100, 100)], fill=(122, 84, 66), width=13, joint="curve")
    cols = [(214, 72, 52, 255), (232, 122, 48, 255), (198, 52, 46, 255), (240, 160, 60, 255)]
    r = seed
    for i in range(30):
        r = (r * 1103515245 + 12345) % 2147483648
        x = r % W
        r = (r * 1103515245 + 12345) % 2147483648
        y = 60 + r % (h - 90)
        r = (r * 1103515245 + 12345) % 2147483648
        a = (r % 628) / 100
        s = 26 + (i % 5) * 9
        leaf(x, y, s, a, cols[i % len(cols)])
    return img


# ---------------------------------------------------------------- 冬：雪
def yuki(h=520, seed=13):
    img = _grad(W, h, (86, 112, 164), (176, 202, 232))
    d = ImageDraw.Draw(img, "RGBA")

    def flake(cx, cy, s, col, wdt=4):
        for i in range(6):
            a = math.pi * i / 3
            ex, ey = cx + math.cos(a) * s, cy + math.sin(a) * s
            d.line([(cx, cy), (ex, ey)], fill=col, width=wdt)
            for t in (.5, .75):
                bx, by = cx + math.cos(a) * s * t, cy + math.sin(a) * s * t
                for sgn in (-1, 1):
                    b = a + sgn * 0.7
                    d.line([(bx, by), (bx + math.cos(b) * s * .28, by + math.sin(b) * s * .28)],
                           fill=col, width=max(wdt - 2, 2))

    r = seed
    for i in range(11):
        r = (r * 1103515245 + 12345) % 2147483648
        x = r % W
        r = (r * 1103515245 + 12345) % 2147483648
        y = 40 + r % (h - 120)
        s = 22 + (i % 4) * 16
        flake(x, y, s, (255, 255, 255, 215), 4)
    for i in range(70):
        r = (r * 1103515245 + 12345) % 2147483648
        x = r % W
        r = (r * 1103515245 + 12345) % 2147483648
        y = r % h
        s = 2 + (i % 4)
        d.ellipse([x, y, x + s, y + s], fill=(255, 255, 255, 200))
    # 雪の積もった稜線
    d.polygon([(-40, h), (0, h - 90), (200, h - 140), (430, h - 70),
               (700, h - 150), (940, h - 80), (1120, h - 130), (1120, h)],
              fill=(250, 252, 255, 250))
    return img


# ---------------------------------------------------------------- 通年：新緑
def shinryoku(h=520, seed=17):
    img = _grad(W, h, (168, 214, 168), (214, 236, 196))
    d = ImageDraw.Draw(img, "RGBA")

    def leaf(cx, cy, s, ang, col):
        pts = []
        for i in range(24):
            t = 2 * math.pi * i / 24
            rr = s * (1 - .3 * abs(math.cos(t * .5)))
            pts.append((cx + math.cos(t) * rr * .5, cy + math.sin(t) * rr))
        d.polygon(_rot(pts, cx, cy, ang), fill=col)

    cols = [(96, 160, 84, 255), (126, 186, 100, 255), (72, 136, 72, 255), (156, 202, 120, 255)]
    r = seed
    for i in range(38):
        r = (r * 1103515245 + 12345) % 2147483648
        x = r % W
        r = (r * 1103515245 + 12345) % 2147483648
        y = r % h
        r = (r * 1103515245 + 12345) % 2147483648
        a = (r % 628) / 100
        leaf(x, y, 28 + (i % 5) * 10, a, cols[i % len(cols)])
    return img


MOTIFS = {
    "桜": sakura, "春": sakura,
    "夏": natsu, "青空": natsu,
    "花火": hanabi, "夏夜": hanabi,
    "すすき": susuki, "秋": susuki,
    "紅葉": momiji,
    "雪": yuki, "冬": yuki,
    "新緑": shinryoku, "通年": shinryoku,
}


def get(name, h=520):
    fn = MOTIFS.get(name, shinryoku)
    return fn(h)


if __name__ == "__main__":
    names = ["桜", "夏", "花火", "すすき", "紅葉", "雪", "新緑"]
    sheet = Image.new("RGB", (W, 520 * len(names)), (255, 255, 255))
    for i, n in enumerate(names):
        sheet.paste(get(n), (0, i * 520))
    sheet.save("motif_sheet.png")
    for n in names:
        get(n).save(f"motif_{n}.png")
    print("ok")
