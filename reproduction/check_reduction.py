#!/usr/bin/env python3
"""Replay the identity-resolved two-UE/one-UE reduction in a new output tree."""
import argparse,gzip,json,os,re,shutil,sys
from pathlib import Path
P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--context',required=True);a=p.parse_args()
from reproduce import verify_files
verify_files()
if a.out.exists():raise SystemExit('Use a new output directory')
os.environ['DOCKER_CONTEXT']=a.context;os.environ['IDREF_DOCKER_CONTEXT']=a.context
sys.path[:0]=[str(P/'testbed'),str(P/'testbed/exp')]
from wire_truth import decode,wire_sessions,upf_log_timeline,upf_state_at
import idref_decode as D
a.out.mkdir(parents=True)

def signature(root,r):
 if r.get('error') or r.get('technical_validity',{}).get('status')!='valid':return {'valid':False,'reason':'invalid-attempt'}
 pc=root/r['pcap'];dec=D.cached(str(pc),str(root/'identity'/f"{r['id']}.json.gz"));legacy,_=decode(str(pc));wire=wire_sessions(legacy)
 logs=gzip.open(root/r['logs'],'rt').read();timeline=upf_log_timeline(str(root/r['logs']))
 ev=r['timing']['events'];fault=ev.get('fault_command_start',ev['observation_origin'])['wall'];end=ev['observation_end']['wall']
 per=[]
 for supi,psis in r['before']['smf_id'].items():
  for psi,old in psis.items():
   ip=old['ip'];old_events=[x for x in wire if x[1]=='est' and x[4]==ip and x[0]<fault]
   seid=old_events[-1][2] if old_events else None
   creates=[x for x in dec['sbi'] if x['path'].rstrip('/').endswith('sm-contexts') and x['from']=='amf' and x['req'].get('/supi')==supi and str(x['req'].get('/pduSessionId'))==str(psi) and x['status']==201 and fault<x['t']<end]
   deletes=[x for x in wire if x[1]=='del' and x[2]==seid and fault<x[0]<end]
   cks=[]
   for cp in r['checkpoints']:
    cc=cp['collection_clock'];t=(cc['start']['wall']+cc['end']['wall'])/2;known,live,n=upf_state_at(t,wire,timeline)
    new=(cp['smf_id'].get(supi) or {}).get(str(psi),{})
    cks.append({'known':known,'old_up_seid_live':seid in live,'upf_identity_ip':live.get(seid),'new_smf_ip':new.get('ip'),'old_context_replaced':bool(new and new.get('ip')!=ip),'upf_log_count':n})
   warning=bool(re.search(r'OLD Session Will Release \[SUPI:'+re.escape(supi)+r',PDU Session identity:'+re.escape(str(psi))+r'\]',logs))
   role={'supi':supi,'psi':str(psi),'old_ip':ip,'old_up_seid':seid,'new_create_frames':[x['frame'] for x in creates],'old_deletion_times':[x[0] for x in deletes],'replacement_log':warning,'checkpoints':cks}
   role['orphan_signature']=bool(seid and creates and warning and not deletes and all(x['known'] and x['old_up_seid_live'] and x['old_context_replaced'] for x in cks) and r['new_sessions_work'])
   role['repair_signature']=bool(seid and creates and warning and deletes and all(x['known'] and not x['old_up_seid_live'] for x in cks) and r['new_sessions_work'])
   per.append(role)
 return {'valid':True,'fault':r['fault'],'roles':per,'new_sessions_work':r['new_sessions_work']}


result={}
for n,name in ((2,'repair-check-ues2'),(1,'repair-check-ues1-retry')):
 root=a.out/name;shutil.copytree(a.input/name,root);(root/'identity').mkdir(exist_ok=True)
 rs=[json.loads(x) for x in (root/'orphan_repl.jsonl').read_text().splitlines()]
 result[str(n)]={r['tag']:signature(root,r) for r in rs}
old=result['2'].get('base-p2',{});new=result['1'].get('base-p2',{});matched=[]
for role in new.get('roles',[]):
 before=next((x for x in old.get('roles',[]) if (x['supi'],x['psi'])==(role['supi'],role['psi'])),None)
 matched.append(bool(before and before['orphan_signature'] and role['orphan_signature']))
result['conclusion']={'mechanism_preserved':bool(matched and all(matched)),'reduction':'two UEs to one UE','retained_logical_identity':'same SUPI and PSI','runtime_ids':'individual captured SEIDs retained, roles compared across fresh sessions','scope':'one controlled reduction, not a complete minimization algorithm'}
result['technical_retry']={'original':'repair-check-ues1','replacement':'repair-check-ues1-retry','reason':'Missing AMF metric caused legacy wrapper exception before new sessions. Original attempts retained.'}
(a.out/'mechanism-reduction.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['conclusion']))
