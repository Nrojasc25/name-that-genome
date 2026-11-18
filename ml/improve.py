"""Training-only diagnostic study; never overwrite the deployed candidate or open holdouts."""
from collections import defaultdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier

from .calibration import summarize
from .dataset_io import digest, write_json
from .labels import CLASS_ORDER
from .preprocessing import TrainingPreprocessor
from .train import read_training_inputs, environment_lock

CONFIG = Path(__file__).parent/'config/improvement.json'
GATES = Path(__file__).parent/'config/evaluation.json'


def sample_weights(labels, candidate):
    labels = np.asarray(labels)
    factor = candidate['likely_pathogenic_weight']
    if not np.isfinite(factor) or factor <= 0:
        raise ValueError('Class multiplier must be positive and finite')
    weights = compute_sample_weight('balanced', labels) if candidate['balanced'] else np.ones(len(labels))
    weights[labels == CLASS_ORDER.index('likely_pathogenic')] *= factor
    # Preserve weighting scale for tree regularization; proportions still change.
    return weights / weights.mean()


def feature_collisions(matrix, labels):
    groups = defaultdict(lambda: np.zeros(5, dtype=int))
    for row, label in zip(matrix, labels, strict=True):
        groups[tuple(row)][label] += 1
    ambiguous = [v for v in groups.values() if np.count_nonzero(v) > 1]
    total = sum(v.sum() for v in groups.values())
    return {'rows': int(total), 'distinct_vectors': len(groups), 'conflicting_vector_groups': len(ambiguous),
            'rows_in_conflicting_groups': int(sum(v.sum() for v in ambiguous)),
            'empirical_maximum_deterministic_accuracy': float(sum(v.max() for v in groups.values()) / total),
            'likely_pathogenic_rows_in_conflicting_groups': int(sum(v[3] for v in ambiguous)),
            'note': 'Training-only feature-equivalence diagnostic after training imputation. Maximum accuracy is an optimistic empirical ceiling for a deterministic classifier on these exact rows/features, not a held-out performance bound. Different variants can share features without sharing biology.'}


def discrimination_gates(summary, baseline_logistic, baseline_dummy, criteria):
    return {'macro_f1': summary['macro_f1'] >= criteria['minimum_macro_f1'],
            'logistic_comparison': summary['macro_f1'] - baseline_logistic >= criteria['minimum_macro_f1_improvement_over_logistic'],
            'dummy_comparison': summary['macro_f1'] - baseline_dummy >= criteria['minimum_macro_f1_improvement_over_dummy'],
            **{'recall_'+str(c): summary['per_class'][c]['recall'] >= criteria['minimum_recall_each_class'] for c in CLASS_ORDER},
            **{k: v['rate'] is not None and v['rate'] <= criteria['maximum_severe_confusion_each_direction'] for k,v in summary['severe_confusion'].items()}}


def select(experiments):
    eligible = [e for e in experiments if all(e['discrimination_gates'].values())]
    if not eligible:
        return None
    return min(eligible, key=lambda e: (-e['mean_fold_macro_f1'],e['mean_fold_log_loss'],e['candidate']['id']))


def extend_features(extra, fit_keys, score_keys):
    names=['phylop100way_snv','phylop100way_snv_missing']
    for key in set(fit_keys) | set(score_keys):
        row=extra[key]
        if set(row)!=set(names): raise ValueError('Unexpected enrichment columns')
        value=row[names[0]]
        if value is not None and not np.isfinite(value): raise ValueError('Nonfinite enrichment')
        if row[names[1]] != float(value is None): raise ValueError('Incorrect missingness indicator')
    observed=[extra[k][names[0]] for k in fit_keys if extra[k][names[0]] is not None]
    fill=float(np.median(observed)) if observed else 0.0
    def matrix(keys):
        return np.array([[fill if extra[k][names[0]] is None else extra[k][names[0]],extra[k][names[1]]] for k in keys])
    return matrix(fit_keys),matrix(score_keys),fill


