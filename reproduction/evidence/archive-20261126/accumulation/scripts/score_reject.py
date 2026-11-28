from pathlib import Path
import json,collections,sys,os,concurrent.futures
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W/'audit/testbed'));os.environ.setdefault('DOCKER_CONTEXT','colima-r5g-reproduction')
from c2 import pcap_ids
rs=[]
for p in sorted((W/'results').glob('reject-worker*/reject.jsonl')):
 for r in map(json.loads,p.read_text().splitlines()):
  r['record_root']=str(p.parent.relative_to(W));rs.append(r)
summary={'scope':'new reconstruction from public recipe/config/capture, not original runner','attempts':len(rs),'expected_attempts':15,'errors':sum(bool(r.get('error')) for r in rs),'arms':{}}
for arm in ['none','targeted','global']:
 rows=[r for r in rs if r['arm']==arm];good=[r for r in rows if not r.get('error')]
 summary['arms'][arm]={'attempts':len(rows),'valid':len(good),'fired':sum(bool(r.get('fault_fired')) for r in good),'signature_candidates':sum(bool(r.get('mechanism_candidate')) for r in good),'release_event_exception':sum(bool(r.get('release_during_reject_signature',{}).get('exception_identities')) for r in good),'persistent_proxy':sum(bool((r.get('snap',{}).get('33.8') or {}).get('viol')) and bool((r.get('snap',{}).get('67.6') or {}).get('viol')) for r in good),'elapsed_s':sum(r.get('attempt_wall_s',0) for r in rows)}
(W/'results/reject-summary.json').write_text(json.dumps(summary,indent=1))
for r in rs:
 if r.get('error'):continue
 p=W/r['record_root']/r['pcap'];out=Path(str(p)[:-3]+'.ids.json')
 if not out.exists():out.write_text(json.dumps(pcap_ids.decode(str(p))))
print(json.dumps(summary,indent=1))
