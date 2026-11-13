"""Pinned official BGE cross encoder, local ONNX only; never consumes gold labels."""
from __future__ import annotations
import hashlib,importlib.metadata,json,math,time
from pathlib import Path
from eval_dataset import ROOT,canonical,digest

REVISION='2cfc18c9415c912f9d8155881c133215df768a70'
HOME=ROOT/'.models/bge-reranker-base'/REVISION


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def passage(row):
    return ' / '.join(row['section_path'])+'\n\n'+row['content_zh']


class BgeReranker:
    def __init__(self,cfg):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np=np;self.cfg=cfg
        for name,version in cfg['packages'].items():
            if importlib.metadata.version(name)!=version:raise ValueError('Reranker runtime version differs: '+name)
        for name,entry in cfg['files'].items():
            path=HOME/name
            if path.stat().st_size!=entry['size_bytes'] or file_sha(path)!=entry['sha256']:raise ValueError('Model file differs: '+name)
        self.tokenizer=Tokenizer.from_file(str(HOME/'tokenizer.json'))
        self.raw_tokenizer=Tokenizer.from_file(str(HOME/'tokenizer.json'))
        self.raw_tokenizer.no_truncation();self.raw_tokenizer.no_padding()
        self.tokenizer.enable_truncation(max_length=cfg['max_length'],strategy='longest_first',direction='right')
        self.tokenizer.enable_padding(pad_id=1,pad_token='<pad>',direction='right')
        options=ort.SessionOptions();options.intra_op_num_threads=cfg['threads'];options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session=ort.InferenceSession(str(HOME/'onnx/model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.inputs=[x.name for x in self.session.get_inputs()]
        if set(self.inputs)!={'input_ids','attention_mask'}:raise ValueError('Unexpected official ONNX input signature: '+str(self.inputs))
        if self.session.get_providers()!=['CPUExecutionProvider']:raise ValueError('CPU provider required')

    def score(self,query,candidates,by_id):
        """Returns public hashes/token counts/scores; passage text stays in memory."""
        start=time.perf_counter_ns();pairs=[(query,passage(by_id[r['chunk_id']])) for r in candidates]
        raw=self.raw_tokenizer.encode_batch(pairs,add_special_tokens=True)
        records=[];batches=[];token_seconds=0.;inference_seconds=0.
        for offset in range(0,len(pairs),self.cfg['batch_size']):
            sub=pairs[offset:offset+self.cfg['batch_size']];t=time.perf_counter_ns()
            encoded=self.tokenizer.encode_batch(sub,add_special_tokens=True)
            inputs={'input_ids':self.np.array([e.ids for e in encoded],dtype=self.np.int64),
                    'attention_mask':self.np.array([e.attention_mask for e in encoded],dtype=self.np.int64)}
            a=time.perf_counter_ns();logits=self.session.run(None,inputs)[0];b=time.perf_counter_ns()
            values=self.np.asarray(logits).reshape(-1).tolist()
            if len(values)!=len(sub) or any(not math.isfinite(v) for v in values):raise ValueError('Invalid cross-encoder logits')
            token_seconds+=(a-t)/1e9;inference_seconds+=(b-a)/1e9
            batches.append({'offset':offset,'size':len(sub),'padded_length':len(encoded[0].ids),
                            'tokenization_and_tensor_seconds':(a-t)/1e9,'inference_seconds':(b-a)/1e9})
            for j,(pair,enc,value) in enumerate(zip(sub,encoded,values)):
                i=offset+j;ids=[v for v,mask in zip(enc.ids,enc.attention_mask) if mask]
                records.append({'chunk_id':candidates[i]['chunk_id'],'before_rank':i+1,'score':value,
                                'query_sha256':digest(pair[0].encode()),'passage_sha256':digest(pair[1].encode()),
                                'input_ids_sha256':digest(canonical(ids)),'original_tokens':len(raw[i].ids),
                                'used_tokens':len(ids),'truncated_tokens':len(raw[i].ids)-len(ids)})
        # Strict deterministic tie break; raw logits are not probabilities.
        order=sorted(records,key=lambda r:(-r['score'],r['chunk_id']))
        ranked=[{**r,'rank':i} for i,r in enumerate(order,1)];end=time.perf_counter_ns()
        return {'results':ranked,'batches':batches,'timing':{'tokenization_and_tensor_seconds':token_seconds,
                'inference_seconds':inference_seconds,'other_seconds':(end-start)/1e9-token_seconds-inference_seconds,
                'total_seconds':(end-start)/1e9}}
