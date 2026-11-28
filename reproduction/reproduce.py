#!/usr/bin/env python3
"""Minimal Recover5G orphan-session package. Python standard library only."""
import argparse,datetime,gzip,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
P=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def run(cmd,**kw):return subprocess.run(cmd,check=True,**kw)
def verify_files():
 for r in json.loads((P/'manifests/files.json').read_text()):
  if sha(P/r['file'])!=r['sha256']:raise RuntimeError('Hash mismatch: '+r['file'])
 print('Package files verified')
def verify_images(ctx):
 for r in json.loads((P/'manifests/images.json').read_text()):
  actual=subprocess.check_output(['docker','--context',ctx,'image','inspect','--format','{{.Id}}',r['tag']],text=True).strip()
  if actual!=r['id']:raise RuntimeError('Image mismatch: '+r['tag'])
 print('Pinned image IDs verified')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['verify','load','analyze','reproduce','build-repair','build-clock','validation-run','validate-cohort','compare-checkers','export-expert','score-expert','constructed-cases','control-multisession']);ap.add_argument('--context');ap.add_argument('--runs',type=int,default=5);ap.add_argument('--instance',type=int,default=7);ap.add_argument('--out',type=Path)
 ap.add_argument('--input',type=Path);ap.add_argument('--private',type=Path);ap.add_argument('--packet',type=Path);ap.add_argument('--predictions',type=Path)
 ap.add_argument('--ues',type=int,choices=[1,2],default=2);ap.add_argument('--timing-v2',action='store_true')
 ap.add_argument('--part',type=int,default=0);ap.add_argument('--parts',type=int,default=1);ap.add_argument('--pilot',action='store_true')
 a=ap.parse_args();verify_files()
 if a.action in ['validate-cohort','compare-checkers','export-expert','score-expert','constructed-cases']:
  from validation.cli import execute
  execute(a);return
 if a.action=='verify':return
 if not a.context or a.context in ['default','colima-recover5g','colima-recover5g-oai']:raise SystemExit('Pass an explicit dedicated Docker context, not a protected original-campaign context')
 e=dict(os.environ,DOCKER_CONTEXT=a.context,R5G_INST=str(a.instance),UERANSIM_IMAGE='r5g/ueransim:4f45e18-p2')
 if a.action=='load':
  run(['docker','--context',a.context,'load','-i',str(P/'images/arm64-runtime-and-build.tar.gz')]);verify_images(a.context);return
 verify_images(a.context)
 if a.action=='build-clock':
  run(['docker','--context',a.context,'run','--rm','--network','none','-v',str(P/'build/clock')+':/clock','r5g/open5gs-build:base','gcc','-O2','-o','/clock/clock','/clock/clock.c']);return
 if a.action=='build-repair':
  run(['docker','--context',a.context,'build','--network=none','-t','r5g/reproduction-repair:e85748e',str(P/'build/repair')]);return
 out=(a.out or P/'runs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')).resolve()
 if out.exists():raise SystemExit('Output directory must be new, preserving prior attempts')
 out.mkdir(parents=True);e['R5G_OUT']=str(out);T=P/'testbed'
 if a.action=='control-multisession':
  run([sys.executable,str(T/'inst.py'),'gen',str(a.instance)],env=e)
  run([sys.executable,str(T/'exp/multisession_control.py')],env=e);return
 if a.action=='validation-run':
  run([sys.executable,str(T/'inst.py'),'gen',str(a.instance)],env=e)
  args=[sys.executable,str(T/'exp/validation_campaign.py'),'--part',str(a.part),'--parts',str(a.parts)]
  if a.pilot:args.append('--pilot')
  run(args,env=e);return
 if a.action=='analyze':shutil.copytree(P/'retained/orphan',out,dirs_exist_ok=True)
 else:
  if not 1<=a.instance<=7 or not 1<=a.runs<=100:raise SystemExit('instance must be 1..7 and runs 1..100')
  run([sys.executable,str(T/'inst.py'),'gen',str(a.instance)],env=e)
  commands=[('base','amf','r5g/open5gs:e85748e'),('repair','amf','r5g/open5gs:e85748e-f12repair'),('base-ctl','none','r5g/open5gs:e85748e'),('repair-ctl','none','r5g/open5gs:e85748e-f12repair')]
  try:
   for tag,fault,image in commands:
    run([sys.executable,str(T/'exp/orphan_repl.py'),'--tag',tag+'-p2','--fault',fault,'--image',image,'--runs',str(a.runs),'--ues',str(a.ues)]+(['--timing-v2'] if a.timing_v2 else []),env=e)
  finally:
   run(['docker','--context',a.context,'compose','-f',str(T/'inst'/str(a.instance)/'docker-compose.yml'),'--profile','ran','down','-t','1'],env=e)
  records=[json.loads(x) for x in (out/'orphan_repl.jsonl').read_text().splitlines()]
  if len(records)!=4*a.runs or any(r.get('error') for r in records):raise RuntimeError('Incomplete campaign or harness failure. Attempts retained, no success reported.')
 for name,args in [('orphan_eval.py',[]),('wire_truth.py',['--kind','orphan']),('orphan_ref_eval.py',[])]:run([sys.executable,str(T/'exp'/name),str(out),*args],env=e)
 print('Outputs:',out)
if __name__=='__main__':main()
