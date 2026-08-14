"""設定をひとまとめにする場所。

■ なぜ設定を1ファイルに集めるのか
パスワードやAPIキーをコードの中に直接書くと、GitHubに上げた瞬間に世界中から見えます。
なので「値そのもの」はコードに書かず、環境変数（.env や GitHubの Secrets）から読みます。
ここはその「読み取り口」だけを置く場所です。

■ 環境変数って何？
プログラムの外側に置いておく設定値のこと。
パソコンで動かすときは .env ファイル、GitHub上で動かすときは Secrets に入れます。
どちらに入っていても、コードからは同じように os.environ で読めます。
"""
import os
from pathlib import Path

# ---------------------------------------------------------------- 基本
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "public"          # 生成した画像を置く場所（ここがネット公開される）
ASSETS = ROOT / "assets"           # AIみるくの切り抜きPNGなど

# ---------------------------------------------------------------- Instagram
# ■ 窓口は graph.instagram.com（Instagramログイン方式）
# graph.facebook.com（Facebookログイン方式）ではない。
# 旧方式はFacebookページを経由するため、ページがビジネスポートフォリオ所有だと
# アプリから解決できずに詰まる。新方式はページを一切経由しない。
IG_GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v23.0")
IG_GRAPH = f"https://graph.instagram.com/{IG_GRAPH_VERSION}"

IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")  # 長期アクセストークン（60日）

# 投稿先のID。空でよい。空なら "me"（トークンの持ち主）に投稿する。
# 新方式ではトークンがアカウントに直結しているので、人がIDを調べる必要がない。
IG_USER_ID = os.environ.get("IG_USER_ID", "")

# 短期トークンを長期に交換するときだけ使う。通常の運用では不要。
IG_APP_SECRET = os.environ.get("IG_APP_SECRET", "")

# 延長した新しいトークンを、GitHubのSecretsに自動で書き戻すためのトークン。
# 空なら書き戻さず、ログに警告を出すだけ（3号さんが手で貼り替える運用になる）。
GH_PAT = os.environ.get("GH_PAT", "")

# ---------------------------------------------------------------- Google
# サービスアカウントのJSONを丸ごと文字列で入れる（GitHub Secretsに貼る想定）
GOOGLE_SA_JSON = os.environ.get("GOOGLE_SA_JSON", "")
SHEET_ID = os.environ.get("SHEET_ID", "1lmt2I2X9U070SAw4La-TpqVmoml0rhh9IpRAFwekfkw")

# Google Drive の写真フォルダ
PHOTO_FOLDERS = {
    "春": "1WYdykx8eQO6-OyIzR0xP2vS0bVT-Ait7",
    "夏": "19iXTbL6Hu7uYLLViELco3QNlg2oZXuAH",
    "秋": "1FRKtTpi_2mQkPaEy-MF9eatN5skrcSgb",
    "冬": "18qNQZslwWMyYb4m7L1_Z08rB4u2dUWey",
    "通年": "1v7SHUAt-pOw9_6pjub790hxw8rxPMeSc",
}
MILK_FOLDER = "1lGaW2k9qgr2KJ3boDtxvCkHqtn9fpoEX"

# ---------------------------------------------------------------- 画像の公開URL
# GitHubのリポジトリに画像をコミットして、その生URLをInstagramに渡す。
# Instagram APIは「ネット上の公開URLにある画像」しか受け取れないため。
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")


def public_url(rel_path: str) -> str:
    """publicフォルダの中のファイルの、ネット上のURLを組み立てる"""
    return (f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
            f"/{GITHUB_BRANCH}/public/{rel_path}")


# ---------------------------------------------------------------- 投稿ルール
MIN_EVENTS = 1          # 1件でも投稿する。スキップは0件の週だけ（2026-08-14変更）
MAX_EVENTS = 8          # カルーセルは最大10枚。表紙と締めで2枚使うので残り8枚
TOKEN_WARN_DAYS = 14    # トークンの残りがこれを切ったら警告して落とす


def check_required():
    """必要な設定が揃っているか、実行前に確認する。

    途中まで動いてから「トークンがありません」で落ちると原因が分かりにくい。
    最初にまとめて確認して、足りないものを全部並べて教える。
    """
    missing = [k for k, v in {
        "IG_ACCESS_TOKEN": IG_ACCESS_TOKEN,
        "GOOGLE_SA_JSON": GOOGLE_SA_JSON,
        "GITHUB_OWNER": GITHUB_OWNER,
        "GITHUB_REPO": GITHUB_REPO,
    }.items() if not v]
    if missing:
        raise SystemExit(
            "設定が足りません: " + ", ".join(missing) +
            "\n.env（パソコン）または GitHub の Secrets を確認してください。")
