"""Execute the real boot logic against a fake filesystem/driver, never hardware.

Only filesystem roots and external IO commands are substituted. The readiness,
wait, refusal, exit-status and mode-selection logic comes from S99board itself.
"""
import os
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]


def posix(path):
    path=Path(path).resolve()
    text=path.as_posix()
    return "/mnt/"+text[0].lower()+text[2:] if os.name=="nt" else text


def shell(script,*arguments,env=None):
    command=(["wsl.exe","--exec","/bin/sh"] if os.name=="nt" else ["/bin/sh"])
    return subprocess.run([*command,posix(script),*map(str,arguments)],capture_output=True,
                           env=env,timeout=25)


def fixture(tmp_path,ready_on=1,partial_names=()):
    root=tmp_path/"root"
    files={"etc/board-mode":"rf\n","lib/firmware/ad9361.bin":"test-bitstream",
           "lib/firmware/display.bin":"display","lib/firmware/system_wrapper.bin":"test-bitstream",
           "lib/firmware/pl.dtbo":"test-overlay","lib/firmware/d480p.dtbo":"display-overlay",
           "sys/class/fpga_manager/fpga0/state":"operating\n",
           "sys/class/gpio/gpio914/direction":"out\n","sys/class/gpio/gpio914/value":"0\n",
           "dev/kmsg":"","proc/mounts":f"none {posix(root)}/sys/kernel/config configfs rw 0 0\n"}
    for relative,text in files.items():
        path=root/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding="utf-8",newline="\n")
    (root/"sys/kernel/config/device-tree/overlays").mkdir(parents=True)
    (root/"sys/bus/iio/devices").mkdir(parents=True)
    tools=tmp_path/"bin"
    tools.mkdir()
    cat=f'''#!/bin/sh
if [ "$1" = "{posix(root)}/lib/firmware/pl.dtbo" ]; then
  n=0
  [ ! -f "{posix(root)}/applies" ] || n=$(/bin/cat "{posix(root)}/applies")
  n=$((n + 1))
  echo "$n" > "{posix(root)}/applies"
  if [ "$n" -ge {ready_on} ]; then
    for pair in 7:ad9361-phy 11:cf-ad9361-lpc 13:cf-ad9361-dds-core-lpc; do
      id=${{pair%%:*}}; name=${{pair#*:}}
      /bin/mkdir -p "{posix(root)}/sys/bus/iio/devices/iio:device$id"
      echo "$name" > "{posix(root)}/sys/bus/iio/devices/iio:device$id/name"
    done
  else
    index=20
    for name in {' '.join(partial_names)}; do
      /bin/mkdir -p "{posix(root)}/sys/bus/iio/devices/iio:device$index"
      echo "$name" > "{posix(root)}/sys/bus/iio/devices/iio:device$index/name"
      index=$((index + 1))
    done
  fi
fi
exec /bin/cat "$@"
'''
    rmdir=f'''#!/bin/sh
[ "$1" = "{posix(root)}/sys/kernel/config/device-tree/overlays/pl" ] || exit 91
echo unsafe > "{posix(root)}/removal-called"
exit 92
'''
    for name,text in {"cat":cat,"rmdir":rmdir,"sleep":"#!/bin/sh\nexit 0\n",
                      "mount":"#!/bin/sh\nexit 0\n"}.items():
        (tools/name).write_text(text,encoding="utf-8",newline="\n")
    # WSL executes these through its filesystem mount; set executable mode there.
    chmod=tmp_path/"chmod.sh"
    chmod.write_text(f'#!/bin/sh\nchmod 755 "{posix(tools)}"/*\n',encoding="utf-8",newline="\n")
    assert shell(chmod).returncode==0
    production=(ROOT/"board/boot/S99board").read_text("utf-8")
    for prefix in ("/sys/","/etc/","/lib/firmware","/dev/","/proc/"):
        production=production.replace(prefix,posix(root)+prefix)
    script=tmp_path/"boot.sh"
    script.write_text(production,encoding="utf-8",newline="\n")
    # Pass PATH in the shell, avoiding Windows/WSL environment translation.
    runner=tmp_path/"run.sh"
    runner.write_text(f'#!/bin/sh\nPATH="{posix(tools)}:/usr/bin:/bin"; export PATH\nexec /bin/sh "{posix(script)}" "$@"\n',encoding="utf-8",newline="\n")
    return root,runner


