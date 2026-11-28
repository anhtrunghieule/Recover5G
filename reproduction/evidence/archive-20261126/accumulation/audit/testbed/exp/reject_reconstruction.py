#!/usr/bin/env python3
"""New reconstruction from issue #5064, not recovery of its original runner.
Five trials per delay arm at IP allocation. Targeted delay applies only to PCF/UDM
cleanup replies. No arm models production latency. Keep every attempt.
"""
import os,sys,argparse,json,gzip,re,time,traceback,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r5g import runner,testbed,dock,capture
from exp.orphan_repl import vm_clock_offset
OUT=Path(runner.RESULTS);OUT.mkdir(parents=True,exist_ok=True)
ANSI=re.compile(r'\x1b\[[0-9;]*m')
def signature(rec):
 text=ANSI.sub('',gzip.open(OUT/rec['logs'],'rt',errors='replace').read());lines=text.splitlines();hits=[]
 for i,line in enumerate(lines):
  if 'Unknown event [SMF_EVT_SESSION_RELEASE]' in line:
   for nextline in lines[i+1:i+5]:
    m=re.search(r'\[(imsi-\d+):(\d+)\] State machine exception',nextline)
    if m:hits.append((m.group(1),int(m.group(2))));break
 rec['release_during_reject_signature']={'pfcp_establishment_timeout':'No PFCP session establishment response' in text,'upf_heartbeat_lost':'No Heartbeat from UPF' in text,'exception_identities':hits}
 retained=[]
 for u,p in hits:
  sn=rec['series'][-1];a=(sn.get('amf_id') or {}).get(u,{}).get('psis',{});s=(sn.get('smf_id') or {}).get(u,{})
  if (p in a or str(p) in a) and p not in s and str(p) not in s:retained.append([u,p])
 rec['same_identity_residue']=retained
 rec['mechanism_candidate']=bool(hits and retained and rec['release_during_reject_signature']['pfcp_establishment_timeout'] and rec['release_during_reject_signature']['upf_heartbeat_lost'])
 return rec
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--part',type=int,required=True);a=ap.parse_args()
 if dock.DOCKER_CONTEXT!='colima-r5g-reproduction' or testbed.INST not in [5,6]:raise SystemExit('Wrong isolated context/instance')
 trials=[(arm,r) for r in range(1,6) for arm in ['none','targeted','global']];random.Random(2026112501).shuffle(trials)
 for idx,(arm,r) in enumerate(trials):
  if idx%2!=a.part:continue
  spec=dict(id=f'reject-{arm}-r{r}',k=2,proc='pdu',nf='upf',boundary='pdu.ip_allocated',mode='crash',downtime=1.,seed=r,window=72.,poll=3.,stagger=.3,netem_ms=150 if arm=='global' else 0,netem_per_nf={'pcf':150,'udm':150} if arm=='targeted' else None)
  start=time.time()
  try:
   testbed.up(image='r5g/open5gs:e85748e');off=vm_clock_offset();rec=signature(runner.run(spec,str(OUT)));rec['clock_offset_s']=off
  except Exception as e:
   rec=dict(spec,error=repr(e),traceback=traceback.format_exc())
   try:capture.stop(str(OUT/'pcap'/f"{spec['id']}.pcap"))
   except Exception:pass
  rec.update(arm=arm,stack=testbed.INST,attempt_wall_s=time.time()-start)
  with (OUT/'reject.jsonl').open('a') as f:f.write(json.dumps(rec)+'\n')
  print(rec['id'],'fired',rec.get('fault_fired'),'candidate',rec.get('mechanism_candidate'),'error',rec.get('error'),flush=True)
 testbed.down()
