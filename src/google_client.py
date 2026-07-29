"""Google スプレッドシートと Drive から読むための部品。

■ サービスアカウントって何？
「プログラム専用のGoogleアカウント」です。人間のアカウントでログインさせようとすると、
毎回パスワードやログイン画面が必要になって、自動化できません。
サービスアカウントは、鍵ファイル（JSON）さえあればログイン画面なしで動けます。

■ 使う前にやること
サービスアカウントは最初、3号さんのファイルを何も見られません。
Googleドライブで、対象のフォルダとスプレッドシートを
「サービスアカウントのメールアドレス」に共有（閲覧者でOK）してください。
手順は docs/セットアップ手順.md に書いてあります。
"""
import io
import json
import datetime as dt

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _creds():
    info = json.loads(config.GOOGLE_SA_JSON)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


# ---------------------------------------------------------------- スプレッドシート
def read_events():
    """イベントマスタを読んで、辞書のリストで返す。

    1行目を見出しとして扱い、2行目以降をデータにする。
    列の順番が変わっても壊れないように、見出しの文字で対応づける。
    （列番号で決め打ちすると、3号さんが列を1つ挿しただけで全部ずれる）
    """
    svc = build("sheets", "v4", credentials=_creds(), cache_discovery=False)
    res = svc.spreadsheets().values().get(
        spreadsheetId=config.SHEET_ID, range="A:Z").execute()
    rows = res.get("values", [])
    if not rows:
        return []
    header = rows[0]
    out = []
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))       # 短い行を空文字で埋める
        out.append({header[i]: r[i].strip() for i in range(len(header))})
    return out


LONG_EVENT_DAYS = 15      # これ以上続くものは「長期のおしらせ」とみなす


def pick_week(events, start: dt.date, end: dt.date):
    """今週ぶんの、掲載可否が ○ のイベントだけを取り出す。

    「開始日〜終了日」が今週と少しでも重なっていれば対象にする。
    夏まつりウィークのような複数日イベントを取りこぼさないため。

    ただし長期のおしらせ（例：夏休みの間ずっと有効な施設無料）は例外扱いにする。
    素直に「重なっていたら載せる」だけにすると、同じお知らせが6週連続で
    毎回1枚目に出てしまい、投稿が代わり映えしなくなる。
    そこで、15日以上続くものは「始まった週」と「終わる週」だけに載せ、
    並び順も後ろに回して、その週の新しい情報を前に出す。
    """
    short, long_ = [], []
    for e in events:
        if e.get("掲載可否", "").strip() != "○":
            continue
        try:
            s = dt.date.fromisoformat(e["開始日"])
            t = dt.date.fromisoformat(e["終了日"] or e["開始日"])
        except (ValueError, KeyError):
            continue                                # 日付が壊れている行は黙って飛ばす
        if not (t >= start and s <= end):
            continue

        span = (t - s).days + 1
        if span >= LONG_EVENT_DAYS:
            starts_here = start <= s <= end
            ends_here = start <= t <= end
            if starts_here or ends_here:
                long_.append((s, e))
            continue                                # 途中の週には出さない
        short.append((s, e))

    short.sort(key=lambda x: x[0])
    long_.sort(key=lambda x: x[0])
    return [e for _, e in short] + [e for _, e in long_]


# ---------------------------------------------------------------- Drive
def list_photos(folder_id):
    svc = build("drive", "v3", credentials=_creds(), cache_discovery=False)
    res = svc.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false",
        fields="files(id,name,mimeType)", pageSize=200).execute()
    return res.get("files", [])


def download(file_id, dest_path):
    svc = build("drive", "v3", credentials=_creds(), cache_discovery=False)
    req = svc.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(buf.getvalue())
    return dest_path
