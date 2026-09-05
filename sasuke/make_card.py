"""「サスケのボドゲ棚」の紹介カードを1枚描く。

■ これは何か
MITAKE CATS のサスケが、みたけのプレイルームに置いてあるボードゲームを1つずつ紹介する
投稿画像（1080×1350のJPEG）を作る。毎週土曜の投稿枠で使う。

■ デザイン（2026-09-04 全面刷新）
上52%が写真、下がクリームの帯。文字はすべてクリームの上に置く。
写真が明るくても暗くても文字が読めなくなることがない、という一点でこの形にしている。
以前の「深緑の枠の中に白いカード、その中に吹き出し」という三重の囲みは廃止した。

■ 写真の置き場所
    sasuke/photos/vol01.jpg  … vol番号で置く（拡張子は .jpg / .jpeg / .png）
    sasuke/photos/宝石の煌き.jpg … ゲーム名で置いてもよい
どちらも無ければ、深緑の地に MITAKE CATS ロゴを置いた代替パネルを描く。
写真が無い週でも投稿は止まらない。

■ このファイル単体でも試せる
    python sasuke/make_card.py --vol 1 --game "宝石の煌き" --serif "…" --out /tmp/card.jpg

■ 日本語の折り返し（禁則処理）
行頭に句読点・小書き仮名・長音符を置かない。置きたくなったら前の行にぶら下げる。
"""
import argparse
import csv
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- 素材の場所
GAMES_CSV = HERE / "games.csv"
FACE_PNG = HERE / "assets" / "sasuke_face.png"
LOGO_PNG = HERE / "assets" / "mitakecats_logo.png"
PHOTO_DIR = HERE / "photos"          # 無くてもよい

# ---------------------------------------------------------------- CSVの列名
COL_NAME = "ゲーム名"
COL_PLAYERS = "プレイ人数"
COL_TIME = "プレイ時間"
COL_AGE = "対象年齢"
COL_YEAR = "発売年"

# 下部に出すスペック3行。（表示ラベル, CSVの列名）。
# 4行あった「うまれた年」は落とした。投稿を見る人が知りたい情報ではないため。
SPEC_ROWS = [
    ("あそぶ人数", COL_PLAYERS),
    ("あそぶ時間", COL_TIME),
    ("対象年齢", COL_AGE),
]

# ---------------------------------------------------------------- 色
CREAM = (255, 240, 215)
GREEN = (62, 107, 79)
GOLD = (212, 164, 74)
INK = (48, 44, 40)
GRAY = (150, 142, 132)
WHITE = (255, 255, 255)

W, H = 1080, 1350
PHOTO_H = 700          # 写真の高さ
BAR_H = 88             # 下帯の高さ
MARGIN = 80            # 左右の余白

# ---------------------------------------------------------------- フォント探索
_FONT_DIRS = [
    "/usr/share/fonts/opentype/noto",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/opentype/noto-cjk",
    "/System/Library/Fonts",
    "C:/Windows/Fonts",
]


def _find_font(*names):
    for name in names:
        for d in _FONT_DIRS:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    raise RuntimeError(
        "日本語フォントが見つかりません。GitHub Actions では fonts-noto-cjk を "
        "入れるステップが必要です（ワークフローに用意してあります）。")


BLACK_F = _find_font("NotoSansCJK-Black.ttc", "NotoSansJP-Black.otf",
                     "NotoSansCJK-Bold.ttc", "NotoSansJP-Bold.otf",
                     "NotoSansCJK-Regular.ttc", "NotoSansJP-Regular.otf")
BOLD_F = _find_font("NotoSansCJK-Bold.ttc", "NotoSansJP-Bold.otf",
                    "NotoSansCJK-Regular.ttc", "NotoSansJP-Regular.otf")
MED_F = _find_font("NotoSansCJK-Medium.ttc", "NotoSansJP-Medium.otf",
                   "NotoSansCJK-Regular.ttc", "NotoSansJP-Regular.otf")


def _f(path, size):
    return ImageFont.truetype(path, size)


