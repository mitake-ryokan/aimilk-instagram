"""「サスケのボドゲ棚」の紹介カードを1枚描く。

■ これは何か
MITAKE CATS のサスケが、みたけの蔵に置いてあるボードゲームを1つずつ紹介する
投稿画像（1080×1350のJPEG）を作る。毎週土曜の投稿枠で使う。

■ このファイル単体でも試せる
    python sasuke/make_card.py --vol 5 --game "ごいた" --serif "みんなでやると燃えるにゃ" --out /tmp/card.jpg
ゲーム名で games.csv を引いて、スペック4行（あそぶ人数／あそぶ時間／
対象年齢／うまれた年）を自動で埋める。

■ 日本語の折り返し（禁則処理）
行頭に句読点・小書き仮名・長音符を置かない。置きたくなったら前の行にぶら下げる。
「、」で行が始まる、「っ」で行が始まる、といった見た目の事故を防ぐ。
"""
import argparse
import csv
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- 素材の場所
# ここに置いてください（無いと分かるようにエラーで止まる）。
GAMES_CSV = HERE / "games.csv"                 # ボードゲーム一覧CSV
FACE_PNG = HERE / "assets" / "sasuke_face.png"  # サスケの顔（丸く切り抜いて使う）
LOGO_PNG = HERE / "assets" / "mitakecats_logo.png"  # MITAKE CATS ロゴ

# ---------------------------------------------------------------- CSVの列名
# ■ 実際のCSVのヘッダーに合わせてある（2026-08-29）
# ヘッダーを変えたくなったら、ここだけ直せばよい。
COL_NAME = "ゲーム名"
COL_PLAYERS = "プレイ人数"
COL_TIME = "プレイ時間"
COL_AGE = "対象年齢"
COL_YEAR = "発売年"

# カードに出すスペック4行。（表示ラベル, CSVの列名）。
SPEC_ROWS = [
    ("あそぶ人数", COL_PLAYERS),
    ("あそぶ時間", COL_TIME),
    ("対象年齢", COL_AGE),
    ("うまれた年", COL_YEAR),
]

# ---------------------------------------------------------------- 色
CREAM = (255, 240, 215)     # #FFF0D7 地の色
GREEN = (62, 107, 79)       # #3E6B4F 深緑（枠・見出し・ゲーム名）
GOLD = (212, 164, 74)       # #D4A44A 区切り線
RED = (196, 74, 46)         # #C44A2E 「みたけの蔵で、あそべます」
WHITE = (255, 255, 255)
INK = (60, 54, 48)          # スペックの値・セリフの文字
GRAY = (120, 112, 104)      # スペックのラベル

W, H = 1080, 1350

# ---------------------------------------------------------------- フォント探索
# ■ 環境でパスが違う（既存の投稿と同じ考え方）
# GitHub Actions では apt で /usr/share/fonts/... に入る。入らない日は
# ワークフロー側が GitHub から直接 NotoSansJP-*.otf を落として同じ場所に置く。
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
# 行頭に置いてはいけない字（句読点・閉じ括弧・小書き仮名・長音符など）。
# 行が始まりそうになったら、その字は前の行の末尾にぶら下げる。
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
                # 行頭に来てほしくない字。前の行にぶら下げてから改行する。
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
    """games.csv を読み込んで、行の並び（辞書のリスト）で返す。"""
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
    """ゲームを1件探す。見つかった行（dict）を返す。無ければ None。

    ■ 探す順番（別名がスラッシュで入っているので3段階）
      1. 完全一致（CSVのゲーム名セルと丸ごと一致）
      2. スラッシュ前の先頭名で一致（代表名が一致）
      3. 部分一致（どこかに含まれる）
    先に見つかったものを採用する。表示名はスラッシュ前の先頭名だけを使う。
    """
    q = (query or "").strip()
    rows = load_games(path)
    for row in rows:                                   # 1. 完全一致
        if (row.get(COL_NAME) or "").strip() == q:
            return row
    for row in rows:                                   # 2. 代表名で一致
        if _first_alias(row.get(COL_NAME)) == q:
            return row
    for row in rows:                                   # 3. 部分一致
        if q and q in (row.get(COL_NAME) or ""):
            return row
    return None


