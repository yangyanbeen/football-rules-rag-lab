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
    flowsettings.KH_INDICES=[{'name':'足球规则知识库','config':{},'index_type':'rag_b0_index_ui.FixedFootballIndex'}]
    flowsettings.KH_INDEX_TYPES=['rag_b0_index_ui.FixedFootballIndex']
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
    import ktem.pages.chat as chat_module
    import ktem.pages.chat.chat_panel as chat_panel_module
    import ktem.pages.help as help_page
    help_page.download_changelogs=lambda release_url:''
    chat_panel_module.PLACEHOLDER_TEXT='请直接输入足球规则问题。回答依据固定资料，并显示可核对的原文来源。'
    # Treat all question text literally; this profile has no URL ingestion or
    # @WebSearch command. These overrides exist only in this new process.
    chat_module.get_urls=lambda text:([],text)
    chat_module.get_mentions_regex=lambda text:([],text)
    original_submit=ChatPage.submit_msg

    def literal_submit(self,chat_input,chat_history,user_id,settings,conv_id,conv_name,first_selector_choices):
        if chat_input and chat_input.get('files'):
            raise ValueError('本入口只支持文字提问，请使用已有的足球规则知识库。')
        return original_submit(self,chat_input,chat_history,user_id,settings,conv_id,conv_name,first_selector_choices,request=None)

    ChatPage.submit_msg=literal_submit

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
    app.chat_page.chat_panel.text_input.placeholder='请输入足球规则问题'
    app.chat_page.chat_panel.text_input.file_types=[]
    app.chat_page.chat_control.cb_suggest_chat.visible=False
    app.chat_page.use_mindmap.visible=False
    for block in demo.blocks.values():
        if isinstance(block,gr.Accordion) and block.label=='Quick Upload':block.visible=False
    demo.css=(demo.css or '')+'\n#chat-input .upload-button {display:none !important;}'
    # Resource editing is outside this fixed-corpus entry point.
    for tab in ('resources-tab','settings-tab'):
        app._tabs[tab].visible=False
    print('Task 6 pinned Dense + Qwen generation; isolated database:',appdata,flush=True)
    demo.queue().launch(server_name=cfg['ui']['host'],server_port=cfg['ui']['port'],
                        share=False,inbrowser=False,allowed_paths=[str(upstream/'assets')])


if __name__=='__main__':main()
