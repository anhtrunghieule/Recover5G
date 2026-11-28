#!/usr/bin/env python3
from pathlib import Path
import json,sys,os,collections,csv,statistics
W=Path(__file__).resolve().parents[1];os.environ.setdefault('DOCKER_CONTEXT','colima-r5g-reproduction');sys.path.insert(0,str(W/'audit/testbed'))
from exp.wire_truth import decode,wire_sessions,upf_log_timeline,upf_state_at
rows=[]
for p in sorted((W/'results').glob('growth-worker*/accumulation.jsonl')):
 for r in map(json.loads,p.read_text().splitlines()):
  row={k:r.get(k) for k in ['id','arm','chain','stack','error','elapsed_s']};row['cycles']=len(r['cycles']);row['service_cycles']=0
  for c in r['cycles']:
   a=c.get('after',{});row['service_cycles']+=int(all(a.get('dl_ok',{}).get(str(i)) and a.get('ul_ok',{}).get(str(i)) for i in [1,2]))
  if not r.get('error'):
   d,g=decode(str(p.parent/r['pcap']));wire=wire_sessions(d);log=upf_log_timeline(str(p.parent/r['logs']));row['wire_establishments']=sum(x[1]=='est' for x in wire);row['wire_deletions']=sum(x[1]=='del' for x in wire)
   row['per_cycle_extra_upf']=[x['after']['counts']['upf_sess']-x['after']['counts']['smf_sess'] for x in r['cycles']]
   row['final']=[]
   for s in r['final']:
    t=(s['t0']+s['t1'])/2+r['clock_offset_s'];known,live,logn=upf_state_at(t,wire,log)
    active={ip for u in s['ues'].values() for ip in u['sessions'].values()}
    row['final'].append({'offset_s':s['offset_s'],'known':known,'wire_live_sessions':len(live),'upf_log_count':logn,'metric_sessions':s['counts']['upf_sess'],'extra_identities':len([ip for ip in live.values() if ip not in active]),'active_ips':sorted(active),'live_identity_map':live,'service':all(s['dl_ok'].get(str(i)) and s['ul_ok'].get(str(i)) for i in [1,2])})
   def mem(s):
    try:return int(s['resources']['upf'].strip().splitlines()[-1])
    except (KeyError,ValueError):return None
   row['upf_cgroup_bytes_initial']=mem(r['initial']);row['upf_cgroup_bytes_final']=mem(r['final'][-1])
  rows.append(row)
S={'complete':len(rows)==15,'expected_chains':15,'chains':len(rows),'errors':sum(bool(r.get('error')) for r in rows),'arms':{}}
for arm in ['baseline','repair','control']:
 rs=[r for r in rows if r['arm']==arm];valid=[r for r in rs if not r.get('error')]
 S['arms'][arm]={'chains':len(rs),'valid_chains':len(valid),'cycles':sum(r['cycles'] for r in rs),'working_service_cycles':sum(r['service_cycles'] for r in rs),'final_extra_identities':[r['final'][-1]['extra_identities'] for r in valid],'wire_verified_final':sum(all(f['known'] and f['wire_live_sessions']==f['metric_sessions'] for f in r['final']) for r in valid),'working_service_at_both_final':sum(all(f['service'] for f in r['final']) for r in valid),'elapsed_s':sum(r['elapsed_s'] for r in rs),'upf_cgroup_change_bytes':[r['upf_cgroup_bytes_final']-r['upf_cgroup_bytes_initial'] for r in valid if r['upf_cgroup_bytes_initial'] is not None and r['upf_cgroup_bytes_final'] is not None]}
(W/'results/growth-scored.json').write_text(json.dumps(rows,indent=1));(W/'results/growth-summary.json').write_text(json.dumps(S,indent=1));print(json.dumps(S,indent=1))
if S['complete']:
 if S['errors']:raise SystemExit('Incomplete/error chains require explicit manuscript qualification')
 out=W/'generated-audit';out.mkdir(exist_ok=True)
 macros={'GrowthChains':5,'GrowthCycles':sum(x['cycles'] for x in S['arms'].values()),'GrowthWork':sum(x['working_service_cycles'] for x in S['arms'].values()),'GrowthBaselineExtra':','.join(map(str,S['arms']['baseline']['final_extra_identities'])),'GrowthHours':f"{sum(x['elapsed_s'] for x in S['arms'].values())/3600:.2f}"}
 for arm in ['baseline','repair','control']:
  rs=[r for r in rows if r['arm']==arm];m=arm.capitalize();macros['Growth'+m+'Final']=f"{min(r['final'][-1]['wire_live_sessions'] for r in rs)}";macros['Growth'+m+'Work']=f"{S['arms'][arm]['working_service_cycles']}/{S['arms'][arm]['cycles']}";macros['Growth'+m+'Verified']=f"{S['arms'][arm]['wire_verified_final']}/{len(rs)}"
 (out/'growth.tex').write_text('% Generated from growth-scored.json and growth-summary.json.\n'+''.join('\\newcommand{\\'+k+'}{'+str(v)+'}\n' for k,v in macros.items()))
 with (out/'growth.csv').open('w') as f:
  wr=csv.writer(f);wr.writerow(['macro','value','source']);wr.writerows((k,v,'experiments/revision-20261125-codex/results/growth-summary.json') for k,v in macros.items())
