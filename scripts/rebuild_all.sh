#!/bin/zsh
# Everything the pages and documents rest on, in order, from one frozen model. Each step is skipped once done under
# the same fingerprint of the model code and parameters, so a stopped build picks up where it was.
#
#     PY=.venv/bin/python scripts/rebuild_all.sh first     # up to the first scenarios
#     (set the Guide's start on the new surface: data/processed/scenarios_guide_page.json and GUIDE_START in the page)
#     PY=.venv/bin/python scripts/rebuild_all.sh second    # the near round and everything after it
#
# Never edit src/ or params while it runs: the fingerprint is taken as each step starts and a change would strand
# what came before. scripts/ is not in the fingerprint.
cd "${0:A:h}/.."
PY=${PY:-.venv/bin/python}
W=${WORKERS:-9}
LOGS=${LOGS:-data/processed/rebuild_logs}
mkdir -p $LOGS
step() {
  local name=$1; shift
  if $PY scripts/build_stamp.py done $name; then echo "$(date '+%m-%d %H:%M') have $name" >> $LOGS/progress; return; fi
  echo "$(date '+%m-%d %H:%M') $name" >> $LOGS/progress
  if ! "$@" > $LOGS/$name.log 2>&1; then
    echo "$(date '+%m-%d %H:%M') FAILED: $name" >> $LOGS/progress
    touch $LOGS/FAILED
    exit 1
  fi
  $PY scripts/build_stamp.py mark $name
}
SURFACE=(--draws 2500 --anchors 600 --local 300 --centers data/processed/emulator_centers.json
  --near 300 --near-centers data/processed/emulator_near_centers.json
  --near2 300 --near2-centers data/processed/emulator_near2_centers.json
  --near3 300 --near3-centers data/processed/emulator_near3_centers.json
  --spread 1200 --test 600 --oneway --years 35 --workers $W --resume)
scenarios() {
  local tag=$1
  step scenarios_$tag $PY scripts/scenarios.py v3
  step scenarios_high_$tag $PY scripts/scenarios.py high
  step prepare_$tag $PY scripts/inject_scenarios.py --prepare
  step verify_$tag $PY scripts/verify_scenarios.py --file data/processed/scenarios_page.json --workers 6
  step inject_$tag $PY scripts/inject_scenarios.py
}
rm -f $LOGS/FAILED
case $1 in
prep)
  step calibrate $PY -c "import sys; sys.path[:0]=['scripts','src']; from build_explorer_data import calibrated; calibrated(1.0, False)"
  step identify $PY scripts/backcast.py --identify
  ;;
first)
  step calibrate $PY -c "import sys; sys.path[:0]=['scripts','src']; from build_explorer_data import calibrated; calibrated(1.0, False)"
  step identify $PY scripts/backcast.py --identify
  step surface $PY scripts/build_emulator.py $SURFACE
  scenarios first
  ;;
second)
  step near_centers $PY scripts/set_centers.py
  step surface_near $PY scripts/build_emulator.py $SURFACE \
    --near4 300 --near4-centers data/processed/emulator_near4_centers.json
  scenarios second
  step verify_guide $PY scripts/verify_scenarios.py --file data/processed/scenarios_guide_page.json \
    --out data/processed/scenarios_guide_start_verified.json --workers 6
  step data $PY scripts/build_explorer_data.py
  step timeline $PY scripts/build_timeline.py --workers $W
  step births $PY scripts/build_births_grid.py --seeds 3 --years 10 --workers $W
  step past_grid $PY scripts/build_past_grid.py --workers $W
  step counterfactual_past $PY scripts/counterfactual_past.py
  step past_data $PY scripts/build_past_data.py
  step null_test $PY scripts/null_test.py
  step quality $PY scripts/quality_check.py
  step work_sensitivity $PY scripts/work_sensitivity.py --workers 6
  step parameters $PY scripts/param_table.py
  step guided $PY scripts/build_guided.py
  step stamp $PY scripts/build_stamp.py record artifacts/explorer_v3/*(.) artifacts/guided/*(.)
  step gate $PY scripts/build_stamp.py check
  ;;
*)
  echo "first or second"; exit 2 ;;
esac
touch $LOGS/DONE_$1
