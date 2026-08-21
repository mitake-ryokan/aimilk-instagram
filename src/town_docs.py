"""町が出すPDFが新しく出たことに気づく。

■ なぜこれが要るのか（2026-08-21 追加）
AIみるくに載せる行事は、これまで観光サイトと3号さんが撮ったチラシから集めていた。
その網には「町が出す暮らしのおしらせ」がまるごと抜けていた。

実際、8月10日の回覧には「すすき草原 臨時駐車場 9/1〜11/30」が載っていたのに、
シートには入っていなかった。仙石原の宿として、いちばん載せたい種類の情報だった。
探す場所が足りなかったのであって、読み落としたのではない。

■ 何をして、何をしないか
する    … 新しいPDFが出たことに気づく／中身を文字にして残す／
          日付が入っている部分を拾って、GitHubのIssue（課題メモ）に書く
しない  … スプレッドシートに書き込む

なぜ書き込まないか。「載せるかどうか」は人が決める、と決めたから。
機械が勝手に足すと、間違ったまま誰も気づかずに投稿へ出る。
それはこの仕組みでいちばん避けたいことなので、
「気づくところまで」を機械に、「選ぶところ」を人に置いている。

■ どこを見ているか
　回覧「まちだより」… 月2回（10日・25日ごろ）。町内会に回る紙。いちばん地元寄り
　広報はこね　　　 … 月1回。町の公式

どちらも一覧ページのURLが変わらない。だから毎回そこから最新にたどり着ける。

■ 「もう読んだPDF」をどうやって覚えているか
GitHubの実行環境は毎回まっさらな新品で、前回のことを何も覚えていない。
そこで読んだURLを state/town_docs_seen.json に書いてコミットしている。
リポジトリを記憶がわりに使っている。画像を public/ に置くのと同じ理屈。
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "town_docs_seen.json"
TEXT_DIR = ROOT / "state" / "town_text"

KAIRAN_INDEX = "https://www.town.hakone.kanagawa.jp/www/contents/1747697722331/index.html"
KOHO_INDEX = "https://www.town.hakone.kanagawa.jp/www/contents/1100000000964/index.html"

# 一覧ページは新しいものが上から並んでいる。上から何件だけ見るか。
# ■ なぜ全部見ないのか
# 回覧のページには78本、広報には117号ぶんのリンクがある。
# 全部読むと初回に大量のPDFを落とすことになるし、意味もない。
# 週1回動かすなら、上から数件だけ見れば新しいものは必ず拾える。
# 回覧は1回ぶんが「回覧・チラシ一覧・世帯配布」の最大3本に分かれるので、
# 4本見ておけば直近2回ぶんが視界に入る。
KAIRAN_MAX = 4
KOHO_MAX = 1

UA = {"User-Agent": "Mozilla/5.0 (compatible; aimilk-bot/1.0; +https://github.com/mitake-ryokan/aimilk-instagram)"}

# 「9月2日」「9 月 2 日」どちらも拾う
DATE_RE = re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日")
ANCHOR_RE = re.compile(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _get(url, binary=False):
    """町のサイトから取ってくる。3回までやり直す。

    役場のサイトは時々応答が遅い。1回で諦めると、
    「今週は新しいPDFが無かった」と嘘の結論になる。それがいちばん困る。
    """
    last = None
    for _ in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=40)
            r.raise_for_status()
            if binary:
                return r.content
            # ■ 文字化けを防ぐ（2026-08-21 追加）
            # 町のサイトはHTTPヘッダに「文字の種類」を書いていない。
            # requests はそれが無いとラテン文字だと決めつけるので、日本語が化ける。
            # 実際、初回の実行で見出しが「å..è¦§8æ..10æ.¥」になった。
            # 見た目が汚いだけなら我慢もできるが、
            # 広報はこねは「広報はこね」という文字でリンクを探しているので、
            # 化けると1件も見つからない。回覧だけ拾えて広報は静かに落ちる、
            # といういちばん気づきにくい失敗になっていた。
            # HTMLの冒頭に書いてある宣言を読んで、そのとおりに読み直す。
            head = r.content[:2048].decode("ascii", "ignore").lower()
            m = re.search(r"charset=[\"\']?([\w-]+)", head)
            r.encoding = (m.group(1) if m else None) or r.apparent_encoding or "utf-8"
            return r.text
        except requests.RequestException as e:
            last = e
    raise RuntimeError(f"取得できませんでした: {url}\n{last}")


def _abs(url):
    if url.startswith("http"):
        return url
    return "https://www.town.hakone.kanagawa.jp" + url


def _links(html):
    """<a>タグを (リンク先, 見出し) の並びで返す。ページに出てくる順のまま。"""
    out = []
    for href, inner in ANCHOR_RE.findall(html):
        text = TAG_RE.sub("", inner)
        text = " ".join(text.split())
        out.append((href, text))
    return out


def find_kairan():
    """回覧「まちだより」の最新PDFを探す。

    このページはPDFへのリンクが直接並んでいる。上から新しい順。
    回覧本体（kairan）だけでなく、チラシ一覧（HP）や世帯配布（setai）も拾う。
    チラシ一覧には「仙石原サロン」「箱根地域 健民祭」のような、
    広報には載らない地区の行事が入っている。ここがいちばんおいしい。
    """
    html = _get(KAIRAN_INDEX)
    found = []
    for href, text in _links(html):
        if href.lower().endswith(".pdf"):
            found.append((_abs(href), text or "回覧まちだより"))
        if len(found) >= KAIRAN_MAX:
            break
    return [("回覧「まちだより」", u, t) for u, t in found]


def find_koho():
    """広報はこねの最新号PDFを探す。

    こちらは2階建て。バックナンバー一覧 → 号のページ → PDF、とたどる。
    一覧に直接PDFが無いので、号のページを1枚めくる必要がある。
    """
    html = _get(KOHO_INDEX)
    issues = [(_abs(h), t) for h, t in _links(html)
              if "広報はこね" in t and "/www/contents/" in h]
    out = []
    for page, title in issues[:KOHO_MAX]:
        sub = _get(page)
        pdfs = [_abs(h) for h, _ in _links(sub) if h.lower().endswith(".pdf")]
        if pdfs:
            out.append(("広報はこね", pdfs[0], title))
    return out


def pdf_text(data):
    """PDFの中身を文字にする。

    pdfminer は「行」ではなく「かたまり」で返してくれる。
    広報も回覧も段組みなので、行で切ると日付と行事名がバラバラになる。
    かたまりのまま扱ったほうが、あとで人が読める形になる。
    """
    import io
    from pdfminer.high_level import extract_text
    return extract_text(io.BytesIO(data))


def date_blocks(text, limit=60):
    """日付が入っているかたまりだけ取り出す。

    ここは賢いことをしていない。「◯月◯日」があるかどうかだけ。
    行事以外（申請の締切など）も混ざるが、それでいい。
    落とすより混ぜるほうが安全で、選ぶのは人だから。
    """
    out, seen = [], set()
    for block in re.split(r"\n\s*\n", text):
        b = " ".join(block.split())
        if not DATE_RE.search(b):
            continue
        if len(b) < 6:
            continue
        b = b[:200]
        if b in seen:
            continue
        seen.add(b)
        out.append(b)
        if len(out) >= limit:
            break
    return out


def load_seen():
    if STATE.exists():
        try:
            return set(json.loads(STATE.read_text())["seen"])
        except (ValueError, KeyError):
            print("::warning::state ファイルが壊れていたので、まっさらから始めます")
    return set()


def save_seen(seen):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"seen": sorted(seen)},
                                ensure_ascii=False, indent=1))


def open_issue(title, body):
    """GitHubのIssue（課題メモ）を1件立てる。

    ■ なぜIssueなのか
    「新しいPDFが出た」を3号さんに届ける道が要る。
    ワークフローが成功して終わると、GitHubはメールを出さない（失敗のときだけ）。
    Issueを立てれば、リポジトリの持ち主にはメールが届く。
    新しい鍵もお金も要らず、今ある仕組みだけで通知になる。
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        print("::warning::GITHUB_TOKEN が無いので、Issueは立てません（ログだけ残します）")
        return None
    r = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body[:60000]}, timeout=30)
    if r.status_code >= 300:
        print(f"::warning::Issueを立てられませんでした: {r.status_code} {r.text[:200]}")
        return None
    return r.json().get("html_url")


