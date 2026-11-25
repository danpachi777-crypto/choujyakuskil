"""Create, validate, and describe a channel episode using its measured audio timing."""

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from urllib.parse import urlparse

FPS = 30
RATE = 48000
ROOT = Path(__file__).resolve().parents[1]
ROLES = {'opening', 'reaction', 'context', 'eyecatch', 'closing'}
KINDS = {'article_post', 'article_comment', 'original_thread', 'provided_post'}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, key, low=0, high=None):
    need(isinstance(value, (int, float)) and not isinstance(value, bool)
         and math.isfinite(value) and value >= low and (high is None or value <= high), key)
    return value


def asset(root, name, required=True):
    need(isinstance(name, str) and name, f'ローカルファイルを指定してください {name!r}')
    candidate = (root / name).resolve()
    need(not Path(name).is_absolute() and candidate.is_relative_to(root), f'プロジェクト内の相対パスを指定してください {name}')
    if required:
        need(candidate.is_file(), f'素材がありません {name}')
    return candidate


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def http(link, field):
    parsed = urlparse(link or '')
    need(parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username, f'公開URLを確認してください {field}')


def probe(name):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_format', '-show_streams', '-show_chapters', '-of', 'json', str(name)
    ]))


def seconds(name, stream_type):
    data = probe(name)
    match = next((s for s in data.get('streams', []) if s['codec_type'] == stream_type), None)
    need(match is not None, f'{stream_type} ストリームがありません {name}')
    try:
        return number(float(match.get('duration', data['format'].get('duration'))), str(name), .001)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'尺を取得できません {name}') from exc


def clean(text):
    return ''.join(text.split())


def identifier(value, label):
    need(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]+', value), f'IDを確認してください {label} {value!r}')
    return value


def init(folder):
    folder.mkdir(parents=True, exist_ok=False)
    for sub in ('出典', '素材', '音声', '音響', '出力'):
        (folder/sub).mkdir()
    shutil.copy2(ROOT/'assets/channel-icon.jpg', folder/'素材/channel-icon.jpg')
    write_json(folder/'project.json', {
        'title': '', 'description': '', 'spoilers': '', 'min_seconds': 480,
        'channel': {'name': 'ネコ王の研究所', 'handle': '@2ch-rank', 'url': 'https://www.youtube.com/@2ch-rank',
                    'icon': '素材/channel-icon.jpg'},
        'cover': None, 'chapters': [], 'sources': [], 'cues': [], 'audio': [],
        'credits': [],
    })
    print(folder/'project.json')


@dataclass(frozen=True)
class Project:
    root: Path
    data: dict
    sources: dict
    cues: list
    starts: list
    marks: dict
    frames: int