def test_one_apply_succeeds_only_when_phy_adc_and_dds_all_exist(tmp_path):
    root,runner=fixture(tmp_path)
    result=shell(runner)
    assert result.returncode==0,result.stdout.decode(errors="replace")+result.stderr.decode(errors="replace")
    assert int((root/"applies").read_text())==1
    assert b"PHY/ADC/DDS names verified (attempt 1)" in result.stdout
    assert not (root/"removal-called").exists()


@pytest.mark.parametrize("names",[[],["ad9361-phy"],["cf-ad9361-lpc"],
    ["cf-ad9361-dds-core-lpc"],["ad9361-phy","cf-ad9361-lpc"]])
def test_incomplete_probe_never_unloads_or_retries(tmp_path,names):
    root,runner=fixture(tmp_path,ready_on=10,partial_names=names)
    result=shell(runner)
    assert result.returncode!=0
    assert (root/"applies").read_text().strip()=="1"
    assert not (root/"removal-called").exists()
    assert b"hot removal disabled; reboot required" in result.stdout
    assert b"bring-up complete" not in result.stdout


@pytest.mark.parametrize("slot",["pl","other-overlay"])
def test_repeated_start_cannot_reconfigure_an_existing_overlay(tmp_path,slot):
    root,runner=fixture(tmp_path)
    (root/"sys/kernel/config/device-tree/overlays"/slot).mkdir()
    firmware=root/"sys/class/fpga_manager/fpga0/firmware"
    firmware.write_bytes(b"sentinel")
    staged=root/"lib/firmware/system_wrapper.bin"
    staged.write_bytes(b"also-must-not-be-replaced")
    result=shell(runner)
    assert result.returncode!=0
    assert b"overlay already present" in result.stdout
    assert firmware.read_bytes()==b"sentinel"
    assert staged.read_bytes()==b"also-must-not-be-replaced"
    assert not (root/"applies").exists()
    assert not (root/"removal-called").exists()


@pytest.mark.parametrize("name",["ad9361-phy","cf-ad9361-lpc","cf-ad9361-dds-core-lpc"])
def test_rf_device_without_visible_overlay_also_blocks_reconfiguration(tmp_path,name):
    root,runner=fixture(tmp_path)
    prepare=tmp_path/"prepare.sh"
    folder=root/"sys/bus/iio/devices/iio:device77"
    prepare.write_text(f'mkdir -p "{posix(folder)}"\necho {name} > "{posix(folder)}/name"\n',encoding="utf-8",newline="\n")
    assert shell(prepare).returncode==0
    result=shell(runner)
    assert result.returncode!=0
    assert b"RF device already present" in result.stdout
    assert not (root/"sys/class/fpga_manager/fpga0/firmware").exists()
    assert not (root/"applies").exists()


@pytest.mark.parametrize("names",[["xadc"],["ad9361-phy"],["ad9361-phy","cf-ad9361-lpc"]])
def test_device1_or_phy_alone_is_not_ready(tmp_path,names):
    root,runner=fixture(tmp_path)
    # Names containing ':' are Linux sysfs names; create them through the
    # POSIX test host rather than Windows' alternate-data-stream path parser.
    prepare=tmp_path/"prepare.sh"
    lines=["#!/bin/sh"]
    for index,name in enumerate(names,1):
        folder=root/f"sys/bus/iio/devices/iio:device{index}"
        lines += [f'mkdir -p "{posix(folder)}"',f'echo "{name}" > "{posix(folder)}/name"']
    prepare.write_text("\n".join(lines)+"\n",encoding="utf-8",newline="\n")
    assert shell(prepare).returncode==0
    before=(root/"sys/class/gpio/gpio914/value").read_bytes()
    result=shell(runner,"--check-rf")
    assert result.returncode==1
    assert (root/"sys/class/gpio/gpio914/value").read_bytes()==before
    assert not (root/"applies").exists()


def test_invalid_mode_fails_before_fabric_reconfiguration(tmp_path):
    root,runner=fixture(tmp_path)
    (root/"etc/board-mode").write_text("typo\n",encoding="utf-8")
    result=shell(runner)
    assert result.returncode!=0
    assert b"invalid mode" in result.stdout
    assert not (root/"applies").exists()
