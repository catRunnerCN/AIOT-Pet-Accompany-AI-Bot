#!/usr/bin/env python3
"""Generate dog emotion predictions for every image inside a directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import torch
from PIL import Image

from dog_emotion_model import build_transforms, create_model

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict dog emotions for a folder of photos.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.cwd()/"testpic",
        help="Directory that holds dog images (defaults to repository root).",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path.cwd() / "models" / "dog_emotion_cnn.pth",
        help="Path to the trained model weights.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path.cwd() / "models" / "metadata.json",
        help="Path to the metadata JSON exported by the notebook.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / "predictions.json",
        help="File to write predictions to.",
    )
    return parser.parse_args()


def load_metadata(metadata_path: Path) -> Dict:
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
    return json.loads(metadata_path.read_text())


def gather_images(input_dir: Path) -> List[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    images = [path for path in input_dir.rglob("*") if path.suffix.lower() in IMAGE_EXTENSIONS]
    if not images:
        raise ValueError(f"No supported image files found under {input_dir}")
    return sorted(images)


def load_model(weights: Path, class_names: List[str]) -> torch.nn.Module:
    if not weights.exists():
        raise FileNotFoundError(f"Model weights not found: {weights}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model(num_classes=len(class_names)).to(device)
    state_dict = torch.load(weights, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def predict(
    model: torch.nn.Module,
    image_paths: List[Path],
    class_names: List[str],
    image_size,
    base_dir: Path,
) -> List[Dict]:
    device = next(model.parameters()).device
    transform = build_transforms(image_size=image_size, augment=False)
    predictions: List[Dict] = []
    for image_path in image_paths:
        image = Image.open(image_path).convert("RGB")
        tensor = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=1)
            confidence, index = torch.max(probs, dim=1)
        try:
            relative_path = str(image_path.relative_to(base_dir))
        except ValueError:
            relative_path = str(image_path)
        predictions.append(
            {
                "image": relative_path,
                "label": class_names[index.item()],
                "confidence": round(float(confidence.item()), 4),
            }
        )
    return predictions


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    weights = args.weights.resolve()
    metadata_path = args.metadata.resolve()
    output_path = args.output.resolve()
    metadata = load_metadata(metadata_path)
    class_names = metadata.get("class_names")
    if not class_names:
        raise ValueError("Metadata is missing class names.")
    image_size = tuple(metadata.get("image_size", (224, 224)))
    image_paths = gather_images(input_dir)
    model = load_model(weights, class_names)
    results = predict(model, image_paths, class_names, image_size, input_dir)
    output_path.write_text(json.dumps(results, indent=2))
    print(f"Saved {len(results)} predictions to {output_path}")


if __name__ == "__main__":
    main()
