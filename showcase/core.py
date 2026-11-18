"""Shared implementation, independently versioned artifacts/configuration per model."""
import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import pandas as pd

ROOT = Path(__file__).resolve().parent
NAMES = ['workflow_intent', 'invoice_discrepancy', 'transaction_anomaly', 'email_classification']
VERSION = '1.0.0'
NUMERIC = {
 'invoice_discrepancy': ['invoice_amount','po_amount','quantity_difference','tax_difference','supplier_incident_rate'],
 'transaction_anomaly': ['amount','hour','account_age_days','daily_count','international'],
}
TEXTS = {
 'workflow_intent': {
 'customer_onboarding': ['Register a new customer account','Complete client identity verification','Set up a customer profile','Enroll a business customer','Start customer KYC checks','Activate a new client account','Collect documents for customer registration','Create a client onboarding case','Verify the new customer identity','Begin customer enrollment'],
 'invoice_processing': ['Process the supplier invoice','Compare an invoice with its purchase order','Check invoice amounts and quantities','Reconcile the vendor bill','Validate an invoice tax calculation','Review the purchase invoice','Record the incoming supplier bill','Match an invoice to goods received','Investigate a billing discrepancy','Submit an invoice for processing'],
 'supplier_management': ['Update the supplier directory','Register a new vendor','Review supplier qualification','Maintain vendor contact information','Assess supplier performance','Change the supplier address','Renew a vendor contract','Check supplier compliance documents','Manage the approved vendor list','Evaluate a supplier relationship'],
 'payment_approval': ['Approve the pending payment','Authorize a vendor transfer','Review a disbursement request','Sign off the payment batch','Release a scheduled payment','Check a payment authorization','Approve the outgoing bank transfer','Confirm payment release permission','Review the treasury payout','Authorize settlement of a bill'],
 'customer_support': ['Help the customer with a login problem','Investigate a customer complaint','Resolve a support ticket','Answer a client service question','Assist a user with account access','Respond to a customer issue','Escalate the customer support case','Troubleshoot a client portal error','Handle the service desk request','Follow up on an unresolved customer ticket'],
 },
 'email_classification': {
 'complaint': ['I am unhappy with your poor service','I want to complain about the damaged delivery','Your service was unacceptable','I am disappointed with the repeated delays','Please escalate my complaint','The product arrived broken and I am upset','This quality is unacceptable and needs investigation','I am dissatisfied with the customer experience','Your team ignored my complaint','I wish to report terrible service'],
 'refund': ['Please refund my payment','I would like my money back','Cancel my order and issue a refund','When will the refund reach my bank','Please reimburse the duplicate charge','I request a full refund','Return the money for my cancelled order','Could you process my reimbursement','I need the refund status','Please reverse the charge and refund me'],
 'invoice_inquiry': ['Please send a copy of the invoice','What is the invoice due date','Can you explain this invoice tax','I have a question about bill number','The invoice total needs clarification','Please confirm the billing amount','Where can I download my invoice','Could you correct the invoice address','Is the attached bill already paid','I need an invoice breakdown'],
 'supplier_communication': ['We are your supplier confirming shipment','Our vendor contract is ready for renewal','Please find our supplier quotation','We can supply the requested materials','Our manufacturing delivery schedule is attached','Please update our vendor bank information','We confirm your purchase order as supplier','Our procurement quotation has been revised','Our supplier certification is attached','We propose new vendor delivery terms'],
 'general_support': ['How do I reset my password','Can you help me access the portal','Where can I find your opening hours','Please help me update my account','I need assistance using your website','How can I contact technical support','Can you explain how this service works','I cannot sign into my account','Please guide me through the setup','I need help with the application'],
 }}


def folder(name):
    if name not in NAMES:
        raise ValueError('Unknown local model')
    return ROOT / 'models' / name


def normalize(text):
    return ' '.join(str(text).lower().split())


