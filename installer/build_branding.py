"""Regenerate installer bitmaps from the shared dark square and blue wave."""
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
BACKGROUND = '#1e1e1e'
ACCENT = '#49a8ed'


def mark(size):
    image = Image.new('RGBA', (size,size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    points = [(3,21),(8,21),(8,11),(14,11),(14,26),(19,26),(19,6),(24,6),(24,21),(29,21)]
    draw.line([(round(x*size/32),round(y*size/32)) for x,y in points], fill=ACCENT, width=max(2,round(2.5*size/32)), joint='curve')
    return image


def build():
    mark(256).save(ROOT/'brand.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    small=Image.new('RGB',(64,64),BACKGROUND)
    small.paste(mark(64),(0,0),mark(64))
    small.save(ROOT/'wizard-small.bmp')
    image=Image.new('RGB',(192,386),BACKGROUND)
    image.paste(mark(132),(30,90),mark(132))
    fontpath=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'segoeui.ttf'
    font=ImageFont.truetype(str(fontpath),21) if fontpath.is_file() else ImageFont.load_default(size=21)
    draw=ImageDraw.Draw(image)
    draw.text((96,252),'Project Hub',font=font,fill='#eeeeee',anchor='mm')
    draw.line((38,292,154,292),fill=ACCENT,width=2)
    image.save(ROOT/'wizard.bmp')


if __name__=='__main__': build()
