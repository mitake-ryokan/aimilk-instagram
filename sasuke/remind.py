"""明日の投稿を、前日にLINEで知らせる。

■ これは何か
毎週金曜18時（JST）に動いて、「明日の土曜20時に何が出るか」をLINEに送る。

■ なぜ前日なのか
投稿してしまうと、Instagramは写真を差し替えられない。
緑の代替パネルで出たあとに「写真を撮ろう」と思っても、その回は直せない。
だから、気づくタイミングを投稿の後ろから前に動かす。前日なら撮り直せる。

■ 何も投稿しない
このスクリプトは queue.json と state を読むだけで、画像も作らないし投稿もしない。
LINEの設定が無いときは、ログに出して静かに終わる。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_card
import notify_line

QUEUE = HERE / "queue.json"
STATE = ROOT / "state" / "sasuke_posted.json"


def load_posted():
    if STATE.exists():
        try:
            return set(int(v) for v in json.loads(STATE.read_text())["posted"])
        except Exception:
            pass
    return set()


def main():
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    posted = load_posted()
    remaining = [e for e in queue if int(e["vol"]) not in posted]

    if not remaining:
        notify_line.send(
            "【サスケのボドゲ棚】\n"
            "明日の投稿はありません。キューを使い切っています。\n"
            "次の回を用意してください。")
        print("■ キューが空です")
        return 0

    entry = min(remaining, key=lambda e: int(e["vol"]))
    vol = int(entry["vol"])
    name = entry.get("display") or entry["game"]
    photo = make_card.find_photo(vol, name)

    if photo:
        photo_line = f"写真は入っています（{photo.name}）"
    else:
        photo_line = ("写真がありません。このままだと深緑のパネルで出ます。\n"
                      f"撮るなら sasuke/photos/{name}.jpg に置いてください。\n"
                      "投稿したあとは写真を差し替えられません。")

    notify_line.send(
        "【サスケのボドゲ棚】明日の投稿\n"
        f"vol.{vol:02d}『{name}』\n"
        f"{entry.get('serif','')}\n\n"
        f"{photo_line}\n\n"
        f"このあとの残りは {len(remaining) - 1} 本です。")
    print(f"■ 明日は vol.{vol:02d}『{name}』／写真: {'あり' if photo else 'なし'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
