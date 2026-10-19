"""下载固定版本的模型数据，不执行模型仓库中的Python代码。"""
import hashlib
import os
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parent.parent
REV='e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
REPO='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
EXPECTED='98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f'

def main():
    folder=ROOT/'models/minilm'
    folder.mkdir(parents=True,exist_ok=True)
    endpoint=os.getenv('HF_ENDPOINT','https://huggingface.co').rstrip('/')
    with httpx.Client(timeout=60,follow_redirects=True) as client:
        for remote,name in [('onnx/model_quint8_avx2.onnx','model.onnx'),('tokenizer.json','tokenizer.json')]:
            target=folder/name
            if target.exists() and (name!='model.onnx' or hashlib.sha256(target.read_bytes()).hexdigest()==EXPECTED):
                print(name,'already present');continue
            tmp=folder/(name+'.part')
            with client.stream('GET',f'{endpoint}/{REPO}/resolve/{REV}/{remote}') as r:
                r.raise_for_status()
                with tmp.open('wb') as out:
                    for chunk in r.iter_bytes(1024*1024):out.write(chunk)
            if name=='model.onnx' and hashlib.sha256(tmp.read_bytes()).hexdigest()!=EXPECTED:
                raise ValueError('model_checksum_mismatch')
            tmp.replace(target)
            print(name,'downloaded',target.stat().st_size,flush=True)

if __name__=='__main__':main()
