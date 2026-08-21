"""毎週の投稿を作って、Instagramに出すところまでを一気にやる本体。

■ 流れ
　1. 設定がそろっているか確認する
　2. トークンの残り日数を見る（短ければ延長する）
　3. スプレッドシートから「今週ぶんで、掲載可否が ○」のイベントを取る
　4. イベントが2件未満なら、投稿せずに終わる（スキップ）
　5. Google Driveから季節に合う写真を取ってくる
　6. 画像を組み立てて public/ に保存する
　7. GitHubにコミットして、画像をネット公開する
　8. その公開URLをInstagramに渡して投稿する

■ 設計の考え方
「途中で失敗したら、黙って終わらない」を最優先にしています。
自動投稿でいちばん怖いのは、エラーではなく沈黙です。
何かおかしければ必ずエラーで落として、GitHubから3号さんにメールが飛ぶようにします。
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

WEEKDAY_JA = "月火水木金土日"


def this_week(today=None):
    """今日から見て「今週」の範囲を返す（木曜投稿なので、木曜〜翌水曜）。"""
    today = today or dt.date.today()
    start = today
    end = today + dt.timedelta(days=6)
    return start, end


def fmt_date(iso_start, iso_end):
    s = dt.date.fromisoformat(iso_start)
    label = f"{s.month}/{s.day} ({WEEKDAY_JA[s.weekday()]})"
    if iso_end and iso_end != iso_start:
        e = dt.date.fromisoformat(iso_end)
        label += f"〜{e.month}/{e.day}"
    return label


# 日付を確かめきれていない行に添える、AIみるくの一言。
# ■ ここが肝
# 「日程要確認」と書くのは、書いた側の都合。読む人には何も起きない。
# 「知ってる人は教えてにゃ」と聞けば、知っている人が答えてくれる。
# 箱根の地域情報はWebに出ないぶん、人の頭の中にある。そこへ取りに行く。
UNCERTAIN_NOTE = "箱根あるある、日にちがまだ分からないにゃ。知ってる人は教えてにゃ"


def vague_date(iso_start):
    """「2026-10-15」→「10月中旬ごろ」。日にちを断定せずに時期だけ伝える。"""
    try:
        d = dt.date.fromisoformat((iso_start or "").strip())
    except (ValueError, TypeError):
        return ""
    part = "上旬" if d.day <= 10 else ("中旬" if d.day <= 20 else "下旬")
    return f"{d.month}月{part}ごろ"


def soften_if_uncertain(e, date_label):
    """日付があいまいな行を「断定しない形」に直す。

    戻り値は (日付の表示, 規模・備考, みるくコメント)。

    ■ 規模・備考を空にしている理由
    あいまいな行の備考欄には「箱根ナビ由来。日付の裏取り未了」のような
    こちらの内部メモが入っている。運用のための覚え書きであって、
    お客様に見せる文ではない。そのまま画像に焼くと、ただの不親切になる。
    """
    if not gc.is_uncertain(e):
        return date_label, e.get("規模・備考", ""), e.get("みるくコメント", "")
    return vague_date(e.get("開始日", "")), "", UNCERTAIN_NOTE


def season_of(d: dt.date):
    m = d.month
    if m in (3, 4, 5):
        return "春"
    if m in (6, 7, 8):
        return "夏"
    if m in (9, 10, 11):
        return "秋"
    return "冬"


def fetch_photo(season, used, workdir):
    """季節フォルダから写真を1枚取ってくる。なければ通年から。それもなければNone。

    同じ投稿の中で同じ写真が2回出ないよう、使ったIDを覚えておく。
    """
    for folder_key in (season, "通年"):
        fid = config.PHOTO_FOLDERS.get(folder_key)
        if not fid:
            continue
        files = [f for f in gc.list_photos(fid) if f["id"] not in used]
        if not files:
            continue
        pick = random.choice(files)
        used.add(pick["id"])
        dest = workdir / f"photo_{pick['id']}{Path(pick['name']).suffix}"
        gc.download(pick["id"], dest)
        print(f"  写真: {folder_key} / {pick['name']}")
        return dest
    print(f"  写真: 見つからないのでイラストを使います（{season}）")
    return None


def save_secret(name, value):
    """GitHubのSecretsを書き換える。成功したらTrue。

    ■ なぜこれが要るのか
    トークンは60日で切れます。毎週延長すれば切れませんが、
    「延長した新しいトークンをどこに保存するか」という問題が残ります。
    保存できなければ、結局60日後に静かに止まる。
    そこで、GitHub自身のSecretsに書き戻して、次回の実行がそれを読むようにします。

    ■ なぜ別のトークン（GH_PAT）が要るのか
    GitHub Actionsが自動で持っている権限では、Secretsは書き換えられません。
    （書き換えられたら、ワークフローを書き換えた人が何でもできてしまうため）
    なので「Secretsを書く権限だけ」を持つ鍵を別に用意して渡します。
    用意していない場合は、警告を出すだけで止めません。投稿自体はできるからです。
    """
    if not config.GH_PAT:
        return False
    repo = f"{config.GITHUB_OWNER}/{config.GITHUB_REPO}"
    r = subprocess.run(
        ["gh", "secret", "set", name, "--body", value, "--repo", repo],
        env={**os.environ, "GH_TOKEN": config.GH_PAT},
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"::warning::Secretsの更新に失敗: {r.stderr[:300]}")
        return False
    return True


def git_push(paths, message):
    """生成した画像をGitHubにコミットして公開する。

    Instagram APIは公開URLの画像しか受け取れない。
    有料の画像置き場を借りなくても、GitHubの公開リポジトリで代用できる。
    """
    subprocess.run(["git", "config", "user.name", "aimilk-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "aimilk-bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add"] + [str(p) for p in paths], check=True)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if r.returncode == 0:
        print("  コミットする変更なし")
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push"], check=True)
    print("  GitHubへ公開しました")


def wait_urls_live(urls, timeout=180):
    """画像のURLが実際に見えるようになるまで待つ。

    GitHubにコミットしても、公開URLから取れるようになるまで数秒〜数十秒かかることがある。
    まだ見えていないURLをInstagramに渡すと「画像が取得できません」で失敗する。
    自分で見に行って、200が返ってから先へ進む。
    """
    import requests
    started = time.time()
    for u in urls:
        while True:
            try:
                if requests.head(u, timeout=20, allow_redirects=True).status_code == 200:
                    break
            except requests.RequestException:
                pass
            if time.time() - started > timeout:
                raise SystemExit(f"画像の公開URLが見えるようになりません: {u}")
            time.sleep(5)
    print("■ 画像の公開URL、すべて確認できました")


def main(dry_run=False):
    config.check_required()
    today = dt.date.today()
    start, end = this_week(today)
    print(f"■ 対象期間: {start} 〜 {end}")

    # --- トークンの健康診断 --------------------------------------------
    # 新方式（graph.instagram.com）には「あと何日？」と聞く窓口がない。
    # 代わりに延長すると残り秒数を返してくれるので、毎回とりあえず延長する。
    # 延長は24時間経っていれば何度でもでき、そのたびに60日に戻る。
    # 延長できないケースが1つある：発行から24時間経っていないトークン。
    # 取ったばかりの初回はここで必ず失敗する。だが失敗＝異常ではない。
    # なので「延長できなかったら、そのトークンがまだ生きているか確かめる」に分ける。
    # 生きていれば進む。死んでいれば止める。
    try:
        new_token, days = ig.refresh_token()
        print(f"■ トークンを延長しました。延長後の残り: 約{days}日")
        print(f"::add-mask::{new_token}")

        if new_token != config.IG_ACCESS_TOKEN:
            if save_secret("IG_ACCESS_TOKEN", new_token):
                print("■ 新しいトークンを GitHub の Secrets に保存しました")
            else:
                print("::warning::新しいトークンを保存できませんでした。"
                      "GH_PAT が未設定です。手動で Secrets の IG_ACCESS_TOKEN を "
                      "更新しないと、いずれ投稿が止まります")
            # 今回の実行は、延長後の新しいトークンで進める
            config.IG_ACCESS_TOKEN = new_token

        if days < config.TOKEN_WARN_DAYS:
            raise SystemExit(
                f"アクセストークンの残りが{days}日です。延長が効いていません。"
                "手動で取り直してください。（投稿は中止しました）")

    except ig.InstagramError as e:
        print(f"■ トークンの延長はできませんでした: {str(e)[:200]}")
        print("　（発行から24時間経っていないトークンは延長できません。初回は正常です）")

    # --- 投稿先の確認 ----------------------------------------------------
    # ここが通れば、トークンは生きている。延長できたかどうかとは別の話。
    try:
        me = ig.whoami()
    except ig.InstagramError as e:
        raise SystemExit(
            "アクセストークンが使えません。取り直して Secrets を更新してください。\n"
            f"（投稿は中止しました）\n{str(e)[:300]}")
    print(f"■ 投稿先: @{me.get('username')}（id: {me.get('user_id')}）")

    # --- イベントを取る --------------------------------------------------
    rows = gc.read_events()
    picked = gc.pick_week(rows, start, end)
    print(f"■ 今週の掲載可（○）イベント: {len(picked)}件")
    for e in picked:
        print(f"   - {e['開始日']} {e['イベント名']}")

    if len(picked) < config.MIN_EVENTS:
        print(f"■ {config.MIN_EVENTS}件未満のため、今週は投稿しません（スキップ）")
        return 0

    picked = picked[:config.MAX_EVENTS]

    # --- 写真をそろえる --------------------------------------------------
    workdir = config.ROOT / "work"
    workdir.mkdir(exist_ok=True)
    used = set()
    season = season_of(today)

    week = {
        "range": f"{start.year}.{start.month}.{start.day} 〜 {end.month}.{end.day}",
        "motif": season,
        "sources": "、".join(sorted({e.get("情報源", "") for e in picked if e.get("情報源")}))
                   or "箱根町ホームページ",
        "photo": str(fetch_photo(season, used, workdir) or ""),
        "events": [],
    }
    for e in picked:
        # まだ先のイベント（告知開始日で前倒しに載せているもの）には「予告」と付ける。
        # 付けないと「今週やっている」と読まれる。告知のつもりが誤情報になってしまう。
        cat = e.get("区分", "")
        try:
            if dt.date.fromisoformat(e["開始日"]) > end:
                cat = f"予告・{cat}" if cat else "予告"
        except (ValueError, KeyError):
            pass
        date_label, scale, note = soften_if_uncertain(
            e, fmt_date(e["開始日"], e.get("終了日", "")))
        week["events"].append({
            "date": date_label,
            "category": cat,
            "title": e.get("イベント名", ""),
            "place": e.get("場所", ""),
            "time": e.get("時間", ""),
            "scale": scale,
            "note": note,
            "motif": e.get("モチーフ", "") or season,
            "photo": str(fetch_photo(season, used, workdir) or ""),
        })

    # --- 画像を作る ------------------------------------------------------
    stamp = today.strftime("%Y%m%d")
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
    git_push(paths, f"AIみるく {stamp} の投稿画像")
    urls = [config.public_url(f"{stamp}/{p.name}") for p in paths]
    wait_urls_live(urls)
    post_id = ig.post_carousel(urls, caption)
    print(f"■ 投稿しました: {post_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
