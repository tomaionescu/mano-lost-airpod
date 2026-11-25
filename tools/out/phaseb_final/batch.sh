#!/bin/zsh
# Review batch: the named jobs one after the other (each waits for the engine lock). After each job it prints short
# checksums of the user's save and settings files and the ~/Pictures file count, which a test run must leave
# unchanged. Shots: shots/phaseb/final/<name>.
cd "$(dirname "$0")/../../.."
U="$HOME/Library/Application Support/Godot/app_userdata/Mano & the Lost AirPod"
V=tools/out/phaseb_final
S=phaseb/final
toma() { shasum "$U/save_v1.json" "$U/settings_v1.json" | awk '{print substr($1,1,8)}' | tr '\n' ' '; }
pics() { ls "$HOME/Pictures" 2>/dev/null | wc -l | tr -d ' '; }
hl() {
  local name=$1; shift
  echo "=== $name start $(date +%H:%M:%S)"
  python3.11 tools/dev/godot.py --timeout 900 --log $V/$name.log -- --headless --path . --log-file "$PWD/$V/$name.engine.log" "$@" 2>&1 | tail -4
  echo "=== $name end $(date +%H:%M:%S) SCRIPT ERRORS: $(grep -c 'SCRIPT ERROR' $V/$name.log) toma: $(toma) pictures: $(pics)"
}
at() {
  local name=$1; local to=$2; shift 2
  rm -rf shots/$S/$name
  echo "=== $name start $(date +%H:%M:%S)"
  python3.11 tools/dev/godot.py --timeout $to --log $V/at_$name.log -- --path . --resolution 1600x900 --position 40,40 --log-file "$PWD/$V/at_$name.engine.log" -- "$@" shots=$S/$name 2>&1 | grep -v "^\[autotest\] shot" | tail -6
  echo "=== $name end $(date +%H:%M:%S) SCRIPT ERRORS: $(grep -c 'SCRIPT ERROR' $V/at_$name.log) toma: $(toma) pictures: $(pics)"
}
sl() {
  local name=$1; local to=$2; shift 2
  rm -rf shots/$S/$name
  echo "=== $name start $(date +%H:%M:%S)"
  python3.11 tools/dev/godot.py --timeout $to --log $V/sl_$name.log -- --path . --resolution 1600x900 --position 40,40 --log-file "$PWD/$V/sl_$name.engine.log" -s tools/out/phaseb_final/root.gd -- "$@" shots=$S/$name 2>&1 | grep -v "^\[autotest\] shot" | tail -6
  echo "=== $name end $(date +%H:%M:%S) SCRIPT ERRORS: $(grep -c 'SCRIPT ERROR' $V/sl_$name.log) toma: $(toma) pictures: $(pics)"
}
echo "toma at start: $(toma) pictures: $(pics)"
for job in "$@"; do
  case $job in
    import) echo "=== import $(date +%H:%M:%S)"; python3.11 tools/dev/godot.py --timeout 900 --log $V/import.log -- --headless --path . --log-file "$PWD/$V/import.engine.log" --import 2>&1 | tail -3; echo "=== import end $(date +%H:%M:%S) toma: $(toma)" ;;
    tests) hl tests res://tests/test_runner.tscn ;;
    line) hl line_check res://scenes/dev/line_check.tscn ;;
    hud) hl hud_check res://scenes/dev/hud_check.tscn ;;
    ui) hl ui_check res://scenes/dev/ui_check.tscn ;;
    basic) at basic 500 autotest=basic ;;
    title) at title 400 autotest=title ;;
    tour) at tour 500 autotest=tour ;;
    times) at times 900 autotest=times ;;
    choices) at choices 500 autotest=choices ;;
    convo) at convo 600 autotest=convo ;;
    convo2) at convo2 600 autotest=convo ids=ishita,joaquin,karim chapter=2 time=last_light ;;
    convo3) at convo3 600 autotest=convo ids=toma,ishita,silvia chapter=3 time=blue ;;
    convo4) at convo4 600 autotest=convo ids=cristina,joaquin,anisha chapter=4 time=night ;;
    convo5) at convo5 600 autotest=convo ids=toma,ian,silvia,ishita chapter=5 time=late ;;
    chapters) at chapters 900 autotest=chapters ;;
    story) at story 2400 autotest=story ;;
    story_shots) at story_shots 2600 autotest=story dlgshots=4 ;;
    ducks) at ducks 900 autotest=ducks ;;
    photos) at photos 900 autotest=photos ;;
    overheard) at overheard 1200 autotest=overheard ;;
    looks) at looks 1500 autotest=looks ;;
    looks_night) at looks_night 1500 autotest=looks night ;;
    looks3) at looks3 600 autotest=looks ids=amphi_lectern,sm14_trace,sm15_note ;;
    photos_v) at photos_v 600 autotest=photos ids=ph_vending,ph_coffee ;;
    side) at side 1200 autotest=side ;;
    idle) at idle 400 autotest=idle ;;
    select) at select 700 autotest=chapter_select ;;
    journal) at journal 400 autotest=journal ;;
    map) at map 400 autotest=map ;;
    place) at place 500 autotest=place ids=planter_survivor,court_survivor5,court_sup4 ;;
    check) echo "=== check $(date +%H:%M:%S)"; python3.11 tools/dev/godot.py --timeout 120 --log $V/check.log -- --headless --path . --check-only -s tools/out/phaseb_final/walk.gd 2>&1 | tail -5; python3.11 tools/dev/godot.py --timeout 120 --log $V/check2.log -- --headless --path . --check-only -s tools/out/phaseb_final/root.gd 2>&1 | tail -5 ;;
    walk) sl walk 3000 ;;
    walk0) sl walk0 600 chapter=0 upto=0 ;;
    walk1) sl walk1 1200 chapter=1 upto=1 ;;
    walk2) sl walk2 1200 chapter=2 upto=2 ;;
    walk3) sl walk3 1500 chapter=3 upto=3 ;;
    walk4) sl walk4 1500 chapter=4 upto=4 ;;
    walk5) sl walk5 1200 chapter=5 ;;
    *) echo "unknown job $job" ;;
  esac
done
echo "=== batch done $(date +%H:%M:%S)"