def prepare(name, records):
    if name in TEXTS:
        texts = [normalize(row['text']) for row in records]
        if any(not text or len(text)>5000 for text in texts):
            raise ValueError('Text must contain 1–5000 characters')
        return texts
    fields=NUMERIC[name]
    frame=pd.DataFrame([{field:float(row[field]) for field in fields} for row in records])
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError('All numeric features must be finite')
    if (frame['invoice_amount' if name=='invoice_discrepancy' else 'amount']<0).any():
        raise ValueError('Amount must be nonnegative')
    if name=='invoice_discrepancy':
        if (frame.po_amount<=0).any() or ((frame.supplier_incident_rate<0)|(frame.supplier_incident_rate>1)).any():
            raise ValueError('PO amount must be positive; incident rate must be in [0,1]')
        frame['amount_difference_ratio']=(frame.invoice_amount-frame.po_amount)/frame.po_amount
        categories=[row['supplier_tier'] for row in records]
        if any(value not in ['established','new','restricted'] for value in categories):
            raise ValueError('Unknown supplier tier')
        frame['supplier_tier']=categories
    elif ((frame.hour<0)|(frame.hour>23)|(frame.account_age_days<0)|(frame.daily_count<0)|~frame.international.isin([0,1])).any():
        raise ValueError('Invalid transaction feature range')
    return frame


def dataset(name, seed=42):
    rng=np.random.default_rng(seed)
    if name in TEXTS:
        train=[]; test=[]
        # Entire linguistic templates are held out, not random near-duplicate rows.
        for label,templates in TEXTS[name].items():
            for i,template in enumerate(templates):
                for company in ['Aster','Birch','Cedar','Dover','Elm','Fern']:
                    row={'text':f'{template} for {company} reference {int(rng.integers(100,999))}.','label':label,'template_group':f'{label}:{i}'}
                    (test if i>=8 else train).append(row)
        return train,test
    rows=[]
    for i in range(1600):
        if name=='invoice_discrepancy':
            po=float(rng.uniform(100,50000)); ratio=float(rng.normal(0,.045)); qty=int(rng.choice([0,0,0,-3,-1,1,2,5])); tax=float(rng.normal(0,15)); history=float(rng.beta(1,8)); tier=str(rng.choice(['established','new','restricted']))
            # Simulated adjudication with stochastic uncertainty, not real enterprise labels.
            risk=abs(ratio)>.025 or abs(qty)>1 or abs(tax)>25
            label=int(risk if rng.random()>.045 else not risk)
            rows.append(dict(invoice_amount=round(po*(1+ratio),2),po_amount=round(po,2),quantity_difference=qty,tax_difference=round(tax,2),supplier_incident_rate=history,supplier_tier=tier,label=label))
        else:
            anomalous=i>=1400
            rows.append(dict(amount=float(rng.lognormal(7 if not anomalous else 9, .6)),hour=int(rng.integers(8,19) if not anomalous else rng.choice([0,1,2,3,22,23])),account_age_days=float(rng.uniform(100,3000) if not anomalous else rng.uniform(1,40)),daily_count=int(rng.poisson(3) if not anomalous else rng.integers(15,50)),international=int(rng.random()<(.1 if not anomalous else .8)),label=int(anomalous)))
    if name=='transaction_anomaly':
        train,normal_test=train_test_split(rows[:1400],test_size=.25,random_state=seed)
        return train,normal_test+rows[1400:]
    return train_test_split(rows,test_size=.25,random_state=seed,stratify=[r['label'] for r in rows])


def evaluate(name, model, records):
    x=prepare(name,records); y=[r['label'] for r in records]
    if name=='transaction_anomaly':
        pred=(model.predict(x)==-1).astype(int)
        return {'roc_auc_synthetic_injections':roc_auc_score(y,-model.score_samples(x)), 'classification_report_at_fitted_threshold':classification_report(y,pred,output_dict=True,zero_division=0),'normal_false_positive_rate':float(np.mean(pred[np.array(y)==0]))}
    pred=model.predict(x)
    return {'accuracy':accuracy_score(y,pred),'macro_f1':f1_score(y,pred,average='macro'),'per_class':classification_report(y,pred,output_dict=True,zero_division=0),'confusion_matrix':confusion_matrix(y,pred,labels=model.classes_).tolist(),'classes':model.classes_.tolist()}


