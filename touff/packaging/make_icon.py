"""Draw Touff's tray face into a multi-size .ico for the exe and the installer.

    python packaging/make_icon.py packaging/build/touff.ico
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from touff.ui.icon import tray_image  # noqa: E402

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
tray_image(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"icon -> {out}")