def prepare(manifest, preview=False):
    root = manifest.resolve().parent
    data = read_json(manifest)
    need(isinstance(data.get('title'), str) and data['title'].strip(), 'title に動画名を入れてください')
    need(isinstance(data.get('description'), str), 'description を入力してください')
    chapters = data['chapters']
    need(chapters and all(isinstance(ch, str) and ch.strip() for ch in chapters), '章題を入力してください')
    need(len(set(chapters)) == len(chapters), '章題が重複しています')
    channel = data['channel']
    need(channel['name'].strip() and channel['handle'].strip(), 'チャンネル名を入れてください')
    http(channel['url'], 'channel.url')
    if channel.get('icon'):
        asset(root, channel['icon'])
    if bg:=data.get('background'):
        movie=asset(root,bg['file'])
        need(isinstance(bg.get('label'),str) and bg['label'].strip(), '背景映像の短い表示名を入力してください')
        need(isinstance(bg.get('source_title'),str) and bg['source_title'].strip(), '背景映像の出典名を入力してください')
        if bg.get('source_url'):
            http(bg['source_url'], 'background.source_url')
        else:
            need(bg.get('origin')=='self_recorded', '背景映像のURL、または自分で録画した素材と分かるoriginを指定してください')
        bg['focus']=number(bg.get('focus',.5),'background.focus',0,1)
        bg['fit']=bg.get('fit','cover')
        need(bg['fit'] in ('cover','contain'),'background.fitはcoverまたはcontainを指定してください')
        bg['offset']=number(bg.get('offset',0),'background.offset')
        bg['duration']=seconds(movie,'video')
    if data.get('cover'):
        asset(root, data['cover'])
    for credit in data.get('credits', []):
        need(credit['label'].strip(), '素材のクレジット名が空です')
        if credit.get('url'):
            http(credit['url'], credit['label'])

    sources = {}
    for source in data['sources']:
        sid = identifier(source['id'], 'source')
        need(sid not in sources, f'出典IDが重複しています {sid}')
        kind = source['kind']
        need(kind in KINDS, f'出典区分を確認してください {sid}')
        need(isinstance(source['post'], str) and source['post'].strip(), f'レス番号または資料内の識別子 {sid}')
        if kind != 'provided_post' or source.get('url'):
            http(source.get('url'), sid)
        if source.get('thread_url'):
            http(source['thread_url'], sid)
        content = asset(root, source['snapshot']).read_text(encoding='utf-8-sig')
        index = source.get('range', [0, len(content)])
        need(len(index) == 2 and all(type(p) is int for p in index)
             and 0 <= index[0] < index[1] <= len(content), f'原文の範囲を確認してください {sid}')
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        need(source.get('sha256') == digest, f'原文の保存時点のSHA-256と一致しません {sid}')
        sources[sid] = dict(source, quote=content[slice(*index)], sha256=digest)

    cues, marks, starts, pos = [], {}, [], 0
    previous_chapter = -1
    audio_lengths, visual_lengths = {}, {}
    phases = []
    for entry in data['cues']:
        key = identifier(entry['id'], 'cue')
        need(key not in marks and key!='end', f'字幕IDが重複しています {key}')
        role = entry['role']
        need(role in ROLES, f'roleを確認してください {key}')
        need(role != 'context' or data.get('allow_context') is True, f'本編の補足ナレーションは依頼に応じて有効化します {key}')
        text = entry.get('text', '')
        ref = entry.get('source')
        need((role == 'reaction') == (ref is not None), f'引用の出典とroleを確認してください {key}')
        if ref:
            need(ref in sources, f'出典IDが見つかりません {ref}')
        chapter = entry['chapter']
        need(type(chapter) is int and 0 <= chapter < len(chapters)
             and previous_chapter <= chapter <= previous_chapter+1, f'章の順番を確認してください {key}')
        if chapter != previous_chapter:
            starts.append(pos)
            previous_chapter = chapter
        if role == 'eyecatch':
            need(not entry.get('voice') and isinstance(text, str), f'アイキャッチの音声は効果音キューに置きます {key}')
            speech_frames = 0
            frames = round(FPS*number(entry.get('seconds', 1.3), f'アイキャッチの尺 {key}', .2, 15))
        else:
            need(isinstance(text, str) and text.strip(), f'字幕が空です {key}')
            voice = asset(root, entry['voice'])
            if voice not in audio_lengths:
                audio_lengths[voice] = seconds(voice, 'audio')
            speech_frames = math.ceil(FPS*audio_lengths[voice])
            frames = speech_frames + round(FPS*number(entry.get('pause', .23), f'話者の間 {key}', 0))
            phase = 'body' if role in {'reaction', 'context'} else role
            if not phases or phase != phases[-1]:
                phases.append(phase)
        visual = entry.get('visual') or data.get('default_visual')
        asset(root, visual)
        layout = entry.get('fit', 'cover')
        need(layout in ('cover', 'contain'), f'fitはcoverかcontainを指定してください {key}')
        motion = entry.get('motion', 'still')
        need(motion in {'still', 'push', 'video'}, f'motionを確認してください {key}')
        seek = number(entry.get('visual_offset', 0), f'素材の開始位置 {key}')
        if motion == 'video':
            if visual not in visual_lengths:
                visual_lengths[visual] = seconds(asset(root, visual), 'video')
            need(seek < visual_lengths[visual], f'素材の尺を超えています {key}')
        marks[key] = pos
        cues.append(dict(entry, start=pos, frames=frames, speech_frames=speech_frames, chapter=chapter,
                         visual=visual, fit=layout, motion=motion, visual_offset=seek))
        pos += frames
    need(cues and len(starts)==len(chapters), 'すべての章に1つ以上の字幕が必要です')
    need(cues[0]['role'] != 'eyecatch' and cues[-1]['role'] != 'eyecatch', '冒頭・締めは音声または反応から始めてください')
    need(phases in (['body'], ['opening','body'], ['body','closing'], ['opening','body','closing']), '冒頭、本編、締めの並びを確認してください')
    used = set()
    for sid, group in groupby(cues, key=lambda cue: cue.get('source')):
        if sid:
            need(sid not in used, f'同じレスが会話の別地点に重複しています {sid}')
            used.add(sid)
            need(clean(''.join(row['text'] for row in group)) == clean(sources[sid]['quote']),
                 f'採用した字幕が保存した引用範囲と一致しません {sid}')
    need(used, '実在する反応の出典が必要です')
    keys = []
    for sid in used:
        source = sources[sid]
        article_comment = source['kind']=='article_comment'
        origin = source.get('url') if article_comment else source.get('thread_url') or source.get('url')
        keys.append((origin or source['snapshot'], 'comment' if article_comment else 'post', source['post']))
    need(len(keys) == len(set(keys)), '同じ投稿を別々の出典IDで登録しています')
    marks['end'] = pos
    for sound in data.get('audio', []):
        need(sound['kind'] in {'bgm', 'se'}, '音源のkindはbgmまたはse')
        asset(root, sound['file'])
        need(sound['title'].strip(), '使用する音源の名前を記録してください')
        http(sound['url'], sound['title'])
        first = marks[sound['at']]/FPS + number(sound.get('delay', 0), sound['title'])
        last = marks[sound.get('until', 'end')]/FPS
        need(first < last <= pos/FPS, f'音源の開始・終了位置 {sound["title"]}')
        number(sound.get('gain_db', -24), f'音量 {sound["title"]}', -80, 3)
        number(sound.get('offset', 0), f'音源の開始位置 {sound["title"]}')
        number(sound.get('fade', .65), f'フェード {sound["title"]}')
    minimum = number(data.get('min_seconds', 480), 'min_seconds')
    need(preview or pos/FPS >= minimum, f'完成尺が不足しています {pos/FPS:.2f}秒 / {minimum:g}秒')
    return Project(root, data, sources, cues, starts, marks, pos)


