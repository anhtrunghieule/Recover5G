#!/usr/bin/env python3
"""Replay the frozen fresh cohort and export new blinded packets in a new directory."""
import argparse,json,shutil
from pathlib import Path
from reproduce import verify_files
from validation.workflow import cohort,compare,export_expert,score_expert
from validation.constructed import generate
from validation_manifest import attach_scoring

P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=P/'evidence/validation-20261126');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
verify_files()
if a.out.exists():raise SystemExit('Use a new output directory')
a.out.mkdir(parents=True)
cohort(a.input/'results/natural-combined',a.out/'cohort-manifest.json')
for name in ('raw','guarded'):
 source=a.input/'results'/('natural-combined' if name=='raw' else 'natural-guarded')
 compare(source,a.out/('comparison-'+name))
attach_scoring(a.out/'cohort-manifest.json',a.out/'comparison-guarded/method-runs.csv')
constructed=a.out/'constructed';generate(constructed);compare(constructed,a.out/'comparison-constructed')
packets={}
for name,source in [('natural',a.input/'results/natural-guarded'),('constructed',constructed)]:
 packet=a.out/'expert-packet'/name;private=a.out/'expert-private'/name
 packets[name]=export_expert(source,packet,private)
 instructions=a.input/'protocol/expert-instructions.md'
 if instructions.is_file():shutil.copy2(instructions,packet/'ASSESSMENT.md')
 for reviewer in (1,2):shutil.copy2(packet/'labels.csv',packet/f'reviewer-{reviewer}.csv')
 score_expert(packet/'labels.csv',packet,private,private/'frozen-predictions.csv',a.out/f'expert-{name}-status.json')
(a.out/'replay.json').write_text(json.dumps({'source':str(a.input.resolve()),'packets':packets,
 'independent_human_adjudication':'pending',
 'guard':'Guarded inputs retain packet-activity annotations. The raw-to-guarded generator and decoder evidence are retained with the release.',
 'targets':'State snapshots and later next-use service have distinct targets. No automatic label is expert truth.'},indent=2)+'\n')
print('Replayed fresh cohort and exported blank expert packets into',a.out)
