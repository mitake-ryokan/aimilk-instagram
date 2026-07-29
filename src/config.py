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
# Graph APIのバージョン。Metaは年に数回上げるので、動かなくなったらここを確認する
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v21.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

IG_USER_ID = os.environ.get("IG_USER_ID", "")          # InstagramビジネスアカウントのID
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")  # 長期アクセストークン
FB_APP_ID = os.environ.get("FB_APP_ID", "")
FB_APP_SECRET = os.environ.get("FB_APP_SECRET", "")

# ---------------------------------------------------------------- Google
# サービスアカウントのJSONを丸ごと文字列で入れる（GitHub Secretsに貼る想定）
GOOGLE_SA_JSON = os.environ.get("GOOGLE_SA_JSON", "")
SHEET_ID = os.environ.get("SHEET_ID", "1U1ha5M1z_W7ytqFi2GtiiZHMv30rnuJ75LA7L9bI56k")

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
MIN_EVENTS = 2          # これ未満の週は投稿しない（スカスカな投稿を出さないため）
MAX_EVENTS = 8          # カルーセルは最大10枚。表紙と締めで2枚使うので残り8枚
TOKEN_WARN_DAYS = 14    # トークンの残りがこれを切ったら警告して落とす


def check_required():
    """必要な設定が揃っているか、実行前に確認する。

    途中まで動いてから「トークンがありません」で落ちると原因が分かりにくい。
    最初にまとめて確認して、足りないものを全部並べて教える。
    """
    missing = [k for k, v in {
        "IG_USER_ID": IG_USER_ID,
        "IG_ACCESS_TOKEN": IG_ACCESS_TOKEN,
        "FB_APP_ID": FB_APP_ID,
        "FB_APP_SECRET": FB_APP_SECRET,
        "GOOGLE_SA_JSON": GOOGLE_SA_JSON,
        "GITHUB_OWNER": GITHUB_OWNER,
        "GITHUB_REPO": GITHUB_REPO,
    }.items() if not v]
    if missing:
        raise SystemExit(
            "設定が足りません: " + ", ".join(missing) +
            "\n.env（パソコン）または GitHub の Secrets を確認してください。")