def srt_time(frame):
    n = round(frame*1000/FPS)
    return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'


def yt_time(frame):
    n = frame//FPS
    return f'{n//3600:02}:{n//60%60:02}:{n%60:02}' if n>=3600 else f'{n//60:02}:{n%60:02}'


def escaped(text):
    return re.sub(r'([\\=;#\n])', r'\\\1', str(text))


def publication(project, folder):
    folder.mkdir(exist_ok=True, parents=True)
    cue_lines = []
    refs = {}
    with (folder/'タイムコード付き出典.tsv').open('w', encoding='utf-8-sig', newline='') as out:
        table = csv.writer(out, delimiter='\t')
        table.writerow(['開始','終了','区分','レス番号','返信先','URL','元スレ','原文ファイル','SHA-256'])
        for cue in project.cues:
            source = project.sources.get(cue.get('source'), {})
            if source:
                refs[source['id']] = source
            a, b = srt_time(cue['start']), srt_time(cue['start']+cue['frames'])
            if cue.get('text'):
                cue_lines.append(f"{len(cue_lines)+1}\n{a} --> {b}\n{cue['text']}\n")
            table.writerow([a, b, source.get('kind', cue['role']), source.get('post', ''), source.get('reply_to', ''),
                            source.get('url', ''), source.get('thread_url', ''), source.get('snapshot', ''), source.get('sha256','')])
    (folder/'字幕.srt').write_text('\n'.join(cue_lines), encoding='utf-8')
    write_json(folder/'編集タイムライン.json', {'fps':FPS,'frames':project.frames,'cues':project.cues,'sources':list(refs.values())})

    end = project.frames
    chapters = list(zip(project.starts, project.data['chapters']))
    closing = next((cue['start'] for cue in project.cues if cue['role']=='closing'), None)
    if closing is not None and closing not in project.starts:
        chapters.append((closing, '締め・感想'))
        chapters.sort()
    tags = [';FFMETADATA1', 'title='+escaped(project.data['title']), 'artist='+escaped(project.data['channel']['name'])]
    for i,(start,label) in enumerate(chapters):
        stop = (chapters[i+1][0] if i+1<len(chapters) else end)
        tags.extend(['[CHAPTER]', f'TIMEBASE=1/{FPS}', f'START={start}', f'END={stop}', 'title='+escaped(label)])
    (folder/'chapters.ffmeta').write_text('\n'.join(tags)+'\n', encoding='utf-8')

    yt = [chapters[0]]
    for frame, name in chapters[1:]:
        if frame//FPS - yt[-1][0]//FPS >= 10 and end//FPS-frame//FPS >= 10:
            yt.append((frame, name))
    title = project.data['title']
    src_urls = dict.fromkeys(s['url'] for s in refs.values() if s.get('url'))
    if not src_urls:
        src_urls = dict.fromkeys(s['thread_url'] for s in refs.values() if s.get('thread_url'))
    description = ['\n'.join(src_urls), title, project.data['description'], project.data.get('spoilers',''),
                   f"{project.data['channel']['name']}\n{project.data['channel']['url']}"]
    if len(yt)>=3:
        description.append('\n'.join(f'{yt_time(f)} {label}' for f,label in yt))
    credits = [c['label']+('\n'+c['url'] if c.get('url') else '') for c in project.data.get('credits',[])]
    credits.extend(dict.fromkeys(f"{'BGM' if a['kind']=='bgm' else '効果音'}　{a['title']}\n{a['url']}" for a in project.data.get('audio',[])))
    if bg:=project.data.get('background'):
        line='背景映像　'+bg['source_title']
        if bg.get('source_url'):
            line+='\n'+bg['source_url']
        credits.append(line)
    if credits:
        description.append('\n\n'.join(credits))
    (folder/'YouTube概要欄.txt').write_text('\n\n'.join(p for p in description if p)+'\n', encoding='utf-8')


