"""Create build/pcsx2/PCSX2/: a PCSX2 data folder for automated tests, so the user's own
configuration (~/.config/PCSX2) is never changed. Copies the user's PCSX2.ini and
changes only what automation needs: keyboard pad, native resolution, raw-frame
screenshots, no shutdown prompt. BIOS folder is linked; memory cards are separate.

usage: .venv/bin/python tools/emu/datapath.py [--headless]
  --headless: build/pcsx2h/PCSX2 for tools/emu/headless.sh, pad bound to the virtual
              gamepad SDL-0 (tools/emu/vpad.py) instead of the keyboard
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
USER = os.path.expanduser('~/.config/PCSX2')
DATA = os.path.join(ROOT, 'build', 'pcsx2', 'PCSX2')   # -datapath build/pcsx2 adds PCSX2/
HEADLESS = '--headless' in sys.argv
if HEADLESS:
    DATA = os.path.join(ROOT, 'build', 'pcsx2h', 'PCSX2')

# PS2 button -> keyboard key (Japanese convention: Circle confirms, Cross cancels)
PAD = {'Up': 'Up', 'Down': 'Down', 'Left': 'Left', 'Right': 'Right',
       'Circle': 'X', 'Cross': 'Z', 'Triangle': 'S', 'Square': 'A',
       'Start': 'Return', 'Select': 'BackSpace', 'L1': 'Q', 'R1': 'W', 'L2': '1', 'R2': '2'}
SET = {'UI': {'ConfirmShutdown': 'false', 'PauseOnFocusLoss': 'false', 'StartFullscreen': 'false'},
       'EmuCore': {'EnablePINE': 'true'},
       'EmuCore/GS': {'upscale_multiplier': '1', 'ScreenshotSize': '2', 'ScreenshotFormat': '0'},
       'Pad1': {k: 'Keyboard/' + v for k, v in PAD.items()}}
SDL = {'Up': 'DPadUp', 'Down': 'DPadDown', 'Left': 'DPadLeft', 'Right': 'DPadRight',
       'Circle': 'FaceEast', 'Cross': 'FaceSouth', 'Triangle': 'FaceNorth', 'Square': 'FaceWest',
       'Start': 'Start', 'Select': 'Back', 'L1': 'LeftShoulder', 'R1': 'RightShoulder',
       'L2': '+LeftTrigger', 'R2': '+RightTrigger', 'L3': 'LeftStick', 'R3': 'RightStick'}
if HEADLESS:
    SET['Pad1'] = {k: 'SDL-0/' + v for k, v in SDL.items()}
    SET['InputSources'] = {'SDL': 'true'}

def main():
    os.makedirs(os.path.join(DATA, 'inis'), exist_ok=True)
    os.makedirs(os.path.join(DATA, 'memcards'), exist_ok=True)
    link = os.path.join(DATA, 'bios')
    if not os.path.islink(link):
        os.symlink(os.path.join(USER, 'bios'), link)
    ini = open(os.path.join(USER, 'inis', 'PCSX2.ini'), encoding='utf-8').read()
    out, section = [], None
    for line in ini.splitlines():
        m = re.match(r'\[(.+)\]$', line)
        if m:
            section = m.group(1)
        else:
            k = line.split('=')[0].strip()
            if section == 'Pad1' and re.match(r'(SDL-|Keyboard)', line.partition('=')[2].strip()):
                continue                      # drop gamepad bindings
            if k in SET.get(section, {}):
                continue
        out.append(line)
        if m and section in SET:
            out += ['%s = %s' % kv for kv in SET[section].items()]
    open(os.path.join(DATA, 'inis', 'PCSX2.ini'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('PCSX2 test data folder:', DATA)

if __name__ == '__main__':
    main()
