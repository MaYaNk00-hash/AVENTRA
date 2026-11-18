from showcase.core import LocalModel, dataset
def test_saved_model_unseen_input():
    model=LocalModel("workflow_intent")
    _,test=dataset("workflow_intent",seed=983)
    result=model.predict(test[0])
    assert result["component"]=="local_ml"
    assert result["artifact_sha256"]
    assert result["duration_ms"]>=0
