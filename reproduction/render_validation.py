#!/usr/bin/env python3
"""Render the declared matched-method summary. Different alert targets remain explicit."""
import argparse,collections,csv,json,statistics
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',type=Path,required=True,help='Frozen validation results directory')
parser.add_argument('--out',type=Path,required=True,help='New output directory')
args=parser.parse_args()
root=args.input
if args.out.exists():raise SystemExit('Use a new output directory')
args.out.mkdir(parents=True)
out=args.out/'tab_fresh_validation.tex'
rows=list(csv.DictReader((root/'comparison-guarded/method-runs.csv').open()));rows=[r for r in rows if r['eligible']=='True']
n=len({r['attempt_id'] for r in rows});names={'liveness':'Liveness','counts':'Counts','identity':'Identity monitor','fixed':'Fixed windows','recovery':'Recovery-aware'}
summary={};lines=[];metrics={}
for m,name in names.items():
 rs=[r for r in rows if r['method']==m]
 alerts=[r for r in rs if r['first_alert_s']]
 uncertain=sum(r['status']=='unknown' for r in rs)
 lo=[float(r['decision_collection_start_s']) for r in alerts if r['decision_collection_start_s']]
 hi=[float(r['decision_collection_end_s']) for r in alerts if r['decision_collection_end_s']]
 times=[float(r['first_alert_s']) for r in alerts]
 bracket=(f'{statistics.median(times):.1f} use' if m=='liveness' and times else (f'{statistics.median(lo):.1f} to {statistics.median(hi):.1f}' if lo and hi else 'n/a'))
 lines.append(f'{name} & {len(alerts)}/{n} & {uncertain}/{n} & {bracket} \\\\')
 metrics['v26-'+m+'-alerts']=len(alerts);metrics['v26-'+m+'-unknown']=uncertain
 summary[m]={'runs':len(rs),'alerts':len(alerts),'unknown':uncertain,'median_alert_s':statistics.median(times) if times else None,'median_collection_interval_s':[statistics.median(lo),statistics.median(hi)] if lo and hi else None,'status':dict(collections.Counter(r['status'] for r in rs))}
text=r'''\begin{table}[t]
\centering
\caption{Matched checks on fresh runs, with method-specific alert targets.}
\label{tab:fresh-validation}\tabstyle
\begin{tabular}{lrrl}
\toprule
Check & Alerts & Unknown & Time (s) \\
\midrule
'''+ '\n'.join(lines)+r'''
\bottomrule
\end{tabular}
\end{table}
'''
out.write_text(text);(args.out/'matched-main-summary.json').write_text(json.dumps({'runs':n,'methods':summary,'expert_accuracy':'pending'},indent=2)+'\n')
print('Wrote',out,'from',n,'eligible runs')

metrics['v26-eligible']=n
manifest=json.loads((root/'cohort-manifest.json').read_text());metrics['v26-attempts']=manifest['attempted'];metrics['v26-excluded']=manifest['counts'].get('excluded',0)
rs={m:{r['attempt_id']:r for r in rows if r['method']==m} for m in names}
different=[]
for rid in rs['recovery']:
 a,b=rs['identity'][rid],rs['recovery'][rid]
 if a['status']!=b['status'] or bool(a['first_alert_s'])!=bool(b['first_alert_s']):different.append({'attempt_id':rid,'identity_status':a['status'],'recovery_status':b['status'],'identity_alert_s':a['first_alert_s'],'recovery_alert_s':b['first_alert_s'],'numeric_deadline':b.get('numeric_deadline_available'),'next_use':b.get('next_use')})
(args.out/'matched-method-differences.json').write_text(json.dumps(different,indent=2)+'\n')
metrics['v26-identity-recovery-differences']=len(different)
metrics['v26-numeric-runs']=sum(r.get('numeric_deadline_available')=='True' for r in rs['recovery'].values())
reg=json.loads((root/'multisession-control/summary.json').read_text())
for k,v in reg.items():
 if isinstance(v,int):metrics['v26-regression-'+k.replace('_','-')]=v
folder=args.out
(folder/'macros_validation.tex').write_text('% Generated from the final validation outputs. See macros_validation.json.\n'+''.join('\\expandafter\\def\\csname rx@'+k+'\\endcsname{'+str(v)+'}\n' for k,v in sorted(metrics.items())))
(folder/'macros_validation.json').write_text(json.dumps({'metrics':metrics,'sources':['results/comparison-guarded/method-runs.csv','results/cohort-manifest.json','results/multisession-control/summary.json'],'independent_expert_labels':'pending'},indent=2)+'\n')
