"""Synthesize only missing narrated cues using the user's verified AquesTalk1 files."""

import argparse
import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipFile

from project import asset, need, read_json

NAMES = ('f1', 'f2')


@contextmanager
def runtime(location):
    if location.is_dir():
        yield location
        return
    with ZipFile(location) as z, tempfile.TemporaryDirectory(prefix='neko-ou-voice-') as temp:
        root = Path(temp)
        for voice in NAMES:
            (root/voice).mkdir()
            for name in ('AquesTalk.dll', 'AqLicence.txt'):
                member = f'assets/runtime/aquestalk/{voice}/{name}'
                need(z.getinfo(member).file_size < 4_000_000, f'音声ファイルの大きさを確認してください {member}')
                (root/voice/name).write_bytes(z.read(member))
        yield root


def generate(manifest, path):
    from aquestalk_runtime import Engine
    root = manifest.resolve().parent
    data = read_json(manifest)
    tasks = []
    for cue in data['cues']:
        if cue.get('role')=='eyecatch':
            continue
        out=asset(root,cue['voice'],required=False)
        if out.is_file():
            continue
        name=cue.get('speaker','f1')
        speed=cue.get('speed',151)
        reading=cue.get('reading','')
        need(name in NAMES and type(speed) is int and 50<=speed<=300 and reading.strip(),
             f'話者、速度、確定読みを確認してください {cue["id"]}')
        need(out.suffix.lower()=='.wav',f'音声の保存先はWAVを指定してください {cue["id"]}')
        tasks.append((out,name,speed,reading))
    need(len({t[0] for t in tasks})==len(tasks),'新規音声の出力先が重複しています')
    if not tasks:
        return
    with runtime(path) as folder:
        engines={}
        for out,name,speed,reading in tasks:
            if name not in engines:
                need((folder/name/'AqLicence.txt').is_file(), f'利用許諾ファイルがありません {name}')
                engines[name]=Engine(folder/name/'AquesTalk.dll')
            binary=engines[name].synth(reading,speed)
            out.parent.mkdir(parents=True,exist_ok=True)
            with out.open('xb') as audio:
                audio.write(binary)
            print(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--runtime',type=Path,default=os.environ.get('AQUESTALK_DIR'))
    args=parser.parse_args()
    try:
        need(args.runtime is not None,'利用権のあるAquesTalk1フォルダか既存の制作ZIPを --runtime に指定してください')
        generate(args.manifest,args.runtime)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1,f'音声生成エラー {exc}\n')


if __name__=='__main__':
    main()
