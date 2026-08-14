"""月1回の「来月の箱根」投稿を作って、Instagramに出す。

■ 週次と何が違うのか（なぜ2本あるのか）
週次「今週のおしらせ」は、地域の人と滞在中の人に向けた関係づくりの投稿。
今週の話なので、読んだ人が泊まりに来ることはまずない。それでいい。

月次「来月の箱根」は**予約導線**。宿泊予約が動くのは1〜2ヶ月前なので、
「今週やってます」では間に合わない。だから1ヶ月前に来月ぶんを丸ごと出す。
毎月1日の夜に出すと、読んだ人にとって「来月頭まで1ヶ月、月末まで2ヶ月」。
ちょうど予約を考える時期に当たる。

■ 中身はほとんど週次と同じ部品を使う
違うのは3つだけ。
　1. 対象期間 … 今日から7日間 → 来月の1日から末日まで
　2. 見出し   … 「今週のおしらせ」→「10月の箱根」
　3. 並べ方   … 数が多くなるので、大きい行事から順に最大8件

画像を作る部分もInstagramへ出す部分も、週次とまったく同じものを呼んでいる。
デザインを直せば両方に効くし、投稿の仕組みを直しても両方に効く。
"""
import os
import sys
import random
import datetime as dt
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
import google_client as gc
import instagram as ig
from builder import build_week_images, build_caption
from run_weekly import (fmt_date, season_of, fetch_photo, save_secret,
                        git_push, wait_urls_live)


