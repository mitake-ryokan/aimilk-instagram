"""Instagramへ投稿する部品。

■ どの窓口を使っているか（2026-07-30 に切り替えた）
Metaには、Instagramに投稿するための窓口が2つあります。

　旧：Facebookログイン方式  … graph.facebook.com を叩く。
　　　Facebookページを経由してInstagramに届ける。ページの所有関係が絡む。
　新：Instagramログイン方式 … graph.instagram.com を叩く。
　　　Facebookページを一切経由しない。Instagramアカウントに直接つながる。

このプロジェクトは**新（Instagramログイン方式）**を使います。
旧方式で組んだところ、Facebookページがビジネスポートフォリオ所有だったため
アプリからページが解決できず（me/accounts が空、ページIDで subcode 33）、
先に進めませんでした。新方式はページを使わないので、その問題が丸ごと消えます。

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
なお**受け付ける形式はJPEGだけ**です。PNGを渡すと処理が失敗します。

■ トークンの寿命
長期アクセストークンは60日で切れます。切れると投稿は静かに止まります。
新方式には「いつ切れるか」を問い合わせる窓口（旧方式の debug_token）がありません。
その代わり、延長すると残り秒数（expires_in）を返してくれます。
そこでこのコードは「毎回とりあえず延長して、返ってきた残り日数を見る」方式にしました。
延長は発行から24時間以上経っていれば何度でもでき、そのたびに60日に戻ります。
"""
import time
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


# ---------------------------------------------------------------- アカウント
def whoami(token=None):
    """つながっているInstagramアカウントの user_id と username を返す。

    旧方式では「Facebookページを調べて、そこにぶら下がるInstagramのIDを取る」
    という遠回りが必要でした。新方式ではトークン自体がアカウントに直結しているので、
    自分に聞けば済みます。IG_USER_ID を人が調べて登録する必要がなくなりました。

    投稿先を間違えないための確認にも使います（run_weekly.py が username を出す）。
    """
    token = token or config.IG_ACCESS_TOKEN
    return _get(f"{config.IG_GRAPH}/me",
                fields="user_id,username", access_token=token)


# ---------------------------------------------------------------- トークン
def refresh_token(token=None):
    """長期トークンを延長し、(新しいトークン, 残り日数) を返す。

    延長できなかった場合は例外ではなく (None, 残り日数不明) にはしません。
    「延長できない」は失効間近か既に失効の可能性が高く、静かに続けるほうが危険なので
    そのまま例外を投げて落とします。GitHubから3号さんにメールが飛びます。
    """
    token = token or config.IG_ACCESS_TOKEN
    res = _get(f"{config.IG_GRAPH}/refresh_access_token",
               grant_type="ig_refresh_token", access_token=token)
    new_token = res["access_token"]
    days = int(res.get("expires_in", 0)) // 86400
    return new_token, days


def exchange_token(short_token, app_secret=None):
    """1時間しか使えない短期トークンを、60日の長期トークンに交換する。

    アプリのダッシュボードの「アクセストークンを生成」で出てくるトークンは
    すでに長期なので、通常この関数は使いません。
    自分でログイン画面から取り直したときのための出口として置いてあります。
    """
    secret = app_secret or config.IG_APP_SECRET
    if not secret:
        raise InstagramError("IG_APP_SECRET が設定されていません")
    res = _get(f"{config.IG_GRAPH}/access_token",
               grant_type="ig_exchange_token",
               client_secret=secret,
               access_token=short_token)
    return res["access_token"]


# ---------------------------------------------------------------- 投稿
def _wait_ready(container_id, token, timeout=300):
    """コンテナの準備が終わるのを待つ。

    Instagramは画像を取りに行って処理するのに数秒〜数十秒かかる。
    準備できる前に公開しようとすると失敗するので、状態を見ながら待つ。
    """
    started = time.time()
    while time.time() - started < timeout:
        st = _get(f"{config.IG_GRAPH}/{container_id}",
                  fields="status_code,status", access_token=token)
        code = st.get("status_code")
        if code == "FINISHED":
            return True
        if code == "ERROR":
            raise InstagramError(
                f"画像の処理に失敗: {st.get('status')}\n"
                "よくある原因は ①画像がJPEGでない ②公開URLにInstagramが届かない "
                "（リポジトリがPrivateになっている）の2つです。")
        time.sleep(5)
    raise InstagramError("画像の処理が時間内に終わりませんでした")


def post_carousel(image_urls, caption, token=None, ig_user_id=None):
    """カルーセル投稿を実行して、投稿IDを返す。"""
    token = token or config.IG_ACCESS_TOKEN
    ig = ig_user_id or config.IG_USER_ID or "me"

    if not 2 <= len(image_urls) <= 10:
        raise InstagramError(f"カルーセルは2〜10枚。今回は{len(image_urls)}枚でした")

    # 1. 1枚ずつ子コンテナを作る
    children = []
    for url in image_urls:
        res = _post(f"{config.IG_GRAPH}/{ig}/media",
                    image_url=url, is_carousel_item="true", access_token=token)
        children.append(res["id"])
        print(f"  子コンテナ作成: {res['id']}  <- {url}")

    for cid in children:
        _wait_ready(cid, token)

    # 2. 親コンテナを作る
    parent = _post(f"{config.IG_GRAPH}/{ig}/media",
                   media_type="CAROUSEL",
                   children=",".join(children),
                   caption=caption,
                   access_token=token)["id"]
    print(f"  親コンテナ作成: {parent}")
    _wait_ready(parent, token)

    # 3. 公開する
    published = _post(f"{config.IG_GRAPH}/{ig}/media_publish",
                      creation_id=parent, access_token=token)
    print(f"  公開完了: {published}")
    return published.get("id")


def post_single(image_url, caption, token=None, ig_user_id=None):
    """1枚だけの投稿（テスト用）"""
    token = token or config.IG_ACCESS_TOKEN
    ig = ig_user_id or config.IG_USER_ID or "me"
    cid = _post(f"{config.IG_GRAPH}/{ig}/media",
                image_url=image_url, caption=caption, access_token=token)["id"]
    _wait_ready(cid, token)
    return _post(f"{config.IG_GRAPH}/{ig}/media_publish",
                 creation_id=cid, access_token=token).get("id")