# ---------------------------------------------------------------- 禁則処理
HEAD_NG = set(
    "、。，．,.・：；:;！？!?)]｝）」』】〕〉》〙〗’”"
    "ぁぃぅぇぉっゃゅょゎ"
    "ァィゥェォッャュョヮ"
    "ー〜~々ヽヾゝゞ"
)


def _wrap(d, text, font, max_w):
    """max_w に収まるように折り返す。禁則（行頭の追い出し＝ぶら下げ）つき。"""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if cur and d.textlength(cur + ch, font=font) > max_w:
            if ch in HEAD_NG:
                cur += ch
                lines.append(cur)
                cur = ""
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- CSV
_games_cache = None


def load_games(path=None):
    global _games_cache
    path = Path(path) if path else GAMES_CSV
    if _games_cache is None:
        if not path.exists():
            raise FileNotFoundError(
                f"ボードゲーム一覧CSVが見つかりません: {path}\n"
                f"ヘッダーは「{COL_NAME},{COL_PLAYERS},{COL_TIME},{COL_AGE},{COL_YEAR}」です。")
        with open(path, encoding="utf-8-sig", newline="") as fp:
            _games_cache = list(csv.DictReader(fp))
    return _games_cache


def _first_alias(name):
    """「ごいた / ごいたカード / 天九紙牌」→「ごいた」。表示・照合用の代表名。"""
    return (name or "").split("/")[0].strip()


def lookup(query, path=None):
    """完全一致 → 代表名一致 → 部分一致 の順で1件探す。"""
    q = (query or "").strip()
    rows = load_games(path)
    for row in rows:
        if (row.get(COL_NAME) or "").strip() == q:
            return row
    for row in rows:
        if _first_alias(row.get(COL_NAME)) == q:
            return row
    for row in rows:
        if q and q in (row.get(COL_NAME) or ""):
            return row
    return None


def _tidy(value):
    """「1995年～」「2人～4人」の全角チルダを、見た目のよい「〜」にそろえる。"""
    return (value or "").strip().replace("～", "〜")


def specs_of(row):
    out = []
    for label, col in SPEC_ROWS:
        out.append((label, _tidy(row.get(col)) or "—"))
    return out


# ---------------------------------------------------------------- 部品
def find_photo(vol, game):
    """この回に使う写真を探す。無ければ None。

    vol番号でもゲーム名でも置けるようにしてある。撮った写真をそのまま
    「vol03.jpg」で放り込めば済む、という運用にしたいため。
    """
    if not PHOTO_DIR.exists():
        return None
    stems = [f"vol{int(vol):02d}", str(game), _first_alias(str(game))]
    for stem in stems:
        for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
            p = PHOTO_DIR / (stem + ext)
            if p.exists():
                return p
    return None


def _cover(im, w, h):
    """はみ出す分を切り落として、w×h をぴったり埋める（CSSの object-fit: cover）。"""
    src_r = im.width / im.height
    dst_r = w / h
    if src_r > dst_r:                      # 横に長い → 左右を切る
        nh = im.height
        nw = int(nh * dst_r)
        left = (im.width - nw) // 2
        im = im.crop((left, 0, left + nw, nh))
    else:                                  # 縦に長い → 上下を切る
        nw = im.width
        nh = int(nw / dst_r)
        top = int((im.height - nh) * 0.4)   # 気持ち上寄り。料理も卓上も上に主役が来る
        im = im.crop((0, top, nw, top + nh))
    return im.resize((w, h), Image.LANCZOS)


def _logo(height, tint=GREEN):
    """MITAKE CATS ロゴ。白背景を透過させ、黒い線を tint 色に着色して返す。

    素材は「白地に黒線」のPNG。そのまま貼るとロゴのまわりに白い四角が乗る。
    明るさだけの画像にして輝度を反転し、「線の濃さ」をそのまま不透明度に使う。
    """
    if not LOGO_PNG.exists():
        raise FileNotFoundError(
            f"MITAKE CATS ロゴが見つかりません: {LOGO_PNG}")
    im = Image.open(LOGO_PNG).convert("L")
    inv = ImageOps.invert(im)
    bbox = inv.getbbox()
    if bbox:
        im = im.crop(bbox)
    w = max(1, int(im.width * height / im.height))
    im = im.resize((w, height), Image.LANCZOS)
    alpha = im.point(lambda p: 255 - p)
    out = Image.new("RGBA", im.size, tuple(tint) + (0,))
    out.putalpha(alpha)
    return out


