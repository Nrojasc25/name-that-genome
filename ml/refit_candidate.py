"""Refit an eligible enriched study candidate on training rows only; never deploy it."""
import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier

from .dataset_io import digest, write_json
from .features import FEATURE_NAMES
from .improve import extend_features, sample_weights, select
from .labels import CLASS_ORDER
from .preprocessing import TrainingPreprocessor
from .train import read_training_inputs, environment_lock


def refit(dataset,features,splits,study,enrichment,output):
    if output.exists(): raise FileExistsError('Candidate output already exists')
    manifest=json.loads((study/'study_manifest.json').read_text())
    for name in ['improvement_report.json','protocol.json']:
        if digest(study/name)!=manifest['outputs_sha256'][name]: raise ValueError('Study checksum mismatch')
    report=json.loads((study/'improvement_report.json').read_text())
    chosen=select(report['experiments'])
    if not chosen or chosen['candidate']['id']!=report['selected_candidate']:
        raise ValueError('No eligible selected candidate')
    if digest(enrichment/'conservation_manifest.json')!=report['enrichment_manifest_sha256']:
        raise ValueError('Enrichment manifest mismatch')
    extra_manifest=json.loads((enrichment/'conservation_manifest.json').read_text())
    if digest(enrichment/'features.json')!=extra_manifest['features_sha256']:
        raise ValueError('Enrichment data mismatch')
    for name,path in [('dataset_manifest',dataset/'dataset_manifest.json'),('feature_manifest',features/'feature_manifest.json'),('split_manifest',splits/'split_manifest.json')]:
        if digest(path)!=manifest['input_sha256'][name]: raise ValueError('Input manifest mismatch')
    protocol=json.loads((splits/'split_manifest.json').read_text())['config']
    vectors,targets,_,inputs=read_training_inputs(dataset,features,splits,protocol)
    keys=sorted(vectors); extra=json.loads((enrichment/'features.json').read_text())
    if set(keys)!=set(extra): raise ValueError('Enrichment must contain exactly training rows')
    processor=TrainingPreprocessor.fit(vectors,training_keys=keys,annotation_version=inputs['features']['annotation_version'])
    extra_x,_,fill=extend_features(extra,keys,keys)
    x=np.column_stack([processor.transform([vectors[k] for k in keys]),extra_x]); y=np.array([targets[k] for k in keys])
    candidate=chosen['candidate']; config=json.loads((study/'protocol.json').read_text())
    model=XGBClassifier(objective='multi:softprob',num_class=5,eval_metric='mlogloss',tree_method='hist',n_jobs=2,
                        random_state=config['seed'],learning_rate=.08,subsample=1.,colsample_bytree=1.,max_depth=candidate['depth'],n_estimators=candidate['trees'])
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.candidate-',dir=output.parent) as temp, threadpool_limits(limits=2):
        directory=Path(temp)
        model.fit(x,y,sample_weight=sample_weights(y,candidate))
        if not np.array_equal(model.classes_,np.arange(5)): raise ValueError('Class order mismatch')
        model.save_model(directory/'model.ubj')
        loaded=XGBClassifier(n_jobs=2);loaded.load_model(directory/'model.ubj')
        probe=np.random.default_rng(config['seed']).choice(len(keys),min(512,len(keys)),replace=False)
        if not np.array_equal(model.predict_proba(x[probe]),loaded.predict_proba(x[probe])):
            raise ValueError('Reload changes outputs')
        processor.save(directory/'base_preprocessor.json')
        write_json(directory/'conservation_preprocessor.json',{'schema':'experimental-phylop-snv-v1','median':fill,
                    'training_keys_sha256':processor.artifact['training_keys_sha256'],'columns':['phylop100way_snv','phylop100way_snv_missing'],
                    'missing_policy':'Training-only median for absent or indel SNV score; explicit missing indicator retained.'})
        (directory/'environment-lock.txt').write_text('\n'.join(environment_lock())+'\n')
        write_json(directory/'candidate_manifest.json',{'candidate':candidate,'study_manifest_sha256':digest(study/'study_manifest.json'),
            'enrichment_manifest_sha256':digest(enrichment/'conservation_manifest.json'),'class_order':list(CLASS_ORDER),
            'feature_names':list(FEATURE_NAMES)+['phylop100way_snv','phylop100way_snv_missing'],'training_rows':len(keys),
            'training_keys_sha256':processor.artifact['training_keys_sha256'],'probability_kind':'uncalibrated',
            'status':'research_candidate_requires_validation_and_fresh_evaluation','release_approved':False,
            'serving_compatible':False,'reload_parity_rows':len(probe),
            'code_sha256':{name:digest(Path(__file__).with_name(name)) for name in ['refit_candidate.py','improve.py','conservation.py']},
            'outputs_sha256':{p.name:digest(p) for p in directory.iterdir()}})
        directory.replace(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['dataset','features','splits','study','enrichment','output']: parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();refit(args.dataset,args.features,args.splits,args.study,args.enrichment,args.output)
