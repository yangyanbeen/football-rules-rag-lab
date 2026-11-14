"""Pinned local structured decoding; semantic decisions remain model-generated."""
def selection_schema(offered,limit):
    def branch(answerable):
        return {'type':'object','properties':{'answerable':{'const':answerable},
          'chunk_ids':{'type':'array','items':{'type':'string','enum':list(offered)},'minItems':1 if answerable else 0,'maxItems':limit if answerable else 0},
          'reason':{'type':'null'} if answerable else {'type':'string','enum':['insufficient_evidence','source_conflict','version_unverified']}},
          'required':['answerable','chunk_ids','reason'],'additionalProperties':False}
    return {'anyOf':[branch(True),branch(False)]}


def grade_schema(q,p):
    props={k:{'type':'array','items':{'type':'boolean'},'minItems':n,'maxItems':n} for k,n in
      [('points',len(q['expected_answer_points'])),('conditions',len(q['required_conditions'])),('citations',len(p['citations']))]}
    props['reason']={'type':'string','minLength':1,'maxLength':500}
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}


def generate(chat,messages,schema):
    from rag_b0 import validate_model_response,GenerationRejected
    cfg=chat.config['llm'];chat.verify_model()
    response=chat.request('/api/chat',{'model':cfg['name'],'messages':messages,'stream':False,'format':schema,
      'keep_alive':cfg['keep_alive'],'options':{k:cfg[k] for k in ('num_ctx','num_predict','num_gpu','num_thread','temperature','seed')}})
    try:chat.verify_model()
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
        raise GenerationRejected('Post-structured-generation model identity failed: '+str(exc),response,retryable=False) from exc
    return validate_model_response(response,chat.config)
