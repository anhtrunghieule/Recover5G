import unittest,sys
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r5g.verdict import assess_observation,assess_next_use,mechanism_preserved,first_stably_clean
from exp.wire_truth import reference,upf_state_at,wire_sessions,changing
from c2 import pcap_ids
U='imsi-999700000000001';V='imsi-999700000000002'
def clean():
 return {'counts':{'amf_ue':2,'amf_sess':2,'smf_sess':2,'upf_sess':2},'amf_id':{U:{'psis':{'1':{}}},V:{'psis':{'1':{}}}},'smf_id':{U:{'1':{'ip':'10.45.0.2'}},V:{'1':{'ip':'10.45.0.3'}}},'ues':{'1':{'rm':'RM-REGISTERED','sessions':{'1':'10.45.0.2'}},'2':{'rm':'RM-REGISTERED','sessions':{'1':'10.45.0.3'}}},'ue_ips':{'1':'10.45.0.2','2':'10.45.0.3'},'dl_ok':{'1':True,'2':True},'upf_log_ips':[]}
class EvidenceTests(unittest.TestCase):
 def test_clean_scope(self):
  r=assess_observation(clean());self.assertEqual(r['status'],'clean');self.assertEqual(r['ideal_relation'],'unknown')
 def test_equal_count_wrong_ip_pairing(self):
  s=clean();s['smf_id'][U]['1']['ip'],s['smf_id'][V]['1']['ip']='10.45.0.3','10.45.0.2';self.assertEqual(assess_observation(s)['status'],'violated')
 def test_equal_count_wrong_session_identity(self):
  s=clean();s['amf_id'][U]['psis']={'2':{}};self.assertEqual(assess_observation(s)['status'],'violated')
 def test_hidden_tunnel_pairing_not_certified(self):
  s=clean();s['unobserved_wrong_teid']=True;self.assertEqual(assess_observation(s)['ideal_relation'],'unknown')
 def test_missing_readouts(self):
  for key in ['amf_id','smf_id','ues','counts']:
   with self.subTest(key=key):s=clean();s[key]=None;self.assertEqual(assess_observation(s)['status'],'unknown')
 def test_missing_count(self):
  s=clean();s['counts']['upf_sess']=None;self.assertEqual(assess_observation(s)['status'],'unknown')
 def test_missing_amf_mapping(self):
  s=clean();s['amf_id'][U].pop('psis');self.assertEqual(assess_observation(s)['status'],'unknown')
 def test_missing_ue_mapping(self):
  s=clean();s['ues']['1']['sessions']=None;self.assertEqual(assess_observation(s)['status'],'unknown')
 def test_missing_smf_ip(self):
  s=clean();s['smf_id'][U]['1']['ip']=None;self.assertEqual(assess_observation(s)['status'],'unknown')
 def test_changing(self):self.assertEqual(assess_observation(clean(),changing=True)['status'],'changing')
 def test_legitimate_retention(self):
  s=clean();s['counts']['upf_sess']=4;self.assertEqual(assess_observation(s,retention_pending=True)['status'],'unknown');self.assertEqual(assess_observation(s)['status'],'violated')
 def test_failed_use_empty_consistent_state(self):self.assertEqual(assess_next_use({'status':'clean'},procedure='release',succeeded=False)['status'],'failed')
 def test_untested_use(self):self.assertEqual(assess_next_use({'status':'clean'})['status'],'unknown')
 def test_unknown_after_successful_use(self):self.assertEqual(assess_next_use({'status':'unknown'},procedure='release',succeeded=True)['status'],'unknown')
 def test_success_is_procedure_specific(self):self.assertEqual(assess_next_use({'status':'clean'},procedure='release',succeeded=True)['procedure'],'release')
 def test_mechanism_guard(self):
  sig={'old_up_seid':'7','deletion_target':'UE2','restart':'SMF'};self.assertTrue(mechanism_preserved(sig,dict(sig),True));self.assertFalse(mechanism_preserved(sig,{'deletion_target':'UE1'},True));self.assertFalse(mechanism_preserved({},sig,True));self.assertFalse(mechanism_preserved(sig,sig,False))
 def test_unknown_suffix_not_convergence(self):self.assertIsNone(first_stably_clean([{'rel':1,'ref_status':'unknown'}]))
 def test_transient_between_checkpoints(self):
  rows=[{'rel':i,'ref_status':x} for i,x in [(1,'clean'),(2,'violated'),(3,'clean')]];self.assertEqual(first_stably_clean(rows),3)
 def test_changing_suffix_not_convergence(self):self.assertIsNone(first_stably_clean([{'rel':1,'ref_status':'clean','changing':'pfcp'}]))
 def test_upf_capture_loss(self):self.assertFalse(upf_state_at(5,[],[(1,'added',1)])[0])
 def test_upf_restart_clears_old_identity(self):self.assertEqual(upf_state_at(5,[(1,'est','7','8','10.45.0.2')],[(.5,'start',0),(1,'added',1),(3,'start',0)])[1],{})
 def test_upf_identifier_reuse_after_deletion(self):
  w=[(1,'est','7','8','10.45.0.2'),(2,'del','7','8',None),(3,'est','7','9','10.45.0.3')];self.assertEqual(upf_state_at(4,w,[(3,'added',1)])[1],{'7':'10.45.0.3'})
 def test_unknown_reference(self):self.assertEqual(reference(clean(),False,{})[0],'unknown')
 def test_capture_collection_guard(self):self.assertEqual(changing(10,11,{'pfcp':[{'t':9.8,'type':50}],'ngap':[],'sbi':[]},[],[]),'pfcp')
 def test_decode_failure_is_fatal(self):
  from subprocess import CompletedProcess
  with patch('subprocess.run',return_value=CompletedProcess([],1,'','decode failed')):
   with self.assertRaises(RuntimeError):pcap_ids.tshark('/tmp/test.pcap','pfcp',[])
if __name__=='__main__':unittest.main(verbosity=2)
