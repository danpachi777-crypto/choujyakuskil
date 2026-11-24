"""Render an episode or a timed excerpt with Pillow, NumPy and FFmpeg."""

import argparse
import functools
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from project import FPS, RATE, ROOT, asset, audit, need, prepare, publication, write_json

W, H = 1920, 1080
MIX_RATE = 24000
INK, IVORY, GOLD = '#0e182a', '#fff8e9', '#ffd278'
SWATCHES = (GOLD, '#a6eee0', '#ffc5cb', '#bfdbff')
FF = ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
COLOR = ['-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709']


@functools.lru_cache(maxsize=80)
def font(size, family='rounded'):
    fonts = {'rounded':'RoundedBlack.ttf','display':'DelaGothicOne.ttf','labels':'NotoSansJP.ttf'}
    f = ImageFont.truetype(str(ROOT/'assets'/fonts[family]), size)
    if family=='labels':
        f.set_variation_by_axes([700])
    return f


def lines_for(text, width, max_size, min_size, family='rounded'):
    explicit = text.splitlines()
    forbidden_start = '、。！？…・」』）)]'
    forbidden_end = '「『（(['
    for size in range(max_size,min_size-1,-2):
        f = font(size, family)
        if all(f.getlength(s)<=width for s in explicit) and len(explicit)<=2:
            return f, explicit
        if len(explicit)!=1:
            continue
        options = []
        for j in range(2,len(text)-1):
            left,right = text[:j].rstrip(), text[j:].lstrip()
            if not left or not right or left[-1] in forbidden_end or right[0] in forbidden_start:
                continue
            a,b = f.getlength(left),f.getlength(right)
            if max(a,b)<=width:
                bonus = width*.17 if left[-1] in '、。！？!? ' else 0
                options.append((abs(a-b)-bonus,left,right))
        if options:
            _,a,b=min(options)
            return f,[a,b]
    raise ValueError(f'字幕を意味の切れ目で分けてください {text}')


def wrapped(draw, text, cy, width=1670, size=76, fill=IVORY):
    f, lines = lines_for(text, width, size, 52)
    for i,line in enumerate(lines):
        y = cy+(i-(len(lines)-1)/2)*(f.size+10)
        draw.text((960,y),line,font=f,fill=fill,anchor='mm',stroke_width=4,stroke_fill='#10182a')


def poster(source, seek, staging):
    name = staging/'poster.jpg'
    try:
        with Image.open(source) as im:
            return ImageOps.exif_transpose(im).convert('RGB')
    except (OSError, ValueError):
        name.unlink(missing_ok=True)
        subprocess.run(FF+['-ss',str(seek),'-i',str(source),'-frames:v','1',str(name)],check=True)
        with Image.open(name) as frame:
            return frame.convert('RGB')


def crop(image, size, mode):
    if mode=='cover':
        return ImageOps.fit(image,size,Image.Resampling.LANCZOS)
    foreground=ImageOps.contain(image,size,Image.Resampling.LANCZOS)
    base=Image.new('RGB',size,INK)
    base.paste(foreground,((size[0]-foreground.width)//2,(size[1]-foreground.height)//2))
    return base


def brand(canvas, project, at, size):
    info=project.data['channel']
    x,y=at
    if icon:=info.get('icon'):
        mask=Image.new('L',(size,size))
        ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1),fill=255)
        face=crop(Image.open(asset(project.root,icon)).convert('RGB'),(size,size),'cover')
        canvas.paste(face,(x,y),mask)
        x+=size+24
    d=ImageDraw.Draw(canvas)
    d.text((x,y+size*.33),info['name'],font=font(max(30,round(size*.42)),'labels'),anchor='lm',fill=IVORY)
    d.text((x,y+size*.73),info['handle'],font=font(max(22,round(size*.27)),'labels'),anchor='lm',fill='#dbe5f5')