def next_month(today=None):
    """来月の初日と末日を返す。

    「末日」は月によって28〜31日と変わるので、
    「翌々月の1日の前日」として求める。うるう年も自動で正しくなる。
    """
    today = today or dt.date.today()
    y, m = today.year, today.month
    start = dt.date(y + (m // 12), (m % 12) + 1, 1)          # 来月の1日
    y2, m2 = start.year, start.month
    nxt = dt.date(y2 + (m2 // 12), (m2 % 12) + 1, 1)         # 翌々月の1日
    return start, nxt - dt.timedelta(days=1)


# 月次で「大きい行事」を前に出すための優先度。数字が小さいほど前。
# ■ なぜ区分で決めるのか
# 「泊まりがけで来る価値があるか」を機械で判定するのは無理なので、
# 経験則で代用する。花火や大きなイベントは遠方から人が来る。
# 地域のおまつりや講座は、地元の人向けの色が濃い。
# 月次は予約導線なので、前者を先に見せる。
CATEGORY_ORDER = {
    "花火": 0,
    "灯り・花火": 0,
    "イベント": 1,
    "自然・季節": 2,
    "音楽・文化": 3,
    "地域のおまつり": 4,
    "おしらせ": 5,
}


def pick_month(events, start: dt.date, end: dt.date):
    """来月ぶんの、投稿してよいイベントを「大きい順」に取り出す。

    週次の pick_week と違って、長期のおしらせを外さない。
    月次は「来月はこういう月です」という紹介なので、
    ひと月まるごと続くものこそ載せる価値がある（すすき草原の見頃など）。
    """
    picked = []
    for e in events:
        if not gc._postable(e):
            continue
        try:
            s = dt.date.fromisoformat(e["開始日"])
            t = dt.date.fromisoformat(e["終了日"] or e["開始日"])
        except (ValueError, KeyError):
            continue
        if not (t >= start and s <= end):
            continue
        picked.append(e)

    picked.sort(key=lambda e: (CATEGORY_ORDER.get(e.get("区分", ""), 9),
                               e.get("開始日", "")))
    return picked


def main(dry_run=False):
    config.check_required()
    today = dt.date.today()
    start, end = next_month(today)
    print(f"■ 対象期間: {start} 〜 {end}（来月ぶん）")

    # --- トークンの健康診断（週次とまったく同じ手順） --------------------
    try:
        new_token, days = ig.refresh_token()
        print(f"■ トークンを延長しました。延長後の残り: 約{days}日")
        print(f"::add-mask::{new_token}")
        if new_token != config.IG_ACCESS_TOKEN:
            if save_secret("IG_ACCESS_TOKEN", new_token):
                print("■ 新しいトークンを GitHub の Secrets に保存しました")
            else:
                print("::warning::新しいトークンを保存できませんでした（GH_PAT 未設定）")
            config.IG_ACCESS_TOKEN = new_token
        if days < config.TOKEN_WARN_DAYS:
            raise SystemExit(f"アクセストークンの残りが{days}日です。（投稿は中止しました）")
    except ig.InstagramError as e:
        print(f"■ トークンの延長はできませんでした: {str(e)[:200]}")

    try:
        me = ig.whoami()
    except ig.InstagramError as e:
        raise SystemExit(
            "アクセストークンが使えません。取り直して Secrets を更新してください。\n"
            f"（投稿は中止しました）\n{str(e)[:300]}")
    print(f"■ 投稿先: @{me.get('username')}（id: {me.get('user_id')}）")

    # --- イベントを取る --------------------------------------------------
    rows = gc.read_events()
    picked = pick_month(rows, start, end)
    print(f"■ {start.month}月の掲載可イベント: {len(picked)}件")
    for e in picked:
        print(f"   - {e['開始日']} [{e.get('区分','')}] {e['イベント名']}")

    if len(picked) < config.MIN_EVENTS:
        print(f"■ {config.MIN_EVENTS}件未満のため、今月は投稿しません（スキップ）")
        return 0

    picked = picked[:config.MAX_EVENTS]

    # --- 写真をそろえる --------------------------------------------------
    workdir = config.ROOT / "work"
    workdir.mkdir(exist_ok=True)
    used = set()
    season = season_of(start)          # 「来月」の季節で選ぶ。今月ではない

    week = {
        "range": f"{start.year}年{start.month}月",
        "motif": season,
        "title1": "AIみるくの",
        "title2": f"{start.month}月の箱根",
        "lead": "来月の箱根・仙石原の予定を\nAIみるくが先まわりでお届けするにゃ",
        "closing": f"{start.month}月の箱根で、待ってるにゃ",
        "caption_head": f"🐾 {start.month}月の箱根、こんなことあるにゃ",
        "caption_lead": (f"{start.month}月の箱根・仙石原の予定を、"
                         "AIみるくが少し早めにお届けするにゃ！\n"
                         "お宿の相談は、お早めがおすすめだにゃ🏮"),
        "sources": "、".join(sorted({e.get("情報源", "") for e in picked if e.get("情報源")}))
                   or "箱根町ホームページ",
        "photo": str(fetch_photo(season, used, workdir) or ""),
        "events": [],
    }
    for e in picked:
        week["events"].append({
            "date": fmt_date(e["開始日"], e.get("終了日", "")),
            "category": e.get("区分", ""),
            "title": e.get("イベント名", ""),
            "place": e.get("場所", ""),
            "time": e.get("時間", ""),
            "scale": e.get("規模・備考", ""),
            "note": e.get("みるくコメント", ""),
            "motif": e.get("モチーフ", "") or season,
            "photo": str(fetch_photo(season, used, workdir) or ""),
        })

    # --- 画像を作る ------------------------------------------------------
    # 週次とファイル名がぶつからないよう、月次は m を付ける
    stamp = f"{start.year}{start.month:02d}_monthly"
    outdir = config.OUT_DIR / stamp
    paths = build_week_images(week, outdir)
    caption = build_caption(week)
    print(f"■ 画像を{len(paths)}枚生成しました -> {outdir}")

    if dry_run:
        print("■ dry-run のためここで終了します（投稿はしません）")
        print("---- キャプション ----")
        print(caption)
        return 0

    # --- 公開して投稿 ----------------------------------------------------
    git_push(paths, f"AIみるく {start.year}年{start.month}月号の投稿画像")
    urls = [config.public_url(f"{stamp}/{p.name}") for p in paths]
    wait_urls_live(urls)
    post_id = ig.post_carousel(urls, caption)
    print(f"■ 投稿しました: {post_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
