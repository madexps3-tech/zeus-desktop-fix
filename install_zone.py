import base64
import gzip
import sys
from pathlib import Path

root = Path(sys.argv[1].strip().strip('"').rstrip("\\/"))
here = Path(__file__).resolve().parent
blob = "".join((here / ("part%d.txt" % i)).read_text(encoding="utf-8").strip() for i in range(4))
data = gzip.decompress(base64.b64decode(blob))
while data:
    name, data = data.split(b"\n", 1)
    length, data = data.split(b"\n", 1)
    size = int(length)
    body, data = data[:size], data[size:]
    if data.startswith(b"\n"):
        data = data[1:]
    path = root.joinpath(*name.decode().split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    print("WROTE", path.name)
print("ZONE_INSTALLED")
