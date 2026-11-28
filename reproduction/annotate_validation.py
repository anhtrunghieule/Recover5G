#!/usr/bin/env python3
"""Mark packet activity during fresh state collections, without using reference verdicts."""
import argparse,concurrent.futures as cf,json,os,shutil,sys
from pathlib import Path
from reproduce import verify_files
from validation.workflow import records

P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--context',required=True);a=p.parse_args()
verify_files()
if a.out.exists():raise SystemExit('Use a new output directory')
os.environ['DOCKER_CONTEXT']=a.context;os.environ['IDREF_DOCKER_CONTEXT']=a.context
sys.path[:0]=[str(P/'testbed/exp'),str(P/'testbed')]
import idref_decode as D
import idref_runs as R
shutil.copytree(a.input,a.out);cache=a.out/'reference';cache.mkdir()
rows=list(records(a.input))
def one(item):
 r,src=item
 if r.get('error') or r.get('technical_validity',{}).get('status')!='valid':return r,src,None
 ref=R.judge_run(r,str(a.input),out=str(cache));ref.pop('model',None)
 dec=D.cached(str(a.input/r['pcap']),R.cache_path(str(cache),str(a.input),str(a.input/r['pcap'])))
 times=[x['t'] for x in dec['pfcp'] if x['type'] in range(50,58)]+[x['t'] for x in dec['ngap']]
 for x in dec['sbi']:
  if 'sm-context' in x['path'] or 'n1-n2-messages' in x['path']:
   times.append(x['t'])
   if x.get('t_rsp'):times.append(x['t_rsp'])
 for s in r.get('series',[]):
  cc=s.get('collection_clock')
  if cc:
   lo=cc['start']['wall']-cc['start']['rtt_s']-.3;hi=cc['end']['wall']+cc['end']['rtt_s']+.3
   s['changing']=any(lo<=t<=hi for t in times)
   s['activity_guard']={'start_wall':lo,'end_wall':hi,'source':'relevant packet activity only, no reference verdict'}
 return r,src,ref
with cf.ThreadPoolExecutor(max_workers=3) as ex:annotated=list(ex.map(one,rows))
files={}
for r,src,_ in annotated:files.setdefault(src['file'],[]).append(r)
for name,rs in files.items():
 with (a.out/name).open('w') as f:
  for r in rs:f.write(json.dumps(r)+'\n')
with (cache/'reference.jsonl').open('w') as f:
 for _,_,r in annotated:
  if r:f.write(json.dumps(r)+'\n')
(a.out/'annotation-provenance.json').write_text(json.dumps({'inputs':[{k:v for k,v in src.items()} for _,src in rows],
 'guard_s':.3,'transport_uncertainty':'Each bracketing request RTT is added to its corresponding end.',
 'reference_verdict_used_for_guard':False},indent=2)+'\n')
print('Annotated',len(rows),'retained attempts into',a.out)
