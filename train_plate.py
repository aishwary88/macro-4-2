"""
train_plate.py
Trains YOLOv8n on the prepared license plate dataset.
Run prepare_dataset.py first.
"""

from pathlib import Path
from ultralytics import YOLO

DATASET_YAML = Path("dataset/data.yaml")
BASE_MODEL   = Path("models/yolov8n.pt")
OUTPUT_DIR   = Path("models")
EPOCHS       = 50
IMG_SIZE     = 640
BATCH        = 16
PROJECT_NAME = "plate_detector"

if not DATASET_YAML.exists():
    raise FileNotFoundError("dataset/data.yaml not found. Run prepare_dataset.py first.")

print("=" * 50)
print("YOLOv8 License Plate Detector Training")
print("=" * 50)
print(f"Dataset : {DATASET_YAML}")
print(f"Model   : {BASE_MODEL}")
print(f"Epochs  : {EPOCHS}")
print(f"ImgSize : {IMG_SIZE}")
print(f"Batch   : {BATCH}")
print("=" * 50)

model = YOLO(str(BASE_MODEL))

results = model.train(
    data=str(DATASET_YAML),
    epochs=EPOCHS,
    imgsz=IMG_SIZE,
    batch=BATCH,
    name=PROJECT_NAME,
    project=str(OUTPUT_DIR),
    patience=15,          # early stopping
    save=True,
    save_period=10,
    val=True,
    plots=True,
    verbose=True,
)

# ── Save best model to models/ root for easy access ──────────────────
best_weights = OUTPUT_DIR / PROJECT_NAME / "weights" / "best.pt"
final_path   = OUTPUT_DIR / "plate_detector.pt"

if best_weights.exists():
    import shutil
    shutil.copy2(best_weights, final_path)
    print(f"\nBest model saved → {final_path}")
else:
    print(f"\nWeights at: {OUTPUT_DIR / PROJECT_NAME / 'weights'}")

print("\nTraining complete.")
print(f"To use the model: YOLO('{final_path}')")
