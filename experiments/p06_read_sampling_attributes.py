"""Read only: compare PHY and ADC sampling-frequency attributes on the P201."""
from pathlib import Path
from datetime import datetime, timezone
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfsig.iio_runtime import use_libiio

OUT = ROOT / "results/p06-sampling-attributes-20261011.json"
if OUT.exists():
    raise RuntimeError("Existing evidence retained; refusing overwrite")
report = {"at_utc": datetime.now(timezone.utc).isoformat(),
          "uri": "ip:192.168.2.1", "writes": False, "buffer_created": False,
          "devices": []}
with use_libiio(Path(r"D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin")):
    import iio
    ctx = iio.Context(report["uri"])
    ctx.set_timeout(3000)
    if ctx.attrs.get("hw_model") != "PUZHI PZSDR P201":
        raise RuntimeError("Unexpected board")
    report["context"] = {k: ctx.attrs.get(k) for k in ("hw_model", "fw_version", "local,kernel")}
    for device_name in ("ad9361-phy", "cf-ad9361-lpc"):
        dev = ctx.find_device(device_name)
        if dev is None:
            raise RuntimeError("Expected device missing")
        item = {"name": dev.name, "id": dev.id, "attributes": {}, "channels": []}
        for name in dev.attrs:
            if "sampling_frequency" in name:
                item["attributes"][name] = dev.attrs[name].value
        for channel in dev.channels:
            if channel.output:
                continue
            attrs = {name: channel.attrs[name].value for name in channel.attrs
                     if "sampling_frequency" in name}
            item["channels"].append({"id": channel.id, "name": channel.name, "attributes": attrs})
        report["devices"].append(item)
    del ctx
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
