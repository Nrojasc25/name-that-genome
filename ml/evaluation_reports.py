"""Diagnostics and plots generated from saved predictions; no fitting or model selection."""

from collections import defaultdict
from pathlib import Path
import os
import tempfile
import warnings

import numpy as np
from sklearn.metrics import f1_score

from .calibration import summarize
from .labels import CLASS_ORDER


def bootstrap(labels, scores, groups, config):
    grouped = defaultdict(list)
    for i,group in enumerate(groups): grouped[group].append(i)
    if len(grouped) > 1:
        units = [np.array(indices) for _,indices in sorted(grouped.items())]
        method = 'Connected-gene cluster bootstrap; few clusters limit precision.'
    else:
        units = [np.array([i]) for i in range(len(labels))]
        method = 'Canonical-variant bootstrap conditional on this one held-out gene component; not uncertainty across unseen genes.'
    rng = np.random.default_rng(config['seed'])
    samples = defaultdict(list)
    for _ in range(config['bootstrap_replicates']):
        indices = np.concatenate([units[i] for i in rng.integers(0,len(units),len(units))])
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore',message='y_pred contains classes not in y_true')
            result = summarize(labels[indices],scores[indices],include_curves=False)
        for key in ['macro_f1','balanced_accuracy','log_loss','multiclass_brier']:
            samples[key].append(result[key])
        for c,name in enumerate(CLASS_ORDER):
            if np.any(labels[indices] == c):
                samples['recall_' + str(name)].append(result['per_class'][name]['recall'])
    alpha = (1 - config['bootstrap_confidence']) / 2
    return {'method':method,'connected_gene_components':len(grouped),'replicates':config['bootstrap_replicates'],
            'intervals':{key:{'lower':float(np.quantile(values,alpha)),'upper':float(np.quantile(values,1-alpha)),'valid_replicates':len(values)} for key,values in samples.items()},
            'note':'Percentile intervals conditional on a fixed selected model and protocol; do not include model-selection uncertainty.'}


def subgroups(partition, scores, stars):
    masks = {}
    types = sorted({r['variant_type'] for r in partition['metadata']})
    for kind in types:
        masks['variant_type:' + kind] = np.array([r['variant_type'] == kind for r in partition['metadata']])
    terms = sorted({term for r in partition['metadata'] for term in r['consequences']})
    for term in terms:
        masks['consequence:' + term] = np.array([term in r['consequences'] for r in partition['metadata']])
    missing = np.array([all(row[name + '_missing'] == 1 for name in ['af_esp','af_exac','af_tgp']) for row in partition['raw']])
    masks['population:all_missing'],masks['population:some_observed'] = missing,~missing
    masks['review:at_least_two_stars'] = np.array([s is not None and s >= 2 for s in stars])
    masks['review:below_two_stars'] = ~masks['review:at_least_two_stars']
    result = {}
    for name,mask in masks.items():
        count = int(mask.sum())
        if not count: continue
        y,p = partition['labels'][mask],scores[mask]
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore',message='y_pred contains classes not in y_true')
            item = summarize(y,p,include_curves=False)
        present = sorted(set(y.tolist()))
        result[name] = {'count':count,'macro_f1_present_classes':float(f1_score(y,p.argmax(axis=1),labels=present,average='macro',zero_division=0)),
                        'accuracy':item['accuracy'],'log_loss':item['log_loss'],'multiclass_brier':item['multiclass_brier'],
                        'class_support':{str(c):int(np.sum(y == i)) for i,c in enumerate(CLASS_ORDER)},
                        'per_class_recall':{str(c):item['per_class'][c]['recall'] if i in present else None for i,c in enumerate(CLASS_ORDER)},
                        'small_sample':count < 30}
    return {'groups':result,'note':'Consequence groups overlap; do not add their counts. Missing classes have null recall. Small groups are descriptive only.'}


def error_examples(partition,scores,limit=10):
    groups = defaultdict(list)
    for i,(truth,prediction) in enumerate(zip(partition['labels'],scores.argmax(axis=1),strict=True)):
        if truth == prediction: continue
        if truth in (0,1) and prediction in (3,4): category='benign_to_pathogenic'
        elif truth in (3,4) and prediction in (0,1): category='pathogenic_to_benign'
        elif truth == 2 or prediction == 2: category='uncertain_confusion'
        else: category='likely_vs_definite'
        row=partition['metadata'][i]
        groups[category].append({'variant_key':row['variant_key'],'clinvar_variation_ids':row['clinvar_variation_ids'],
                                'true_label':str(CLASS_ORDER[truth]),'predicted_label':str(CLASS_ORDER[prediction]),
                                'top_score':float(scores[i,prediction]),'variant_type':row['variant_type'],'consequences':row['consequences']})
    return {name:sorted(rows,key=lambda r:(-r['top_score'],r['variant_key']))[:limit] for name,rows in sorted(groups.items())}


def render_plots(report,output:Path):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir()) / 'ntg-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for partition,entry in report['partitions'].items():
        selected=entry['selected']
        fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
        labels=['Benign','Likely benign','Uncertain','Likely pathogenic','Pathogenic']
        for ax,values,title in zip(axes,[selected['confusion_matrix'],selected['row_normalized_confusion_matrix']],['Counts','Fraction of each true class']):
            values=np.asarray(values)
            ax.imshow(values,cmap='Blues',vmin=0,vmax=None if title=='Counts' else 1)
            for i in range(5):
                for j in range(5):
                    text=str(int(values[i,j])) if title=='Counts' else f'{values[i,j]:.2f}'
                    ax.text(j,i,text,ha='center',va='center',color='white' if values[i,j] > values.max()*.55 else 'black',fontsize=9)
            ax.set_xticks(range(5),labels,rotation=35,ha='right');ax.set_yticks(range(5),labels)
            ax.set(xlabel='Predicted class',ylabel='ClinVar label',title=title)
        fig.suptitle(f'{partition.replace("_"," ").title()} - five-class confusion')
        fig.savefig(output / f'{partition}_confusion.png',dpi=150);plt.close(fig)
        fig,axes=plt.subplots(2,3,figsize=(12,7),layout='constrained')
        for name,ax in zip(CLASS_ORDER,axes.flat):
            ax.plot([0,1],[0,1],color='gray',linestyle='--',linewidth=1)
            for kind,color in [('raw','#9b5c1f'),('selected','#176b9a')]:
                bins=entry[kind]['reliability'][name]['bins']
                populated=[b for b in bins if b['count']]
                ax.plot([b['mean_probability'] for b in populated],[b['observed_fraction'] for b in populated],marker='o',label=kind,color=color,markersize=4)
            ax.set(xlim=(0,1),ylim=(0,1),title=str(name).replace('_',' ').title(),xlabel='Mean predicted membership',ylabel='Observed fraction')
        axes.flat[-1].axis('off')
        handles,legend_labels=axes.flat[0].get_legend_handles_labels()
        axes.flat[-1].legend(handles,legend_labels,loc='center')
        axes.flat[-1].text(.05,.2,'10 equal-width bins. Empty bins omitted.\nBin counts are in the JSON report.\nRaw and selected curves overlap if\ncalibration was rejected.',fontsize=10)
        fig.suptitle(f'{partition.replace("_"," ").title()} - per-class reliability')
        fig.savefig(output / f'{partition}_reliability.png',dpi=150);plt.close(fig)
