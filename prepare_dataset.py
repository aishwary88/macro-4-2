"""
prepare_dataset.py
Converts google_images/ (Pascal VOC XML) to YOLO format dataset.
All plate-number labels are normalized to a single class: "plate"
Splits 80/20 train/val and creates data.yaml for YOLOv8 training.
"""

import os
import glob
import shutil
import random
import xml.etree.ElementTree as ET
from pathlib import Path

SRC_DIR     = Path("google_images")
DATASET_DIR = Path("dataset")
TRAIN_RATIO = 0.8
SEED        = 42
CLASS_NAME  = "plate"
CLASS_ID    = 0

# ── Create directory structure ────────────────────────────────────────
for split in ("train", "val"):
    (DATASET_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

print("Dataset directories created.")

# ── Collect all paired (image, xml) files ────────────────────────────
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

xml_files = list(SRC_DIR.glob("*.xml"))
pairs = []

for xml_path in xml_files:
    # Find matching image (same stem, any image extension)
    stem = xml_path.stem
    img_path = None
    for ext in IMAGE_EXTS:
        candidate = SRC_DIR / (stem + ext)
        if candidate.exists():
            img_path = candidate
            break
    if img_path is None:
        # Try case-insensitive extensions
        for f in SRC_DIR.iterdir():
            if f.stem == stem and f.suffix.lower() in IMAGE_EXTS:
                img_path = f
                break
    if img_path:
        pairs.append((img_path, xml_path))

print(f"Found {len(pairs)} image+annotation pairs.")

# ── Parse XML and convert to YOLO format ─────────────────────────────
def parse_voc_xml(xml_path):
    """Parse Pascal VOC XML, return (width, height, list of boxes).
    Each box: (class_id, cx, cy, w, h) normalized 0-1.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size = root.find("size")
    img_w = int(size.find("width").text)
    img_h = int(size.find("height").text)

    if img_w == 0 or img_h == 0:
        return None

    boxes = []
    for obj in root.findall("object"):
        bndbox = obj.find("bndbox")
        xmin = float(bndbox.find("xmin").text)
        ymin = float(bndbox.find("ymin").text)
        xmax = float(bndbox.find("xmax").text)
        ymax = float(bndbox.find("ymax").text)

        # Clamp to image bounds
        xmin = max(0, min(xmin, img_w))
        xmax = max(0, min(xmax, img_w))
        ymin = max(0, min(ymin, img_h))
        ymax = max(0, min(ymax, img_h))

        if xmax <= xmin or ymax <= ymin:
            continue

        cx = ((xmin + xmax) / 2) / img_w
        cy = ((ymin + ymax) / 2) / img_h
        bw = (xmax - xmin) / img_w
        bh = (ymax - ymin) / img_h

        boxes.append((CLASS_ID, cx, cy, bw, bh))

    return boxes

# ── Filter valid pairs ────────────────────────────────────────────────
valid_pairs = []
skipped = 0
for img_path, xml_path in pairs:
    boxes = parse_voc_xml(xml_path)
    if boxes is None or len(boxes) == 0:
        skipped += 1
        continue
    valid_pairs.append((img_path, xml_path, boxes))

print(f"Valid pairs: {len(valid_pairs)}  |  Skipped (no boxes): {skipped}")

# ── Split train/val ───────────────────────────────────────────────────
random.seed(SEED)
random.shuffle(valid_pairs)

split_idx  = int(len(valid_pairs) * TRAIN_RATIO)
train_set  = valid_pairs[:split_idx]
val_set    = valid_pairs[split_idx:]

print(f"Train: {len(train_set)}  |  Val: {len(val_set)}")

# ── Copy files ────────────────────────────────────────────────────────
def write_split(pairs_list, split_name):
    img_dir = DATASET_DIR / "images" / split_name
    lbl_dir = DATASET_DIR / "labels" / split_name
    for img_path, xml_path, boxes in pairs_list:
        # Copy image
        dst_img = img_dir / img_path.name
        shutil.copy2(img_path, dst_img)
        # Write YOLO label txt
        label_name = img_path.stem + ".txt"
        dst_lbl = lbl_dir / label_name
        with open(dst_lbl, "w") as f:
            for cls, cx, cy, bw, bh in boxes:
                f.write(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")

write_split(train_set, "train")
write_split(val_set,   "val")
print("Files copied.")

# ── Write data.yaml ───────────────────────────────────────────────────
yaml_content = f"""# YOLOv8 dataset config — Indian License Plate Detection
path: {DATASET_DIR.resolve().as_posix()}
train: images/train
val:   images/val

nc: 1
names:
  0: {CLASS_NAME}
"""

yaml_path = DATASET_DIR / "data.yaml"
yaml_path.write_text(yaml_content)
print(f"data.yaml written → {yaml_path}")

# ── Quick sanity check ────────────────────────────────────────────────
train_imgs = list((DATASET_DIR / "images" / "train").iterdir())
val_imgs   = list((DATASET_DIR / "images" / "val").iterdir())
train_lbls = list((DATASET_DIR / "labels" / "train").iterdir())
val_lbls   = list((DATASET_DIR / "labels" / "val").iterdir())

print("\n=== Dataset Summary ===")
print(f"Train images : {len(train_imgs)}")
print(f"Train labels : {len(train_lbls)}")
print(f"Val   images : {len(val_imgs)}")
print(f"Val   labels : {len(val_lbls)}")
print(f"Classes      : 1  ({CLASS_NAME})")
print(f"data.yaml    : {yaml_path}")
print("\nDataset ready. Run training with:")
print("  python train_plate.py")
