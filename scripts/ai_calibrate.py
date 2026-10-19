"""Check the AI channels against what forecasters expect, in the status quo.

    .venv/bin/python scripts/ai_calibrate.py

The consensus (OECD 2024, Acemoglu 2024, Goldman Sachs 2023, Penn Wharton 2025): at the pace most expect, about
+0.5 points a year of productivity growth from AI, with little change in unemployment. The model's pace for that is
5% a year. Runs the 2025 status quo for ten years with no AI, 5% and 15%, over a small grid of the augmentation gain
and the share of displaced work that comes back as new tasks, and prints what each gives. Nothing is written to the
parameters: the chosen values are put in params.py by hand, with the reason.
"""
import pickle
import sys
import pathlib
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402

GRID = [(g, r, s) for g in (.25, .30) for r in (.8, .95) for s in (.2, .45)]


def run(job):
    blob, rate, gain, share, speed = job
    soc = model.scenario(pickle.loads(blob), {"policy": {"regime": "status_quo"},
                                              "automation": {"ai_progress_rate": rate, "augmentation_gain": gain,
                                                             "reinstatement_share": share, "reinstatement_speed": speed}})
    rows = [soc.step() for _ in range(10)]
    last = rows[-1]
    return rate, gain, (share, speed), {"productivity": last["automation_productivity"], "unemp": last["unemployment_rate"],
                               "displaced": last["automation_displaced_fte"], "new": last["automation_new_task_fte"],
                               "output": last["output_index"], "emp": last["employment_rate_16_74"]}


def main():
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    jobs = [(blob, 0.0, .12, .5, .2)] + [(blob, rate, g, r, s) for rate in (.05, .15) for g, r, s in GRID]
    with ProcessPoolExecutor(9) as ex:
        res = list(ex.map(run, jobs))
    none = res[0][3]
    print(f"no AI: unemployment {none['unemp']:.3f}, output {none['output']:.3f}")
    print("rate  gain  new-task share | AI productivity by 2035 (pp/yr) | unemployment vs none | output vs none")
    for rate, g, r, o in res[1:]:
        pp = 100 * (o["productivity"] ** (1 / 10) - 1)
        print(f"{rate:.2f}  {g:.2f}  {r}            | {100 * (o['productivity'] - 1):5.1f}% ({pp:.2f} pp/yr)"
              f"          | {100 * (o['unemp'] - none['unemp']):+.2f} pp            | {100 * (o['output'] / none['output'] - 1):+.1f}%")


if __name__ == "__main__":
    main()
