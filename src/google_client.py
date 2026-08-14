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


def _postable(e):
    """この行を投稿してよいか。

    ■ 判定のルール（2026-08-14 変更）
    以前は「○ の行だけ投稿」だった。つまり毎週人間が保留をさばく前提。
    だがリマインドの仕組みもないのに人の記憶に頼る設計は、実際に止まった。
    かといって全部自動にすると、箱根ナビの間違った日付（実例あり）を
    そのまま投稿して、間違った日に人を送り出しかねない。

    そこで「情報源が信頼できるかどうか」で分ける。
      ○                     → 投稿する（人が明示的にOKを出した）
      ×                     → 投稿しない（人が明示的に止めた）
      確度が「高」            → 投稿する（広報はこね・公式・ウォーカープラス等。
                                裏取り済みの情報源なので人の確認を待たない）
      確度が「中」「低」       → 投稿しない（箱根ナビの裏取りなし等。
                                出したいときだけ人が ○ にする）
      確度が空欄             → 投稿する（★2026-08-14 追加）

    ■ なぜ「確度が空欄」を投稿するのか
    ここがこのシステムの一番おいしいところ。
    回覧板・自治会・旅館組合青年部・公民館の掲示板——Webに出ない地域の情報は、
    3号さんが自分の足と耳で拾ってくる。それがこの投稿の差別化点そのもの。
    その一次情報に「確度」を書かせるのは筋が通らない。本人が見聞きしたのだから。

    自動収集したものには必ず確度を入れる決まりにしてあるので、
    「確度が空欄」＝「人が手で入れた」と見なして構わない。
    3号さんは 日付・イベント名・場所 の3つだけ埋めれば、それで投稿に載る。

    ふだんの作業はゼロ。拾った情報を放り込むときも、3列だけ。
    """
    mark = e.get("掲載可否", "").strip()
    if mark == "○":
        return True
    if mark == "×":
        return False
    kakudo = e.get("確度", "").strip()
    if kakudo == "":
        return True          # 人が手で入れた一次情報
    return kakudo == "高"


def _date_or_none(s):
    try:
        return dt.date.fromisoformat((s or "").strip())
    except (ValueError, AttributeError):
        return None


def pick_week(events, start: dt.date, end: dt.date):
    """今週ぶんの、投稿してよいイベントを取り出す（判定は _postable を参照）。

    「開始日〜終了日」が今週と少しでも重なっていれば対象にする。
    夏まつりウィークのような複数日イベントを取りこぼさないため。

    ■ 3つの箱に分けている
    　1. 今週おきること          … その週の主役。先頭に出す
    　2. 告知（まだ先だが推したい）… 「告知開始日」を書いた行だけ。2番目
    　3. 長期のおしらせ          … 期間の長いもの。後ろに回す

    長期のおしらせを別扱いにするのは、素直に「重なっていたら載せる」だけだと
    同じお知らせが6週連続で毎回1枚目に出て、投稿が代わり映えしなくなるため。
    15日以上続くものは「始まった週」と「終わる週」だけに載せる。

    ■ 「告知開始日」列（任意）について
    申し込みが要るイベントは、開催週に1回出しても遅い。申込は締切っている。
    スポGOMIのように主催側として推したいものは、何週も前から繰り返し出したい。
    そこで「告知開始日」に日付を書くと、その日から開催日まで毎週の投稿に出る。
    空欄なら今までどおり、開催週にだけ出る。書いた行だけが変わる。
    """
    now, promo, long_ = [], [], []
    for e in events:
        if not _postable(e):
            continue
        s = _date_or_none(e.get("開始日"))
        t = _date_or_none(e.get("終了日")) or s
        if s is None:
            continue                                # 日付が壊れている行は黙って飛ばす

        happening = (t >= start and s <= end)
        if happening:
            span = (t - s).days + 1
            if span >= LONG_EVENT_DAYS:
                starts_here = start <= s <= end
                ends_here = start <= t <= end
                if starts_here or ends_here:
                    long_.append((s, e))
                continue                            # 途中の週には出さない
            now.append((s, e))
            continue

        # まだ先のイベント。告知開始日が来ていれば「告知」として載せる
        p = _date_or_none(e.get("告知開始日"))
        if p is not None and p <= end and s > end:
            promo.append((s, e))

    for bucket in (now, promo, long_):
        bucket.sort(key=lambda x: x[0])
    return [e for _, e in now] + [e for _, e in promo] + [e for _, e in long_]


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
