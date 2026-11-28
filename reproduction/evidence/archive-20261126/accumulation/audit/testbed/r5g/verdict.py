"""Evidence-aware proxy interface. No clean proxy certifies the ideal relation.
Legacy list-returning checks remain available for reproducing historical tables.
"""
from copy import deepcopy
from . import oracle

def assess_observation(snapshot, *, changing=False, retention_pending=False):
 reasons=[];s=deepcopy(snapshot)
 if changing:reasons.append('state-changing-during-collection')
 if retention_pending:reasons.append('configured-retention-not-expired')
 for k in ('amf_id','smf_id','ues','counts'):
  if not isinstance(s.get(k),dict):reasons.append('missing-'+k)
 if not reasons:
  if any(s['counts'].get(k) is None for k in ('amf_ue','amf_sess','smf_sess','upf_sess')):reasons.append('missing-count')
  for u,x in s['ues'].items():
   if not isinstance(x,dict) or not x.get('rm') or not isinstance(x.get('sessions'),dict):reasons.append('incomplete-ue-readout');continue
   if any(not ip for ip in x['sessions'].values()):reasons.append('missing-ue-ip')
  for x in s['amf_id'].values():
   if not isinstance(x,dict) or not isinstance(x.get('psis'),(dict,list)):reasons.append('missing-amf-identity-map')
  for x in s['smf_id'].values():
   if not isinstance(x,dict):reasons.append('missing-smf-identity-map');continue
   if any(not isinstance(b,dict) or not b.get('ip') for b in x.values()):reasons.append('missing-smf-ip')
 if reasons:return {'status':'changing' if changing else 'unknown','reasons':sorted(set(reasons)),'violations':[],'ideal_relation':'unknown'}
 try:
  s['amf_id']={u:dict(x,psis={int(p):v for p,v in x['psis'].items()} if isinstance(x['psis'],dict) else {int(p):{} for p in x['psis']}) for u,x in s['amf_id'].items()}
  s['smf_id']={u:{int(p):b for p,b in x.items()} for u,x in s['smf_id'].items()}
  # Probes are optional. Missing probes are recorded, never fabricated as successful.
  s.setdefault('dl_ok',{});s.setdefault('ue_ips',{});s.setdefault('upf_log_ips',[])
  v=oracle.check_R(s)+oracle.check_R_id(s)
 except (ValueError,TypeError,KeyError) as e:
  return {'status':'unknown','reasons':['malformed-readout:'+type(e).__name__],'violations':[],'ideal_relation':'unknown'}
 return {'status':'violated' if v else 'clean','reasons':[],'violations':v,'ideal_relation':'unknown','unobserved':['complete-URI-SEID-TEID-correspondence','UDM-registration','ghost-attribution'],'probes_observed':bool(s['dl_ok'])}

def assess_next_use(post, *, procedure=None, succeeded=None):
 if not procedure or succeeded is None:return {'status':'unknown','procedure':procedure,'reason':'procedure-or-outcome-unavailable'}
 if not succeeded:return {'status':'failed','procedure':procedure,'reason':'request-did-not-succeed'}
 return {'status':'repaired' if post['status']=='clean' else post['status'],'procedure':procedure,'scope':'tested-procedure-and-observed-proxy-only'}

def mechanism_preserved(original, candidate, predicate_holds):
 """Signatures must be identity-resolved events, not only count predicates."""
 return bool(predicate_holds and original and all(k in candidate and candidate[k]==v for k,v in original.items()))

def first_stably_clean(rows):
 """Do not turn an all-unknown suffix or a changing collection into convergence."""
 for i,r in enumerate(rows):
  if all(x['ref_status']=='clean' and not x.get('changing') for x in rows[i:]):return r['rel']
 return None
