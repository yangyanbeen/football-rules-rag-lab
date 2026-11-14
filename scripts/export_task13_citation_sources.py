"""Export source metadata for all99 frozen chunks; no source/answer body is emitted."""
from task13_core import *
from citation_catalog_guard import safe_render

if __name__=='__main__':
    corpus=local_corpus();sources={}
    for cid in sorted(corpus):sources[cid]=safe_render([cid],corpus)[1][0]
    value={'version':'task13-citation-sources-1.0','corpus':record(ROOT/app_config()['corpus']),
        'generator':record(__file__),'records':len(sources),'sources':sources,
        'scope':'Metadata and hashes only; not raw source text, translation, answers or expert judgments.'}
    write_new(ROOT/'data/manifests/task13_citation_sources.json',value)
    print(json.dumps({'status':'PASS','records':len(sources),'full_text_emitted':False}))
