"""Validation-only policy selection, one-time held-out scoring, and repeatable report rendering."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from threadpoolctl import threadpool_limits

from .calibration import (acceptance, choose_calibration, choose_confidence, confidence_summary,
                          fit_temperature, probabilities, standard_mask, summarize)
from .dataset_io import digest, write_json
from .evaluation_data import EvaluationInputs
from .evaluation_reports import bootstrap, error_examples, render_plots, subgroups
from .features import FEATURE_NAMES
from .labels import CLASS_ORDER
from .train import fit_model, make_model, selected_columns

CONFIG_PATH = Path(__file__).parent / 'config/evaluation.json'
CODE_FILES = ['evaluate.py','calibration.py','evaluation_data.py','evaluation_reports.py']


def key_digest(keys):
    return hashlib.sha256('\n'.join(sorted(keys)).encode()).hexdigest()


def code_fingerprints():
    return {name:digest(Path(__file__).with_name(name)) for name in CODE_FILES}


def calibrate(inputs,cache,output,config_path=CONFIG_PATH):
    if output.exists(): raise FileExistsError('Policy output exists; choose a fresh directory before test access')
    if (inputs.splits / 'evaluation_access.json').exists():
        raise ValueError('Holdouts already opened for this split. New policy tuning needs an explicit test-reuse/new-holdout study.')
    config=json.loads(config_path.read_text())
    validation=inputs.load_partition('validation')
    indices=np.arange(len(validation['keys']))
    fit,selection=train_test_split(indices,train_size=config['validation_calibration_fit_fraction'],stratify=validation['labels'],random_state=config['seed'])
    fit_keys=[validation['keys'][i] for i in fit];selection_keys=[validation['keys'][i] for i in selection]
    with threadpool_limits(limits=2):
        logits=inputs.logits(validation)
        temperature=fit_temperature(logits[fit],validation['labels'][fit],config['temperature_bounds'])
        calibration=choose_calibration(logits[selection],validation['labels'][selection],temperature,config)
        scores=probabilities(logits[selection],calibration['temperature'])
        confidence=choose_confidence(validation['labels'][selection],scores,config['confidence_selection'])
        latency=inputs.measure_latency(cache,fit_keys,calibration['temperature'],config)
        # Refit the best pre-existing logistic recipe on training rows only for fair held-out baselines.
        training=inputs.load_partition('train')
        training_report=json.loads((inputs.model_path / 'training_report.json').read_text())
        logistic_results=[r for r in training_report['experiments'] if r['candidate']['algorithm']=='logistic']
        best=min(logistic_results,key=lambda r:(-r['cv_mean_macro_f1'],r['cv_mean_log_loss'],r['candidate']['id']))['candidate']
        baseline=fit_model(make_model(best,inputs.model_manifest['config']['seed']),best,
                           training['full_matrix'][:,selected_columns(best)],training['labels'])
    policy={'schema_version':1,'protocol':config,'protocol_sha256':digest(config_path),'input_fingerprints':inputs.fingerprints,
            'evaluation_code_sha256':code_fingerprints(),'class_order':list(CLASS_ORDER),
            'model_name':inputs.model_manifest['model_name'],'model_version':inputs.model_manifest['model_version'],
            'calibration':calibration,'confidence_rule':confidence,'latency':latency,
            'selection_partitions':{'fit_count':len(fit),'selection_count':len(selection),'fit_keys_sha256':key_digest(fit_keys),'selection_keys_sha256':key_digest(selection_keys)},
            'logistic_candidate':best,'baseline_training_keys_sha256':key_digest(training['keys']),
            'dummy_prior':(np.bincount(training['labels'],minlength=5)/len(training['labels'])).tolist(),
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'holdouts_opened':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.calibration-',dir=output.parent) as temp:
        directory=Path(temp)
        joblib.dump(baseline,directory/'logistic_baseline.joblib')
        membership=[{'variant_key':validation['keys'][i],'partition':'calibration_fit' if i in set(fit) else 'policy_selection'} for i in indices]
        write_json(directory/'validation_membership.json',membership)
        policy['outputs_sha256']={p.name:digest(p) for p in directory.iterdir()}
        write_json(directory/'policy.json',policy)
        lines=['# Validation-only calibration and confidence selection','',
               f"Calibration fit rows: {len(fit)}. Separate policy-selection rows: {len(selection)}.",
               f"Fitted temperature: {temperature:.6f}. Retained: {calibration['accepted']}. Active temperature: {calibration['temperature']:.6f}.",
               f"Probability kind: {calibration['probability_kind']}. Confidence rule accepted: {confidence['accepted']}.",'',
               '## Calibration checks','']
        lines += [f'- {name}: {passed}' for name,passed in calibration['checks'].items()]
        lines += ['',f"Warm single-variant p95: {latency['p95_ms']:.3f} ms.",
                  'No test or gene-challenge predictions were read. Temperature scaling preserves argmax, so it cannot repair poor Likely pathogenic recall.',
                  'Calibration is retained only when the independent validation-selection subset passes all predeclared checks. The fitted temperature is not refitted afterward.',
                  'Low confidence is a separate flag. Every row retains its original five-class argmax prediction.']
        (directory/'validation_report.md').write_text('\n'.join(lines)+'\n')
        directory.replace(output)
    return policy


def reserve_holdouts(splits,output,policy_path,policy):
    ledger=splits/'evaluation_access.json'
    record={'state':'reserved_before_label_access','opened_at_utc':datetime.now(timezone.utc).isoformat(),
            'output':str(output.resolve()),'policy_path':str(policy_path.resolve()),'policy_sha256':digest(policy_path),
            'protocol_sha256':policy['protocol_sha256'],'input_fingerprints':policy['input_fingerprints']}
    # Exclusive creation applies across output directories, not just this run's destination.
    with ledger.open('x') as stream: json.dump(record,stream,indent=2)
    return ledger,record


def score_holdouts(inputs,policy_directory,output,config_path=CONFIG_PATH):
    if output.exists(): raise FileExistsError('Evaluation output exists; use render for saved predictions')
    policy_path=policy_directory/'policy.json'
    policy=json.loads(policy_path.read_text())
    if policy['protocol_sha256'] != digest(config_path) or policy['input_fingerprints'] != inputs.fingerprints:
        raise ValueError('Protocol or inputs changed after validation policy selection')
    if policy['evaluation_code_sha256'] != code_fingerprints():
        raise ValueError('Evaluation implementation changed after policy freeze')
    for name,checksum in policy['outputs_sha256'].items():
        if digest(policy_directory/name) != checksum: raise ValueError('Policy artifact checksum mismatch')
    ledger,access=reserve_holdouts(inputs.splits,output,policy_path,policy)
    output.mkdir(parents=True)
    write_json(output/'evaluation_policy.json',policy)
    baseline=joblib.load(policy_directory/'logistic_baseline.joblib')
    records=[]
    with threadpool_limits(limits=2):
        for name in ['test','gene_challenge']:
            partition=inputs.load_partition(name)
            logits=inputs.logits(partition)
            raw=probabilities(logits)
            selected=probabilities(logits,policy['calibration']['temperature'])
            logistic=baseline.predict_proba(partition['full_matrix'][:,selected_columns(policy['logistic_candidate'])])
            stars=inputs.review_stars(partition['metadata'])
            flags=standard_mask(selected,policy['confidence_rule'])
            for i,key in enumerate(partition['keys']):
                records.append({'partition':name,'variant_key':key,'label_id':int(partition['labels'][i]),
                                'gene_group':partition['groups'][i],'metadata':partition['metadata'][i],
                                'raw_features':partition['raw'][i],'review_stars':stars[i],
                                'raw_scores':raw[i].tolist(),'selected_scores':selected[i].tolist(),
                                'logistic_scores':logistic[i].tolist(),'dummy_scores':policy['dummy_prior'],
                                'decision':str(CLASS_ORDER[int(selected[i].argmax())]),'confidence_status':'standard' if flags[i] else 'low'})
    write_json(output/'heldout_predictions.json',records)
    access.update(state='predictions_saved',predictions_sha256=digest(output/'heldout_predictions.json'))
    write_json(ledger,access)
    write_json(output/'evaluation_manifest.json',{'policy_sha256':digest(output/'evaluation_policy.json'),
               'predictions_sha256':access['predictions_sha256'],'access_ledger':str(ledger),'test_reuse':False,
               'created_at_utc':datetime.now(timezone.utc).isoformat(),'code_sha256':code_fingerprints()})
    result=render(output)
    access['state']='complete';write_json(ledger,access)
    return result


def render(output):
    manifest=json.loads((output/'evaluation_manifest.json').read_text())
    if digest(output/'evaluation_policy.json')!=manifest['policy_sha256'] or digest(output/'heldout_predictions.json')!=manifest['predictions_sha256']:
        raise ValueError('Saved evaluation inputs were modified')
    policy=json.loads((output/'evaluation_policy.json').read_text())
    config=policy['protocol']
    rows=json.loads((output/'heldout_predictions.json').read_text())
    report={'protocol_version':config['protocol_version'],'protocol_sha256':policy['protocol_sha256'],
            'probability_kind':policy['calibration']['probability_kind'],'temperature':policy['calibration']['temperature'],
            'confidence_rule':policy['confidence_rule'],'latency':policy['latency'],'partitions':{},
            'threshold_source':'Frozen project engineering criteria, not clinical standards.',
            'test_reuse':False,'test_reuse_warning':config['test_reuse_policy']}
    for name in ['test','gene_challenge']:
        subset=[r for r in rows if r['partition']==name]
        labels=np.array([r['label_id'] for r in subset])
        scores={kind:np.array([r[kind+'_scores'] for r in subset]) for kind in ['raw','selected','dummy','logistic']}
        entry={kind:summarize(labels,p,config['reliability_bins']) for kind,p in scores.items()}
        partition={'keys':[r['variant_key'] for r in subset],'labels':labels,'metadata':[r['metadata'] for r in subset],
                   'raw':[r['raw_features'] for r in subset],'groups':[r['gene_group'] for r in subset]}
        entry['count']=len(subset)
        entry['confidence']=confidence_summary(labels,scores['selected'],policy['confidence_rule'])
        entry['bootstrap']=bootstrap(labels,scores['selected'],partition['groups'],config)
        entry['subgroups']=subgroups(partition,scores['selected'],[r['review_stars'] for r in subset])
        entry['error_examples']=error_examples(partition,scores['selected'])
        entry['gates']=acceptance(entry['selected'],entry['raw'],entry['dummy'],entry['logistic'],entry['confidence'],policy['latency'],config)
        entry['passes']=all(entry['gates'].values())
        report['partitions'][name]=entry
    required=['test','gene_challenge'] if config['acceptance']['require_gene_challenge_gates'] else ['test']
    report['release_approved']=all(report['partitions'][name]['passes'] for name in required)
    report['release_status']='accepted_by_project_gates' if report['release_approved'] else 'rejected_by_project_gates'
    write_json(output/'evaluation_report.json',report)
    lines=['# Phase 5 held-out evaluation','',f"Release status: **{report['release_status']}**.",'',
           'These are the first scores on the reserved test and connected-gene challenge for this frozen split. Future changes cannot treat these sets as untouched.',
           f"Calibration: {report['probability_kind']}; temperature {report['temperature']:.6f}. Low confidence is separate from the Uncertain class.",'',
           '| Partition | Rows | Macro-F1 | Balanced accuracy | Log loss | Brier (0-2) | Mean class ECE |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for name,entry in report['partitions'].items():
        m=entry['selected'];lines.append(f"| {name} | {entry['count']} | {m['macro_f1']:.4f} | {m['balanced_accuracy']:.4f} | {m['log_loss']:.4f} | {m['multiclass_brier']:.4f} | {m['mean_class_ece']:.4f} |")
    for name,entry in report['partitions'].items():
        lines += ['',f'## {name}: per-class results','', '| Class | Precision | Recall | F1 | AP | Prevalence | Support |','|---|---:|---:|---:|---:|---:|---:|']
        for label in CLASS_ORDER:
            m=entry['selected']['per_class'][label];ap=entry['selected']['one_vs_rest_average_precision'][label]
            lines.append(f"| {label} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1-score']:.4f} | {ap['average_precision']:.4f} | {ap['prevalence']:.4f} | {int(m['support'])} |")
        lines += ['', 'Per-gene results (macro-F1 over classes present; — means no examples):', '',
                  '| Gene | Rows | Macro-F1 | B recall | LB recall | VUS recall | LP recall | P recall |', '|---|---:|---:|---:|---:|---:|---:|---:|']
        for group, metrics in entry['subgroups']['groups'].items():
            if group.startswith('gene:'):
                recalls = ['—' if metrics['per_class_recall'][label] is None else f"{metrics['per_class_recall'][label]:.1%}" for label in CLASS_ORDER]
                lines.append(f"| {group[5:]} | {metrics['count']} | {metrics['macro_f1_present_classes']:.4f} | " + ' | '.join(recalls) + ' |')
        lines += ['',f"Baseline macro-F1: dummy {entry['dummy']['macro_f1']:.4f}; logistic {entry['logistic']['macro_f1']:.4f}.",
                  f"Standard-confidence coverage: {entry['confidence']['coverage']:.1%}; accuracy within that subset: {entry['confidence']['standard_accuracy']}.",'', 'Failed gates:']
        lines += ['- '+gate for gate,passed in entry['gates'].items() if not passed] or ['- None.']
        interval=entry['bootstrap']['intervals']['macro_f1']
        lines += ['',f"95% macro-F1 bootstrap interval: [{interval['lower']:.4f}, {interval['upper']:.4f}]. {entry['bootstrap']['method']}",
                  f"![{name} confusion]({name}_confusion.png)",f"![{name} reliability]({name}_reliability.png)"]
    lines += ['', '## Interpretation and next steps','',
              'Temperature scaling preserves argmax and does not repair class separation. Review Likely pathogenic recall and its confusion with Uncertain/Pathogenic before any model release.',
              'Acceptance gates use point estimates and are project criteria, not validated clinical standards. Bootstrap intervals do not account for model-selection uncertainty; the primary test has few gene clusters and the challenge contains only one connected gene group.',
              'The JSON report contains raw/calibrated comparisons, confusion matrices, reliability bin counts, per-class AP (non-interpolated PR area), intervals, subgroup coverage, severe errors, and concrete misclassified variants.',
              'Future model or feature changes require a new holdout or an explicitly documented reused-test study. Do not adjust these acceptance thresholds after seeing this report.',
              'Low-confidence flags do not suppress or change five-class decisions. Calibration acceptance is validation-based and is separate from release acceptance.']
    (output/'evaluation_report.md').write_text('\n'.join(lines)+'\n')
    render_plots(report,output)
    write_json(output/'render_manifest.json',{'evaluation_manifest_sha256':digest(output/'evaluation_manifest.json'),
               'code_sha256':code_fingerprints(),'outputs_sha256':{p.name:digest(p) for p in sorted(output.iterdir()) if p.name.endswith('.png') or p.name in ['evaluation_report.json','evaluation_report.md']}})
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['calibrate','final','render'])
    for name in ['dataset','features','splits','model','cache','policy']:
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=CONFIG_PATH)
    args=parser.parse_args()
    if args.action=='render': result=render(args.output)
    else:
        if not all([args.dataset,args.features,args.splits,args.model]): parser.error('dataset/features/splits/model are required')
        inputs=EvaluationInputs(args.dataset,args.features,args.splits,args.model)
        if args.action=='calibrate':
            if args.cache is None: parser.error('cache is required')
            result=calibrate(inputs,args.cache,args.output,args.config)
        else:
            if args.policy is None: parser.error('policy is required')
            result=score_holdouts(inputs,args.policy,args.output,args.config)
    print(json.dumps({'release_status':result.get('release_status'), 'calibration_accepted':result.get('calibration',{}).get('accepted')},indent=2))


if __name__=='__main__': main()
