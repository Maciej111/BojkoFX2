"""One-off script to reorganize raw FX CSV data into data/raw_dl_fx/download/m30/"""
import os
import shutil

SRC = r'C:\dev\projects\BojkoFx\data\raw_dl'
DST_M30 = r'C:\dev\projects\BojkoFx\data\raw_dl_fx\download\m30'

os.makedirs(DST_M30, exist_ok=True)

copied = {}   # filename -> first source path
skipped = []  # duplicates

for root, dirs, files in os.walk(SRC):
    for f in files:
        if '_m30_' in f and f.endswith('.csv'):
            dst_path = os.path.join(DST_M30, f)
            src_path = os.path.join(root, f)
            if f not in copied:
                shutil.copy2(src_path, dst_path)
                copied[f] = src_path
                print(f'  [COPY] {f}  <-  {root}')
            else:
                skipped.append(src_path)
                print(f'  [SKIP dup] {src_path}')

print()
print(f'Done. {len(copied)} unique files copied to {DST_M30}')
if skipped:
    print(f'{len(skipped)} duplicate(s) skipped.')

