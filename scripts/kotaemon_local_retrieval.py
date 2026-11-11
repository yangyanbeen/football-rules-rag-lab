"""Pinned file retrieval without an unused remote reranker or scoring model.

The upstream factory eagerly resolves a reranker even when reranking is off.
Keep its actual retrieval/permission implementation and configure only the
factory for this local Ollama profile. This is not a new reranking algorithm.
"""
from ktem.embeddings.manager import embedding_models_manager
from ktem.index.file.pipelines import DocumentRetrievalPipeline


class LocalDocumentRetrievalPipeline(DocumentRetrievalPipeline):
    @classmethod
    def get_user_settings(cls):
        values = super().get_user_settings()
        for key in ('reranking_llm', 'use_reranking', 'use_llm_reranking'):
            values.pop(key, None)
        return values

    @classmethod
    def get_pipeline(cls, user_settings, index_settings, selected):
        name = index_settings.get('embedding') or embedding_models_manager.get_default_name()
        pipeline = cls(
            get_extra_table=user_settings['prioritize_table'],
            top_k=user_settings['num_retrieval'],
            mmr=user_settings['mmr'],
            embedding=embedding_models_manager[name],
            retrieval_mode=user_settings['retrieval_mode'],
            llm_scorer=None,
            rerankers=[],
        )
        pipeline.set_run({'.doc_ids': selected}, temp=False)
        return pipeline
