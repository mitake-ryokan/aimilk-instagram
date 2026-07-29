"""Instagramへ投稿する部品。

■ Instagramへの投稿は2段階
Instagram APIは「画像を送りつけて投稿」ではありません。
　1. まず「これから投稿する箱（コンテナ）」を作る … 画像のURLを渡す
　2. 次に「その箱を公開する」 … 公開の合図を送る
カルーセル（複数枚）の場合は、
　1枚ずつ箱を作る → それらをまとめる親の箱を作る → 親を公開する
という3段階になります。

■ なぜ画像を「URL」で渡すのか
Instagram APIは、ファイルそのものを受け取ってくれません。
「ネット上のここにあります」というURLを渡すと、Instagram側が取りに来る仕組みです。
だから画像をどこかに公開しておく必要があります（このプロジェクトではGitHubを使う）。

■ トークンの寿命
長期アクセストークンは約60日で切れます。切れると投稿は静かに止まります。
毎回の実行で残り日数を確認し、短くなっていたら自動で延長します。
"""
import time
import datetime as dt
import requests

import config


class InstagramError(RuntimeError):
    pass


def _get(url, **params):
    r = requests.get(url, params=params, timeout=60)
    if not r.ok:
        raise InstagramError(f"GET {url} 失敗: {r.status_code} {r.text[:400]}")
    return r.json()


def _post(url, **data):
    r = requests.post(url, data=data, timeout=120)
    if not r.ok:
        raise InstagramError(f"POST {url} 失敗: {r.status_code} {r.text[:400]}")
    return r.json()


# ---------------------------------------------------------------- トークン
def token_days_left(token=None):
    """トークンの残り日数を調べる。

    Metaの debug_token という窓口に「このトークンいつまで有効？」と聞く。
    expires_at が 0 のときは無期限扱い（ページトークンなど）なので大きい数を返す。
    """
    token = token or config.IG_ACCESS_TOKEN
    app_token = f"{config.FB_APP_ID}|{config.FB_APP_SECRET}"
    data = _get(f"{config.GRAPH}/debug_token",
                input_token=token, access_token=app_token).get("data", {})
    exp = data.get("expires_at", 0)
    if not exp:
        return 9999
    left = dt.datetime.fromtimestamp(exp) - dt.datetime.now()
    return left.days


def refresh_token(token=None):
    """長期トークンを延長して、新しいトークンを返す。

    延長すると「そこからまた約60日」になる。毎週実行していれば切れることはない。
    ただし新しいトークンは保存しないと意味がないので、
    呼び出し側（run_weekly.py）でGitHubのSecretsを更新する。
    """
    token = token or config.IG_ACCESS_TOKEN
    res = _get(f"{config.GRAPH}/oauth/access_token",
               grant_type="fb_exchange_token",
               client_id=config.FB_APP_ID,
               client_secret=config.FB_APP_SECRET,
               fb_exchange_token=token)
    return res["access_token"]


# ---------------------------------------------------------------- 投稿
def _wait_ready(container_id, token, timeout=300):
    """コンテナの準備が終わるのを待つ。

    Instagramは画像を取りに行って処理するのに数秒〜数十秒かかる。
    준備できる前に公開しようとすると失敗するので、状態を見ながら待つ。
    """
    started = time.time()
    while time.time() - started < timeout:
        st = _get(f"{config.GRAPH}/{container_id}",
                  fields="status_code,status", access_token=token)
        code = st.get("status_code")
        if code == "FINISHED":
            return True
        if code == "ERROR":
            raise InstagramError(f"画像の処理に失敗: {st.get('status')}")
        time.sleep(5)
    raise InstagramError("画像の処理が時間内に終わりませんでした")


def post_carousel(image_urls, caption, token=None, ig_user_id=None):
    """カルーセル投稿を実行して、投稿IDを返す。"""
    token = token or config.IG_ACCESS_TOKEN
    ig = ig_user_id or config.IG_USER_ID

    if not 2 <= len(image_urls) <= 10:
        raise InstagramError(f"カルーセルは2〜10枚。今回は{len(image_urls)}枚でした")

    # 1. 1枚ずつ子コンテナを作る
    children = []
    for url in image_urls:
        res = _post(f"{config.GRAPH}/{ig}/media",
                    image_url=url, is_carousel_item="true", access_token=token)
        children.append(res["id"])
        print(f"  子コンテナ作成: {res['id']}  <- {url}")

    for cid in children:
        _wait_ready(cid, token)

    # 2. 親コンテナを作る
    parent = _post(f"{config.GRAPH}/{ig}/media",
                   media_type="CAROUSEL",
                   children=",".join(children),
                   caption=caption,
                   access_token=token)["id"]
    print(f"  親コンテナ作成: {parent}")
    _wait_ready(parent, token)

    # 3. 公開する
    published = _post(f"{config.GRAPH}/{ig}/media_publish",
                      creation_id=parent, access_token=token)
    print(f"  公開完了: {published}")
    return published.get("id")


def post_single(image_url, caption, token=None, ig_user_id=None):
    """1枚だけの投稿（テスト用）"""
    token = token or config.IG_ACCESS_TOKEN
    ig = ig_user_id or config.IG_USER_ID
    cid = _post(f"{config.GRAPH}/{ig}/media",
                image_url=image_url, caption=caption, access_token=token)["id"]
    _wait_ready(cid, token)
    return _post(f"{config.GRAPH}/{ig}/media_publish",
                 creation_id=cid, access_token=token).get("id")
