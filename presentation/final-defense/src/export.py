#!/usr/bin/env python3
"""Export the finished PPTX through LibreOffice and render every PDF page."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

BASE=Path(__file__).resolve().parents[1]
TITLE='交小西DormSense_结题答辩展示'
FONT='/Library/Fonts/msyh.ttc'
manifest=json.loads((BASE/'src/manifest.json').read_text(encoding='utf-8'))
with tempfile.TemporaryDirectory(prefix='dormsense-export-') as directory:
    temp=Path(directory)
    subprocess.run(['/opt/homebrew/bin/soffice','-env:UserInstallation='+(temp/'profile').as_uri(),'--headless','--convert-to','pdf','--outdir',str(temp),str(BASE/(TITLE+'.pptx'))],check=True)
    pdf=temp/(TITLE+'.pdf')
    assert pdf.is_file() and pdf.stat().st_size>10000
    shutil.copyfile(pdf,BASE/(TITLE+'.pdf'))
    subprocess.run(['pdftoppm','-scale-to-x','1600','-scale-to-y','900','-png',str(pdf),str(temp/'slide')],check=True)
    pages=sorted(temp.glob('slide-*.png'))
    assert len(pages)==len(manifest['slides'])
    for number,page in enumerate(pages,1):shutil.copyfile(page,BASE/'previews'/f'slide-{number:02}.png')
    subprocess.run(['pdftotext','-layout',str(pdf),str(BASE/'.build/pdf-text.txt')],check=True)

count=len(manifest['slides']);columns=4;cell_w=480;cell_h=304
contact=Image.new('RGB',(columns*cell_w,((count+columns-1)//columns)*cell_h),'#EAF3FA');draw=ImageDraw.Draw(contact)
font=ImageFont.truetype(FONT,20)
for n,slide in enumerate(manifest['slides'],1):
    x=((n-1)%columns)*cell_w;y=((n-1)//columns)*cell_h
    contact.paste(Image.open(BASE/'previews'/f'slide-{n:02}.png').resize((464,261)),(x+8,y+8))
    label=f'{n:02}  '+slide['title']
    while font.getlength(label)>cell_w-24:label=label[:-2]+'…'
    draw.text((x+12,y+275),label,font=font,fill='#182B3B')
contact.save(BASE/'previews/全部页面总览.png')
selected=[4,6,7,8,10,13]
contact=Image.new('RGB',(1600,3*482),'#EAF3FA');draw=ImageDraw.Draw(contact)
for index,n in enumerate(selected):
    x=(index%2)*800;y=(index//2)*482
    contact.paste(Image.open(BASE/'previews'/f'slide-{n:02}.png').resize((784,441)),(x+8,y+8))
    draw.text((x+15,y+455),f'{n:02}  '+manifest['slides'][n-1]['title'],font=font,fill='#182B3B')
contact.save(BASE/'previews/精选页面.png')
print(json.dumps({'pdf':str(BASE/(TITLE+'.pdf')),'pages':count,'previews':count,'overview':'previews/全部页面总览.png'},ensure_ascii=False))
