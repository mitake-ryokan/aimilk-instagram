"""LINEに短い知らせを1通送る。

■ これは何か
GitHub Actions の中から、3号さんのLINEにメッセージを届けるための部品。
「投稿できた」「失敗した」「明日はこれが出る」を知らせる。
GitHubの通知メールは埋もれるが、LINEなら気づける、という理由で用意した。

■ どのアカウントから送るか
通知専用の LINE公式アカウント「みたけ口コミ通知」（友だちは3号さん本人だけ）。
お客様向けの「温泉旅館みたけ サービス案内」とは別アカウント。
送り先を間違えてもお客様には届かない、という状態を保つこと。

■ 設定がなくても止まらない
LINE_CHANNEL_TOKEN と LINE_TO のどちらかが空なら、何もせずに戻る。
通知は「あると助かるもの」であって、投稿の本体ではない。
通知に失敗したせいで投稿が落ちる、という事故を起こさない作りにしてある。

■ 通数
LINEの無料プラン（コミュニケーション）は、こちらから送るプッシュが月200通まで。
ここから送るのは週に1〜2通なので、無料枠で足りる。

■ 単体で試す
    LINE_CHANNEL_TOKEN=xxx LINE_TO=Uxxxx python sasuke/notify_line.py "テストにゃ"
"""
import json
import os
import sys
import urllib.error
import urllib.request

PUSH_URL = "https://api.line.me/v2/bot/message/push"
MAX_CHARS = 4900          # LINEの1通の上限は5000文字。少し余裕を持たせる。


def send(text):
    """LINEに1通送る。送れたら True、送らなかった／失敗したら False。

    例外は投げない。呼び出し側が通知の成否で止まらないようにするため。
    """
    token = os.environ.get("LINE_CHANNEL_TOKEN", "").strip()
    to = os.environ.get("LINE_TO", "").strip()
    if not token or not to:
        print("■ LINEの設定（LINE_CHANNEL_TOKEN / LINE_TO）がないので、"
              "通知は送りません。投稿には影響しません。")
        return False

    body = json.dumps({
        "to": to,
        "messages": [{"type": "text", "text": str(text)[:MAX_CHARS]}],
    }).encode("utf-8")
    req = urllib.request.Request(
        PUSH_URL, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            res.read()
        print("■ LINEに通知しました")
        return True
    except urllib.error.HTTPError as e:
        # 401はトークン切れ、429は無料枠の使い切り。どちらも投稿は続けてよい。
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        print(f"::warning::LINEの通知に失敗しました（HTTP {e.code}）{detail}")
    except Exception as e:
        print(f"::warning::LINEの通知に失敗しました（{e}）")
    return False


def run_url():
    """いま動いている GitHub Actions の実行ページのURL。ローカルなら空。"""
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


if __name__ == "__main__":
    send(" ".join(sys.argv[1:]) or "テスト送信です")