def overlay_for(project,cue,style):
    overlay=Image.new('RGBA',(W,H))
    d=ImageDraw.Draw(overlay)
    role=cue['role']
    if role in {'opening','eyecatch','closing'}:
        x=np.arange(W)[None,:]
        y=np.arange(H)[:,None]
        if role=='eyecatch':
            shade=np.full((H,W),150,dtype='uint8')
        else:
            dark=np.broadcast_to(np.interp(x,[0,620,1480,W],[226,188,44,46]),(H,W))
            shade=np.maximum(dark,np.interp(y,[0,695,1010,1080],[0,0,233,246])).astype('uint8')
        overlay.paste((9,17,34), (0,0,W,H),Image.fromarray(shade))
        # A chapter card is visible for a beat between two complete remarks.
        if role=='eyecatch':
            d.rounded_rectangle((355,263,1565,817),42,fill=(10,19,37,248),outline='#ad8a55',width=3)
            brand(overlay,project,(630,320),120)
            wrapped(d,cue.get('text') or project.data['chapters'][cue['chapter']],630,1060,90,GOLD)
            return overlay
        brand(overlay,project,(97,101),154)
        label=cue.get('heading') or (project.data['title'] if role=='opening' else 'ご視聴ありがとうございました')
        f, headline = lines_for(label,1080,91,53,'display')
        for i,line in enumerate(headline):
            d.text((91,426+i*(f.size+13)),line,font=f,anchor='lm',fill=GOLD if i==0 else IVORY,stroke_width=2,stroke_fill=INK)
        if context:=cue.get('note'):
            d.text((96,694),context,font=font(37,'labels'),anchor='lm',fill='#dae4f3')
        d.line((88,823,1832,823),fill=(222,195,146,153),width=2)
        wrapped(d,cue['text'],936,size=64)
        return overlay

    d.rectangle((0,0,W,58),fill=(12,22,36,248))
    for x,align,text in ((72,'lm',project.data['title']), (1848,'rm',project.data['chapters'][cue['chapter']])):
        family='labels'
        f=font(30,family)
        if f.getlength(text)>880:
            f=font(25,family)
        need(f.getlength(text)<=880, f'ヘッダー用に短い見出しを設定してください {text}')
        d.text((x,29),text,font=f,anchor=align,fill=IVORY)
    d.rectangle((0,825,W,H),fill=(13,22,37,251))
    d.line((0,827,W,827),fill='#657c97',width=2)
    ref=project.sources.get(cue.get('source'))
    color=SWATCHES[style%len(SWATCHES)] if ref else IVORY
    wrapped(d,cue['text'],926,size=78 if ref and len(cue['text'])<=22 else 68,fill=color)
    if ref:
        category={'article_post':'記事掲載レス','article_comment':'記事下コメント','original_thread':'元スレ投稿','provided_post':'提供された投稿'}[ref['kind']]
        credit='　'.join(filter(None,[category,ref.get('label',''),f"#{ref['post']}",f"→ #{ref['reply_to']}への返信" if ref.get('reply_to') else '']))
    else:
        credit='補足'
    if cue.get('note'):
        credit+='　／　'+cue['note']
    f=font(25,'labels')
    visual_note=cue.get('visual_label', project.data.get('visual_label',''))
    w=1844-f.getlength(visual_note)-(38 if visual_note else 0)-104
    need(f.getlength(credit)<=w,f'出典欄の表示が長過ぎます {cue["id"]}')
    d.rounded_rectangle((73,1028,83,1051),4,fill=color)
    d.text((104,1039),credit,font=f,anchor='lm',fill=color if ref else IVORY)
    if visual_note:
        d.text((1844,1039),visual_note,font=f,anchor='rm',fill='#c6ceda')
    return overlay


def stage(project,cue,style,staging):
    src=asset(project.root,cue['visual'])
    im=poster(src,cue['visual_offset'],staging)
    card=cue['role'] in {'opening','eyecatch','closing'}
    box=(0,0,W,H) if card else (279,60,1362,766)
    n=box[2:]
    base=crop(im,(W,H),'cover')
    if not card:
        base=base.resize((480,270)).filter(ImageFilter.GaussianBlur(12)).resize((W,H))
        base=Image.blend(base,Image.new('RGB',(W,H),INK),.72)
    overlay=overlay_for(project,cue,style)
    if cue['motion']=='still':
        base.paste(crop(im,n,cue['fit']),box[:2])
        base.paste(overlay,(0,0),overlay)
    else:
        crop(im,n,cue['fit']).save(staging/'still.png')
        overlay.save(staging/'overlay.png')
    base.save(staging/'base.png')
    return box


