"""Pipeline self-test: identity build == clean disc, and a stress build that shifts
every NB10 entry and moves files (for a boot test in the emulator).

usage: .venv/bin/python tools/dev/isotest.py identity | stress [out.iso]
  identity  build with no changes; the image must have the clean SHA-1
  stress    grow NB10 entry 2 (HDD-install icon text) by 4 MB, so entries 3-141 shift
            and N10.KHD/KBD move, and pad the ELF by 1 MB so it moves too
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import build, iso, nbx, setup

def main():
    mode = sys.argv[1]
    clean = setup.CLEAN
    recs = iso.records(clean)
    files = build.build_files(clean, recs)
    if mode == 'identity':
        out = os.path.join(build.ROOT, 'build', 'identity.iso')
        build.write(clean, out, files)
        digest = setup.sha1(out)
        print('identity: %s' % ('OK' if digest == setup.CLEAN_SHA1 else 'FAILED ' + digest))
        os.remove(out)
    elif mode == 'stress':
        out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(build.ROOT, 'build', 'stress.iso')
        elf = bytearray(files[iso.ELF_NAME])
        archive = files[nbx.NAME]
        e2 = nbx.entry(archive, elf, 2)
        files[nbx.NAME] = nbx.apply(archive, elf, {2: e2 + bytes(4 << 20)})
        files[iso.ELF_NAME] = bytes(elf) + bytes(1 << 20)
        moved = build.write(clean, out, files)
        print('stress: moved %s' % moved)

if __name__ == '__main__':
    main()