def _clean_year(value):
    """「1995年～」→「1995年」。末尾の「～」（波ダッシュ各種）を取り除く。"""
    return (value or "").strip().rstrip("～〜~ 　")


def specs_of(row):
    """行から、カードに出す (ラベル, 値) の4行を作る。"""
    out = []
    for label, col in SPEC_ROWS:
        value = (row.get(col) or "").strip()
        if col == COL_YEAR:
            value = _clean_year(value)
        out.append((label, value or "—"))
    return out


# ---------------------------------------------------------------- 部品
def _round_face(diameter):
    """サスケの顔を丸く切り抜いて返す。"""
    if not FACE_PNG.exists():
        raise FileNotFoundError(
            f"サスケの顔の画像が見つかりません: {FACE_PNG}\n"
            "sasuke/assets/sasuke_face.png を置いてください。")
    im = Image.open(FACE_PNG).convert("RGBA")
    # 短辺で正方形に中央クロップしてから丸くする。
    side = min(im.size)
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize(
        (diameter, diameter), Image.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    im.putalpha(mask)
    return im


def _logo(height):
    """MITAKE CATS ロゴを高さ height に合わせて返す。"""
    if not LOGO_PNG.exists():
        raise FileNotFoundError(
            f"MITAKE CATS ロゴが見つかりません: {LOGO_PNG}\n"
            "sasuke/assets/mitakecats_logo.png を置いてください。")
    im = Image.open(LOGO_PNG).convert("RGBA")
    w = int(im.width * height / im.height)
    return im.resize((w, height), Image.LANCZOS)


def _fit_game(d, name, max_w, max_lines=3):
    """ゲーム名が max_lines に収まる、いちばん大きい文字サイズを選ぶ。"""
    for size in (116, 100, 86, 74, 64, 56, 48):
        font = _f(BLACK_F, size)
        lines = _wrap(d, name, font, max_w)
        if len(lines) <= max_lines:
            return font, lines, size
    font = _f(BLACK_F, 48)
    lines = _wrap(d, name, font, max_w)[:max_lines]
    return font, lines, 48


# ---------------------------------------------------------------- 本体
def render(vol, game, serif, out_path, csv_path=None):
    """カードを1枚描いて out_path に保存する。表示に使ったゲーム名を返す。

    game は games.csv に実在する名前（別名スラッシュ可）。
    見つからなければ SystemExit で止める（黙って空のカードを出さない）。
    """
    row = lookup(game, csv_path)
    if row is None:
        raise SystemExit(
            f"ゲーム『{game}』が {GAMES_CSV.name} に見つかりません。"
            "queue.json のゲーム名を、CSVに実在する名前にしてください。")
    display_name = _first_alias(row.get(COL_NAME)) or game
    specs = specs_of(row)

    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # --- 深緑の角丸枠 ---------------------------------------------------
    d.rounded_rectangle((26, 26, W - 26, H - 26), radius=44,
                        outline=GREEN, width=10)

    # --- 左上：深緑プレート「サスケのボドゲ棚 vol.XX」 -----------------
    plate_text = f"サスケのボドゲ棚 vol.{int(vol):02d}"
    pf = _f(BOLD_F, 40)
    pad_x, pad_y = 34, 20
    tw = d.textlength(plate_text, font=pf)
    asc, desc = pf.getmetrics()
    th = asc + desc
    px0, py0 = 60, 62
    px1, py1 = px0 + tw + pad_x * 2, py0 + th + pad_y * 2
    d.rounded_rectangle((px0, py0, px1, py1), radius=22, fill=GREEN)
    d.text((px0 + pad_x, py0 + pad_y), plate_text, font=pf, fill=WHITE)

    # --- 右上：MITAKE CATS ロゴ ---------------------------------------
    logo = _logo(84)
    img.paste(logo, (W - 60 - logo.width, 66), logo)

    # --- 中央：白い角丸カード -----------------------------------------
    cx0, cy0, cx1, cy1 = 78, 250, W - 78, 980
    d.rounded_rectangle((cx0, cy0, cx1, cy1), radius=40, fill=WHITE)
    inner_l, inner_r = cx0 + 56, cx1 - 56
    inner_w = inner_r - inner_l

    # ゲーム名（深緑・特大・折り返し）
    gf, glines, gsize = _fit_game(d, display_name, inner_w, max_lines=3)
    gy = cy0 + 60
    line_h = int(gsize * 1.18)
    for ln in glines:
        lw = d.textlength(ln, font=gf)
        d.text(((cx0 + cx1) / 2 - lw / 2, gy), ln, font=gf, fill=GREEN)
        gy += line_h
    gy += 18

    # 金色の区切り線
    d.line((inner_l, gy, inner_r, gy), fill=GOLD, width=6)
    gy += 44

    # スペック4行（ラベルは灰、値は黒）
    lf = _f(MED_F, 40)
    vf = _f(BOLD_F, 44)
    label_w = max(d.textlength(lb, font=lf) for lb, _ in specs)
    row_gap = 74
    value_x = inner_l + label_w + 44
    for label, value in specs:
        d.text((inner_l, gy), label, font=lf, fill=GRAY)
        vlines = _wrap(d, value, vf, inner_r - value_x)
        d.text((value_x, gy - 4), vlines[0], font=vf, fill=INK)
        gy += row_gap

    # カード下端：赤茶「みたけの蔵で、あそべます」
    tag = "みたけの蔵で、あそべます"
    tgf = _f(BLACK_F, 44)
    tgw = d.textlength(tag, font=tgf)
    d.text(((cx0 + cx1) / 2 - tgw / 2, cy1 - 84), tag, font=tgf, fill=RED)

    # --- 下部左：サスケの丸い顔 ---------------------------------------
    face_d = 236
    face_x, face_y = 74, H - 60 - face_d
    face = _round_face(face_d)
    # 顔のふちに深緑の輪をつける（吹き出しと視覚的にそろえる）
    d.ellipse((face_x - 5, face_y - 5, face_x + face_d + 5, face_y + face_d + 5),
              outline=GREEN, width=6)
    img.paste(face, (face_x, face_y), face)

    # --- その右：白い吹き出し（セリフ） -------------------------------
    bx0 = face_x + face_d + 40
    bx1 = W - 70
    by0 = face_y - 6
    by1 = H - 74
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=34,
                        fill=WHITE, outline=GREEN, width=5)
    # しっぽ（顔のほうを指す三角）
    tail_cy = face_y + face_d // 2
    d.polygon([(bx0 + 4, tail_cy - 26), (bx0 + 4, tail_cy + 26),
               (bx0 - 30, tail_cy)], fill=WHITE, outline=GREEN)
    d.line([(bx0 + 4, tail_cy - 26), (bx0 - 30, tail_cy),
            (bx0 + 4, tail_cy + 26)], fill=GREEN, width=5)

    sf = _f(MED_F, 40)
    s_pad = 40
    slines = _wrap(d, serif, sf, (bx1 - bx0) - s_pad * 2)
    sasc, sdesc = sf.getmetrics()
    s_line_h = int((sasc + sdesc) * 1.28)
    block_h = s_line_h * len(slines)
    sy = by0 + ((by1 - by0) - block_h) // 2
    for ln in slines:
        d.text((bx0 + s_pad, sy), ln, font=sf, fill=INK)
        sy += s_line_h

    # --- 保存（JPEGのみ） ---------------------------------------------
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return display_name


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="サスケのボドゲ棚カードを1枚描く")
    ap.add_argument("--vol", type=int, required=True)
    ap.add_argument("--game", required=True, help="games.csv に実在するゲーム名")
    ap.add_argument("--serif", default="", help="吹き出しのセリフ")
    ap.add_argument("--out", required=True, help="出力先（.jpg）")
    ap.add_argument("--csv", default=None, help="CSVの場所（省略時 sasuke/games.csv）")
    args = ap.parse_args(argv)
    name = render(args.vol, args.game, args.serif, args.out, args.csv)
    print(f"■ 描きました: vol.{args.vol:02d} 『{name}』 -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
