"""
Fix corrupted EURUSD 2024 CSV file
Remove lines with incorrect number of fields
"""
import os
import csv

print("="*60)
print("FIXING EURUSD 2024 CSV FILE")
print("="*60)
print()

input_file = "data/raw/eurusd-tick-2024-01-01-2024-12-31.csv"
output_file = "data/raw/eurusd-tick-2024-01-01-2024-12-31_fixed.csv"
backup_file = "data/raw/eurusd-tick-2024-01-01-2024-12-31_backup.csv"

if not os.path.exists(input_file):
    print(f"❌ File not found: {input_file}")
    exit(1)

# Get file size
file_size_mb = os.path.getsize(input_file) / (1024*1024)
print(f"Input file: {input_file}")
print(f"Size: {file_size_mb:.1f} MB")
print()

# Backup original
print("Creating backup...")
import shutil
shutil.copy2(input_file, backup_file)
print(f"✓ Backup created: {backup_file}")
print()

# Process file
print("Scanning for corrupted lines...")
print("(This may take a few minutes...)")
print()

good_lines = 0
bad_lines = 0
expected_fields = None

with open(input_file, 'r', encoding='utf-8', errors='ignore') as fin:
    with open(output_file, 'w', encoding='utf-8', newline='') as fout:

        for line_num, line in enumerate(fin, 1):
            # Progress indicator every 1M lines
            if line_num % 1000000 == 0:
                print(f"  Processed {line_num:,} lines... (Good: {good_lines:,}, Bad: {bad_lines})")

            # Count fields in this line
            fields = line.strip().split(',')
            num_fields = len(fields)

            # First line (header) - determine expected field count
            if line_num == 1:
                expected_fields = num_fields
                fout.write(line)
                good_lines += 1
                print(f"Header: {num_fields} fields expected")
                print(f"Columns: {', '.join(fields)}")
                print()
                continue

            # Check if this line has correct number of fields
            if num_fields == expected_fields:
                fout.write(line)
                good_lines += 1
            else:
                bad_lines += 1
                if bad_lines <= 10:  # Show first 10 bad lines
                    print(f"  Line {line_num}: {num_fields} fields (expected {expected_fields})")
                    print(f"    Content: {line[:100]}...")

print()
print("="*60)
print("RESULTS")
print("="*60)
print(f"Total lines processed: {line_num:,}")
print(f"Good lines: {good_lines:,}")
print(f"Bad lines removed: {bad_lines}")
print(f"Success rate: {(good_lines/line_num)*100:.2f}%")
print()

if bad_lines > 0:
    print(f"✓ Fixed file saved to: {output_file}")
    print()

    # Replace original with fixed
    print("Replacing original with fixed version...")
    os.remove(input_file)
    os.rename(output_file, input_file)
    print(f"✓ Original file updated")
    print(f"✓ Backup available at: {backup_file}")
else:
    print("✓ No corrupted lines found - file is clean")
    os.remove(output_file)

print()
print("="*60)
print("✅ FILE REPAIR COMPLETE")
print("="*60)

