cd "rom scanner"
py -m PyInstaller --onefile --console --noconfirm --name rom-dumper --distpath dist --workpath build --specpath . extract_rom.py
