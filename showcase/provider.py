"""External AI is opt-in and separate from model predictions."""
import os
from fastapi import HTTPException

def enabled(name,default=False):
    return os.getenv(name,str(default)).lower()=='true'

def configuration():
    return {'showcase_mode':enabled('SHOWCASE_MODE',True),'local_ml_enabled':enabled('LOCAL_ML_ENABLED',True),'external_ai_enabled':enabled('EXTERNAL_AI_ENABLED'), 'provider':os.getenv('AI_PROVIDER','google'), 'model':os.getenv('AI_MODEL','gemini-3.8-flash'), 'key_configured':bool(os.getenv('AI_PROVIDER_API_KEY') or os.getenv('GEMINI_API_KEY'))}

class GoogleProvider:
    def plan(self,request,capabilities):
        # Isolated REST adapter; original Gemini integration remains untouched.
        import requests
        import re
        config=configuration()
        if not re.fullmatch(r'gemini-[A-Za-z0-9._-]+',config['model']):
            raise HTTPException(422,'Invalid model ID')
        key=os.getenv('AI_PROVIDER_API_KEY') or os.getenv('GEMINI_API_KEY')
        if not key: raise HTTPException(503,'Provider key is not configured')
        try:
            with requests.Session() as session:
                session.trust_env=False
                r=session.post('https://generativelanguage.googleapis.com/v1beta/models/'+config['model']+':generateContent',headers={'x-goog-api-key':key},json={'contents':[{'parts':[{'text':'Explain this showcase request. Do not claim to execute anything: '+request}]}]},timeout=(5,30),allow_redirects=False)
                if r.status_code!=200: raise HTTPException(502,'External provider request failed')
                text=r.json()['candidates'][0]['content']['parts'][0]['text']
        except requests.RequestException:
            raise HTTPException(502,'External provider unavailable')
        except (KeyError,IndexError,ValueError):
            raise HTTPException(502,'Invalid provider response')
        return {'component':'external_ai','provider':'google','model':config['model'],'output':text,'used_for_local_prediction':False}

def get_provider():
    if not enabled('EXTERNAL_AI_ENABLED'): raise HTTPException(403,'External AI is disabled; no network call made')
    if os.getenv('AI_PROVIDER','google')!='google': raise HTTPException(422,'Provider not implemented')
    return GoogleProvider()
