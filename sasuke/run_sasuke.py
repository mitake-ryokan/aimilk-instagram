"""「サスケのボドゲ棚」を毎週土曜に1本投稿する本体。

■ 流れ
  1. 設定がそろっているか確認する
  2. queue.json の中から「まだ投稿していない、いちばん小さい vol」を1つ取る
  3. そのゲームが games.csv に実在するか確かめる（無ければ止める）
  4. トークンを延長する（みるくと同じ仕組み・同じ IG_ACCESS_TOKEN を使う）
  5. カードを描く／締めロゴ画像を並べる（どちらもJPEG）
  6. GitHubに公開して、[カード, 締めロゴ] の2枚カルーセルを queue の caption で投稿
  7. 「vol.XX は投稿済み」を state に記録してコミットする

■ みるくの投稿とは別物
このスクリプトは AIみるく（木曜）とはワークフローもjobも分けてある。
片方が失敗しても、もう片方は巻き込まれない。
ただしトークンだけは新設せず、みるくと同じ IG_ACCESS_TOKEN を延長して使い回す。
延長のやり方（refresh_token）も保存のやり方（save_secret）も、みるくのものをそのまま呼ぶ。
"""
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))     # みるくの部品（config / instagram / run_weekly）
sys.path.insert(0, str(HERE))             # make_card

import config
import instagram as ig
# ■ トークンの保存・画像の公開・公開URL待ちは、みるくの実装をそのまま借りる。
#   コピーせずに import することで、直し忘れによる食い違いを防ぐ（run_monthly と同じやり方）。
from run_weekly import save_secret, git_push, wait_urls_live
import make_card

QUEUE = HERE / "queue.json"
CLOSING_SRC = HERE / "assets" / "closing.jpg"    # 締めロゴ画像（2枚目・JPEG）
STATE = ROOT / "state" / "sasuke_posted.json"


def check_required():
    """サスケに必要な設定だけを確認する。

    みるくの config.check_required() は Google スプレッドシートも必須にするが、
    サスケはシートを見ないので、そこは要らない。足りないものを全部並べて教える。
    """
    missing = [k for k, v in {
        "IG_ACCESS_TOKEN": config.IG_ACCESS_TOKEN,
        "GITHUB_OWNER": config.GITHUB_OWNER,
        "GITHUB_REPO": config.GITHUB_REPO,
    }.items() if not v]
    if missing:
        raise SystemExit(
            "設定が足りません: " + ", ".join(missing) +
            "\nGitHub の Secrets（またはワークフローの env）を確認してください。")


def load_queue():
    if not QUEUE.exists():
        raise SystemExit(f"投稿キューがありません: {QUEUE}")
    data = json.loads(QUEUE.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit("queue.json は空でないリストにしてください")
    return data


def load_posted():
    if STATE.exists():
        try:
            return set(int(v) for v in json.loads(STATE.read_text())["posted"])
        except (ValueError, KeyError, TypeError):
            print("::warning::state が壊れていたので、まっさらから始めます")
    return set()


def save_posted(posted):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"posted": sorted(posted)},
                                ensure_ascii=False, indent=1))


def pick_next(queue, posted):
    """まだ投稿していない、いちばん小さい vol のエントリを返す。無ければ None。"""
    remaining = [e for e in queue if int(e["vol"]) not in posted]
    if not remaining:
        return None
    return min(remaining, key=lambda e: int(e["vol"]))


def ensure_token():
    """トークンを延長して、必要なら Secrets に書き戻す（みるくと同じ）。

    延長できないのは「発行から24時間経っていないトークン」のときくらいで、
    それは異常ではない。延長の可否とは別に、最後に whoami で生きているか確かめる。
    """
    try:
        new_token, days = ig.refresh_token()
        print(f"■ トークンを延長しました。延長後の残り: 約{days}日")
        print(f"::add-mask::{new_token}")
        if new_token != config.IG_ACCESS_TOKEN:
            if save_secret("IG_ACCESS_TOKEN", new_token):
                print("■ 新しいトークンを GitHub の Secrets に保存しました")
            else:
                print("::warning::新しいトークンを保存できませんでした（GH_PAT 未設定）。"
                      "手動で Secrets を更新しないと、いずれ投稿が止まります")
            config.IG_ACCESS_TOKEN = new_token
        if days < config.TOKEN_WARN_DAYS:
            raise SystemExit(
                f"アクセストークンの残りが{days}日です。延長が効いていません。"
                "手動で取り直してください。（投稿は中止しました）")
    except ig.InstagramError as e:
        print(f"■ トークンの延長はできませんでした: {str(e)[:200]}")
        print("　（発行から24時間経っていないトークンは延長できません。初回は正常です）")

    try:
        me = ig.whoami()
    except ig.InstagramError as e:
        raise SystemExit(
            "アクセストークンが使えません。取り直して Secrets を更新してください。\n"
            f"（投稿は中止しました）\n{str(e)[:300]}")
    print(f"■ 投稿先: @{me.get('username')}（id: {me.get('user_id')}）")


