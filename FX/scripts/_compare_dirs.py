from pathlib import Path
import hashlib

pairs = {
    'raw_dl':             Path(r'C:\dev\projects\BojkoFx\data\raw_dl'),
    'raw_dl_fx/m30':      Path(r'C:\dev\projects\BojkoFx\data\raw_dl_fx\download\m30'),
}

for label, folder in pairs.items():
    files = sorted(folder.glob('*.csv'))
    total_size = sum(f.stat().st_size for f in files)
    print(f"\n[{label}]  {len(files)} files  |  {total_size/1024/1024:.1f} MB")

# Per-file comparison
print("\n--- Per-file size comparison (raw_dl vs raw_dl_fx/m30) ---")
a_dir = pairs['raw_dl']
b_dir = pairs['raw_dl_fx/m30']
a_files = {f.name: f for f in sorted(a_dir.glob('*.csv'))}
b_files = {f.name: f for f in sorted(b_dir.glob('*.csv'))}

all_names = sorted(set(a_files) | set(b_files))
diff_count = 0
for name in all_names:
    a_size = a_files[name].stat().st_size if name in a_files else 0
    b_size = b_files[name].stat().st_size if name in b_files else 0
    same = "==" if a_size == b_size else "!!"
    if same == "!!":
        diff_count += 1
    print(f"  {same}  {name:50s}  raw_dl={a_size:>9}  m30={b_size:>9}")

print(f"\nFiles with size difference: {diff_count}")

