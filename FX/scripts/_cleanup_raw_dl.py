import os, glob

txt_files = glob.glob(r'C:\dev\projects\BojkoFx\data\raw_dl\*.txt')
for f in txt_files:
    os.remove(f)
    print('  removed:', os.path.basename(f))
print(f'Removed {len(txt_files)} .txt files.')