def commit_state(message):
    subprocess.run(["git", "config", "user.name", "aimilk-bot"], check=True)
    subprocess.run(["git", "config", "user.email",
                    "aimilk-bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", "state"], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("  記録に変更なし")
        return
    subprocess.run(["git", "commit", "-m", message], check=True)
    # ■ pull --rebase を挟む理由
    # 同じワークフローの中で、投稿画像のコミットが先に走っていることがある。
    # 手元が古いまま push すると弾かれる。取り込んでから積み直す。
    subprocess.run(["git", "pull", "--rebase", "--autostash"], check=False)
    subprocess.run(["git", "push"], check=True)
    print("  記録をGitHubに残しました")


def main(dry_run=False):
    print("■ 町のPDFを見に行きます")
    docs = find_kairan() + find_koho()
    for src, url, title in docs:
        print(f"   [{src}] {title} -> {url}")

    seen = load_seen()
    fresh = [d for d in docs if d[1] not in seen]
    if not fresh:
        print("■ 新しいPDFはありませんでした")
        return 0
    print(f"■ 新しいPDFが{len(fresh)}本あります")

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    sections = []
    for src, url, title in fresh:
        print(f"   読みます: {title}")
        try:
            text = pdf_text(_get(url, binary=True))
        except Exception as e:                      # noqa: BLE001
            # ■ ここで落とさない理由
            # PDFが1本読めなかっただけで投稿の仕組みごと騒ぐ必要はない。
            # 読めなかったことは記録に残さないので、次回もう一度試される。
            print(f"::warning::読めませんでした（次回もう一度試します）: {url} / {e}")
            continue
        name = re.sub(r"[^A-Za-z0-9._-]", "_", url.rsplit("/", 1)[-1])
        (TEXT_DIR / f"{name}.txt").write_text(text)
        blocks = date_blocks(text)
        print(f"     日付を含む記述: {len(blocks)}件")
        sections.append((src, url, title, blocks))
        seen.add(url)

    if not sections:
        print("■ 読めたPDFがありませんでした")
        return 0

    lines = ["町から新しいおしらせが出ました。",
             "**日付が入っている部分だけ**を機械が抜いたものです。",
             "行事以外（申請の締切など）も混ざります。載せるかどうかは人が決めてください。",
             ""]
    for src, url, title, blocks in sections:
        lines.append(f"## {src}：{title}")
        lines.append(f"元のPDF → {url}")
        lines.append("")
        lines += [f"- {b}" for b in blocks] or ["- （日付を含む記述は見つかりませんでした）"]
        lines.append("")
    lines.append("---")
    lines.append("全文は `state/town_text/` に置いてあります。")
    body = "\n".join(lines)

    if dry_run:
        print("■ dry-run のため、Issueも記録も残しません")
        print("---- Issueに書く予定の中身 ----")
        print(body[:4000])
        return 0

    titles = "／".join(t for _, _, t, _ in sections)
    url = open_issue(f"町の新しいおしらせ（{titles}）", body)
    print(f"■ Issueを立てました: {url}")
    save_seen(seen)
    commit_state(f"町のPDFを読みました（{titles}）")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
