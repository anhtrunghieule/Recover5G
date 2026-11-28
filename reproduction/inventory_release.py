#!/usr/bin/env python3
"""Join retained attempts to headline evaluators without upgrading legacy clock evidence."""
import argparse,collections,csv,hashlib,json,sys
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
A=a.archive.resolve();sys.path.insert(0,str(A/'testbed/exp'))
from hostsleep import host_sleep_s
if a.out.exists():raise SystemExit('Use a new output file')
hashes={}
def sha(f):
 if f not in hashes:hashes[f]=hashlib.sha256(f.read_bytes()).hexdigest()
 return hashes[f]
def csvrows(rel):
 with (A/rel).open() as f:return list(csv.DictReader(f))
def attempts(rels):
 rows=[]
 for rel in rels:
  f=A/rel
  for line,text in enumerate(f.read_text().splitlines(),1):
   r=json.loads(text);reasons=[]
   if r.get('error'):reasons.append('harness-error')
   if not r.get('error') and host_sleep_s(r)>0:reasons.append('host-sleep')
   pc=f.parent/r.get('pcap','__missing__')
   rows.append({'record':r,'manifest':{'run_id':r['id'],'source':rel,'source_sha256':sha(f),'line':line,
    'legacy_filter_eligible':not reasons,'reasons':reasons,'clock_evidence':'legacy-host-clock, no new guest-clock guarantee',
    'capture':str(pc.relative_to(A)) if pc.is_file() else None,'capture_sha256':sha(pc) if pc.is_file() else None,
    'scored_in_result':False,'expert_scored':False}})
 paths=collections.Counter(x['manifest']['capture'] for x in rows if x['manifest']['capture'])
 for x in rows:
  m=x['manifest'];m['capture_path_reused']=bool(m['capture'] and paths[m['capture']]>1)
 return rows
groups=[]
def finish(name,rows,outputs,unit='run'):
 ms=[x['manifest'] for x in rows]
 groups.append({'result':name,'unit':unit,'attempted':len(ms),'legacy_filter_eligible':sum(x['legacy_filter_eligible'] for x in ms),
  'scored_in_result':sum(x['scored_in_result'] for x in ms),'not_scored':sum(not x['scored_in_result'] for x in ms),
  'expert_scored':0,'outputs':[{'file':s,'sha256':sha(A/s)} for s in outputs],'attempts':ms})

mainfiles=['results/raw/main/main_mixed.jsonl','results/raw/main/main_amfsurv.jsonl']
rows=attempts(mainfiles);selected={}
for x in rows:
 if x['manifest']['legacy_filter_eligible']:selected[x['record']['id']]=x
scored={r['id'] for r in csvrows('results/raw/main/main_runs.csv')}
for rid,x in selected.items():x['manifest']['scored_in_result']=rid in scored
assert sum(x['manifest']['scored_in_result'] for x in rows)==len(scored)
finish('main placement and same-oracle comparison',rows,['results/raw/main/main_runs.csv','results/raw/main/main_summary.json'])

files=[str(f.relative_to(A)) for f in sorted((A/'results/raw/timing').glob('timing_*.jsonl'))]
rows=attempts(files);selected={};clean=set()
for x in rows:
 r=x['record'];cond=Path(x['manifest']['source']).stem.removeprefix('timing_');key=(cond,r['proc'],r['boundary'],r['nf'])
 # Exact legacy evaluator order: a sleep-overlapping attempt cannot replace an earlier clean attempt.
 if 'host-sleep' in x['manifest']['reasons'] and key in clean:continue
 if x['manifest']['legacy_filter_eligible']:clean.add(key)
 selected[key]=x
evaluated=csvrows('results/raw/timing/timing_runs.csv')
for r in evaluated:
 key=(r['cond'],r['proc'],r['boundary'],r['nf']);x=selected[key]
 x['manifest']['scored_in_result']=not bool(r['error'])
 x['manifest']['schedule_cell']=list(key)
assert sum(x['manifest']['scored_in_result'] for x in rows)==sum(not r['error'] for r in evaluated)
finish('matched delay schedules',rows,['results/raw/timing/timing_runs.csv','results/raw/timing/timing_summary.json'],'schedule attempt')

rows=attempts(['results/raw/orphan/orphan_repl.jsonl','results/raw/orphan-oai/orphan_oai.jsonl'])
evaluated=csvrows('results/raw/orphan/orphan_eval.csv')
scored={r['id'] for r in evaluated if not r['error'] and r['ran']!='UERANSIM, stock gNB not restarted'}
for x in rows:
 m=x['manifest'];r=x['record'];m['scored_in_result']=m['legacy_filter_eligible'] and r['id'] in scored
 if not m['scored_in_result'] and not m['reasons']:m['reasons'].append('pilot or non-recovering-RAN condition outside headline comparison')
assert sum(x['manifest']['scored_in_result'] for x in rows)==len(scored)
finish('flagship orphan repair across RAN conditions',rows,['results/raw/orphan/orphan_eval.csv','results/raw/orphan/orphan_summary.csv'])

rows=attempts(['results/raw/heldout/heldout.jsonl'])
scored={r['id'] for r in csvrows('results/raw/heldout/heldout_runs.csv')}
for x in rows:x['manifest']['scored_in_result']=x['manifest']['legacy_filter_eligible'] and x['record']['id'] in scored
assert sum(x['manifest']['scored_in_result'] for x in rows)==len(scored)
finish('sleep-filtered shared-readout reference cohort',rows,['results/raw/heldout/heldout_runs.csv','results/raw/heldout/heldout_summary.json'])

for name,raw,table,unit in [('capacity chains','impact_exhaust.jsonl','impact_exhaust_chains.csv','chain'),('address and tunnel reuse','impact_reuse.jsonl','impact_reuse_runs.csv','run')]:
 rows=attempts(['results/raw/impact/'+raw]);evaluated={r['id']:r for r in csvrows('results/raw/impact/'+table)}
 for x in rows:
  m=x['manifest'];e=evaluated[x['record']['id']];m['scored_in_result']=not bool(e['excluded'])
  if e['excluded']:m['reasons'].append(e['excluded'])
 finish(name,rows,['results/raw/impact/'+table,'results/raw/impact/impact_summary.json'],unit)

result={'scope':'Headline archived cohorts. Fresh validation has its own guest-clock cohort manifest.',
 'definition':'Scored means included in the named automated result. It does not mean independently adjudicated or necessarily reference-decidable.',
 'historical_readout_audit':'The unfiltered 1,489 snapshots are a separate historical audit, not this sleep-filtered cohort.',
 'capture_warning':'A reused path cannot guarantee retention of the earlier attempt capture. Source rows remain retained.',
 'groups':groups}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
print([(g['result'],g['attempted'],g['scored_in_result']) for g in groups])
