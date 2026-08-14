"""縦長写真に対応したレイアウト（2案）

■ なぜ作り直したか
これまでの「上部に横帯」レイアウトは、横長写真を前提にしていた。
縦長（9:16など、ストーリーズ用に撮った）写真を横帯に入れると、
横幅に合わせて拡大→上下がごっそり切れる。空と地面だけが残って何の写真か分からなくなる。

■ 2つの案
A案 全面写真：写真を1枚まるごと背景にして、下に情報カードを重ねる。
　　9:16の写真だと上下が少し切れるが、被写体は残る。写真の力が一番出る。
B案 縦2分割：左に縦写真、右に情報。写真の縦横比がほぼそのまま活きる。
　　情報量が多い回に向く。文字が読みやすい。
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import motifs

# ■ iPhoneの写真（HEIC）を開けるようにする
# 3号さんがスマホで撮ってDriveに入れる写真は、たいていHEIC形式。
# Pillow単体では開けず、pillow-heif を「登録」してはじめて開けるようになる。
# requirements.txt に入れるだけでは効かない。この2行が本体。
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass    # 入っていない環境（手元での試作など）では、HEICなし運用として動く

W, H = 1080, 1350
FOOT = 78

CREAM = (251, 244, 228)
RED = (216, 64, 47)
DARK = (58, 42, 34)
GRAY = (150, 140, 130)
WHITE = (255, 255, 255)
SOFT = (245, 226, 220)

# 全スライドのフッターに入れる署名。
# ■ 必ず「実在するInstagramのユーザーネーム」を書くこと
# ここは「この投稿は誰のものか」を示す場所で、見た人が検索して辿り着ける文字列でなければ
# 意味がない。キャラクターの呼び名（AIみるく）は本文の名乗りで伝わるので、混ぜない。
HANDLE = "@mitake_hakone"

# ■ フォントの場所は環境によって違う
# 手元のパソコンでは全部の太さが入っていても、GitHub Actionsのサーバーには
# 太字（Black）や中字（Medium）が入っていないことがある。
# パスを決め打ちにすると、そこで「cannot open resource」で落ちる。
# 見つかった順に使い、無ければ細い太さで代用する。デザインは少し変わるが、止まらない。
_FONT_DIRS = [
    "/usr/share/fonts/opentype/noto",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/opentype/noto-cjk",
    "/System/Library/Fonts",                       # Mac
    "C:/Windows/Fonts",                            # Windows
]


def _find_font(*names):
    """候補の名前を順に探して、最初に見つかったパスを返す。"""
    for name in names:
        for d in _FONT_DIRS:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    raise RuntimeError(
        "日本語フォントが見つかりません。"
        "GitHub Actions で動かす場合は fonts-noto-cjk と fonts-noto-cjk-extra を "
        "インストールするステップが必要です。")


BLACK_F = _find_font("NotoSansCJK-Black.ttc", "NotoSansCJK-Bold.ttc",
                     "NotoSansCJK-Regular.ttc", "NotoSansJP-Bold.otf")
BOLD_F = _find_font("NotoSansCJK-Bold.ttc", "NotoSansCJK-Regular.ttc",
                    "NotoSansJP-Bold.otf")
MED_F = _find_font("NotoSansCJK-Medium.ttc", "NotoSansCJK-Regular.ttc",
                   "NotoSansJP-Regular.otf")

_cache = {}


def _f(p, s):
    return ImageFont.truetype(p, s)


# AIみるくの切り抜きPNGの場所。
# ■ なぜ「このファイルからの相対」で組み立てるのか
# ただの "milk_cutout.png" だと「いま実行している場所」基準で探すため、
# 手元では動くのにGitHub Actions（リポジトリのルートで実行）では見つからない。
# __file__（このファイル自身の場所）を起点にすれば、どこから実行しても同じ場所を指す。
_MILK_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "milk_cutout.png"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "milk_cutout.png"),
    "milk_cutout.png",
]


def _milk(h, src=None):
    if src is None:
        for c in _MILK_CANDIDATES:
            if os.path.exists(c):
                src = c
                break
        else:
            # AIみるくがいない投稿は「壊れた画像」ではなく「別人の投稿」。
            # 写真やフォントと違って代用が利かないので、ここは止める。
            # このファイルはリポジトリに入っているので、無い＝配置ミス。直せば二度と起きない。
            raise FileNotFoundError(
                "assets/milk_cutout.png が見つかりません。"
                "リポジトリの assets フォルダに切り抜きPNGがあるか確認してください。")
    k = (src, h)
    if k not in _cache:
        im = Image.open(src)
        _cache[k] = im.resize((int(im.width * h / im.height), h), Image.LANCZOS)
    return _cache[k]


def _wrap(d, text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if d.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def _wrap_cap(d, text, font, max_w, max_lines):
    """折り返した上で、行数を超えたぶんは「…」で打ち切る。

    自動投稿では、3号さんが備考欄に長い文章を書いた回に
    文字が枠からはみ出して事故になる。入り切らないことを前提に、
    必ず枠内で収まるところまでで切る。
    """
    lines = _wrap(d, text, font, max_w)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines


# AIみるくは画像の右下に立つので、文字はここより右に置かない。
# （高さ300で貼ると幅238。右端から60余白なので x=782 から先はAIみるくの領域）
TEXT_L, TEXT_R = 90, 770


# 写真を使った枚に入れる注釈。
# ■ なぜ必要か
# 花火の記事に花火の写真が載っていれば、読む人は「その行事の写真」だと受け取る。
# うちの写真は季節の風景（イメージ）なので、そのまま出すと誤認になる。
# 免責文では防げない種類の誤解なので、写真そのものに注釈を焼き込む。
# イラスト（モチーフ）の枚には入れない。イラストを実写と誤認する人はいないため。
PHOTO_NOTE = "※写真はイメージ（季節の風景）で、イベント当日のものではありません"


def _fill(src_path, motif, bw, bh, anchor="center"):
    """指定サイズいっぱいに画像を配置（センタークロップ）。

    戻り値は (画像, 写真を使ったかどうか)。
    「写真を使ったか」を返すのは、写真の枚にだけ注釈を入れるため。
    anchor="top" にすると上寄せで切る。人物や被写体が上にある縦写真向け。
    """
    # 写真が開けなかったら、止まらずにイラストへ落とす。
    # Driveには将来、想定外の形式（動画のサムネイル、壊れたファイル等）が
    # 混ざるかもしれない。1枚のせいで週の投稿ごと止めない。
    im = None
    if src_path and os.path.exists(src_path):
        try:
            im = Image.open(src_path).convert("RGB")
        except Exception as e:
            print(f"  写真が開けないためイラストに切り替え: {os.path.basename(src_path)} ({e})")
    used_photo = im is not None
    if im is None:
        im = motifs.get(motif, bh).convert("RGB")
    sc = max(bw / im.width, bh / im.height)
    im = im.resize((max(int(im.width * sc), bw), max(int(im.height * sc), bh)), Image.LANCZOS)
    left = (im.width - bw) // 2
    top = 0 if anchor == "top" else (im.height - bh) // 2
    return im.crop((left, top, left + bw, top + bh)), used_photo


def _scrim(img, box, strength=210, direction="up"):
    """写真の上に文字を置くための暗いグラデーション。

    写真は明るさがバラバラなので、そのまま白文字を置くと読めない回が出る。
    帯を敷いておけば、どんな写真でも一定の読みやすさが保証できる。
    """
    x0, y0, x1, y1 = box
    h = y1 - y0
    lay = Image.new("RGBA", (x1 - x0, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for i in range(h):
        t = i / max(h - 1, 1)
        a = int(strength * (t if direction == "down" else (1 - t)) ** 1.4)
        d.line([(0, i), (x1 - x0, i)], fill=(30, 22, 18, a))
    img.paste(Image.alpha_composite(
        img.crop(box).convert("RGBA"), lay).convert("RGB"), (x0, y0))


def auto_strength(img, box, target=95, lo=90, hi=250):
    """写真の明るさを測って、スクリムの濃さを自動で決める。

    明るい写真（雪原、青空）は強く暗くしないと白文字が読めない。
    暗い写真（夜の花火）に同じ濃さをかけると真っ黒に潰れる。
    文字を置く範囲の平均の明るさを実際に測って、必要な分だけかける。
    自動投稿では「どんな写真が来るか分からない」ので、この判定が要る。
    """
    reg = img.crop(box).convert("L").resize((32, 32))
    px = list(reg.getdata())
    mean = sum(px) / len(px)
    need = (mean - target) / 255 * 420
    return int(max(lo, min(hi, need)))


def _footer(d):
    d.rectangle([0, H - FOOT, W, H], fill=RED)
    ft = _f(BOLD_F, 30)
    d.text((60, H - FOOT // 2), "温泉旅館みたけ ｜ 箱根・仙石原", font=ft, fill=WHITE, anchor="lm")
    d.text((W - 60, H - FOOT // 2), HANDLE, font=ft, fill=(255, 220, 214), anchor="rm")


# ==================================================== A案：全面写真＋下部カード
def event_full(ev, week):
    # ── 先に文字を組み立てて、カードの高さを決める ──────────────
    # 先に高さを測っておかないと、備考が長い回にカードから文字があふれる。
    # 「文字の量に合わせてカードを伸ばす」ほうが、事故が起きない。
    md = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tf = _f(BLACK_F, 58)
    lf = _f(BLACK_F, 28)
    vf = _f(BOLD_F, 34)
    nf = _f(MED_F, 30)

    title_lines = _wrap_cap(md, ev["title"], tf, TEXT_R - TEXT_L, 2)

    # ■ なぜカードの中にも日付を入れるのか（2026-08-14 追加）
    # 日付は左上の赤いピルにも出しているが、あれは写真の上に乗っている。
    # 写真が明るい回や、細かい模様の上に来た回は、そこだけ読み飛ばされる。
    # 実際に9月号で「日付が入っていない」と読まれた。
    # 場所・時間と同じ並びに置けば、目線が下に落ちたところで必ず一度は通る。
    # ピルは残す。遠目でわかる「いつの話か」の役と、
    # カードの中の「この行事は何日か」の役は、別のもの。
    rows = []
    if ev.get("date"):
        rows.append(("日付", _wrap_cap(md, ev["date"], vf, TEXT_R - 175, 1), RED))
    for label, key in (("場所", "place"), ("時間", "time"), ("規模", "scale")):
        if ev.get(key):
            rows.append((label, _wrap_cap(md, ev[key], vf, TEXT_R - 175, 2), DARK))
    note_lines = _wrap_cap(md, ev["note"], nf, TEXT_R - TEXT_L, 2) if ev.get("note") else []

    card_h = 44 + 74 * len(title_lines) + 14
    for _, vls, _color in rows:
        card_h += 52 * len(vls)
    if note_lines:
        card_h += 6 + 42 * len(note_lines)
    card_h = max(card_h + 40, 300)
    CY = H - FOOT - 40 - card_h

    img = Image.new("RGB", (W, H), CREAM)
    photo, used_photo = _fill(ev.get("photo"), ev.get("motif") or week.get("motif", "通年"),
                              W, H - FOOT, anchor=ev.get("anchor", "center"))
    img.paste(photo, (0, 0))
    # 上下にスクリム。濃さは写真の明るさから自動で決める
    _scrim(img, (0, 0, W, 300), auto_strength(img, (0, 0, W, 200), 90, 60, 200), "up")
    _scrim(img, (0, CY - 230, W, H - FOOT),
           auto_strength(img, (0, CY - 90, W, CY + 50), 95, 70, 215), "down")
    d = ImageDraw.Draw(img)

    # 日付のピル。日付の長さは「8/3 (月)」から「7/31 (金)〜8/5」まで幅が変わるので、
    # 幅を決め打ちにすると長い回に文字がはみ出す。文字を測ってから描く。
    dtf = _f(BLACK_F, 42)
    pill_r = 60 + 40 + int(md.textlength(ev["date"], font=dtf)) + 40
    d.rounded_rectangle([60, 60, pill_r, 132], radius=36, fill=RED)
    d.text(((60 + pill_r) // 2, 96), ev["date"], font=dtf, fill=WHITE, anchor="mm")
    if ev.get("category"):
        d.text((pill_r + 30, 96), ev["category"], font=_f(BOLD_F, 32),
               fill=(255, 246, 236), anchor="lm")

    # 情報カード
    d.rounded_rectangle([50, CY, W - 50, H - FOOT - 40], radius=36, fill=CREAM)

    y = CY + 44
    for ln in title_lines:
        d.text((TEXT_L, y), ln, font=tf, fill=DARK)
        y += 74
    y += 14
    for label, vls, color in rows:
        d.text((TEXT_L, y), label, font=lf, fill=RED)
        for vl in vls:
            d.text((175, y), vl, font=vf, fill=color)
            y += 52
    if note_lines:
        y += 6
        for ln in note_lines:
            d.text((TEXT_L, y), ln, font=nf, fill=(96, 80, 70))
            y += 42

    # 写真の枚にだけ、注釈を入れる（イラストの枚には入れない）
    # 場所はカードのすぐ上・左寄せ。右上は日付ピル、右下はAIみるくがいるため。
    if used_photo:
        d.text((60, CY - 22), PHOTO_NOTE, font=_f(MED_F, 22),
               fill=(255, 255, 255), anchor="lm")

    m = _milk(300)
    img.paste(m, (W - m.width - 60, H - FOOT - 60 - m.height), m)
    _footer(d)
    return img


def cover_full(week):
    img = Image.new("RGB", (W, H), CREAM)
    photo, used_photo = _fill(week.get("photo"), week.get("motif", "通年"),
                              W, H - FOOT, anchor=week.get("anchor", "center"))
    img.paste(photo, (0, 0))
    _scrim(img, (0, 0, W, H - FOOT),
           auto_strength(img, (0, H - FOOT - 460, W, H - FOOT), 78, 110, 250), "down")
    _scrim(img, (0, 0, W, 340), auto_strength(img, (0, 0, W, 200), 95, 60, 190), "up")
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([60, 60, 460, 132], radius=36, fill=RED)
    d.text((260, 96), "温泉旅館みたけ", font=_f(BLACK_F, 38), fill=WHITE, anchor="mm")
    if used_photo:
        d.text((W - 60, 178), PHOTO_NOTE, font=_f(MED_F, 22),
               fill=(255, 255, 255), anchor="rm")

    # 見出しは差し替えられるようにしてある（週次と月次で同じ部品を使うため）。
    # 下線の長さは見出しの実寸から出す。決め打ちだと「10月の箱根」で長すぎ、
    # 「今週のおしらせ」で短すぎ、どちらかが必ずみっともなくなる。
    t1 = week.get("title1", "AIみるくの")
    t2 = week.get("title2", "今週のおしらせ")
    lead = week.get("lead", "箱根・仙石原まわりの予定を\nAIみるくがまとめてお届けするにゃ")
    tf = _f(BLACK_F, 88)

    y = H - FOOT - 470
    d.text((70, y), t1, font=tf, fill=WHITE)
    d.text((70, y + 104), t2, font=tf, fill=(255, 214, 206))
    d.line([74, y + 226, 74 + int(d.textlength(t2, font=tf)), y + 226],
           fill=(255, 160, 148), width=8)
    d.text((70, y + 254), week.get("range", ""), font=_f(BOLD_F, 42), fill=(255, 238, 230))
    d.text((70, y + 320), lead, font=_f(MED_F, 32), fill=(255, 234, 226), spacing=12)

    m = _milk(360)
    img.paste(m, (W - m.width - 40, H - FOOT - m.height), m)
    _footer(d)
    return img


# ==================================================== B案：縦2分割
def event_split(ev, week):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    for yy in range(0, H, 48):
        for xx in range(0, W, 48):
            d.ellipse([xx, yy, xx + 4, yy + 4], fill=(244, 234, 213))

    PW = 560                              # 写真の幅。560×1272 ≒ 0.44 で縦写真に近い
    ph, ph_used = _fill(ev.get("photo"), ev.get("motif") or week.get("motif", "通年"),
                        PW, H - FOOT, anchor=ev.get("anchor", "center"))
    img.paste(ph, (0, 0))

    d = ImageDraw.Draw(img)
    x = PW + 46
    d.rounded_rectangle([x, 70, x + 210, 142], radius=36, fill=RED)
    d.text((x + 105, 106), ev["date"], font=_f(BLACK_F, 38), fill=WHITE, anchor="mm")
    if ev.get("category"):
        d.text((x, 176), ev["category"], font=_f(BOLD_F, 28), fill=GRAY)

    y = 226
    ft = _f(BLACK_F, 50)
    for ln in _wrap(d, ev["title"], ft, W - x - 40)[:3]:
        d.text((x, y), ln, font=ft, fill=DARK)
        y += 64
    y += 20
    for label, key in (("場所", "place"), ("時間", "time"), ("規模", "scale")):
        if ev.get(key):
            d.text((x, y), label, font=_f(BLACK_F, 26), fill=RED)
            y += 36
            for ln in _wrap(d, ev[key], _f(BOLD_F, 32), W - x - 40)[:2]:
                d.text((x, y), ln, font=_f(BOLD_F, 32), fill=DARK)
                y += 44
            y += 10
    if ev.get("note"):
        y += 8
        for ln in _wrap(d, ev["note"], _f(MED_F, 28), W - x - 40)[:5]:
            d.text((x, y), ln, font=_f(MED_F, 28), fill=(96, 80, 70))
            y += 40

    m = _milk(300)
    img.paste(m, (W - m.width - 20, H - FOOT - m.height - 10), m)
    if ev.get("milk"):
        d.rounded_rectangle([x - 10, H - FOOT - 400, W - 30, H - FOOT - 290],
                            radius=26, fill=SOFT)
        d.multiline_text((x + 16, H - FOOT - 376), ev["milk"],
                         font=_f(BOLD_F, 30), fill=RED, spacing=10)
    _footer(d)
    return img


def cover_split(week):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    for yy in range(0, H, 48):
        for xx in range(0, W, 48):
            d.ellipse([xx, yy, xx + 4, yy + 4], fill=(244, 234, 213))
    PW = 560
    cph, _cused = _fill(week.get("photo"), week.get("motif", "通年"), PW, H - FOOT,
                        anchor=week.get("anchor", "center"))
    img.paste(cph, (0, 0))
    d = ImageDraw.Draw(img)
    x = PW + 46
    d.rounded_rectangle([x, 80, x + 380, 152], radius=36, fill=RED)
    d.text((x + 190, 116), "温泉旅館みたけ", font=_f(BLACK_F, 34), fill=WHITE, anchor="mm")
    d.text((x, 214), "AIみるくの", font=_f(BLACK_F, 62), fill=DARK)
    d.text((x, 292), "今週の", font=_f(BLACK_F, 62), fill=RED)
    d.text((x, 370), "おしらせ", font=_f(BLACK_F, 62), fill=RED)
    d.line([x + 4, 470, x + 300, 470], fill=(240, 160, 147), width=8)
    d.text((x, 500), week.get("range", ""), font=_f(BOLD_F, 32), fill=GRAY)
    d.text((x, 566), "箱根・仙石原の\n予定をAIみるくが\nまとめてお届け\nするにゃ",
           font=_f(MED_F, 32), fill=DARK, spacing=14)
    m = _milk(330)
    img.paste(m, (W - m.width - 20, H - FOOT - m.height - 10), m)
    _footer(d)
    return img


# ==================================================== 締め（共通）
DISCLAIMER = ("AIみるくはAIだから、まちがえることもあるのにゃ！\n"
              "ごめんにゃ！おでかけ前に、主催者さんの\n"
              "公式おしらせで確認してほしいにゃ")


def closing(week):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    for yy in range(0, H, 48):
        for xx in range(0, W, 48):
            d.ellipse([xx, yy, xx + 4, yy + 4], fill=(244, 234, 213))
    m = _milk(500)
    img.paste(m, ((W - m.width) // 2, 80), m)
    d.text((W // 2, 640), week.get("closing", "今週も、いい箱根を にゃ"),
           font=_f(BLACK_F, 58), fill=DARK, anchor="mm")
    d.rounded_rectangle([60, 710, 1020, 1030], radius=32, fill=WHITE, outline=RED, width=5)
    d.text((W // 2, 758), "おことわり", font=_f(BLACK_F, 36), fill=RED, anchor="mm")
    d.multiline_text((W // 2, 872), DISCLAIMER, font=_f(BOLD_F, 38), fill=DARK,
                     anchor="mm", align="center", spacing=16)
    # 出典は長くなりがち（情報源が3つ並ぶ週もある）ので、枠の幅で折り返す。
    # 2行に収まらない分は「…」で切る。枠からのはみ出しだけは絶対にさせない。
    src_font = _f(MED_F, 24)
    src_lines = _wrap_cap(d, f"出典：{week.get('sources', '箱根町ホームページ')}",
                          src_font, 860, 2)
    sy = 990 - (len(src_lines) - 1) * 16
    for ln in src_lines:
        d.text((W // 2, sy), ln, font=src_font, fill=GRAY, anchor="mm")
        sy += 32
    d.text((W // 2, 1100), "温泉旅館みたけ", font=_f(BLACK_F, 46), fill=RED, anchor="mm")
    d.text((W // 2, 1165), "箱根・仙石原　白いにごり湯の宿", font=_f(MED_F, 30), fill=GRAY, anchor="mm")
    _footer(d)
    return img


LAYOUTS = {
    "full": (cover_full, event_full),
    "split": (cover_split, event_split),
}


def build(week, layout="full", outdir="out_v", prefix="v"):
    cover, event = LAYOUTS[layout]
    os.makedirs(outdir, exist_ok=True)
    imgs = [cover(week)] + [event(e, week) for e in week.get("events", [])[:8]] + [closing(week)]
    paths = []
    for i, im in enumerate(imgs):
        # ■ なぜJPEGなのか（PNGではダメ）
        # Instagramのコンテンツ公開APIは JPEG しか受け付けない。
        # PNGを渡すと、投稿の直前に「画像の処理に失敗」で落ちる。
        # 原因がURLにあるのか画像にあるのか分からない失敗の仕方をするので、
        # ここで確実にJPEGにしておく。
        p = os.path.join(outdir, f"{prefix}_{layout}_{i + 1:02d}.jpg")
        im.convert("RGB").save(p, "JPEG", quality=92, optimize=True, subsampling=1)
        paths.append(p)
    return paths
