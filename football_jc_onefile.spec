from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = [("config.json", "."), ("data/demo_sample_data.csv", "data")] + collect_data_files("rapidocr_onnxruntime")
binaries = collect_dynamic_libs("onnxruntime")
hiddenimports = collect_submodules("rapidocr_onnxruntime") + collect_submodules("onnxruntime") + collect_submodules("keyring.backends")
a = Analysis(["app/main.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="FootballJCAssistant", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
