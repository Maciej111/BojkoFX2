import shutil
from pathlib import Path

dest = Path(r'C:\dev\projects\BojkoFx\data\raw_dl')
# dukascopy-node tworzy podkatalog 'download/' względem CWD — szukamy rekurencyjnie
base = Path(r'C:\dev\projects\BojkoFx\data\raw_dl')
copied = []
for f in base.rglob('*.csv'):
    if f.parent == dest:
        continue  # skip files already in dest
    dst = dest / f.name
    if not dst.exists() or dst.stat().st_size < f.stat().st_size:
        shutil.copy2(f, dst)
        copied.append(f.name)

print(f'Copied: {len(copied)}')
for fn in sorted(copied):
    print(f'  {fn}')
print()
print('All CSV in raw_dl:')
for f in sorted(dest.glob('*.csv')):
    print(f'  {f.stat().st_size:>10,}  {f.name}')
