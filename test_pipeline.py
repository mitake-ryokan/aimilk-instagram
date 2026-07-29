"""投稿システムの通しテスト（Google・Instagramにはつながない）

■ 何をテストするか
・スプレッドシートの行 → 週データ への変換が正しいか
・日付の絞り込み（今週ぶんだけ拾う）が正しいか
・複数日にまたがるイベントを取りこぼさないか
・イベントが2件未満のときにちゃんとスキップするか
・画像とキャプションが最後まで生成できるか
"""
import sys, csv, datetime as dt
from pathlib import Path
sys.path.insert(0, "aimilk/src")

import google_client as gc      # pick_week だけ使う（通信はしない）
import builder
import run_weekly as rw

rows = list(csv.DictReader(open("events_add.csv", encoding="utf-8")))
print(f"読み込み: {len(rows)}件")

ng = 0

# ---- 1. 日付の絞り込み ----------------------------------------------
def check(name, start, end, expect_names):
    global ng
    got = [e["イベント名"] for e in gc.pick_week(
        [dict(r, 掲載可否="○") for r in rows], start, end)]
    ok = set(got) == set(expect_names)
    print(f"{'OK ' if ok else 'NG '} {name}: {got}")
    if not ok:
        print(f"     期待: {expect_names}")
        ng += 1

check("8/1〜8/7の週（複数日イベントを含む）",
      dt.date(2026, 8, 1), dt.date(2026, 8, 7),
      ["芦ノ湖夏まつりウィーク", "御神幸祭", "箱根園サマーナイトフェスタ",
       "太閤ひょうたん祭", "湖尻龍神祭", "鳥居焼まつり・流燈祭"])

check("7/20〜7/26の週（長期おしらせが始まる週＝載る）",
      dt.date(2026, 7, 20), dt.date(2026, 7, 26),
      ["町立観光施設が小中学生無料"])

check("8/25〜8/31の週（長期おしらせが終わる週＝載る）",
      dt.date(2026, 8, 25), dt.date(2026, 8, 31),
      ["すすきまつり", "町立観光施設が小中学生無料"])

check("9/10〜9/16の週",
      dt.date(2026, 9, 10), dt.date(2026, 9, 16),
      ["仙石原すすきまつり"])

check("12/1〜12/7の週（何もない週）",
      dt.date(2026, 12, 1), dt.date(2026, 12, 7), [])

# ---- 2. 掲載可否のフィルタ -------------------------------------------
picked = gc.pick_week(rows, dt.date(2026, 8, 1), dt.date(2026, 8, 7))
print(f"{'OK ' if picked == [] else 'NG '} 保留の行は拾わない: {len(picked)}件")
if picked:
    ng += 1

# ---- 3. 日付表示 ------------------------------------------------------
cases = [("2026-08-02", "", "8/2 (日)"),
         ("2026-07-31", "2026-08-05", "7/31 (金)〜8/5"),
         ("2026-08-16", "2026-08-16", "8/16 (日)")]
for s, e, expect in cases:
    got = rw.fmt_date(s, e)
    ok = got == expect
    print(f"{'OK ' if ok else 'NG '} 日付表示 {s}/{e or '-'} -> {got}")
    if not ok:
        print(f"     期待: {expect}")
        ng += 1

# ---- 4. 季節判定 ------------------------------------------------------
for d, expect in [(dt.date(2026, 7, 29), "夏"), (dt.date(2026, 10, 5), "秋"),
                  (dt.date(2026, 1, 5), "冬"), (dt.date(2026, 4, 5), "春")]:
    got = rw.season_of(d)
    ok = got == expect
    print(f"{'OK ' if ok else 'NG '} 季節判定 {d} -> {got}")
    if not ok:
        ng += 1

# ---- 5. 画像とキャプションの生成 ---------------------------------------
ok_rows = [dict(r, 掲載可否="○") for r in rows]
picked = gc.pick_week(ok_rows, dt.date(2026, 8, 1), dt.date(2026, 8, 7))[:8]
week = {
    "range": "2026.8.1 〜 8.7", "motif": "夏",
    "sources": "、".join(sorted({e["情報源"] for e in picked if e["情報源"]})),
    "photo": "photos/20240801_132515000_iOS.jpg",
    "events": [{
        "date": rw.fmt_date(e["開始日"], e["終了日"]),
        "category": e["区分"], "title": e["イベント名"], "place": e["場所"],
        "time": e["時間"], "scale": e["規模・備考"], "note": e["みるくコメント"],
        "motif": e["モチーフ"] or "夏", "photo": "",
    } for e in picked],
}
paths = builder.build_week_images(week, "test_out")
cap = builder.build_caption(week)
print(f"OK  画像生成: {len(paths)}枚")
print(f"{'OK ' if len(cap) <= 2200 else 'NG '} キャプション長: {len(cap)}文字（上限2200）")
if len(cap) > 2200:
    ng += 1
if "AIみるくはAIだから" not in cap:
    print("NG  免責文が入っていない")
    ng += 1
else:
    print("OK  免責文あり")
import re
bare = re.findall(r"(?<!AI)みるく", cap)
print(f"{'OK ' if not bare else 'NG '} 「AI」なしの みるく 表記: {len(bare)}件")
if bare:
    ng += 1

print("\n" + ("すべて通りました" if ng == 0 else f"失敗 {ng}件"))
sys.exit(1 if ng else 0)
