#!/usr/bin/env python3
"""Build the offline deck and editable PowerPoint from one scene definition.
Run from the repository root: .venv/bin/python presentation/final-defense/src/build.py
No network, board access, or changes to application code.
"""
from __future__ import annotations
import base64
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.opc.packuri import PackURI
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
ASSETS = BASE / 'assets'
BUILD = BASE / '.build'
for folder in (ASSETS, BUILD, BASE / 'previews', BASE / 'design'):
    folder.mkdir(parents=True, exist_ok=True)
W, H = 1600, 900
P = {'paper':'FFFFFF','ink':'182B3B','blue':'005AA6','cyan':'039ACF','led':'89DFFD','quiet':'647584','panel':'EAF3FA'}
CN, EN = 'Microsoft' + ' YaHei', 'Arial'
TITLE = '交小西DormSense_结题答辩展示'
FONT = Path('/Library/Fonts/msyh.ttc')
BOLD = Path('/Library/Fonts/msyhbd.ttc')
TEMPLATE = ASSETS / '2021simpleblue.pptx'
BG_FILES = {'cover':'tpl-cover-bg.png','contents':'tpl-contents-bg.png','body':'tpl-content-bg.png','closing':'tpl-closing-bg.png'}

def walk(shapes):
    for shape in shapes:
        yield shape
        if shape.shape_type == 6:
            yield from walk(shape.shapes)

def clean_template_text(slide, keep_badges=False):
    for shape in walk(slide.shapes):
        if not shape.has_text_frame:
            continue
        if keep_badges and shape.text.strip() in ('C','ONTENTS','CONTENTS'):
            continue
        if keep_badges and shape.text.strip() in ('01','02','03','04'):
            parent=shape._element.getparent()
            sibling=next((s for s in parent if s.tag.endswith('}sp')), None)
            if sibling is not None:
                xfrm=sibling.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm')
                if xfrm is not None:
                    off=xfrm.find('{http://schemas.openxmlformats.org/drawingml/2006/main}off')
                    ext=xfrm.find('{http://schemas.openxmlformats.org/drawingml/2006/main}ext')
                    shape.left=int(off.get('x'));shape.width=int(ext.get('cx'))
            tf=shape.text_frame
            tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
            tf.word_wrap=False
            for paragraph in tf.paragraphs:
                paragraph.alignment=PP_ALIGN.CENTER
                for run in paragraph.runs:
                    run.font.name='Arial Black';run.font.size=Pt(20);run.font.bold=True
        else:
            shape.text_frame.clear()

def template_shell():
    deck=Presentation(TEMPLATE)
    ids=deck.slides._sldIdLst
    for item in list(ids)[2:-1]:
        deck.part.drop_rel(item.rId);ids.remove(item)
    cover,contents,closing=list(deck.slides)
    # add_slide numbers by slide count; make the retained closing part contiguous.
    closing.part._partname=PackURI('/ppt/slides/slide3.xml')
    clean_template_text(cover);clean_template_text(contents,True);clean_template_text(closing)
    return deck,cover,contents,closing

bg_signature=hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()+':2'
bg_stamp=BUILD/'template-background-version.txt'
if not all((ASSETS/f).exists() for f in BG_FILES.values()) or not bg_stamp.exists() or bg_stamp.read_text()!=bg_signature:
    bg,_,_,_=template_shell()
    bg.slides.add_slide(bg.slide_layouts[5])
    with tempfile.TemporaryDirectory(prefix='dormsense-template-') as temp:
        temp=Path(temp);background_ppt=temp/'backgrounds.pptx';bg.save(background_ppt)
        subprocess.run(['/opt/homebrew/bin/soffice','-env:UserInstallation='+ (temp/'lo-profile').as_uri(),'--headless','--convert-to','pdf','--outdir',str(temp),str(background_ppt)],check=True,stdout=subprocess.PIPE)
        subprocess.run(['pdftoppm','-scale-to-x','1600','-scale-to-y','900','-png',str(temp/'backgrounds.pdf'),str(temp/'bg')],check=True,stdout=subprocess.PIPE)
        for kind,n in [('cover',1),('contents',2),('closing',3),('body',4)]:
            shutil.copyfile(temp/f'bg-{n}.png',ASSETS/BG_FILES[kind])
    bg_stamp.write_text(bg_signature)
BG_DATA={kind:'data:image/png;base64,'+base64.b64encode((ASSETS/f).read_bytes()).decode() for kind,f in BG_FILES.items()}

