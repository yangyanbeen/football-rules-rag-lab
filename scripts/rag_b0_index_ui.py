"""Read-only selector contract for the pinned ChatPage, not a second index."""
import gradio as gr
from ktem.app import BasePage
from ktem.index.base import BaseIndex


class FixedCorpusSelector(BasePage):
    def __init__(self, app):
        self._app=app
        gr.Markdown('**足球规则知识库** · 5份中文资料 / 99个知识段\n\n依据固定资料回答；非官方赛季规则，未经过裁判专家审校。')
        self.mode=gr.Dropdown(choices=['all'],value='all',visible=False)
        self.files=gr.Dropdown(choices=[],value=[],multiselect=True,visible=False)
        self.selector_choices=gr.State([])

    def default(self):return ['all',[]]

    def as_gradio_component(self):return [self.mode,self.files]


class FixedCorpusInfo(BasePage):
    def __init__(self, app):
        self._app=app
        gr.Markdown('本入口使用固定的足球规则中文资料。请在 Chat 中提问，并查看回答旁的原文及来源链接。')


class FixedFootballIndex(BaseIndex):
    def get_selector_component_ui(self):
        if not hasattr(self,'_fixed_selector'):
            self._fixed_selector=FixedCorpusSelector(self._app)
        return self._fixed_selector

    def get_index_page_ui(self):return FixedCorpusInfo(self._app)

    def get_indexing_pipeline(self,settings,user_id):
        raise ValueError('This profile has no upload or indexing operation')

    # The reasoning worker performs the sole retrieval from Task 5's index.
    def get_retriever_pipelines(self,settings,user_id,selected=None):return []
