"""PINE IPC client for PCSX2 (EnablePINE in the test data folder, slot 28011).

  pine.py status            -> running / paused / shutdown
  pine.py read ADDR [N]     -> N bytes of EE memory as hex (default 16)
  pine.py title | id
  pine.py save SLOT         -> save state slot (build/pcsx2h/PCSX2/sstates)
  pine.py load SLOT         -> load state slot
  pine.py write ADDR HEX    -> write bytes (multiple of 4) to EE memory
Messages: u32 size (incl. header) | u8 opcode | args; replies: u32 size | u8 result | data.
"""
import os, socket, struct, sys

SOCK = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'pcsx2.sock')

def call(op, args=b''):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(SOCK)
    s.sendall(struct.pack('<IB', 5 + len(args), op) + args)
    head = s.recv(5)
    size, res = struct.unpack('<IB', head)
    data = b''
    while len(data) < size - 5:
        data += s.recv(size - 5 - len(data))
    s.close()
    if res:
        raise IOError('PINE error %d' % res)
    return data

def read32(addr):
    return struct.unpack('<I', call(2, struct.pack('<I', addr)))[0]

def read(addr, n):
    out = b''
    for a in range(addr, addr + n, 4):
        out += struct.pack('<I', read32(a))
    return out[:n]

def write32(addr, v):
    call(6, struct.pack('<II', addr, v))

def write(addr, data):
    for k in range(0, len(data), 4):
        write32(addr + k, struct.unpack_from('<I', data, k)[0])

def status():
    return {0: 'running', 1: 'paused', 2: 'shutdown'}.get(struct.unpack('<I', call(0xF))[0], '?')

def string(op):
    d = call(op)
    n = struct.unpack('<I', d[:4])[0]
    return d[4:4 + n].rstrip(b'\0').decode('utf-8', 'replace')

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'status':
        print(status())
    elif cmd == 'read':
        a = int(sys.argv[2], 0)
        print(read(a, int(sys.argv[3], 0) if len(sys.argv) > 3 else 16).hex(' '))
    elif cmd == 'load':
        call(10, struct.pack('<B', int(sys.argv[2])))
    elif cmd == 'write':
        write(int(sys.argv[2], 0), bytes.fromhex(sys.argv[3]))
    elif cmd == 'save':
        call(9, struct.pack('<B', int(sys.argv[2])))
    elif cmd in ('title', 'id'):
        print(string(0xB if cmd == 'title' else 0xC))