# Compile only a host exporter, which includes (rather than reimplements) the firmware.
subprocess.run(['clang++', '-std=c++11', str(BASE/'src/led_frames.cpp'), '-o', str(BUILD/'led_frames')], check=True)
raw = subprocess.check_output([str(BUILD/'led_frames')])
LED = json.loads(raw)
header = ROOT/'firmware/arduino-uno-r4/include/led_companion.h'
LED['source'] = str(header.relative_to(ROOT))
LED['source_sha256'] = hashlib.sha256(header.read_bytes()).hexdigest()
LED['example_inputs'] = {'temperature_c':24,'humidity_pct':55,'light_ratio':0.46,'dark_light_ratio':0.04}
assert LED['width'] == 12 and LED['height'] == 8
for key, frames in LED['states'].items():
    assert frames and all(len(f['rows']) == 8 and all(len(r) == 12 and set(r) <= {'0','1'} for r in f['rows']) for f in frames), key
(ASSETS/'led-frames.json').write_text(json.dumps(LED, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

# Public metadata preserves the names and purchases already shown in this deck.
public_data = json.loads((BASE/'src/public-data.json').read_text(encoding='utf-8'))
groups = public_data['team_groups']
assert len(groups) == 3 and all(len(g) == 2 and all(isinstance(n, str) and n.strip() for n in g) for g in groups), 'Public team metadata must contain three pairs of names'
logo = ROOT/'hermes/branding/xiaoxi-logo.png'
shutil.copyfile(logo, ASSETS/'xiaoxi-logo.png')
logo_data = 'data:image/png;base64,' + base64.b64encode(logo.read_bytes()).decode()

class Scene:
    def __init__(self, title, seconds, note, bullets, source, dark=False, kind='body'):
        self.title, self.seconds, self.note, self.bullets, self.source = title, seconds, note, bullets, source
        self.dark, self.elements, self.kind = dark, [], kind
        self.bg = P['ink'] if dark else P['paper']
        self.fg = P['paper'] if dark else P['ink']
        self.elements.append(dict(kind='background',x=0,y=0,w=W,h=H,background=kind))
    def text(self, text, x, y, w, size=32, color=None, bold=False, font=CN, h=None, align='left', role=None):
        height = h or (len(text.split('\n')) * size * 1.25 + 12)
        self.elements.append(dict(kind='text',text=text,x=x,y=y,w=w,h=height,size=size,color=color or self.fg,bold=bold,font=font or CN,align=align,role=role))
    def rect(self,x,y,w,h,color,r=0):
        self.elements.append(dict(kind='rect',x=x,y=y,w=w,h=h,color=color,r=r))
    def circle(self,x,y,d,color):
        self.elements.append(dict(kind='circle',x=x,y=y,w=d,h=d,color=color))
    def line(self,x,y,x2,y2,color,width=4):
        self.elements.append(dict(kind='line',x=x,y=y,x2=x2,y2=y2,color=color,width=width))
    def arrow(self,x,y,x2,y2,color=None):
        color = color or P['blue']
        self.line(x,y,x2,y2,color,5)
        a = math.atan2(y2-y,x2-x)
        for d in (-.6,.6): self.line(x2,y2,x2-16*math.cos(a+d),y2-16*math.sin(a+d),color,5)
    def matrix(self,key,x,y,w,frame=0,live=None):
        self.elements.append(dict(kind='matrix',key=key,x=x,y=y,w=w,h=w*2/3,frame=frame,live=live))
    def picture(self,x,y,w,h):
        self.elements.append(dict(kind='picture',x=x,y=y,w=w,h=h))
    def head(self, subtitle=None):
        self.text(self.title,158,46,1360,60,bold=True,role='h2')
        if subtitle: self.text(subtitle,82,164,1420,29,P['quiet'])
    def foot(self,n):
        self.text('交小西 DormSense',80,834,700,22,P['panel'] if self.dark else P['quiet'])
        self.text(f'{n} / {len(S)}',1400,834,120,22,P['panel'] if self.dark else P['quiet'],font=EN,align='right')

S=[]
def add(title, seconds, note, bullets, source, dark=False, kind='body'):
    scene=Scene(title,seconds,note,bullets,source,dark,kind)
    S.append(scene)
    return scene
purchases=public_data['purchases_yuan']
assert public_data['budget_yuan']==200 and round(sum(v for _,v in purchases),2)==57.64
from content import populate
populate(add,P,groups,purchases)
MAIN_SLIDES=sum(bool(s.seconds) for s in S)
TOTAL_SECONDS=sum(s.seconds for s in S)
assert len(S)==20 and MAIN_SLIDES==18 and TOTAL_SECONDS==855
for i,scene in enumerate(S,1):
    if scene.kind=='body':scene.foot(i)
LED_SLIDE=next(i for i,s in enumerate(S) if any(e.get('live')=='main' for e in s.elements))

# Common rendering helpers.
def matrix_cells(e, frame=None):
    f=frame or LED['states'][e['key']][e['frame']]
    unit=e['w']/12
    for r,row in enumerate(f['rows']):
        for c,b in enumerate(row):
            yield e['x']+c*unit+unit*.12,e['y']+r*unit+unit*.12,unit*.76,P['led'] if b=='1' else '254A6A'

def graphic_svg(e):
    k=e['kind'];c='#'+e.get('color',P['ink'])
    if k=='background':return f'<image href="{BG_DATA[e["background"]]}" x="0" y="0" width="1600" height="900"/>'
    if k=='rect': return f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" rx="{e["r"]}" fill="{c}"/>'
    if k=='circle': return f'<circle cx="{e["x"]+e["w"]/2}" cy="{e["y"]+e["h"]/2}" r="{e["w"]/2}" fill="{c}"/>'
    if k=='line': return f'<path d="M{e["x"]},{e["y"]} L{e["x2"]},{e["y2"]}" stroke="{c}" stroke-width="{e["width"]}" fill="none"/>'
    if k=='matrix':
        cells=''.join(f'<rect x="{x:.3f}" y="{y:.3f}" width="{d:.3f}" height="{d:.3f}" fill="#{color}"/>' for x,y,d,color in matrix_cells(e))
        live=f' data-led="{e["live"]}" data-state="{e["key"]}"' if e['live'] else ''
        return f'<g{live} data-x="{e["x"]}" data-y="{e["y"]}" data-w="{e["w"]}"><rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" fill="#{P["ink"]}"/>{cells}</g>'
    if k=='picture': return f'<image href="{logo_data}" x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}"/>'
    return ''

def svg_scene(s):
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(s.title)}">']
    for e in s.elements:
        if e['kind']!='text':out.append(graphic_svg(e));continue
        anchor={'left':'start','right':'end','center':'middle'}[e['align']]
        x=e['x']+({'left':0,'right':e['w'],'center':e['w']/2}[e['align']])
        out.append(f'<text x="{x}" y="{e["y"]+e["size"]}" fill="#{e["color"]}" font-family="{e["font"]}" font-size="{e["size"]}" font-weight="{700 if e["bold"] else 400}" text-anchor="{anchor}">')
        for n,line in enumerate(e['text'].split('\n')):out.append(f'<tspan x="{x}" dy="{0 if n==0 else e["size"]*1.25}">{html.escape(line)}</tspan>')
        out.append('</text>')
    return ''.join(out)+'</svg>'

for i,s in enumerate(S,1): (BASE/'previews'/f'slide-{i:02}.svg').write_text(svg_scene(s),encoding='utf-8')

# GIF is embedded in PowerPoint; fixed PDF shows its first frame.
images=[]
for state in ['happy','temperature','humidity','light','sleepy']:
    for f in LED['states'][state][::3]:
        im=Image.new('RGB',(810,540),'#'+P['ink']);draw=ImageDraw.Draw(im)
        e=dict(x=0,y=0,w=810,key=state,frame=0)
        for x,y,d,c in matrix_cells(e,f):draw.rectangle((round(x),round(y),round(x+d),round(y+d)),fill='#'+c)
        images.append(im)
images[0].save(ASSETS/'LED_五种状态演示.gif',save_all=True,append_images=images[1:],duration=300,loop=0,optimize=True)

# Editable PowerPoint: text boxes, vector cells, connectors and shapes.
prs,cover_slide,contents_slide,closing_slide=template_shell()
prs.core_properties.title='交小西 DormSense｜结题答辩'
prs.core_properties.subject='宿舍环境感知与自然语言智能交互系统'
prs.core_properties.author=' · '.join(n for g in groups for n in g)
prs.core_properties.keywords='DormSense, LED, course defense, editable'
def coord(v): return Inches(v/120)
def color(hexvalue):return RGBColor.from_string(hexvalue)
def solid(shape,hexvalue):
    shape.fill.solid();shape.fill.fore_color.rgb=color(hexvalue);shape.line.fill.background()
    shape._element.spPr.append(OxmlElement('a:effectLst'))
max_original_id={k:max((x.shape_id for x in v.shapes),default=0) for k,v in [('cover',cover_slide),('contents',contents_slide),('closing',closing_slide)]}
ordered_slides=[]
for n,s in enumerate(S,1):
    if s.kind=='cover':slide=cover_slide
    elif s.kind=='contents':slide=contents_slide
    elif s.kind=='closing':slide=closing_slide
    else:slide=prs.slides.add_slide(prs.slide_layouts[5])
    ordered_slides.append(slide)
    for e in s.elements[1:]:
        k=e['kind']
        if k=='text':
            shape=slide.shapes.add_textbox(coord(e['x']),coord(e['y']),coord(e['w']),coord(e['h']))
            tf=shape.text_frame;tf.clear();tf.word_wrap=False
            tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
            tf.vertical_anchor=MSO_ANCHOR.TOP
            for j,line in enumerate(e['text'].split('\n')):
                p=tf.paragraphs[0] if j==0 else tf.add_paragraph()
                p.alignment={'left':PP_ALIGN.LEFT,'right':PP_ALIGN.RIGHT,'center':PP_ALIGN.CENTER}[e['align']]
                p.space_before=p.space_after=Pt(0);p.line_spacing=Pt(e['size']*.6*1.25)
                r=p.add_run();r.text=line;r.font.name=e['font'];r.font.size=Pt(e['size']*.6);r.font.bold=e['bold'];r.font.color.rgb=color(e['color'])
                props=r._r.get_or_add_rPr();ea=OxmlElement('a:ea');ea.set('typeface',CN);props.append(ea)
        elif k in ('rect','circle'):
            typ=MSO_SHAPE.OVAL if k=='circle' else MSO_SHAPE.ROUNDED_RECTANGLE if e['r'] else MSO_SHAPE.RECTANGLE
            shape=slide.shapes.add_shape(typ,coord(e['x']),coord(e['y']),coord(e['w']),coord(e['h']));solid(shape,e['color'])
            if e.get('r') and shape.adjustments:shape.adjustments[0]=min(.2,e['r']/min(e['w'],e['h']))
        elif k=='line':
            shape=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,coord(e['x']),coord(e['y']),coord(e['x2']),coord(e['y2']))
            shape.line.color.rgb=color(e['color']);shape.line.width=Pt(e['width']*.6)
            shape._element.spPr.append(OxmlElement('a:effectLst'))
        elif k=='matrix':
            shape=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,coord(e['x']),coord(e['y']),coord(e['w']),coord(e['h']));solid(shape,P['ink'])
            for x,y,d,c in matrix_cells(e):solid(slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,coord(x),coord(y),coord(d),coord(d)),c)
            if n==LED_SLIDE+1:slide.shapes.add_picture(str(ASSETS/'LED_五种状态演示.gif'),coord(e['x']),coord(e['y']),coord(e['w']),coord(e['h']))
        elif k=='picture':slide.shapes.add_picture(str(ASSETS/'xiaoxi-logo.png'),coord(e['x']),coord(e['y']),coord(e['w']),coord(e['h']))
    # Discard Office's built-in shape style, whose effectRef adds a theme shadow.
    for item in slide.shapes:
        if item.shape_id<=max_original_id.get(s.kind,0):continue
        for style in item._element.xpath('./p:style'):
            item._element.remove(style)
    timing=f'建议 {s.seconds} 秒' if s.seconds else '附录：不计入主线'
    slide.notes_slide.notes_text_frame.text=f'{n}. {s.title}\n{timing}\n\n{s.note}\n\n依据：\n'+'\n'.join(s.source)
