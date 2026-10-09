"""予約箱（posts/）に入っている投稿を、決めた時刻にInstagramへ出す。

■ これは何か
サスケのボドゲ棚のような「毎週決まった形」ではない、臨時の投稿のための仕組み。
お知らせ、季節の投稿、求人、相談ごとなど。

■ 流れ
  1. Claude（または3号さん）が posts/<日付_名前>/ を作り、プルリクエストを出す
  2. 3号さんがスマホの GitHub アプリで画像と文章を確認して、マージする（＝承認）
  3. このスクリプトが30分おきに main を見て、時刻が来たものを投稿する

  main に入っていない（＝マージされていない）ものは、そもそもここから見えない。
  だから「承認されていないものは出ない」は、仕組みとして守られている。

■ 1本ぶんのフォルダの中身
  posts/2026-10-10_kagami/
    post.json      いつ出すか（publish_at）と、自分用の題（title）
    caption.txt    Instagramのキャプション全文
    1.jpg 2.jpg …  画像。1枚なら単体、2〜10枚ならカルーセル。並びは数字の順

■ このスクリプトが書き足すもの（人は触らない）
    published.json  投稿できた記録。これがあるものは二度と出さない
    failed.json     失敗した記録。これがあるものは自動ではやり直さない
    expired.json    時刻を24時間以上過ぎていたので出さなかった記録

■ 使い方
    python posts/run_posts.py            時刻が来たものを投稿する（Actionsが30分おきに呼ぶ）
    python posts/run_posts.py --check    中身を点検するだけ（プルリクエストのたびに呼ぶ）
    python posts/run_posts.py --dry-run  投稿せず、何が出るかだけ表示する
"""
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "sasuke"))

JST = dt.timezone(dt.timedelta(hours=9))
EXPIRE_AFTER = dt.timedelta(hours=24)   # これより古いものは出さない
MAX_HASHTAGS = 5                        # みたけの決まり（Instagramは5個まで）
MAX_CAPTION = 2200                      # Instagramのキャプション上限
RESULT_FILES = ("published.json", "failed.json", "expired.json")


class PostError(Exception):
    pass


# ---------------------------------------------------------------- 読み込みと点検
def images_of(d):
    """1.jpg, 2.jpg … を数字の順に返す。jpeg / JPG も拾う。"""
    imgs = [p for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg") and p.stem.isdigit()]
    return sorted(imgs, key=lambda p: int(p.stem))


def load(d):
    """1本ぶんを読んで、点検して、(時刻, キャプション, 画像) を返す。

    おかしなところは全部まとめて PostError にする。
    1つ直してはまた1つ見つかる、を繰り返さないため。
    """
    problems = []
    meta = {}
    meta_path = d / "post.json"
    if not meta_path.exists():
        problems.append("post.json がありません")
    else:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"post.json が読めません（{e}）")

    when = None
    raw = meta.get("publish_at", "")
    if meta and not raw:
        problems.append("post.json に publish_at（いつ出すか）がありません")
    elif raw:
        try:
            when = dt.datetime.fromisoformat(raw)
            if when.tzinfo is None:
                problems.append(f"publish_at に時差がありません: {raw}"
                                "（日本時間なら末尾に +09:00 を付ける）")
                when = None
        except ValueError:
            problems.append(f"publish_at の形が違います: {raw}"
                            "（例: 2026-10-10T20:00:00+09:00）")

    caption = ""
    cap_path = d / "caption.txt"
    if not cap_path.exists():
        problems.append("caption.txt がありません")
    else:
        caption = cap_path.read_text(encoding="utf-8").strip()
        if not caption:
            problems.append("caption.txt が空です")
        if len(caption) > MAX_CAPTION:
            problems.append(f"キャプションが長すぎます（{len(caption)}字／上限{MAX_CAPTION}字）")
        tags = re.findall(r"#[^\s#]+", caption)
        if len(tags) > MAX_HASHTAGS:
            problems.append(f"ハッシュタグが{len(tags)}個あります（みたけの決まりは{MAX_HASHTAGS}個まで）")

    imgs = images_of(d)
    if not imgs:
        problems.append("画像（1.jpg, 2.jpg …）がありません")
    if len(imgs) > 10:
        problems.append(f"画像が{len(imgs)}枚あります（Instagramは10枚まで）")
    for p in imgs:
        problems.extend(check_image(p))

    if problems:
        raise PostError("\n".join(f"  - {x}" for x in problems))
    return when, caption, imgs


def check_image(p):
    """Instagramが受け付ける画像かどうか。JPEGであることと、縦横比。"""
    out = []
    head = p.read_bytes()[:3]
    if head[:2] != b"\xff\xd8":
        out.append(f"{p.name} がJPEGではありません（拡張子だけ.jpgになっている可能性）")
        return out
    try:
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
        ratio = w / h
        if not 0.8 <= ratio <= 1.91:
            out.append(f"{p.name} の縦横比がInstagramの範囲外です（{w}x{h}）。"
                       "縦長は4:5（1080x1350）まで")
    except ImportError:
        pass
    return out


def status_of(d):
    for name in RESULT_FILES:
        if (d / name).exists():
            return name.split(".")[0]
    return None


def post_dirs():
    if not POSTS.exists():
        return []
    return sorted(d for d in POSTS.iterdir()
                  if d.is_dir() and not d.name.startswith((".", "_")))


