#!/usr/bin/env python3
"""Repeated-recovery workload. Five independent chains per arm, ten cycles per chain.
No reset within a chain. Five-second settling sample per cycle and 34/68-second
final samples. Intermediate samples are workload observations, not deadline verdicts.
Each worker rotates arms across its three independent chains to avoid fixed stack assignment.
"""
import argparse,gzip,json,os,random,sys,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r5g import capture,dock,runner,testbed,workload
from r5g.testbed import c,CORE_NFS
from exp.orphan_repl import sn,vm_clock_offset
OUT=Path(runner.RESULTS); OUT.mkdir(parents=True,exist_ok=True)

def snap():
 t0=time.time(); s=sn([1,2]); s['t0']=t0; s['t1']=time.time()
 s['resources']={n:dock.dexec(c(n),'cat /proc/1/status | sed -n "/VmRSS/p;/VmSize/p;/Threads/p"; cat /sys/fs/cgroup/memory.current 2>/dev/null').stdout for n in ['amf','smf','upf']}
 return s

def one(chain,arm):
 image='r5g/open5gs:e85748e'+('-f12repair' if arm=='repair' else '')
 rid=f'growth-{arm}-r{chain}'; pc=OUT/'pcap'/f'{rid}.pcap'; start=time.time()
 rec={'id':rid,'chain':chain,'arm':arm,'stack':testbed.INST,'start':start,'cycles':[], 'image':image,'image_id':dock.image_id(image),'ueransim_id':dock.image_id(os.environ['UERANSIM_IMAGE'])}
 try:
  testbed.up(image=image); capture.start(str(pc)); runner.reset(); runner.bring_to('session',[1,2]);time.sleep(2)
  rec['clock_offset_s']=vm_clock_offset();rec['initial']=snap()
  for cycle in range(1,11):
   row={'cycle':cycle,'start':time.time(),'before':snap()};rec['cycles'].append(row)
   if arm!='control':
    row['fault_at']=dock.kill(c('amf'));dock.start(c('amf'))
    for _ in range(100):
     if 'NG Setup procedure is successful' in dock.logs(c('gnb'),since=row['fault_at']):break
     time.sleep(.3)
    else:raise RuntimeError('No NG Setup after AMF restart')
   else:time.sleep(1)
   for i in [1,2]:workload.power_off(i)
   time.sleep(2)
   for i in [1,2]:workload.power_on(i)
   row['registered']={i:workload.wait_registered(i,45) for i in [1,2]}
   if any(v is None for v in row['registered'].values()):raise RuntimeError('registration failed')
   time.sleep(2)
   for i in [1,2]:workload.ps_establish(i)
   row['new_sessions']={i:list(workload.wait_session(i,40)) for i in [1,2]}
   if any(v[0] is None for v in row['new_sessions'].values()):raise RuntimeError('session establishment failed')
   row['new_at']=time.time();time.sleep(5);row['after']=snap();row['elapsed_s']=time.time()-row['start']
   # Preserve partial progress independently of completion.
   (OUT/f'{rid}.progress.json').write_text(json.dumps(rec,indent=1))
   print(rid,cycle,row['after']['counts'],flush=True)
  rec['final']=[]
  for cp in [34,68]:
   time.sleep(max(0,row['new_at']+cp-time.time()));s=snap();s['offset_s']=cp;rec['final'].append(s)
 except Exception as e:rec['error']=repr(e);rec['traceback']=traceback.format_exc()
 finally:
  log=OUT/'logs'/f'{rid}.log.gz';log.parent.mkdir(exist_ok=True)
  with gzip.open(log,'wt') as f:
   for n in CORE_NFS+['gnb']:f.write(f'\n===== {n} =====\n'+dock.logs(c(n),since=start))
  rec['logs']=str(log.relative_to(OUT));rec['pcap']=os.path.relpath(capture.stop(str(pc)),OUT);rec['elapsed_s']=time.time()-start
  with (OUT/'accumulation.jsonl').open('a') as f:f.write(json.dumps(rec)+'\n')
  print('CHAIN_DONE',rid,rec.get('error','ok'),flush=True)
 return not rec.get('error')

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--worker',type=int,required=True);a=ap.parse_args()
 if dock.DOCKER_CONTEXT!='colima-r5g-claude' or testbed.INST not in [1,2,3]:raise SystemExit('Requires isolated r5g-claude context and stack 1..3')
 # Three workers, five rounds, rotating arms. Each round supplies one chain per arm.
 arms=['baseline','repair','control'];success=True
 for chain in range(1,6):
  arm=arms[(a.worker-1+chain-1)%3]
  success=one(chain,arm) and success
 testbed.down()
 sys.exit(0 if success else 1)
