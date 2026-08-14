"""週データから、投稿画像一式とキャプションを作る入口。

レイアウトの中身は layouts_v.py にある。
ここは「A案（全面写真）で組み立てる」という方針を固定するだけの薄い層。
将来レイアウトを変えたくなったら、ここ1行を差し替えれば全体が切り替わる。
"""
from pathlib import Path
import layouts_v

LAYOUT = "full"          # A案（全面写真＋下部カード）

DISCLAIMER_LINES = [
    "──────────",
    "※AIみるくはAIだから、まちがえることもあるのにゃ！ごめんにゃ！",
    "おでかけ前に、主催者さんの公式おしらせで確認してほしいにゃ🙏",
]

HASHTAGS = ("#箱根 #仙石原 #温泉旅館みたけ #箱根イベント #地域のおしらせ "
            "#AIみるく #箱根旅行 #箱根温泉 #ボードゲーム")


def build_week_images(week, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths = layouts_v.build(week, LAYOUT, outdir=str(outdir), prefix="p")
    return [Path(p) for p in paths]


def build_caption(week):
    """投稿本文。免責文と出典は必ず入る（データ側から消せない）。

    見出しと書き出しは week 側から差し替えられる（週次と月次で共用するため）。
    差し替えても、免責文・出典・ハッシュタグは必ず付く。ここは動かせない。
    """
    L = [week.get("caption_head", "🐾 AIみるくの今週のおしらせ にゃ"), ""]
    L.append("こんにちは、温泉旅館みたけの看板猫、AIみるくだにゃ。")
    L.append(week.get("caption_lead",
                      "今週の箱根・仙石原のイベントを、AIみるくがまとめてお届けするにゃ！"))
    L.append("")
    for ev in week.get("events", []):
        L.append(f"📅 {ev['date']}　{ev['title']}")
        line = ""
        if ev.get("place"):
            line += f"📍{ev['place']}"
        if ev.get("time"):
            line += f"　{ev['time']}"
        if line:
            L.append(line)
        if ev.get("note"):
            L.append(ev["note"])
        L.append("")
    L += DISCLAIMER_LINES
    L.append(f"（出典：{week.get('sources', '箱根町ホームページ')}）")
    L.append("──────────")
    L.append("")
    L.append(HASHTAGS)
    return "\n".join(L)