def run_picture(writer,project,cue,style,staging,offset,count,end):
    x,y,width,height=stage(project,cue,style,staging)
    inputs=['-loop','1','-framerate',str(FPS),'-i',str(staging/'base.png')]
    rgb='scale=in_range=full:out_range=limited:out_color_matrix=bt709'
    if cue['motion']=='still':
        filters=f'[0:v]{rgb},format=yuv420p[scene]'
    else:
        if cue['motion']=='push':
            inputs+=['-loop','1','-framerate',str(FPS),'-i',str(staging/'still.png')]
            progress=f'min(on/{max(1,cue["frames"]-1)},1)'
            motion=(f'[1:v]scale={width*2}:-2:flags=lanczos,zoompan=z=\'1+0.035*{progress}\':'
                    f'x=\'iw/2-iw/zoom/2\':y=\'ih/2-ih/zoom/2\':d=1:s={width}x{height}:fps={FPS},')
        else:
            src=asset(project.root,cue['visual'])
            inputs+=['-ss',str(cue['visual_offset']),'-i',str(src)]
            if cue['fit']=='cover':
                fit=f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}'
            else:
                fit=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={INK}'
            motion=f'[1:v]fps={FPS},{fit},tpad=stop=-1:stop_mode=clone,'
        inputs+=['-loop','1','-framerate',str(FPS),'-i',str(staging/'overlay.png')]
        filters=(f'[0:v]{rgb},format=yuv420p[b];{motion}setsar=1[m];[b][m]overlay={x}:{y}[back];'
                 f'[2:v]{rgb},format=yuva420p[o];[back][o]overlay=0:0[scene]')
    fade = ',fade=t=out:st='+str(max(0,(cue['frames']-20)/FPS))+':d='+str(min(19,cue['frames']-1)/FPS) if end and cue['frames']>1 else ''
    filters += f';[scene]setsar=1{fade},trim=start_frame={offset}:end_frame={offset+count},setpts=PTS-STARTPTS[v]'
    subprocess.run(FF+inputs+['-filter_complex_threads','2','-filter_complex',filters,'-map','[v]','-frames:v',str(count),
                               '-threads','1','-f','rawvideo','-pix_fmt','yuv420p','-'],
                   stdout=writer.stdin,check=True)


def pcm(path,channels):
    b=subprocess.check_output(FF+['-i',str(path),'-vn','-ar',str(MIX_RATE),'-ac',str(channels),'-f','f32le','-'])
    return np.frombuffer(b,dtype='<f4').reshape(-1,channels)


