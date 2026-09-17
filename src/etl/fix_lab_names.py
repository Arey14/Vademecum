import csv
import re
import os

csv_path = os.path.join(os.path.dirname(__file__), "vademecum_laboratorios.csv")

def clean_name(slug):
    # Remove numeric ID suffix
    name = re.sub(r'-\d+$', '', slug)
    # Replace hyphens with spaces
    name = name.replace('-', ' ')
    # Capitalize first letter of each word
    name = name.title()
    return name

rows = []
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

fixed = 0
for row in rows:
    url = row['url']
    # Extract slug from URL
    match = re.search(r'/laboratorio/([^/]+)/', url)
    if match:
        slug = match.group(1)
        current_name = row['nombre'].strip()
        
        # Fix empty names
        if not current_name:
            new_name = clean_name(slug)
            row['nombre'] = new_name
            fixed += 1
            continue
        
        # Fix truncated names (start with "s ")
        if current_name.startswith('s '):
            new_name = clean_name(slug)
            row['nombre'] = new_name
            fixed += 1
            continue
        
        # Fix names missing trailing "s" from slug
        slug_no_id = re.sub(r'-\d+$', '', slug)
        if slug_no_id.endswith('s') and not current_name.lower().endswith('s') and len(current_name) > 0:
            new_name = clean_name(slug)
            if new_name != current_name:
                row['nombre'] = new_name
                fixed += 1

with open(csv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['nombre', 'url', 'direccion', 'ciudad', 'provincia', 'telefono', 'productos'])
    writer.writeheader()
    writer.writerows(rows)

print(f"Fixed {fixed} names out of {len(rows)} rows")