slide_ids={str(prs.part.related_slide(item.rId).part.partname):item for item in list(prs.slides._sldIdLst)}
for item in list(prs.slides._sldIdLst):prs.slides._sldIdLst.remove(item)
for slide in ordered_slides:prs.slides._sldIdLst.append(slide_ids[str(slide.part.partname)])
prs.save(BASE/(TITLE+'.pptx'))

# Full per-slide script includes time ranges and explicit physical-demo fallback.
time=0;script=['# 交小西 DormSense 结题答辩逐页讲稿','', f'主线 {MAIN_SLIDES} 页，约 14 分 15 秒，其中实物演示 4 分钟；另留 45 秒切换缓冲。附录不计时。','', '使用 2021simpleblue 校级蓝色模板；逐页口述与 PowerPoint 演讲者备注一致。','']
for n,s in enumerate(S,1):
    start=f'{time//60:02}:{time%60:02}';time+=s.seconds;end=f'{time//60:02}:{time%60:02}'
    script.extend([f'## 第 {n} 页：{s.title}', '', f'建议 {start}–{end}，{s.seconds} 秒。' if s.seconds else '附录，按提问使用。', '', '**屏幕重点**',''])
    script.extend('- '+b for b in s.bullets)
    script.extend(['','**口述**','',s.note,'','**依据**',''])
    script.extend('- `'+p+'`' for p in s.source);script.append('')