def train(name):
    target=folder(name); artifacts=target/'artifacts'; artifacts.mkdir(parents=True,exist_ok=True)
    train_rows,test_rows=dataset(name)
    if name in TEXTS:
        model=make_pipeline(TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True),LogisticRegression(max_iter=1200,class_weight='balanced',random_state=42))
    elif name=='invoice_discrepancy':
        columns=NUMERIC[name]+['amount_difference_ratio']
        model=make_pipeline(ColumnTransformer([('numbers','passthrough',columns),('category',OneHotEncoder(handle_unknown='ignore'),['supplier_tier'])]),RandomForestClassifier(n_estimators=160,min_samples_leaf=4,class_weight='balanced',random_state=42,n_jobs=1))
    else:
        model=make_pipeline(StandardScaler(),IsolationForest(n_estimators=160,contamination=.05,random_state=42,n_jobs=1))
    model.fit(prepare(name,train_rows),[row['label'] for row in train_rows] if name!='transaction_anomaly' else None)
    joblib.dump(model,artifacts/'model.joblib')
    # Evaluate a fresh reload, not the in-memory estimator.
    reloaded=joblib.load(artifacts/'model.joblib')
    metrics=evaluate(name,reloaded,test_rows)
    data={'train':train_rows,'test':test_rows}
    (target/'dataset.json').write_text(json.dumps(data,indent=2))
    report={'name':name,'version':VERSION,'provenance':'Synthetic showcase data generated locally; no customer records or real-world validation. Text templates authored for this showcase; numeric labels from simulated adjudication with noise; anomaly test includes deliberate synthetic injections.', 'split':'Held-out template groups (text); stratified independent rows (invoice); normal-only train with held-out normals + injections (anomaly)', 'train_count':len(train_rows),'test_count':len(test_rows),'seed':42,'metrics':metrics,'artifact_sha256':hashlib.sha256((artifacts/'model.joblib').read_bytes()).hexdigest(),'dataset_sha256':hashlib.sha256((target/'dataset.json').read_bytes()).hexdigest()}
    (artifacts/'report.json').write_text(json.dumps(report,indent=2))
    return report


class LocalModel:
    def __init__(self,name):
        self.name=name; self.path=folder(name)/'artifacts'; self.model=joblib.load(self.path/'model.joblib'); self.report=json.loads((self.path/'report.json').read_text())
        if hashlib.sha256((self.path/'model.joblib').read_bytes()).hexdigest()!=self.report['artifact_sha256']:
            raise ValueError('Artifact fingerprint mismatch')

    def predict(self,record):
        started=time.perf_counter(); x=prepare(self.name,[record])
        if self.name=='transaction_anomaly':
            flag=bool(self.model.predict(x)[0]==-1)
            result={'anomaly':flag,'raw_anomaly_score':float(self.model.score_samples(x)[0]),'decision_function':float(self.model.decision_function(x)[0]),'review_recommendation':'Review unusual transaction' if flag else 'No anomaly flagged; normal controls still apply','score_meaning':'Lower raw scores are more unusual; not a fraud probability'}
        else:
            probs=self.model.predict_proba(x)[0]; predicted=self.model.classes_[int(np.argmax(probs))]
            result={'prediction':str(predicted),'probabilities':{str(k):float(v) for k,v in zip(self.model.classes_,probs)},'model_score':float(max(probs)),'score_meaning':'Uncalibrated classifier probability; not a guarantee'}
            if self.name=='email_classification':
                result['recommended_routing']={'complaint':'Service escalation','refund':'Refund review','invoice_inquiry':'Accounts receivable','supplier_communication':'Procurement','general_support':'Support desk'}[str(predicted)]
        return {'component':'local_ml','model':self.name,'version':self.report['version'],'artifact_sha256':self.report['artifact_sha256'],'duration_ms':round((time.perf_counter()-started)*1000,3),'input_features':x if isinstance(x,list) else x.to_dict(orient='records'),'output':result}


if __name__=='__main__':
    for name in NAMES:
        print(json.dumps(train(name)))