_face_cache = None


def _sasuke_cutout(width):
    """サスケのイラストを、背景（クリームのベタ）を抜いて返す。

    以前は円形に切り抜いていたが、全身のイラストを円に押し込むと頭も体も
    窮屈になる。背景の色を抜いて、輪郭のまま置くほうが素材が生きる。
    """
    global _face_cache
    if _face_cache is None:
        if not FACE_PNG.exists():
            raise FileNotFoundError(f"サスケの画像が見つかりません: {FACE_PNG}")
        im = Image.open(FACE_PNG).convert("RGB")
        px = im.load()
        bg = px[2, 2]                       # 四隅は必ず背景色
        mask = Image.new("L", im.size, 255)
        mp = mask.load()
        for y in range(im.height):
            for x in range(im.width):
                r, g, b = px[x, y]
                if (abs(r - bg[0]) < 14 and abs(g - bg[1]) < 14
                        and abs(b - bg[2]) < 14):
                    mp[x, y] = 0
        out = im.convert("RGBA")
        out.putalpha(mask)
        _face_cache = out.crop(out.getbbox())
    im = _face_cache
    h = int(im.height * width / im.width)
    return im.resize((width, h), Image.LANCZOS)


def _photo_panel(vol, game):
    """上部に置く 1080×PHOTO_H の絵を作る。写真があれば写真、無ければ代替パネル。"""
    p = find_photo(vol, game)
    if p:
        return _cover(Image.open(p).convert("RGB"), W, PHOTO_H)

    # --- 写真が無い週の代替パネル -------------------------------------
    # 深緑の地に、うすい菱形の連続模様とロゴ。「写真の撮り忘れ」ではなく
    # 「そういうデザイン」に見えることを狙っている。
    panel = Image.new("RGB", (W, PHOTO_H), GREEN)
    d = ImageDraw.Draw(panel)
    step = 96
    for gy in range(-step, PHOTO_H + step, step):
        for gx in range(-step, W + step, step):
            off = step // 2 if (gy // step) % 2 else 0
            cx, cy, r = gx + off, gy, 13
            d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                      fill=(74, 122, 92))
    logo = _logo(190, tint=(228, 216, 188))
    panel.paste(logo, ((W - logo.width) // 2 - 60,
                       (PHOTO_H - logo.height) // 2 - 30), logo)
    return panel


def _vgrad(w, h, color, top_a, bot_a):
    """上から下へ濃さの変わる幕。写真の上に置く白文字を読ませるために使う。"""
    l = Image.new("L", (1, h))
    lp = l.load()
    for y in range(h):
        t = y / max(1, h - 1)
        lp[0, y] = int(top_a + (bot_a - top_a) * t)
    l = l.resize((w, h))
    out = Image.new("RGBA", (w, h), tuple(color) + (0,))
    out.putalpha(l)
    return out


def _fit_game(d, name, max_w):
    """ゲーム名の文字サイズを決める。

    まず1行に収まる最大サイズを探す。ゲーム名は「見出し」なので、
    折り返すと途端に見出しに見えなくなるため、1行を強く優先する。
    どうしても1行に入らない長い名前だけ、小さめの2行に落とす。
    """
    for size in (104, 92, 82, 72, 64):
        font = _f(BLACK_F, size)
        if len(_wrap(d, name, font, max_w)) == 1:
            return font, [name], size
    font = _f(BLACK_F, 64)
    return font, _wrap(d, name, font, max_w)[:2], 64


# ---------------------------------------------------------------- 本体
def render(vol, game, serif, out_path, csv_path=None, display=None):
    """カードを1枚描いて out_path に保存する。表示に使ったゲーム名を返す。

    display を渡すと、カードに大きく出す名前だけを差し替えられる。
    CSVには版まで入った名前（「カタン：カプコン版」）で載っているが、
    見出しとしては「カタン」と出したい、というときに使う。
    スペックの引き当てには game（CSVの名前）を使うので、数字はずれない。
    """
    row = lookup(game, csv_path)
    if row is None:
        raise SystemExit(
            f"ゲーム『{game}』が {GAMES_CSV.name} に見つかりません。"
            "queue.json のゲーム名を、CSVに実在する名前にしてください。")
    display_name = (display or "").strip() or _first_alias(row.get(COL_NAME)) or game
    specs = specs_of(row)

    img = Image.new("RGB", (W, H), CREAM)
    img.paste(_photo_panel(vol, display_name), (0, 0))

    # 写真の上端を少しだけ暗くする。白いプレートの文字を確実に読ませるため。
    scrim = _vgrad(W, 300, (14, 26, 20), 140, 0)
    img.paste(scrim, (0, 0), scrim)

    d = ImageDraw.Draw(img)

    # --- 左上：シリーズ名のプレート -----------------------------------
    pf = _f(BOLD_F, 36)
    label = "サスケのボドゲ棚"
    tw = d.textlength(label, font=pf)
    d.rounded_rectangle((64, 60, 64 + tw + 52, 140), radius=40, fill=GREEN)
    d.text((90, 80), label, font=pf, fill=WHITE)

    # --- サスケ（写真とクリームの境目にまたがせる） --------------------
    cat_w = 320
    cat = _sasuke_cutout(cat_w)
    img.paste(cat, (W - cat_w - 30, PHOTO_H - cat.height + 45), cat)

    # --- 下：クリームの帯 ---------------------------------------------
    # サスケは写真とクリームの境目にまたがるだけで、文字の高さまでは
    # 降りてこない。なので下の帯では左右いっぱいの幅を使える。
    x = MARGIN
    text_w = W - MARGIN * 2
    y = PHOTO_H + 56

    d.text((x, y), f"vol.{int(vol):02d}", font=_f(BOLD_F, 40), fill=GOLD)
    y += 62

    gf, glines, gsize = _fit_game(d, display_name, text_w)
    for ln in glines:
        d.text((x, y), ln, font=gf, fill=GREEN)
        y += int(gsize * 1.17)

    y += 8
    d.line((x, y, W - MARGIN, y), fill=GOLD, width=5)
    y += 40

    sf = _f(MED_F, 38)
    for ln in _wrap(d, serif, sf, text_w):
        d.text((x, y), ln, font=sf, fill=INK)
        y += 56
    y += 26

    lf = _f(MED_F, 28)
    vf = _f(BOLD_F, 36)
    cx = x
    for label_, value in specs:
        d.text((cx, y), label_, font=lf, fill=GRAY)
        d.text((cx, y + 34), value, font=vf, fill=INK)
        cx += max(d.textlength(label_, font=lf),
                  d.textlength(value, font=vf)) + 62

    # --- 下帯 ---------------------------------------------------------
    d.rectangle((0, H - BAR_H, W, H), fill=GREEN)
    bf = _f(BOLD_F, 32)
    d.text((MARGIN - 10, H - BAR_H + 26), "プレイルームで、あそべます",
           font=bf, fill=CREAM)
    handle = "@mitake_hakone"
    d.text((W - MARGIN + 10 - d.textlength(handle, font=bf), H - BAR_H + 26),
           handle, font=bf, fill=CREAM)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return display_name


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="サスケのボドゲ棚カードを1枚描く")
    ap.add_argument("--vol", type=int, required=True)
    ap.add_argument("--game", required=True, help="games.csv に実在するゲーム名")
    ap.add_argument("--serif", default="", help="ひとこと（下の帯に入る）")
    ap.add_argument("--out", required=True, help="出力先（.jpg）")
    ap.add_argument("--csv", default=None, help="CSVの場所（省略時 sasuke/games.csv）")
    ap.add_argument("--display", default=None, help="カードに出す名前（省略時はCSVの名前）")
    args = ap.parse_args(argv)
    name = render(args.vol, args.game, args.serif, args.out, args.csv, args.display)
    print(f"■ 描きました: vol.{args.vol:02d} 『{name}』 -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