(BASE/'逐页讲稿.md').write_text('\n'.join(script),encoding='utf-8')

# Standalone HTML: no fonts, libraries, telemetry, or network fetches.
slides=[];mobile=[]
for n,s in enumerate(S,1):
    svg=svg_scene(s)
    # HTML uses semantic text layers, while the backdrop contains graphics only.
    graphics=''.join(graphic_svg(e) for e in s.elements if e['kind']!='text')
    texts=[]
    for e in s.elements:
        if e['kind']!='text':continue
        tag=e.get('role') or 'div';text=html.escape(e['text']).replace('\n','<br>')
        texts.append(f'<{tag} class="scene-text" style="left:{e["x"]}px;top:{e["y"]}px;width:{e["w"]}px;height:{e["h"]}px;font-size:{e["size"]}px;color:#{e["color"]};font-weight:{700 if e["bold"] else 400};font-family:\'{e["font"]}\',\'{CN}\',sans-serif;text-align:{e["align"]}">{text}</{tag}>')
    slides.append(f'<section class="slide" id="slide-{n}" data-index="{n-1}" aria-label="第{n}页 {html.escape(s.title)}"><div class="stage"><svg class="backdrop" viewBox="0 0 1600 900" aria-hidden="true">{graphics}</svg>'+''.join(texts)+'</div></section>')
    phone_title=s.title
    mobile.append(f'<article class="phone-slide" data-index="{n-1}"><h{1 if n==1 else 2}>{html.escape(phone_title)}</h{1 if n==1 else 2}><div class="phone-art" aria-hidden="true">{svg}</div><ul>'+''.join('<li>'+html.escape(b)+'</li>' for b in s.bullets)+'</ul></article>')
