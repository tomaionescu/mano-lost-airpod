"""Make Godot import the ambience and music OGGs as looping streams (AudioStreamOggVorbis.loop = true).

Writes/updates assets/audio/{amb,music}/*.ogg.import: an existing file keeps its uid/paths and only gets loop=true;
a missing one gets a minimal [remap]+[params] stub that Godot completes on the next import (it reads [params] from it).
One-shots and footsteps keep Godot's default (loop=false) so their players finish and free themselves.

python3.11 -I tools/py/audio_import.py
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
AUDIO = os.path.join(ROOT, "assets", "audio")

STUB = """[remap]

importer="oggvorbisstr"
type="AudioStreamOggVorbis"

[deps]

source_file="res://assets/audio/{group}/{name}"

[params]

loop=true
loop_offset=0
bpm=0
beat_count=0
bar_beats=4
"""


def main():
    for group in ("amb", "music"):
        for ogg in sorted(glob.glob(os.path.join(AUDIO, group, "*.ogg"))):
            imp = ogg + ".import"
            name = os.path.basename(ogg)
            if os.path.exists(imp):
                txt = open(imp).read()
                new = re.sub(r"(?m)^loop=.*$", "loop=true", txt)
                if "loop=" not in new:
                    new = new.rstrip("\n") + "\nloop=true\n"
                if new != txt:
                    open(imp, "w").write(new)
                    print("updated", group, name)
                else:
                    print("ok     ", group, name)
            else:
                open(imp, "w").write(STUB.format(group=group, name=name))
                print("stub   ", group, name)


if __name__ == "__main__":
    main()
