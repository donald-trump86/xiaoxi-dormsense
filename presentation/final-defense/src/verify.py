#!/usr/bin/env python3
"""Check deck structure, common metadata, embedded animation and export artifacts."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import zipfile
from PIL import Image
from pptx import Presentation
from lxml import etree

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
TITLE='交小西DormSense_结题答辩展示'
manifest=json.loads((BASE/'src/manifest.json').read_text(encoding='utf-8'))
geometry=json.loads((BASE/'.build/geometry.json').read_text(encoding='utf-8'))
assert not geometry,geometry
prs=Presentation(BASE/(TITLE+'.pptx'))
assert len(prs.slides)==len(manifest['slides'])==20
assert manifest['main_slides']==18 and manifest['total_seconds']==855
assert sum(s['seconds'] for s in manifest['slides'])==855
for n,(slide,info) in enumerate(zip(prs.slides,manifest['slides']),1):
    assert info['note'] in slide.notes_slide.notes_text_frame.text,('notes',n)
    for ref in info['source']:
        if not ref.startswith('https://'):assert (ROOT/ref).is_file(),(n,ref)
    assert (BASE/'previews'/f'slide-{n:02}.png').is_file()
    assert (BASE/'previews'/f'slide-{n:02}.svg').is_file()
with zipfile.ZipFile(BASE/(TITLE+'.pptx')) as package:
    duplicates=[n for n,count in Counter(package.namelist()).items() if count>1]
    assert not duplicates,duplicates
    assert package.testzip() is None
    external=[]
    for name in package.namelist():
        if name.endswith('.rels'):
            external.extend((name,r.get('Target')) for r in etree.fromstring(package.read(name)) if r.get('TargetMode')=='External')
    assert not external,external
    assert any(n.startswith('ppt/media/') and n.endswith('.gif') for n in package.namelist())
    template_media=[]
    for i in (1,2,18):
        assert len(prs.slides[i-1].shapes)>0
    assert len(prs.slide_layouts)==7 and len(prs.slide_masters)==1
led=json.loads((BASE/'assets/led-frames.json').read_text(encoding='utf-8'))
assert led['source_sha256']==hashlib.sha256((ROOT/led['source']).read_bytes()).hexdigest()
assert len(led['states'])==9
for state,frames in led['states'].items():
    assert frames and all(len(f['rows'])==8 and all(len(r)==12 and set(r)<={'0','1'} for r in f['rows']) for f in frames),state
animation=Image.open(BASE/'assets/LED_五种状态演示.gif')
duration=0
for frame in range(animation.n_frames):
    animation.seek(frame);duration+=animation.info['duration']
assert duration==30000,duration
metadata=json.loads((BASE/'src/public-data.json').read_text(encoding='utf-8'))
assert round(sum(v for _,v in metadata['purchases_yuan']),2)==57.64
assert sum(len(group) for group in metadata['team_groups'])==6
web=(BASE/'index.html').read_text(encoding='utf-8')
assert len(re.findall(r'<section class="slide(?: active)?"',web))==20
assert not re.findall(r'(?:src|href)=["\']https?://',web)
notes=(BASE/'逐页讲稿.md').read_text(encoding='utf-8')
assert all(item['note'] in notes for item in manifest['slides'])
text='\n'.join(i['title']+' '+i['note'] for i in manifest['slides'])
phrases=['不等于','更不能','不能据此','不代表','需确认','未经验证','不声称','不保证','不构成','不能证明','避免误解']
assert not [p for p in phrases if p in text]
report={'slides':20,'main_slides':18,'main_seconds':855,'speaker_notes':'all 20 match content metadata','source_references':'all local paths exist; comparison URL recorded','geometry_issues':0,'duplicate_zip_entries':duplicates,'pptx_external_relationships':len(external),'template_layouts':len(prs.slide_layouts),'template_masters':len(prs.slide_masters),'budget':57.64,'team_members':6,'led_states':9,'gif_duration_seconds':duration/1000,'gif_embedded':True,'led_matches_current_header':True,'external_asset_urls':0,'template_sha256':hashlib.sha256((BASE/'assets/2021simpleblue.pptx').read_bytes()).hexdigest(),'defensive_phrase_scan':'passed'}
(BASE/'qa').mkdir(exist_ok=True)
(BASE/'qa/structure.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
files={}
for name in (TITLE+'.pptx',TITLE+'.pdf','index.html','逐页讲稿.md'):
    data=(BASE/name).read_bytes();files[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
(BASE/'qa/final.json').write_text(json.dumps({'files':files,'preview_count':20,'selected_overview':[4,6,7,8,10,13]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
