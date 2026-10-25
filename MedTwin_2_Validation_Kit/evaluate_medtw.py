#!/usr/bin/env python3
"""MedTwin 2.0 research-only evidence evaluator.

Evaluates *user-supplied, genuinely labeled predictions*; does not train models,
generate clinical predictions or claim performance from examples. Every output
is bound to the dataset, split, checkpoint and prediction-file metadata.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, brier_score_loss, confusion_matrix, mean_absolute_error,
    mean_squared_error, average_precision_score)


def load_csv(path, columns):
    frame = pd.read_csv(path)
    missing = [c for c in columns if c not in frame.columns]
    if missing: raise ValueError(f"Missing required columns in {path}: {missing}")
    if frame.empty: raise ValueError("No labeled evaluation rows supplied")
    return frame


def meta(args, n):
    return {'dataset': args.dataset, 'dataset_version': args.dataset_version,
            'evaluation_split': args.split, 'model_checkpoint': args.checkpoint,
            'prediction_source': str(Path(args.csv).resolve()), 'n_rows': n,
            'results_kind': 'computed_from_supplied_labeled_evidence',
            'medtw_accuracy_target': '>0.95 is an objective, not an assumed result'}


def ensure_eval_split(args):
    if args.split not in {'test', 'external_test'}:
        raise ValueError('Only fixed held-out test or external_test splits may be scored for publication.')
    if not args.dataset.strip() or not args.checkpoint.strip():
        raise ValueError('Dataset and immutable checkpoint identifier are required.')


def classification(args):
    df=load_csv(args.csv,['patient_id','y_true','score'])
    for col in ['y_true','score']:
        df[col] = pd.to_numeric(df[col], errors='raise')
    y=df.y_true.to_numpy();p=df.score.to_numpy()
    if not np.isin(y, [0,1]).all(): raise ValueError('Binary y_true must be 0 or 1')
    if not np.isfinite(p).all() or np.any((p<0)|(p>1)):
        raise ValueError('Scores must be finite positive-class probabilities in [0,1]')
    if df.patient_id.isna().any(): raise ValueError('Missing patient_id; leakage risk')
    if not 0 <= args.threshold <= 1: raise ValueError('threshold outside [0,1]')
    pred=(p>=args.threshold).astype(int)
    tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    acc=float(accuracy_score(y,pred));sens=tp/(tp+fn) if tp+fn else None
    spec=tn/(tn+fp) if tn+fp else None
    results={'task':'binary_classification','threshold':args.threshold,'accuracy':acc,
       'precision':float(precision_score(y,pred,zero_division=0)),
       'recall_sensitivity':sens,'specificity':spec,
       'f1':float(f1_score(y,pred,zero_division=0)),
       'balanced_accuracy':float(np.mean([v for v in [sens,spec] if v is not None])),
       'auroc':float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None,
       'average_precision':float(average_precision_score(y,p)) if y.sum()>0 else None,
       'brier_score':float(brier_score_loss(y,p)),
       'confusion_matrix':{'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)},
       'n_patients':int(df.patient_id.nunique()),
       'accuracy_strictly_gt_95_percent':bool(acc>.95)}
    return results,len(df)


def mask_array(path):
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(path)
    if p.suffix.lower()=='.npy': a=np.load(p,allow_pickle=False)
    else: a=np.asarray(Image.open(p))
    if a.ndim != 2: raise ValueError(f'Expected 2D mask, got {a.shape}: {p}')
    if not np.isin(np.unique(a),[0,1,255]).all():
        raise ValueError(f'Mask must be binary 0/1 or 0/255: {p}')
    return (a>0)


def segmentation(args):
    df=load_csv(args.csv,['patient_id','reference_mask','predicted_mask'])
    di=[];ious=[];empty=[]
    for _,row in df.iterrows():
        a=mask_array(row.reference_mask);b=mask_array(row.predicted_mask)
        if a.shape!=b.shape: raise ValueError(f'Mask shapes differ: {a.shape} vs {b.shape}')
        inter=int(np.logical_and(a,b).sum()); sa=int(a.sum());sb=int(b.sum());uni=int(np.logical_or(a,b).sum())
        # Prespecified convention: both empty -> Dice=1/IoU=1; one empty -> both 0.
        dice=2*inter/(sa+sb) if sa+sb>0 else 1.0
        iou=inter/uni if uni>0 else 1.0
        di.append(dice); ious.append(iou);empty.append(sa==0)
    return {'task':'binary_segmentation','mean_dice':float(np.mean(di)),
            'mean_iou':float(np.mean(ious)),'n_empty_reference_masks':int(sum(empty)),
            'n_nonempty_reference_masks':int(len(empty)-sum(empty)),
            'both_empty_convention':'Dice=1,IoU=1; must also report nonempty-only values',
            'mean_dice_nonempty_reference':float(np.mean([d for d,e in zip(di,empty) if not e])) if not all(empty) else None,
            'mean_iou_nonempty_reference':float(np.mean([d for d,e in zip(ious,empty) if not e])) if not all(empty) else None},len(df)


def forecasting(args):
    df=load_csv(args.csv,['patient_id','target','horizon','y_true','y_pred'])
    if df[['patient_id','target','horizon']].isna().any().any():raise ValueError('Missing target/patient/horizon')
    for c in ('y_true','y_pred'):df[c]=pd.to_numeric(df[c],errors='raise')
    if not np.isfinite(df[['y_true','y_pred']].to_numpy()).all():raise ValueError('Invalid numeric target')
    groups=[]
    for (target,horizon),s in df.groupby(['target','horizon']):
        y=s.y_true.to_numpy();p=s.y_pred.to_numpy()
        groups.append({'target':str(target),'horizon':str(horizon),'n':len(s),
            'n_patients':int(s.patient_id.nunique()),
            'MAE':float(mean_absolute_error(y,p)),
            'RMSE':float(np.sqrt(mean_squared_error(y,p)))})
    return {'task':'forecasting','per_target_and_horizon':groups,
            'note':'A legitimate chronological split and task-specific forecast target must be demonstrated separately'},len(df)


def lab_extraction(args):
    # Evaluation key: patient_id, source_id, analyte_code; one row per unique observation.
    df=load_csv(args.csv,['patient_id','source_id','analyte_code','reference_value',
                           'predicted_value','reference_unit','predicted_unit'])
    if df[['patient_id','source_id','analyte_code']].duplicated().any():
        raise ValueError('Duplicate observations. Disambiguate collection time/test method in source_id.')
    r=pd.to_numeric(df.reference_value,errors='coerce');p=pd.to_numeric(df.predicted_value,errors='coerce')
    observed=np.isfinite(r)&np.isfinite(p)
    units=(df.reference_unit.astype(str).str.strip().str.lower()==
           df.predicted_unit.astype(str).str.strip().str.lower())
    matches=observed&units&(np.abs(r-p)<=args.abs_tolerance)
    return {'task':'numeric_lab_extraction_on_pre_matched_observations',
        'value_and_unit_exact_match_rate_at_tolerance':float(matches.mean()),
        'extracted_numeric_rate':float(observed.mean()),
        'unit_match_rate':float(units.mean()),
        'tolerance_in_reference_units':args.abs_tolerance,
        'matched_correct':int(matches.sum()),
        'caveat':'Does not compute missed observations, false-positive extraction, document-level NER precision/recall, OCR error or medical correctness; requires independently annotated corpora.'},len(df)


def detection(args):
    try:
        from pycocotools.coco import COCO
        from pycocotools.cocoeval import COCOeval
    except ImportError as exc:
        raise RuntimeError('Install pycocotools to evaluate detection; never substitute classification accuracy for mAP.') from exc
    if not args.annotations:raise ValueError('COCO annotations JSON must be specified for detection')
    gt=COCO(args.annotations);dt=gt.loadRes(args.csv)
    ev=COCOeval(gt,dt,'bbox');ev.evaluate();ev.accumulate();ev.summarize()
    return {'task':'bbox_detection','coco_mAP_50_95':float(ev.stats[0]),
        'coco_AP_50':float(ev.stats[1]),'coco_AP_75':float(ev.stats[2]),
        'COCO_reference_annotations':str(args.annotations),
        'evaluation_protocol':'COCOeval bbox default IoU thresholds, area bins and max detections'}, len(gt.imgs)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('task',choices=['classification','segmentation','forecast','lab_extraction','detection'])
    ap.add_argument('--csv',required=True,help='Labeled prediction CSV, or COCO predictions JSON for detection')
    ap.add_argument('--dataset',required=True,help='Authentic dataset name')
    ap.add_argument('--dataset-version',required=True)
    ap.add_argument('--checkpoint',required=True,help='Frozen model checkpoint ID/hash')
    ap.add_argument('--split',choices=['test','external_test'],required=True)
    ap.add_argument('--threshold',type=float,default=0.5,help='Predeclared binary positive probability threshold')
    ap.add_argument('--abs-tolerance',type=float,default=0.0,help='Absolute lab-value tolerance after verified unit normalization')
    ap.add_argument('--annotations',help='COCO reference annotations JSON for detection')
    ap.add_argument('--output',help='Write JSON artifact, otherwise print JSON')
    args=ap.parse_args()
    try:
        ensure_eval_split(args)
        fn={'classification':classification,'segmentation':segmentation,'forecast':forecasting,
            'lab_extraction':lab_extraction,'detection':detection}[args.task]
        result,n=fn(args)
        report={**meta(args,n),**result}
        data=json.dumps(report,indent=2,allow_nan=False)
        if args.output:
            Path(args.output).parent.mkdir(parents=True,exist_ok=True)
            Path(args.output).write_text(data+'\n',encoding='utf-8')
        print(data)
    except (ValueError,RuntimeError,FileNotFoundError,KeyError) as e:
        print(f'EVALUATION FAILED (no result reported): {e}',file=sys.stderr)
        raise SystemExit(2)

if __name__=='__main__':main()
