#!/usr/bin/env python3
"""Replay release results in a new copy, without undeclared working directories."""
import argparse,json,os,shutil,subprocess,sys,time
from pathlib import Path
from reproduce import verify_files
P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--context',required=True)
p.add_argument('--stages',default='main,reference,orphan,timing,impact,heartbeat,macros');a=p.parse_args()
verify_files()
if a.out.exists():raise SystemExit('Use a new output directory. Prior attempts must remain intact.')
out=a.out.resolve();A=out/'archive';shutil.copytree(P/'evidence/archive-20261126',A)
env=dict(os.environ,DOCKER_CONTEXT=a.context,IDREF_DOCKER_CONTEXT=a.context)
T=A/'testbed/exp';raw=A/'results/raw';logs=out/'logs';logs.mkdir();events=[]
def call(stage,args,extra=None):
 start=time.monotonic();e=dict(env,**(extra or {}));log=logs/(stage+'.log')
 with log.open('w') as f:r=subprocess.run(args,cwd=out,env=e,stdout=f,stderr=subprocess.STDOUT)
 events.append({'stage':stage,'command':[str(x) for x in args],'returncode':r.returncode,'elapsed_s':time.monotonic()-start,'log':str(log.relative_to(out))})
 (out/'commands.json').write_text(json.dumps(events,indent=2)+'\n')
 if r.returncode:raise SystemExit('Replay failed at '+stage+'. See '+str(log))
def py(stage,script,*args,extra=None):call(stage,[sys.executable,str(script),*[str(x) for x in args]],extra)
for stage in a.stages.split(','):
 if stage=='main':
  if not (raw/'main/main_mixed.jsonl').is_file():raise SystemExit('Final main campaign is not frozen in this release yet')
  py('main',T/'main_eval.py',raw/'main')
  py('main-reference',T/'idref_eval.py',raw/'main','--out',raw/'idref','--no-decode','--tag','main')
  py('main-yield',T/'main_yield.py',raw/'main',raw/'idref/main')
 elif stage=='reference':
  py('reference',T/'idref_eval.py',raw/'heldout',raw/'timing','--out',raw/'idref','--no-decode','--tag','release-reference')
  merged=json.loads((raw/'idref/idref_summary.json').read_text())
  new=json.loads((raw/'idref/idref_summary_release-reference.json').read_text())
  for key in list(merged):
   if key.startswith(('heldout.','timing.')):del merged[key]
  for k,v in new.items():
   if not k.startswith(('heldout.','timing.')):continue
   if isinstance(v,list) and len(v)==2:merged[k+'.lo'],merged[k+'.hi']=v
   elif not isinstance(v,(list,dict)):merged[k]=v
  (raw/'idref/idref_summary.json').write_text(json.dumps(merged,indent=1)+'\n')
 elif stage=='orphan':
  py('orphan',T/'orphan_eval.py',raw/'orphan',raw/'orphan-oai')
  py('orphan-wire',T/'wire_truth.py',raw/'orphan','--kind','orphan')
  py('orphan-reference',T/'orphan_ref_eval.py',raw/'orphan')
 elif stage=='timing':py('timing',T/'timing_eval.py',raw/'timing')
 elif stage=='impact':py('impact',T/'impact_eval.py',extra={'R5G_OUT':str(raw/'impact')})
 elif stage=='heartbeat':py('heartbeat',P/'testbed/c2/phase_eval.py',A/'historical-artifact/results/real/campaign2/phase','--out',out/'heartbeat-event-audit.csv')
 elif stage=='macros':
  required=[raw/'main/main_summary.json',raw/'main/main_yield.json',raw/'idref/idref_summary_main.json']
  missing=[str(x.relative_to(A)) for x in required if not x.is_file()]
  if missing:raise SystemExit('Incomplete headline inputs: '+', '.join(missing))
  py('macros-rev25',A/'paper/gen_macros.py',A,out/'generated-rev25')
  py('macros-rev26',A/'paper/gen_macros_rev26.py',A,out/'generated-rev26')
 else:raise SystemExit('Unknown stage '+stage)
print('Replayed into',out)
