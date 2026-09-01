from PyInstaller.utils.hooks import collect_data_files

datas = [("config.json", "."), ("data/demo_sample_data.csv", "data")]
a = Analysis(["app/main.py"], pathex=["."], binaries=[], datas=datas, hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FootballJCAssistant", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name="FootballJCAssistant")