def run(dataset, features, splits, baseline, output, config_path=CONFIG, enrichment=None):
    if output.exists():
        raise FileExistsError('Preserve previous studies; choose a new versioned directory')
    config=json.loads(config_path.read_text())
    protocol=json.loads((splits/'split_manifest.json').read_text())['config']
    vectors,targets,fold_ids,inputs=read_training_inputs(dataset,features,splits,protocol)
    manifest=json.loads((baseline/'model_manifest.json').read_text())
    if manifest['split_id'] != inputs['splits']['split_id'] or manifest['feature_manifest_sha256'] != digest(features/'feature_manifest.json'):
        raise ValueError('Baseline belongs to different inputs')
    for name in ['training_report.json','training_oof.parquet']:
        if digest(baseline/name) != manifest['outputs_sha256'][name]:
            raise ValueError('Baseline checksum mismatch')
    old=json.loads((baseline/'training_report.json').read_text())
    logistic=max((e for e in old['experiments'] if e['candidate']['algorithm']=='logistic'), key=lambda e:e['cv_mean_macro_f1'])
    dummy=next(e for e in old['experiments'] if e['candidate']['algorithm']=='dummy')
    criteria=json.loads(GATES.read_text())['acceptance']
    keys=sorted(vectors); y=np.array([targets[k] for k in keys]); annotation=inputs['features']['annotation_version']
    extra=None
    if bool(config.get('extra_features')) != bool(enrichment):
        raise ValueError('Enrichment must be explicitly declared in the protocol')
    if enrichment:
        extra_manifest=json.loads((enrichment/'conservation_manifest.json').read_text())
        if extra_manifest['split_manifest_sha256']!=digest(splits/'split_manifest.json') or extra_manifest['partition']!='train':
            raise ValueError('Enrichment partition mismatch')
        if digest(enrichment/'features.json')!=extra_manifest['features_sha256']:
            raise ValueError('Enrichment checksum mismatch')
        extra=json.loads((enrichment/'features.json').read_text())
        if set(extra)!=set(keys): raise ValueError('Enrichment must contain exactly training keys')
    processor=TrainingPreprocessor.fit(vectors,training_keys=keys,annotation_version=annotation)
    collision=feature_collisions(np.asarray(processor.transform([vectors[k] for k in keys])),y)
    enriched_collision=None
    if extra:
        full_extra,_,_=extend_features(extra,keys,keys)
        enriched_collision=feature_collisions(np.column_stack([processor.transform([vectors[k] for k in keys]),full_extra]),y)
    prepared=[]
    for fold in range(protocol['cv_folds']):
        train=[k for k in keys if fold_ids[k]!=fold]; score=[k for k in keys if fold_ids[k]==fold]
        pre=TrainingPreprocessor.fit(vectors,training_keys=train,annotation_version=annotation)
        prepared.append((train,score,np.asarray(pre.transform([vectors[k] for k in train])),np.asarray(pre.transform([vectors[k] for k in score]))))
    enriched_folds=[extend_features(extra,train,score) for train,score,_,_ in prepared] if extra else None
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.improvement-',dir=output.parent) as temp, threadpool_limits(limits=2):
        dest=Path(temp)
        write_json(dest/'protocol.json',config)
        experiments=[]; predictions=[]
        for candidate in config['candidates']:
            print('Training',candidate['id'],flush=True)
            oof={}; folds=[]
            for f,(train,score,x,z) in enumerate(prepared):
                train_y=np.array([targets[k] for k in train])
                if extra and candidate['id']!='baseline-replay':
                    x=np.column_stack([x,enriched_folds[f][0]])
                    z=np.column_stack([z,enriched_folds[f][1]])
                model=XGBClassifier(objective='multi:softprob',num_class=5,eval_metric='mlogloss',tree_method='hist',n_jobs=2,
                                    random_state=config['seed']+f,learning_rate=.08,subsample=1.,colsample_bytree=1.,
                                    max_depth=candidate['depth'],n_estimators=candidate['trees'])
                model.fit(x,train_y,sample_weight=sample_weights(train_y,candidate))
                if not np.array_equal(model.classes_,np.arange(5)):
                    raise ValueError('Class-order mismatch')
                p=model.predict_proba(z)
                oof.update(zip(score,p.tolist(),strict=True))
                folds.append(summarize(np.array([targets[k] for k in score]),p,include_curves=False))
            if set(oof)!=set(keys): raise ValueError('Incomplete OOF predictions')
            scores=np.asarray([oof[k] for k in keys]); summary=summarize(y,scores)
            item={'candidate':candidate,'oof':summary,'folds':folds,
                  'mean_fold_macro_f1':float(np.mean([m['macro_f1'] for m in folds])),
                  'mean_fold_log_loss':float(np.mean([m['log_loss'] for m in folds])),
                  'discrimination_gates':discrimination_gates(summary,logistic['oof_metrics']['macro_f1'],dummy['oof_metrics']['macro_f1'],criteria)}
            experiments.append(item)
            predictions.extend({'candidate_id':candidate['id'],'variant_key':k,'class_scores':oof[k]} for k in keys)
            print(f"  macro-F1 {summary['macro_f1']:.4f}; LP recall {summary['per_class']['likely_pathogenic']['recall']:.4f}; eligible {all(item['discrimination_gates'].values())}",flush=True)
        selected=select(experiments)
        # Baseline replay must match historical training OOF, not just aggregate scores.
        old_rows=pq.read_table(baseline/'training_oof.parquet',filters=[('candidate_id','=',old['selected_candidate'])]).to_pylist()
        old_map={r['variant_key']:r['class_scores'] for r in old_rows}
        replay=[r for r in predictions if r['candidate_id']=='baseline-replay']
        if not replay or any(not np.array_equal(r['class_scores'],old_map[r['variant_key']]) for r in replay):
            raise ValueError('Baseline replay changed; investigate before interpreting improvement')
        pq.write_table(pa.Table.from_pylist(predictions),dest/'training_oof.parquet',compression='zstd')
        report={'study_version':config['study_version'],'training_rows':len(keys),'feature_collisions':collision,'enriched_feature_collisions':enriched_collision,
                'enrichment_manifest_sha256':digest(enrichment/'conservation_manifest.json') if extra else None,
                'enrichment_fold_imputation':[f[2] for f in enriched_folds] if extra else None,'experiments':experiments,
                'selected_candidate':selected['candidate']['id'] if selected else None,'release_approved':False,
                'heldout_labels_loaded':False,'baseline_replay_identical':True,
                'interpretation':'Post-v1-failure development study; training OOF used for selection, not unbiased release evidence. No new calibration/confidence policy or deployment.',
                'gates_sha256':digest(GATES),'protocol_sha256':digest(config_path),
                'baseline_logistic_oof_macro_f1':logistic['oof_metrics']['macro_f1'],
                'next_step':'Fresh independent holdout and validation policy required before promotion; if none eligible, improve feature/data coverage before further tuning.'}
        write_json(dest/'improvement_report.json',report)
        lines=['# Phase 5 model-improvement study','',report['interpretation'],'',
               f"Training rows: {len(keys):,}. Baseline replay matches the original OOF predictions exactly.",
               f"Selected candidate: **{report['selected_candidate'] or 'none — no candidate passes discrimination gates'}**. Release approved: **no**.",'',
               '| Candidate | Macro-F1 | Benign recall | Likely benign recall | Uncertain recall | Likely pathogenic recall | Pathogenic recall | P/LP → B/LB | Eligible |',
               '|---|---:|---:|---:|---:|---:|---:|---:|---|']
        for e in experiments:
            m=e['oof']; recalls=' | '.join(f"{m['per_class'][c]['recall']:.3f}" for c in CLASS_ORDER)
            lines.append(f"| {e['candidate']['id']} | {m['macro_f1']:.4f} | {recalls} | {m['severe_confusion']['pathogenic_to_benign']['rate']:.3%} | {all(e['discrimination_gates'].values())} |")
        lines+=['','## Feature sufficiency','',f"{collision['distinct_vectors']:,} distinct feature vectors among {len(keys):,} training variants. {collision['rows_in_conflicting_groups']:,} rows belong to identical-vector groups with conflicting labels; {collision['likely_pathogenic_rows_in_conflicting_groups']:,} are Likely pathogenic.",
                f"Optimistic empirical deterministic accuracy ceiling on these training vectors: {collision['empirical_maximum_deterministic_accuracy']:.2%}.",collision['note'],'',
                '## Decision','',report['next_step'],
                'Acceptance thresholds and the active API model are unchanged. Increasing Likely pathogenic training weight is not calibration and cannot be assumed to improve all classes. See JSON for every class, fold, severe-error direction, distribution metric, and failed gate. Confidence/calibration/latency gates have not been reassessed in this study.']
        if enriched_collision:
            lines += ['', '## Conservation experiment', '',
                      f"Extra features: SNV phyloP100way and its missingness indicator. Fold medians use fit rows only. Enriched vectors: {enriched_collision['distinct_vectors']:,}; conflicting rows: {enriched_collision['rows_in_conflicting_groups']:,}; empirical deterministic accuracy ceiling: {enriched_collision['empirical_maximum_deterministic_accuracy']:.2%}.",
                      'Baseline replay uses the original 42 features; all other candidates use the two additional experimental columns. These columns are not deployed or claimed compatible with the existing serving schema.']
        (dest/'improvement_report.md').write_text('\n'.join(lines)+'\n')
        (dest/'environment-lock.txt').write_text('\n'.join(environment_lock())+'\n')
        write_json(dest/'study_manifest.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'protocol':config,'protocol_sha256':digest(config_path),
                  'code_sha256':{n:digest(Path(__file__).with_name(n)) for n in ['improve.py','train.py','preprocessing.py','calibration.py']},
                  'input_sha256':{'dataset_manifest':digest(dataset/'dataset_manifest.json'),'feature_manifest':digest(features/'feature_manifest.json'),
                                  'split_manifest':digest(splits/'split_manifest.json'),'baseline_manifest':digest(baseline/'model_manifest.json')},
                  'outputs_sha256':{p.name:digest(p) for p in dest.iterdir()}})
        dest.replace(output)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['dataset','features','splits','baseline','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--config',type=Path,default=CONFIG)
    parser.add_argument('--enrichment',type=Path)
    args=parser.parse_args()
    result=run(args.dataset,args.features,args.splits,args.baseline,args.output,args.config,args.enrichment)
    print(json.dumps({'selected_candidate':result['selected_candidate'],'release_approved':False}))


if __name__=='__main__': main()
