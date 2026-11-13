"""Retrospective environment observation; does not rewrite frozen run evidence."""
import ctypes,importlib.metadata,json,os,platform,sys
from eval_dataset import ROOT
from bm25_index import record,write_new
from bm25_retrieval_eval import now


def main():
    memory=None
    if os.name=='nt':
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
        value=Memory();value.length=ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):memory=value.total_phys
    result={'version':'hybrid-environment-1.0','captured_at':now(),'python':platform.python_version(),'implementation':platform.python_implementation(),
            'system':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),'logical_cpus':os.cpu_count(),
            'physical_memory_bytes':memory,'packages':{name:importlib.metadata.version(name) for name in ('numpy','chromadb','chroma-hnswlib')},
            'dense_model':json.loads((ROOT/'config/dense_index.json').read_text('utf-8'))['model'],
            'dense_device':'CPU; num_gpu=0; num_thread=8','fusion_device':'CPU; concurrency1',
            'random_seed':'Not applicable: deterministic ranking over fixed saved lists; no stochastic selection',
            'scope':'Observed after dev/test fusion on the same host; supplemental metadata, not a before-run capture or repeat benchmark',
            'producer_sha256':record(__file__)['sha256']}
    write_new(ROOT/'reports/retrieval/hybrid_rrf_b0/acceptance/environment.json',result)
    print(json.dumps({k:result[k] for k in ('python','logical_cpus','physical_memory_bytes')}))


if __name__=='__main__':main()
