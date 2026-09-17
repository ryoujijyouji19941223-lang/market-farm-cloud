from __future__ import annotations
import argparse
from .engine import load_config, analyze, save_run
from .dashboard import render


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("session", choices=["morning","evening"])
    args=ap.parse_args()
    cfg=load_config()
    regime, results=analyze(cfg)
    state=save_run(args.session,cfg,regime,results)
    render(cfg,regime,results,state)
    for r in results:
        print(r["name"], r.get("action"), round(r.get("probability_up",.5)*100,1))

if __name__=="__main__": main()