# ---------------------------------------------------------------- 記録を残す
def write_result(d, name, data):
    (d / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def commit(paths, message):
    """記録をコミットして push する。サスケの record_posted と同じ手順。"""
    subprocess.run(["git", "config", "user.name", "aimilk-bot"], check=True)
    subprocess.run(["git", "config", "user.email",
                    "aimilk-bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add"] + [str(p) for p in paths], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "pull", "--rebase", "--autostash"], check=False)
    subprocess.run(["git", "push"], check=True)


def image_url(d, p):
    import config
    return (f"https://raw.githubusercontent.com/{config.GITHUB_OWNER}/{config.GITHUB_REPO}"
            f"/{config.GITHUB_BRANCH}/posts/{d.name}/{p.name}")


# ---------------------------------------------------------------- 本体
def check_all():
    """プルリクエストのときに呼ぶ。中身の点検だけをして、投稿はしない。"""
    now = dt.datetime.now(dt.timezone.utc)
    bad = 0
    dirs = [d for d in post_dirs() if status_of(d) is None]
    if not dirs:
        print("■ 予約箱に、まだ出していない投稿はありません")
        return 0
    for d in dirs:
        try:
            when, caption, imgs = load(d)
        except PostError as e:
            bad += 1
            print(f"::error::{d.name} に直すところがあります\n{e}")
            continue
        kind = "単体" if len(imgs) == 1 else f"カルーセル{len(imgs)}枚"
        print(f"■ {d.name}: {when.astimezone(JST):%Y-%m-%d %H:%M} に出します（{kind}）")
        if when < now - EXPIRE_AFTER:
            bad += 1
            print(f"::error::{d.name} の時刻は24時間以上前です。このままマージしても出ません。"
                  "publish_at を直してください")
        elif when < now:
            print(f"::warning::{d.name} の時刻はもう過ぎています。マージすると30分以内に出ます")
    return 1 if bad else 0


def run(dry_run=False):
    import instagram as ig
    import notify_line
    from run_sasuke import ensure_token
    from run_weekly import wait_urls_live

    now = dt.datetime.now(dt.timezone.utc)
    failures = 0
    token_ready = False

    for d in post_dirs():
        if status_of(d):
            continue
        try:
            when, caption, imgs = load(d)
        except PostError as e:
            failures += 1
            print(f"::error::{d.name} を読めませんでした\n{e}")
            if not dry_run:
                write_result(d, "failed.json", {"at": now.isoformat(), "error": str(e)})
                commit([d / "failed.json"], f"予約投稿 {d.name} の中身に不備（投稿していません）")
                notify_line.send(f"【予約投稿】{d.name} は中身に不備があったので出していません\n{e}")
            continue

        if when > now:
            print(f"■ {d.name}: まだ時刻前（{when.astimezone(JST):%m/%d %H:%M}）")
            continue

        if now - when > EXPIRE_AFTER:
            failures += 1
            print(f"::error::{d.name} は予定時刻を24時間以上過ぎているので出しません")
            if not dry_run:
                write_result(d, "expired.json", {"at": now.isoformat(),
                                                 "publish_at": when.isoformat()})
                commit([d / "expired.json"], f"予約投稿 {d.name} は時刻切れのため出していません")
                notify_line.send(f"【予約投稿】{d.name} は予定時刻を24時間以上過ぎていたので、"
                                 "出していません。出したい場合は時刻を直してください。")
            continue

        kind = "単体" if len(imgs) == 1 else f"カルーセル{len(imgs)}枚"
        print(f"■ 今から出します: {d.name}（{kind}）")
        if dry_run:
            print("---- キャプション ----")
            print(caption)
            continue

        try:
            if not token_ready:
                ensure_token()
                token_ready = True
            urls = [image_url(d, p) for p in imgs]
            wait_urls_live(urls)
            if len(urls) == 1:
                post_id = ig.post_single(urls[0], caption)
            else:
                post_id = ig.post_carousel(urls, caption)
        except (Exception, SystemExit) as e:
            # ■ 自動ではやり直さない
            # 30分おきに同じ失敗を繰り返して、LINEに何十通も届くのを防ぐ。
            # 直したら failed.json を消すプルリクエストを出せば、次の回でまた試す。
            failures += 1
            msg = f"{type(e).__name__}: {e}"
            print(f"::error::{d.name} の投稿に失敗しました\n{msg}")
            write_result(d, "failed.json", {"at": now.isoformat(), "error": msg[:1000]})
            commit([d / "failed.json"], f"予約投稿 {d.name} は失敗しました")
            notify_line.send(f"【予約投稿】{d.name} の投稿に失敗しました\n{msg[:500]}\n"
                             f"{notify_line.run_url()}")
            continue

        # 投稿できたら、すぐに記録する。ここを先にしないと、次の回でもう一度出てしまう。
        write_result(d, "published.json", {"post_id": post_id,
                                           "published_at": dt.datetime.now(JST).isoformat()})
        commit([d / "published.json"], f"予約投稿 {d.name} を投稿")
        print(f"■ 投稿しました: {d.name}（{post_id}）")
        notify_line.send(f"【予約投稿】投稿しました\n{d.name}\n"
                         f"https://www.instagram.com/mitake_hakone/")

    return 1 if failures else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check_all())
    sys.exit(run(dry_run="--dry-run" in sys.argv))
