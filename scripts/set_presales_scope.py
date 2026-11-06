"""将当前蚊帐 FAQ 统一限制在售前；原文件先备份，话术与素材不变。"""
import argparse
import copy
import json
import os
from datetime import datetime
from pathlib import Path
import uuid


def migrate(document):
    result=copy.deepcopy(document)
    for row in result.get('records',[]):
        # 后续新增通用接待模板不属于原蚊帐售前知识的批量迁移范围。
        if row.get('origin')=='general_reception_template':continue
        row['conditions']={**row.get('conditions',{}),'reception':'presales','stages':['presales']}
    return result


def apply(path):
    path=Path(path)
    original=path.read_bytes()
    document=json.loads(original.decode('utf-8'))
    result=migrate(document)
    if result==document:
        return None,len(result.get('records',[]))
    backups=path.parent/'backups'
    backups.mkdir(parents=True,exist_ok=True)
    backup=backups/f'{path.stem}-before-presales-{datetime.now():%Y%m%d-%H%M%S-%f}.json'
    backup.write_bytes(original)
    temporary=path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()
    return backup,len(result.get('records',[]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path',type=Path,default=Path(__file__).resolve().parents[1]/'data/faq.json')
    arguments=parser.parse_args()
    backup,count=apply(arguments.path)
    print(f'{count} 条答案已限制在售前；'+(f'备份：{backup}' if backup else '范围已经一致，无需重复修改。'))