options=''.join(f'<option value="{n}">{n+1}. {html.escape(s.title)}</option>' for n,s in enumerate(S))
meta=[dict(title=s.title,seconds=s.seconds,note=s.note,source=s.source) for s in S]
controls=''.join(f'<button type="button" data-state="{key}">{label}</button>' for key,label in [('happy','笑脸'),('temperature','温度'),('humidity','湿度'),('light','亮度'),('sleepy','困倦'),('hot','流汗'),('cry','故障'),('connecting','连接'),('voice','语音')])
html_code='''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>交小西 DormSense · 结题答辩</title>
<style>
:root{--paper:#FFFFFF;--ink:#182B3B;--blue:#005AA6;--led:#89DFFD;--quiet:#647584;--panel:#EAF3FA}
*{box-sizing:border-box}body{margin:0;display:flex;flex-direction:column;min-height:100svh;background:var(--paper);color:var(--ink);font-family:__CN__,sans-serif}button,select{font:inherit}button{cursor:pointer}button:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid var(--blue);outline-offset:4px}button:disabled{opacity:.4;cursor:default}
.deck{position:relative;width:100%;height:calc(100svh - 68px);overflow:hidden;display:grid;place-items:center}.slide{display:none;position:relative;width:100%;height:100%;overflow:hidden}.slide.is-active{display:block}.stage{position:absolute;width:1600px;height:900px;left:50%;top:50%;transform-origin:0 0;transform:scale(var(--scale)) translate(-50%,-50%)}.backdrop{position:absolute;inset:0;width:1600px;height:900px}.scene-text{position:absolute;margin:0;line-height:1.25;white-space:nowrap;letter-spacing:0}.phone-deck{display:none}
[data-ui].toolbar{order:2;height:68px;display:flex;align-items:center;gap:12px;padding:8px 24px;background:var(--ink);color:var(--paper)}[data-ui] button,[data-ui] select{min-height:42px;padding:8px 15px;border:0;border-radius:4px;background:var(--paper);color:var(--ink)}[data-ui] select{max-width:420px;flex:1}[data-ui] .counter{white-space:nowrap;font-family:Arial,sans-serif;margin-left:auto}[data-ui] button[aria-pressed="true"]{background:var(--led)}
[data-ui].led-controls{order:1;position:relative;margin:0 auto;display:none;gap:6px;flex-wrap:wrap;justify-content:center;background:var(--panel);padding:10px;max-width:calc(100% - 48px);width:max-content;z-index:3}[data-ui].led-controls.is-open{display:flex}[data-ui].led-controls button{font-size:16px;padding:6px 10px;min-height:40px}[data-ui] .control-note{width:100%;font-size:14px;color:var(--quiet);text-align:center;margin:3px 0 0}.note-panel{position:fixed;right:20px;top:20px;bottom:90px;max-width:540px;width:calc(100% - 40px);padding:28px;background:var(--ink);color:var(--paper);overflow:auto;z-index:5}.note-panel[hidden]{display:none}.note-panel h2{font-size:28px;margin:0 0 18px}.note-panel p{font-size:20px;line-height:1.7}.note-panel code{font-family:__CN__,sans-serif;overflow-wrap:anywhere;font-size:14px}.note-panel button{float:right}.toast{position:fixed;left:50%;top:18px;transform:translateX(-50%);background:var(--ink);color:var(--paper);padding:12px 20px;z-index:9}.toast[hidden]{display:none}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
@media(max-width:699px){.deck{display:none}.phone-deck{display:block;min-height:calc(100svh - 132px);padding:26px 22px 190px}.phone-slide{display:none}.phone-slide.is-active{display:block}.phone-slide h1,.phone-slide h2{font-size:32px;line-height:1.18;margin:0 0 26px}.phone-art{width:100%;overflow:hidden;background:var(--panel);margin:0 0 24px}.phone-art svg{width:100%;height:auto;display:block}.phone-slide ul{margin:0;padding-left:22px;font-size:18px;line-height:1.65}.phone-slide li{margin-bottom:10px}[data-ui].toolbar{position:fixed;bottom:0;left:0;right:0;height:auto;min-height:112px;flex-wrap:wrap;padding:10px 14px;gap:8px;z-index:4}[data-ui].toolbar select{max-width:none;flex:1 1 100%;order:-1}[data-ui].toolbar button{font-size:14px;padding:7px 10px;min-height:38px}[data-ui].counter{font-size:14px}[data-ui].led-controls{position:fixed;left:12px;right:12px;bottom:127px;transform:none;margin:0;max-width:none;width:auto;max-height:200px;overflow:auto}[data-ui].led-controls button{font-size:14px;padding:6px 9px;min-height:38px}.note-panel{bottom:142px;top:12px;padding:22px}.note-panel p{font-size:18px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
@media print{.toolbar,.led-controls,.phone-deck,.note-panel{display:none!important}.deck{display:block;height:auto;overflow:visible}.slide{display:block;width:1600px;height:900px;break-after:page}.stage{position:relative;left:0;top:0;transform:none}}
</style></head><body>
<main class="deck" aria-label="结题答辩幻灯片">__SLIDES__</main><main class="phone-deck" aria-label="手机阅读版">__MOBILE__</main>
<nav class="toolbar" data-ui aria-label="演示控制"><button type="button" id="prev" aria-label="上一页">← 上一页</button><button type="button" id="next" aria-label="下一页">下一页 →</button><select id="jump" aria-label="选择幻灯片">__OPTIONS__</select><button type="button" id="notes" aria-pressed="false">讲稿</button><button type="button" id="matrix-toggle" aria-pressed="false">点阵演示</button><button type="button" id="fullscreen">全屏</button><span class="counter" id="counter" aria-live="polite"></span></nav>
<div class="led-controls" data-ui aria-label="点阵状态演示">__CONTROLS__<button type="button" id="play" aria-pressed="true">暂停动画</button><button type="button" id="step">下一帧</button><button type="button" id="carousel">自动轮播</button><p class="control-note">固件像素帧 · 数值为示例 · 正常四幕轮播</p></div>
<aside class="note-panel" data-ui id="note-panel" aria-label="逐页讲稿" hidden><button type="button" id="close-notes">关闭讲稿</button><div id="note-content"></div></aside><div class="toast" id="toast" role="status" hidden></div><div id="announcement" class="sr-only" aria-live="polite"></div>
<script id="led-data" type="application/json">__LED__</script><script id="slide-data" type="application/json">__META__</script>
<script>
'use strict';
const LED=JSON.parse(document.getElementById('led-data').textContent),meta=JSON.parse(document.getElementById('slide-data').textContent);
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let current=0,tick=0,selected='happy',mode='carousel',running=!matchMedia('(prefers-reduced-motion: reduce)').matches;
let manualControls=false,noticeTimer;
const stateNames={happy:'笑脸',temperature:'温度',humidity:'湿度',light:'亮度',sleepy:'困倦',hot:'流汗',cry:'传感故障',connecting:'连接中',voice:'语音波形'};
const escapeText=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
function fit(){const d=$('.deck'),controls=$('.led-controls');if(innerWidth>=700)d.style.height=Math.max(200,innerHeight-$('.toolbar').offsetHeight-(controls.classList.contains('is-open')?controls.offsetHeight:0))+'px';document.documentElement.style.setProperty('--scale',Math.min(d.clientWidth/1600,d.clientHeight/900)||1)}
function setSlide(n,writeHash=true){current=Math.max(0,Math.min(meta.length-1,n));$$('.slide,.phone-slide').forEach(e=>{const active=+e.dataset.index===current;e.classList.toggle('is-active',active);e.setAttribute('aria-hidden',String(!active))});$('#jump').value=current;$('#prev').disabled=current===0;$('#next').disabled=current===meta.length-1;$('#counter').textContent=`${current+1} / ${meta.length}`;$('#note-content').innerHTML=`<h2>${escapeText(meta[current].title)}</h2><p>${meta[current].seconds?'建议 '+meta[current].seconds+' 秒':'附录，按提问使用'}</p><p>${escapeText(meta[current].note)}</p><p><code>${meta[current].source.map(escapeText).join('<br>')}</code></p>`;if(writeHash)history.replaceState(null,'',`#${current+1}`);$('#announcement').textContent=`第${current+1}页，${meta[current].title}`;manualControls=current===__LED_INDEX__;$('#matrix-toggle').hidden=current!==__LED_INDEX__;$('#matrix-toggle').setAttribute('aria-pressed',String(manualControls));$('.led-controls').classList.toggle('is-open',manualControls);window.scrollTo(0,0);fit();paint()}
function paint(){const carousel=['happy','temperature','humidity','light'];const key=mode==='carousel'?carousel[Math.floor(tick/60)%4]:selected;$$('[data-led]').forEach(g=>{const target=g.dataset.led;const live=target==='main'?key:g.dataset.state;const frames=LED.states[live],frame=frames[tick%frames.length],x=+g.dataset.x,y=+g.dataset.y,w=+g.dataset.w,u=w/12;g.innerHTML=`<rect x="${x}" y="${y}" width="${w}" height="${w*2/3}" fill="#182B3B"/>`+frame.rows.map((row,r)=>[...row].map((bit,c)=>`<rect x="${x+(c+.12)*u}" y="${y+(r+.12)*u}" width="${u*.76}" height="${u*.76}" fill="${bit==='1'?'#89DFFD':'#254A6A'}"/>`).join('')).join('');g.dataset.renderedState=live;g.dataset.frame=String(tick%frames.length)});$$('.led-controls [data-state]').forEach(b=>b.setAttribute('aria-pressed',String(mode==='manual'&&b.dataset.state===selected)));$('#play').textContent=running?'暂停动画':'播放动画';$('#play').setAttribute('aria-pressed',String(running));$('#carousel').setAttribute('aria-pressed',String(mode==='carousel'))}
$('#prev').onclick=()=>setSlide(current-1);$('#next').onclick=()=>setSlide(current+1);$('#jump').onchange=e=>setSlide(+e.target.value);
function toggleNotes(open){$('#note-panel').hidden=!open;$('#notes').setAttribute('aria-pressed',String(open));if(open)$('#close-notes').focus();else $('#notes').focus()}
$('#notes').onclick=()=>toggleNotes($('#note-panel').hidden);$('#close-notes').onclick=()=>toggleNotes(false);
$('#matrix-toggle').onclick=()=>{manualControls=!manualControls;$('.led-controls').classList.toggle('is-open',manualControls);$('#matrix-toggle').setAttribute('aria-pressed',String(manualControls));fit()};
$$('.led-controls [data-state]').forEach(b=>b.onclick=()=>{mode='manual';selected=b.dataset.state;tick=0;paint();$('#announcement').textContent=stateNames[selected]+'，示例状态'});
$('#play').onclick=()=>{running=!running;paint()};$('#step').onclick=()=>{running=false;tick++;paint()};$('#carousel').onclick=()=>{mode='carousel';tick=0;paint()};
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('#toast').hidden=true,3500)}
$('#fullscreen').onclick=async()=>{try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();else await document.exitFullscreen()}catch{toast('请使用浏览器菜单进入全屏，或按系统全屏快捷键。')}};
addEventListener('keydown',e=>{if(e.target.matches('select,input,textarea,button')||e.altKey||e.ctrlKey||e.metaKey)return;if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();setSlide(current+1)}else if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();setSlide(current-1)}else if(e.key==='Home'){e.preventDefault();setSlide(0)}else if(e.key==='End'){e.preventDefault();setSlide(meta.length-1)}else if(e.key.toLowerCase()==='n')toggleNotes($('#note-panel').hidden);else if(e.key==='Escape'&&!$('#note-panel').hidden)toggleNotes(false)});
addEventListener('resize',fit);addEventListener('hashchange',()=>{const n=Number(location.hash.slice(1));if(Number.isInteger(n)&&n>=1&&n<=meta.length)setSlide(n-1,false)});
matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',e=>{running=!e.matches;paint()});
setInterval(()=>{if(running&&!document.hidden){tick++;paint()}},100);
setSlide(Math.max(0,(Number(location.hash.slice(1))||1)-1),false);
window.deck={go:n=>setSlide(n-1),get index(){return current+1},get running(){return running},get state(){return mode==='manual'?selected:'carousel'}};
</script></body></html>'''
for marker,value in [('__LED_INDEX__',str(LED_SLIDE)),('__CN__',"'"+CN+"'"),('__SLIDES__',''.join(slides)),('__MOBILE__',''.join(mobile)),('__OPTIONS__',options),('__CONTROLS__',controls),('__LED__',json.dumps(LED,ensure_ascii=False,separators=(',',':'))),('__META__',json.dumps(meta,ensure_ascii=False))]:html_code=html_code.replace(marker,value)
(BASE/'index.html').write_text(html_code,encoding='utf-8')

