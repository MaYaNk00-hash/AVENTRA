import numpy as np

def compute_macro_f05(gt_dict, pred_dict):
    """
    Compute macro-averaged F_0.5 score across all S1 entities.
    
    gt_dict: dict mapping s1_id -> set of true matched IDs (or empty set for singletons)
    pred_dict: dict mapping s1_id -> set of predicted matched IDs (or empty set)
    
    Formula:
    F_0.5 = (1.25 * Precision * Recall) / (0.25 * Precision + Recall)
    
    Special cases:
    - If True is empty and Pred is empty: score = 1.0 (correct singleton)
    - If True is empty and Pred is non-empty: score = 0.0 (false merge on singleton)
    - If True is non-empty and Pred is empty: score = 0.0 (missed all matches)
    - If Precision + Recall == 0: score = 0.0
    """
    scores = []
    
    for s1_id, true_set in gt_dict.items():
        pred_set = pred_dict.get(s1_id, set())
        
        len_true = len(true_set)
        len_pred = len(pred_set)
        
        if len_true == 0:
            if len_pred == 0:
                scores.append(1.0)
            else:
                scores.append(0.0)
        else:
            if len_pred == 0:
                scores.append(0.0)
            else:
                tp = len(true_set.intersection(pred_set))
                if tp == 0:
                    scores.append(0.0)
                else:
                    precision = tp / len_pred
                    recall = tp / len_true
                    denom = 0.25 * precision + recall
                    if denom > 0:
                        f05 = (1.25 * precision * recall) / denom
                        scores.append(f05)
                    else:
                        scores.append(0.0)
                        
    return float(np.mean(scores))

if __name__ == "__main__":
    # Test example from README:
    # Pred: [S2-00047, S2-00193, S3-00812]
    # Ground truth: [S2-00047, S3-00812]
    # Precision = 2/3, Recall = 1.0 -> F0.5 = 0.7142857...
    gt = {"S1-00001": {"S2-00047", "S3-00812"}}
    pred = {"S1-00001": {"S2-00047", "S2-00193", "S3-00812"}}
    print("Test calculation:", compute_macro_f05(gt, pred))
