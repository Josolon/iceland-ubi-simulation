"""Quick end-to-end check: calibrate, run status quo and a 450k reform for a few years."""
import pickle, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ubisim.abm import params, model
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_explorer_data import cache_fresh, stamp_cache

CACHE = pathlib.Path(__file__).resolve().parents[1] / "data/processed/calibrated_status_quo.pkl"
t = time.time()
if "--recalibrate" not in sys.argv and cache_fresh(CACHE):
    base = pickle.loads(CACHE.read_bytes())
else:
    base = model.Society(params.load(policy={"regime": "status_quo", "wage_setting": "status_quo"})).calibrate()
    stamp_cache(CACHE, pickle.dumps(base))
print("ready", round(time.time() - t, 1), "s")
print({k: round(float(v), 1) for k, v in base.accounts0.items()})
years = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
ref = None
for label, ov in [("status quo", {}), ("platform 450k", {"policy": {"regime": "platform", "wage_setting": "free_market"}})]:
    soc = model.scenario(base, ov)
    soc.reference = ref
    for _ in range(years):
        h = soc.step()
        keys = ["year", "employment_rate_16_74", "baseline_workers_stopped", "new_ventures", "emigrants", "immigrants",
                "births", "price_level", "balance_bn", "wage_Elementary", "wage_Professionals", "wage_Managers"]
        if label == "status quo":
            ref = (ref or []) + [{k[4:]: v for k, v in h.items() if k.startswith("acc_")}]
        print(label, {k: (round(h[k], 3) if isinstance(h[k], float) else h[k]) for k in keys}, round(time.time() - t, 1))