def audit(project, video):
    data = probe(video)
    pic = next(s for s in data['streams'] if s['codec_type']=='video')
    snd = next(s for s in data['streams'] if s['codec_type']=='audio')
    need(pic['codec_name']=='h264' and pic['width']==1920 and pic['height']==1080, '完成動画の解像度・コーデックを確認してください')
    need(pic['avg_frame_rate']=='30/1' and int(pic['nb_frames'])==project.frames, '映像フレームと台本が一致しません')
    need(snd['codec_name']=='aac' and snd['sample_rate']==str(RATE) and snd['channels']==2, '音声仕様を確認してください')
    audio_duration = float(snd['duration'])
    need(abs(audio_duration-project.frames/FPS) < .1, '映像と音声の全尺にずれがあります')
    subprocess.run(['ffmpeg','-v','error','-xerror','-nostdin','-i',str(video),'-map','0:v:0','-map','0:a:0','-f','null','-'], check=True)
    return {'seconds': project.frames/FPS,'fps': FPS,'frames':project.frames,
            'posts':len({c['source'] for c in project.cues if c.get('source')}),
            'roles':dict(Counter(c['role'] for c in project.cues))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('init').add_argument('folder', type=Path)
    plan = commands.add_parser('plan')
    plan.add_argument('manifest', type=Path)
    plan.add_argument('--preview', action='store_true')
    audit_cmd = commands.add_parser('audit')
    audit_cmd.add_argument('manifest', type=Path)
    audit_cmd.add_argument('video', type=Path)
    make_digest = commands.add_parser('digest')
    make_digest.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    try:
        if args.action=='init':
            init(args.folder.resolve())
        elif args.action=='digest':
            print(hashlib.sha256(args.snapshot.read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest())
        else:
            p = prepare(args.manifest, getattr(args,'preview',False))
            if args.action=='plan':
                publication(p, p.root/'出力')
                print(f"{p.frames/FPS:.2f}秒 / {len(p.cues)}字幕")
            else:
                report = audit(p, args.video)
                write_json(args.video.parent/'完成検査.json', report)
                print(report)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'検査エラー {exc}\n')


if __name__ == '__main__':
    main()
