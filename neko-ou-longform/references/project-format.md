# 制作データとコマンド

標準の依存関係は Python 3.11 以降、Pillow、NumPy、FFmpeg・ffprobe。Python環境は既存のものを優先する。色と字幕の再現に必要なフォントはライセンスと一緒に同梱。各作品の納品場所は本スキルの外に新しく作る。

```sh
skill="${CODEX_HOME:-$HOME/.codex}/skills/neko-ou-longform"
python3 "$skill/scripts/project.py" init "$HOME/Movies/新規の題材名"
```

作成された project.json に以下の情報を入れる。素材のパスは project.json からの相対パス。空の初期ファイルは、本番の内容を用意してから書き出す。

## project.json

| キー | 内容 |
|---|---|
| title / description / spoilers | 動画名、短い視聴者向け紹介、ネタバレ注意。 |
| min_seconds | 完成品の下限。通常480。尺の指定がある場合は変更する。 |
| channel | name、handle、url、icon。初期値はネコ王の研究所。 |
| cover | 作成済みのJPEG・PNGサムネイル。必要な場合に指定すると完成動画と同じフォルダへコピー。 |
| background | 背景を別の動画として出す設定。未指定なら通常の情景背景。詳細は下記。 |
| default_visual | cueにvisualがないときに使うローカル画像や映像。 |
| visual_label | 映像の補足表示。例は情景イラストによる再構成。cue単位でも指定できる。 |
| chapters | 章題の配列。cuesのchapterは0からの添字。 |
| sources | 引用本文を保存した投稿の登録。 |
| cues | 発話、絵、字幕、役割を並べた配列。 |
| audio | 名前・URL付きのBGM、効果音。 |
| credits | 素材と原作のクレジット配列。各要素にlabel、必要に応じてurl。 |

### 出典と字幕

- sourcesの各要素にid、kind、post、snapshot、sha256を入れる。kindはarticle_post、article_comment、original_thread、provided_postのいずれか。publicの出典にはurlを記載し、元スレを確認できたときはthread_urlも指定する。返信はreply_to、画面に表示するサイト名はlabelに入れる。提供された資料の識別子もpostへ入れる。
- snapshotは照合した一つの投稿の原文UTF-8テキスト。rangeは文字単位の開始位置と終端の直後で、省略すると全文。sha256は `python3 "$skill/scripts/project.py" digest "出典/投稿.txt"` で出せる。前後の文脈・確認日・採用理由が必要なら出典フォルダの控えに併記する。
- 各cueにid、role、chapterを指定する。roleはopening、reaction、eyecatch、closing。ユーザーが本編の補足ナレーションを依頼したときはallow_contextをtrueにしてcontextを使用する。
- reactionにはsourceで出典IDを指定する。長い投稿は同じsourceのcueを連続させ、textをつなげると採用範囲と一致するようにする。空白と字幕改行は照合時に無視する。口語と誤字を原文に残す場合はreadingを修正する。noteには短い説明を入れられる。
- 発話のあるcueにtext、voiceを入れる。pauseは発話後の静かな尺を秒で指定できる。初期値は0.23秒。読みが定まっている場合はreadingも残す。eyecatchはsecondsで表示尺を決め、必要に応じてtextに章題を設定し、効果音はaudioに置く。
- cueのvisualで使用素材を選ぶ。motionはstill、push、video。videoはvisual_offsetで素材開始位置を指定できる。fitはcoverまたはcontain。余白のある画像、縦長コマ、注視点を切りたくない場合はcontainが使える。openingやclosingにはheadingを指定できる。
- audioの要素にはkind（bgmまたはse）、file、title、url、at（開始するcueのID）を入れる。untilは終了するcueのIDまたはend。delay、offset、fadeは秒、gain_dbはdB。ループ利用が許され、繰り返しを試聴済みのBGMにはloopをtrueにできる。

### ゲーム映像などの背景

背景動画を指定すると、本編の挿絵の横に独立した動画欄を設ける。章や字幕が切り替わっても、背景の再生位置は全体のタイムラインから求める。背景の音声はミックスに使わない。

```json
{
  "background": {
    "file": "素材/走行映像.mp4",
    "label": "GTA VI",
    "source_title": "Grand Theft Auto VI ／ Rockstar Games",
    "source_url": "https://www.rockstargames.com/VI/an-extended-look",
    "fit": "cover",
    "focus": 0.15
  }
}
```

labelは映像の確認結果に合わせる。自分で録画した素材ならsource_urlの代わりにoriginへself_recordedを指定できる。fitはcoverかcontain。coverのfocusは横の切り出し位置で0が左、1が右。ミニマップや両端の要素を残したければcontainを使う。offsetで背景動画の先頭からの位置を秒でずらせる。映像が短い場合は先に連続した背景トラックを作る。繰り返し映像になるので、繰り返しが目立つときは前もって複数の走行カットを編集する。引用するゲーム素材の利用条件は公開方法に合わせて確認する。

### 音声と書き出し

既存のWAVや音声エンジンを選び、voiceにファイルを入れる。AquesTalk1の使用権を確認した場合は、補助スクリプトで不足WAVだけ生成できる。cueに確定読みのreading（かな）、speaker（f1またはf2）、speed、未使用のWAV相対パスを指定する。同梱のアダプタが扱えるのは以前の環境で検証済みのDLL2種。DLL・使用許諾ファイルはスキルに同梱していない。pefileとunicornが必要。

このMacでは、以前の制作パッケージ `~/Downloads/YouTube_VIVANT第22話_20261025/VIVANT第22話_制作一式.zip` を音声環境の出所として参照できる。現在も利用条件を確認し、同じ環境で生成する場合はパッケージのパスを渡す。許諾のある別環境や収録WAVでも制作できる。

```sh
python3 "$skill/scripts/voice.py" project.json --runtime "/利用できる既存プロジェクト.zip"
python3 "$skill/scripts/project.py" plan project.json
python3 "$skill/scripts/render.py" project.json --preview --seconds 20
python3 "$skill/scripts/render.py" project.json
python3 "$skill/scripts/project.py" audit project.json "出力/完成動画.mp4"
```

- `plan`は原文、素材、発話尺、章の整合を調べ、字幕・概要欄・タイムコード付き出典表を作る。まだ短い試作は`plan --preview`で検査できる。
- `render --preview --start 字幕ID --seconds 12`で区間の試写を作れる。通常の仕上げは`--preview`なし。検査済みの完成動画と関連ファイルを出力する。別版は新しい出力フォルダを使い、そこへ`--output`で書き出す。
- BGMの区切り、字幕改行、問いかけ、素材の権利などの編集判断は脚本と試写で確かめる。プログラムは保存された原文との一致を検査し、公開元そのものの正しさは担当者が確認する。
- 以前の完成例は `~/Movies/フリーレン第1話_ネコ王の研究所版`。導入9.6秒、再会前のアイキャッチ1.3秒、投稿84件、締めと登録案内の配置を確認できる。題材や尺は新規プロジェクトで決める。