# Template previews show three actual layouts from the selected university template.
def font(size,bold=False):return ImageFont.truetype(str(BOLD if bold else FONT),size)
for n,kind in enumerate(('cover','contents','body'),1):
    im=Image.open(ASSETS/BG_FILES[kind]).convert('RGB')
    draw=ImageDraw.Draw(im)
    if kind=='cover':draw.text((645,360),'交小西 DormSense',font=font(70,True),fill='#'+P['blue'])
    elif kind=='contents':
        for y,label in [(325,'项目定位'),(457,'硬件与 MQTT'),(591,'点阵与智能体'),(725,'成果与实物演示')]:draw.text((400,y),label,font=font(42,True),fill='#'+P['ink'])
    else:
        draw.text((158,46),'MQTT 与智能体工作流程',font=font(60,True),fill='#'+P['ink'])
        draw.text((90,300),'沿用模板母版，内容图解保留可编辑。',font=font(38),fill='#'+P['blue'])
    im.save(BASE/'design'/f'模板预览-{n}.png')
contact=Image.new('RGB',(1920,420),'#'+P['paper']);draw=ImageDraw.Draw(contact)
for n,label in [(1,'封面 · 原模板照片与蓝色切面'),(2,'目录 · 原模板校园与序号'),(3,'正文 · 原模板标题标识')]:
    contact.paste(Image.open(BASE/'design'/f'模板预览-{n}.png').resize((624,351)),((n-1)*648,0));draw.text(((n-1)*648+15,366),label,font=font(24,True),fill='#'+P['ink'])
