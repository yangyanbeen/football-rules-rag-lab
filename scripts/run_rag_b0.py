"""Isolated loopback Kotaemon profile for Task 6; no upstream files are edited."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from rag_b0 import ROOT, load_config
from rag_b0_worker_client import call_worker
from kotaemon_runtime_env import configure_local_runtime


def main():
    cfg=load_config()
    upstream=ROOT/'third_party/kotaemon-v0.12.0'
    for name in ('USE_MS_GRAPHRAG','USE_LIGHTRAG','USE_NANO_GRAPHRAG','USE_GLOBAL_GRAPHRAG'):
        os.environ[name]='false'
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',GRADIO_ANALYTICS_ENABLED='false',
                      USE_LOW_LLM_REQUESTS='true',KH_FIRST_SETUP='false')
    configure_local_runtime()
    for path in (upstream,upstream/'libs/ktem',upstream/'libs/kotaemon'):
        sys.path.insert(0,str(path))
    os.chdir(upstream)
    from theflow.settings import settings as flowsettings
    flowsettings.load_settings()

    appdata=(ROOT/cfg['ui']['app_data']).resolve()
    if not appdata.is_relative_to(ROOT/'.runtime/rag-b0'):
        raise ValueError('Isolated app data must stay in the Task 6 runtime directory')
    for key,suffix in (('KH_APP_DATA_DIR',''),('KH_USER_DATA_DIR','user_data'),
                       ('KH_MARKDOWN_OUTPUT_DIR','markdown'),('KH_CHUNKS_OUTPUT_DIR','chunks'),
                       ('KH_ZIP_OUTPUT_DIR','zip_output'),('KH_ZIP_INPUT_DIR','zip_input')):
        path=appdata/suffix;path.mkdir(parents=True,exist_ok=True)
        setattr(flowsettings,key,path)
    flowsettings.KH_DATABASE='sqlite:///'+str(appdata/'user_data/sql.db')
    flowsettings.KH_FILESTORAGE_PATH=str(appdata/'user_data/files')
    flowsettings.KH_DOCSTORE={'__type__':'kotaemon.storages.SimpleFileDocumentStore','path':str(appdata/'docstore')}
    flowsettings.KH_VECTORSTORE={'__type__':'kotaemon.storages.ChromaVectorStore','path':str(appdata/'unused-vectorstore')}
    flowsettings.KH_APP_DATA_EXISTS=True
    flowsettings.KH_ENABLE_FIRST_SETUP=False
    flowsettings.KH_APP_NAME='足球规则 RAG B0'
    flowsettings.KH_DEMO_MODE=False
    flowsettings.KH_SSO_ENABLED=False
    flowsettings.KH_GRADIO_SHARE=False
    flowsettings.KH_FEATURE_USER_MANAGEMENT=False
    flowsettings.KH_FEATURE_CHAT_SUGGESTION=False
    flowsettings.KH_INDICES=[]
    flowsettings.KH_INDEX_TYPES=[]
    flowsettings.KH_REASONINGS=['rag_b0_pipeline.FootballRagB0Pipeline']
    flowsettings.KH_LLMS={'ollama':{'spec':{'__type__':'kotaemon.llms.ChatOpenAI',
        'base_url':'http://127.0.0.1:11434/v1/','model':cfg['llm']['name'],'api_key':'ollama','temperature':0},'default':True}}
    flowsettings.KH_EMBEDDINGS={}
    flowsettings.KH_RERANKINGS={}
    flowsettings.SETTINGS_REASONING['lang']['value']='zh'
    os.environ['GRADIO_TEMP_DIR']=str(appdata/'gradio')
    os.environ['HF_HOME']=os.environ['HF_HUB_CACHE']=str(appdata/'huggingface')

    import gradio as gr
    print('Task 6: importing pinned Kotaemon UI',flush=True)
    from ktem.main import App
    from ktem.pages.chat import ChatPage

    def local_title(self, chat_history):
        if len(chat_history)==1:
            return gr.update(value=str(chat_history[0][0])[:40]),True
        return gr.update(),False

    # The upstream default names a conversation via another LLM call. The
    # isolated process instead uses the first question, without model traffic.
    ChatPage.check_and_suggest_name_conv=local_title
    print('Task 6: verifying pinned model and index',flush=True)
    if call_worker(check=True)['status']!='READY':raise ValueError('Worker not ready')
    app=App()
    print('Task 6: building isolated ChatPage',flush=True)
    demo=app.make()
    # Resource editing is outside this fixed-corpus entry point.
    for tab in ('resources-tab','settings-tab'):
        app._tabs[tab].visible=False
    print('Task 6 pinned Dense + Qwen generation; isolated database:',appdata,flush=True)
    demo.queue().launch(server_name=cfg['ui']['host'],server_port=cfg['ui']['port'],
                        share=False,inbrowser=False,allowed_paths=[str(upstream/'assets')])


if __name__=='__main__':main()
