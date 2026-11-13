"""Deterministic two-channel rank fusion; standard library, no labels/models."""
from __future__ import annotations
import math,re,copy
from fractions import Fraction
from itertools import zip_longest

CHANNELS=('dense','bm25')
METHODS=('dense','bm25','union','rrf')
SOURCE_FIELDS=('chunk_id','source_url','source_lines','law_number','record_sha256','content_zh_sha256')


def number(value):
    try:return type(value) in (int,float) and math.isfinite(value)
    except OverflowError:return False


def parameters(k,top_k):
    if type(k) is not int or not 0<=k<=1000000:raise ValueError('k must be an integer in [0, 1000000]')
    if type(top_k) is not int or not 1<=top_k<=99:raise ValueError('top_k must be an integer in [1, 99]')


def candidates(channels):
    if not isinstance(channels,dict) or set(channels)!=set(CHANNELS):raise ValueError('Both declared channels required; no silent fallback')
    found={}
    for channel,rows in channels.items():
        if not isinstance(rows,list) or len(rows)>99:raise ValueError('Invalid channel list')
        seen=set()
        for rank,row in enumerate(rows,1):
            if (not isinstance(row,dict) or set(row)!=set(SOURCE_FIELDS)|{'rank','score'}|({'distance'} if channel=='dense' else set())
                or not isinstance(row['chunk_id'],str) or not re.fullmatch(r'[0-9A-Za-z_-]+',row['chunk_id'])
                or row['chunk_id'] in seen or type(row['rank']) is not int or row['rank']!=rank
                or not number(row['score']) or (channel=='bm25' and row['score']<=0)):
                raise ValueError('Duplicate ID, invalid rank, score or result schema')
            if channel=='dense' and (not number(row['distance']) or abs(row['score']-(1-row['distance']))>1e-6):raise ValueError('Dense distance/score mismatch')
            if (type(row['law_number']) is not int or not 1<=row['law_number']<=17
                or not isinstance(row['source_url'],str) or not row['source_url'].startswith('https://en.wikipedia.org/wiki/')
                or not isinstance(row['source_lines'],list) or len(row['source_lines'])!=2
                or any(type(n) is not int for n in row['source_lines']) or not 0<row['source_lines'][0]<=row['source_lines'][1]
                or any(not isinstance(row[p],str) or not re.fullmatch('[a-f0-9]{64}',row[p]) for p in ('record_sha256','content_zh_sha256'))):
                raise ValueError('Invalid source metadata')
            seen.add(row['chunk_id']);metadata={p:row[p] for p in SOURCE_FIELDS}
            target=found.setdefault(row['chunk_id'],{**metadata,'sources':{}})
            if any(target[p]!=metadata[p] for p in SOURCE_FIELDS):raise ValueError('Same ID has conflicting source metadata')
            target['sources'][channel]={p:row[p] for p in ('rank','score')+(('distance',) if channel=='dense' else ())}
    return found


def fuse(channels,k=60,top_k=10):
    parameters(k,top_k);found=candidates(channels)
    scores={cid:sum((Fraction(1,k+r['rank']) for r in row['sources'].values()),Fraction()) for cid,row in found.items()}
    union=[];seen=set()
    for pair in zip_longest(*(channels[c] for c in CHANNELS)):
        for row in pair:
            if row is not None and row['chunk_id'] not in seen:seen.add(row['chunk_id']);union.append(row['chunk_id'])
    orders={c:[r['chunk_id'] for r in channels[c]] for c in CHANNELS}
    orders.update(union=union,rrf=sorted(found,key=lambda cid:(-scores[cid],cid)))
    def score(method,cid):
        if method=='rrf':return float(scores[cid])
        if method=='union':return None
        return found[cid]['sources'][method]['score']
    # Each output owns its nested metadata. Callers may annotate one ranking
    # without changing the input packet or another method's provenance.
    return {method:[{**copy.deepcopy(found[cid]),'rank':rank,'score':score(method,cid)} for rank,cid in enumerate(ids[:top_k],1)] for method,ids in orders.items()}