def mix(project,start,stop,output):
    per_frame=MIX_RATE//FPS
    samples=(stop-start)*per_frame
    voice=np.zeros((samples,1),dtype='f4')
    for cue in project.cues:
        a=(cue['start']-start)*per_frame
        if not cue.get('voice') or a>=samples or a+cue['speech_frames']*per_frame<=0:
            continue
        x=pcm(asset(project.root,cue['voice']),1)
        end=min(samples,a+len(x))
        begin=max(0,a)
        audio=x[begin-a:end-a]
        if len(audio):
            rms=np.sqrt(np.mean(audio**2))
            peak=np.max(abs(audio))
            voice[begin:end]=audio*min(.86/max(.01,peak),.115/max(.005,rms))
    result=np.repeat(voice,2,axis=1)
    ticks=MIX_RATE//50
    padded=np.pad(voice[:,0],(0,(-samples)%ticks))
    envelope=np.sqrt(np.mean(padded.reshape(-1,ticks)**2,axis=1))
    duck=np.convolve(np.interp(envelope,[0,.02,.09],[1,.9,.50]), np.ones(5)/5,mode='same')
    for cue in project.data.get('audio',[]):
        onset=project.marks[cue['at']]*per_frame+round(cue.get('delay',0)*MIX_RATE)
        until=project.marks[cue.get('until','end')]*per_frame
        first=max(onset,start*per_frame)
        last=min(until,stop*per_frame)
        if last<=first:
            continue
        media=pcm(asset(project.root,cue['file']),2)
        media=media[round(cue.get('offset',0)*MIX_RATE):]
        need(len(media)>0,cue['title']+' の音源開始位置が曲の尺を超えています')
        position=np.arange(first-onset,last-onset)
        if cue['kind']=='bgm' and cue.get('loop'):
            overlap=min(round(.075*MIX_RATE),len(media)//4)
            period=len(media)-overlap
            local=position%period
            chunk=media[local].copy()
            seam=(position>=period)&(local<overlap)
            if np.any(seam):
                t=(local[seam]/overlap)[:,None]
                chunk[seam]=chunk[seam]*t+media[period+local[seam]]*(1-t)
        else:
            position=position[position<len(media)]
            if not len(position):
                continue
            chunk=media[position].copy()
        fade=round(cue.get('fade',.65)*MIX_RATE)
        if fade:
            later=until-onset if cue.get('loop') and cue['kind']=='bgm' else min(until-onset,len(media))
            gain=np.minimum(np.minimum(position/fade,(later-1-position)/fade),1).clip(0,1)
            chunk*=gain[:,None]
        begin=first-start*per_frame
        if cue['kind']=='bgm':
            chunk*=np.interp(np.arange(begin,begin+len(chunk)),np.arange(len(duck))*ticks,duck).astype('f4')[:,None]
        result[begin:begin+len(chunk)]+=chunk*float(10**(cue.get('gain_db',-24)/20))
    subprocess.run(FF+['-f','f32le','-ar',str(MIX_RATE),'-ac','2','-i','-','-af','loudnorm=I=-16:LRA=8:TP=-1.5',
                       '-ar',str(RATE),'-c:a','aac','-b:a','160k',str(output)],
                   input=result.astype('<f4',copy=False).tobytes(),check=True)


def render(project,out,start,stop,preview,preset):
    with tempfile.TemporaryDirectory(prefix='neko-ou-',dir=out.parent) as temp:
        stage_dir=Path(temp)
        audio=stage_dir/'sound.m4a'
        mix(project,start,stop,audio)
        publication(project,stage_dir)
        target=stage_dir/'video.mp4'
        args=FF+['-f','rawvideo','-pixel_format','yuv420p','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','-',
                 '-i',str(audio)]
        if not preview:
            args+=['-f','ffmetadata','-i',str(stage_dir/'chapters.ffmeta'),'-map_chapters','2','-map_metadata','2']
        args+=['-map','0:v:0','-map','1:a:0','-c:v','libx264','-threads','4','-preset',preset,'-crf','18',
               '-c:a','copy','-movflags','+faststart']+COLOR+[str(target)]
        with subprocess.Popen(args,stdin=subprocess.PIPE) as writer:
            style=-1
            last_source=None
            for i,cue in enumerate(project.cues):
                ident=cue.get('source')
                if ident and ident!=last_source:
                    style+=1
                last_source=ident
                a=max(start,cue['start'])
                b=min(stop,cue['start']+cue['frames'])
                if a<b:
                    run_picture(writer,project,cue,style,stage_dir,a-cue['start'],b-a,i==len(project.cues)-1)
                    if i%8==0 or cue['role']=='eyecatch':
                        print(f'{b/FPS:.2f}秒 / {project.frames/FPS:.2f}秒',flush=True)
            writer.stdin.close()
            need(writer.wait()==0,'完成MP4の書き出しに失敗しました')
        if not preview:
            write_json(stage_dir/'完成検査.json',audit(project,target))
            for name in ('完成検査.json','字幕.srt','編集タイムライン.json','タイムコード付き出典.tsv','YouTube概要欄.txt','chapters.ffmeta'):
                shutil.copy2(stage_dir/name,out.parent/name)
            if project.data.get('cover'):
                cover=asset(project.root,project.data['cover'])
                suffix=cover.suffix.lower()
                need(suffix in {'.png','.jpg','.jpeg'},'サムネイルはPNGまたはJPGにしてください')
                shutil.copy2(cover,out.parent/f'YouTubeサムネイル{suffix}')
        target.replace(out)
    print(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--start',help='試写を始める字幕ID')
    parser.add_argument('--seconds',type=float,default=15)
    parser.add_argument('--preset',default='fast',choices=['veryfast','fast','medium','slow'])
    args=parser.parse_args()
    try:
        p=prepare(args.manifest,args.preview)
        need(not args.start or args.preview,'途中からの書き出しは試写に指定してください')
        start=p.marks[args.start] if args.start else 0
        stop=min(p.frames,start+round(FPS*args.seconds)) if args.preview else p.frames
        need(stop>start,'試写の長さを指定してください')
        dest=(args.output or p.root/'出力'/('試写.mp4' if args.preview else '完成動画.mp4')).resolve()
        need(not dest.exists(),f'既存ファイルがあります {dest}')
        dest.parent.mkdir(parents=True,exist_ok=True)
        render(p,dest,start,stop,args.preview,args.preset)
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as exc:
        parser.exit(1,f'書き出しエラー {exc}\n')


if __name__=='__main__':
    main()