contact.save(BASE/'design'/'三种模板预览.png')

# Machine-readable manifest supports structural checks and HTML/PPT consistency.
manifest={'title':TITLE,'slides':meta,'main_slides':MAIN_SLIDES,'total_seconds':TOTAL_SECONDS,'template':'assets/2021simpleblue.pptx','led_slide':LED_SLIDE+1,'led_source_sha256':LED['source_sha256'],'fonts':[CN,EN],'budget':dict(purchases),'palette':P}
(BASE/'src'/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
# Geometric checks use actual font advances; no text box is auto-shrunk.
issues=[]
for n,s in enumerate(S,1):
    for e in s.elements:
        if e['kind']=='text':
            measure=font(round(e['size']),e['bold'])
            for line in e['text'].split('\n'):
                width=measure.getlength(line)
                if width>e['w']+4:issues.append(dict(slide=n,text=line,width=round(width),box=e['w']))
            if e['x']<0 or e['x']+e['w']>W+1 or e['y']+e['h']>H+1:issues.append(dict(slide=n,text=e['text'],issue='outside canvas'))
(BUILD/'geometry.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'slides':len(S),'main_seconds':TOTAL_SECONDS,'geometry_issues':len(issues),'pptx':str(BASE/(TITLE+'.pptx')),'html':str(BASE/'index.html')},ensure_ascii=False))
