"""Build redistributable UI webfonts from the OFL-licensed Noto Sans SC source.

Usage: python scripts/build_ui_fonts.py path/to/NotoSansSC-VF.ttf
Build dependencies: fonttools[woff], brotli. The app only serves the built files.
"""
import copy
import sys
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


def build(source,output):
    chars=set(chr(n) for n in range(0x20,0x100))
    chars.update(chr(n) for a,b in ((0x2000,0x2070),(0x3000,0x3040),(0xff00,0xfff0)) for n in range(a,b))
    # All GB2312 Chinese characters, independent of private customer records.
    for first in range(0xb0,0xf8):
        for second in range(0xa1,0xff):
            try:chars.add(bytes((first,second)).decode('gb2312'))
            except UnicodeDecodeError:pass
    font=TTFont(source)
    options=subset.Options();options.name_IDs=[0,1,2,3,4,6,13,14];options.name_languages=['*']
    sub=subset.Subsetter(options=options);sub.populate(unicodes=[ord(c) for c in chars]);sub.subset(font)
    output.mkdir(parents=True,exist_ok=True)
    for weight,style in ((400,'Regular'),(600,'Semibold')):
        face=instantiateVariableFont(copy.deepcopy(font),{'wght':weight},inplace=True)
        for name in face['name'].names:
            value={1:'PAC UI Sans',2:style,3:'PACUISans-'+style,4:'PAC UI Sans '+style,6:'PACUISans-'+style}.get(name.nameID)
            if value:name.string=value.encode(name.getEncoding())
        face.flavor='woff2';path=output/f'pac-ui-sans-{weight}-v1.woff2';face.save(path)
        print(path.name,path.stat().st_size,flush=True)


if __name__=='__main__':build(sys.argv[1],Path(__file__).resolve().parents[1]/'static/fonts')
