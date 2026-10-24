import sys
import os

# wlp-copy.py <src> <dst> [x]
# Copies a file from the Windows mount into the WSL lab, normalizing CRLF to LF.
# Pass "x" as third arg to chmod 755 (for scripts).

src, dst = sys.argv[1], sys.argv[2]
data = open(src, 'rb').read().replace(b'\r\n', b'\n')
open(dst, 'wb').write(data)
if len(sys.argv) > 3 and sys.argv[3] == 'x':
    os.chmod(dst, 0o755)
print('copied {} -> {} ({} bytes, {} lines)'.format(src, dst, len(data), data.count(b'\n')))
