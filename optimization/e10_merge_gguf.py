"""Merge verified Qwen GGUF shards without requantizing any tensor.

Uses the official llama.cpp gguf wheel, isolated under the E10 tools directory.
Merge and verification are separate processes to bound mapped working memory.
"""
import argparse,gc,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.runtime/phase2/e10-gguf-tools'))
import gguf

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def merge(paths,dest):
    assert not dest.exists()
    readers=[gguf.GGUFReader(str(p)) for p in paths]
    tensors=[t for r in readers for t in r.tensors]
    assert len({t.name for t in tensors})==len(tensors)
    first=readers[0];arch=first.fields['general.architecture'].contents()
    metadata={k:f for k,f in first.fields.items() if not k.startswith(('GGUF.','split.'))}
    writer=gguf.GGUFWriter(dest,arch)
    for k,f in metadata.items():
        if k=='general.architecture':continue
        writer.add_key_value(k,f.contents(),f.types[0],f.types[-1] if f.types[0]==gguf.GGUFValueType.ARRAY else None)
    for t in tensors:writer.add_tensor_info(t.name,t.data.shape,t.data.dtype,t.data.nbytes,raw_dtype=t.tensor_type)
    writer.write_header_to_file();writer.write_kv_data_to_file();writer.write_ti_data_to_file()
    audit=[]
    for ix,t in enumerate(tensors,1):
        h=hashlib.sha256(t.data).hexdigest();writer.write_tensor_data(t.data)
        audit.append(dict(name=t.name,shape=[int(v) for v in t.shape],dtype=int(t.tensor_type),nbytes=t.data.nbytes,sha256=h))
        if ix%50==0:print(json.dumps(dict(tensors_copied=ix,total=len(tensors))),flush=True)
    writer.close()
    value=dict(inputs=[dict(path=str(p),sha256=digest(p)) for p in paths],output=str(dest),arch=arch,
        metadata={k:hashlib.sha256(json.dumps(f.contents(),ensure_ascii=False,separators=(',',':')).encode()).hexdigest() for k,f in metadata.items()},
        tensors=audit,requantized=False,split_metadata_removed=True)
    dest.with_suffix('.merge.json').write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())

def verify(dest):
    expected=json.loads(dest.with_suffix('.merge.json').read_text('utf8'));reader=gguf.GGUFReader(str(dest))
    assert len(reader.tensors)==len(expected['tensors'])
    for t,e in zip(reader.tensors,expected['tensors']):
        assert t.name==e['name'] and [int(v) for v in t.shape]==e['shape'] and int(t.tensor_type)==e['dtype']
        assert t.data.nbytes==e['nbytes'] and hashlib.sha256(t.data).hexdigest()==e['sha256']
    for k,h in expected['metadata'].items():
        assert hashlib.sha256(json.dumps(reader.fields[k].contents(),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==h,k
    value=dict(output=str(dest),sha256=digest(dest),tensors_verified=len(reader.tensors),metadata_verified=len(expected['metadata']),requantized=False,
        parameter_name=reader.fields.get('general.name').contents() if reader.fields.get('general.name') else None,
        file_type=reader.fields.get('general.file_type').contents() if reader.fields.get('general.file_type') else None)
    dest.with_suffix('.verified.json').write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(value),flush=True)

def test(folder):
    import numpy as np
    folder.mkdir(parents=True,exist_ok=False)
    w=gguf.GGUFWriter(folder/'test.gguf','qwen2',split_max_tensors=1)
    w.add_name('E10 merge fixture');w.add_uint32('qwen2.context_length',8192)
    w.add_tensor('test.a',np.arange(12,dtype=np.float32).reshape(3,4))
    w.add_tensor('test.b',np.arange(8,dtype=np.float16).reshape(2,4))
    w.add_tensor('test.quant',np.arange(288,dtype=np.uint8).reshape(2,144),raw_dtype=gguf.GGMLQuantizationType.Q4_K)
    w.write_header_to_file();w.write_kv_data_to_file();w.write_tensors_to_file();w.close()
    paths=sorted(folder.glob('test-*.gguf'));assert len(paths)==3
    merge(paths,folder/'merged.gguf');verify(folder/'merged.gguf')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['merge','verify','test']);p.add_argument('--out',type=Path,required=True);p.add_argument('inputs',nargs='*',type=Path);a=p.parse_args()
    if a.mode=='test':test(a.out)
    elif a.mode=='merge':merge(a.inputs,a.out)
    else:verify(a.out)