def record_posted(vol):
    """「vol.XX 投稿済み」を state に書いてコミットする。

    ■ pull --rebase を挟む理由（town_docs と同じ）
    直前に画像コミットが push 済みのことがある。手元が古いまま push すると弾かれるので、
    取り込んでから積み直す。
    """
    posted = load_posted()
    posted.add(int(vol))
    save_posted(posted)
    subprocess.run(["git", "config", "user.name", "aimilk-bot"], check=True)
    subprocess.run(["git", "config", "user.email",
                    "aimilk-bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", str(STATE)], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("  記録に変更なし")
        return
    subprocess.run(["git", "commit", "-m",
                    f"サスケのボドゲ棚 vol.{int(vol):02d} を投稿"], check=True)
    subprocess.run(["git", "pull", "--rebase", "--autostash"], check=False)
    subprocess.run(["git", "push"], check=True)
    print("  投稿済みの記録をGitHubに残しました")


def main(dry_run=False):
    check_required()

    if not CLOSING_SRC.exists():
        raise SystemExit(
            f"締めロゴ画像がありません: {CLOSING_SRC}\n"
            "sasuke/assets/closing.jpg（JPEG）を置いてください。")

    queue = load_queue()
    posted = load_posted()
    entry = pick_next(queue, posted)
    if entry is None:
        # ■ ここは「成功」にしない（2026-09-05 変更）
        # 以前は return 0 で静かに終わっていた。GitHub は緑のチェックを出すだけで
        # メールも飛ばないので、投稿が止まったことに誰も気づけない。
        # 何も投稿できていないのだから失敗として扱い、失敗通知を届かせる。
        print("::error::サスケのボドゲ棚のキューを使い切りました。"
              "sasuke/queue.json に次の回を追加してください。"
              "追加するまで、毎週この失敗が出ます。")
        return 1

    # ■ 切れる前に気づけるようにする
    # 残りが少なくなったらログに警告を出す。メールは飛ばないが、
    # Actions の画面に黄色い印が付くので、見に行けば分かる。
    remaining = len([e for e in queue if int(e["vol"]) not in posted]) - 1
    if remaining <= 3:
        print(f"::warning::キューの残りは、この回のあと {remaining} 本です。"
              "そろそろ次の分を用意してください。")

    vol = int(entry["vol"])
    game = entry["game"]
    serif = entry.get("serif", "")
    caption = entry.get("caption", "")
    print(f"■ 今回の投稿: vol.{vol:02d} 『{game}』")

    if not caption.strip():
        raise SystemExit(f"vol.{vol:02d} の caption が空です。queue.json を確認してください。")

    # --- カードを描く／締めロゴを並べる（どちらも public/ の下に置く） ----
    voldir = f"vol{vol:02d}"
    outdir = config.OUT_DIR / "sasuke" / voldir
    outdir.mkdir(parents=True, exist_ok=True)
    card_path = outdir / "card.jpg"
    closing_path = outdir / "closing.jpg"
    # display は任意。入れておくと、カードの見出しだけ短い名前にできる
    # （例: game="カタン：カプコン版" / display="カタン"）。
    name = make_card.render(vol, game, serif, card_path,
                            display=entry.get("display"),
                            crop=entry.get("crop"),
                            origin=entry.get("origin"))
    shutil.copyfile(CLOSING_SRC, closing_path)      # 締めロゴをそのまま公開位置へ
    print(f"■ カードを描きました: 『{name}』 -> {card_path}")

    if dry_run:
        print("■ dry-run のためここで終了します（投稿はしません）")
        print("---- キャプション ----")
        print(caption)
        return 0

    # --- トークン確認 → 公開 → 投稿 ------------------------------------
    ensure_token()
    paths = [card_path, closing_path]
    git_push(paths, f"サスケのボドゲ棚 vol.{vol:02d} の投稿画像")
    urls = [config.public_url(f"sasuke/{voldir}/{p.name}") for p in paths]
    wait_urls_live(urls)
    post_id = ig.post_carousel(urls, caption)       # caption は無編集でそのまま
    print(f"■ 投稿しました: {post_id}")

    record_posted(vol)
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
