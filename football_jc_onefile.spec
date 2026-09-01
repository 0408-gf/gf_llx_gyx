from PyInstaller.utils.hooks import collect_data_files

datas = [("config.json", "."), ("data/demo_sample_data.csv", "data")]
a = Analysis(["app/main.py"], pathex=["."], binaries=[], datas=datas, hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="FootballJCAssistant", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
