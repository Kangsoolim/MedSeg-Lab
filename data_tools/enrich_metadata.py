"""Re-export GT distance/target metadata from real NIfTI sources."""
from pathlib import Path
import argparse
from export_package import ROOT,read_json,enrich_case
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,default=ROOT/'frontend/public/demo');args=p.parse_args()
    for entry in read_json(args.package/'index.json')['cases']:
        enrich_case(args.package/entry['case_id']/'case.json')
    print('GT_DISTANCE_AND_TARGET_CHECKS_EXPORTED')
