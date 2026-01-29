"""Shared model definitions and transforms for the dog emotion project."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import torch
from torch import nn
from torchvision import models, transforms
from torchvision.models import VGG16_Weights


@dataclass(frozen=True)
class ModelConfig:
    image_size: Tuple[int, int] = (224, 224)
    dropout: float = 0.4
    freeze_backbone: bool = True
    pretrained: bool = True


def build_transforms(image_size: Tuple[int, int] = (224, 224), augment: bool = True) -> transforms.Compose:
    """Create torchvision transforms for training or evaluation."""
    resize = transforms.Resize(image_size)
    augmentation: list = []
    if augment:
        augmentation.extend(
            [
                transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3),
                transforms.RandomRotation(15),
            ]
        )
    return transforms.Compose(
        [resize]
        + augmentation
        + [
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )


class DogEmotionVGG(nn.Module):
    """Transfer-learning classifier on top of a pretrained VGG16 backbone."""

    def __init__(
        self,
        num_classes: int,
        dropout: float = 0.4,
        pretrained: bool = True,
        freeze_backbone: bool = True,
    ) -> None:
        super().__init__()
        weights = VGG16_Weights.IMAGENET1K_V1 if pretrained else None
        self.backbone = models.vgg16(weights=weights)
        if freeze_backbone:
            for parameter in self.backbone.features.parameters():
                parameter.requires_grad = False
        in_features = self.backbone.classifier[-1].in_features
        self.backbone.classifier[-1] = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(in_features, num_classes),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.backbone(inputs)


def create_model(
    num_classes: int,
    dropout: float = ModelConfig.dropout,
    pretrained: bool = ModelConfig.pretrained,
    freeze_backbone: bool = ModelConfig.freeze_backbone,
) -> DogEmotionVGG:
    return DogEmotionVGG(
        num_classes=num_classes,
        dropout=dropout,
        pretrained=pretrained,
        freeze_backbone=freeze_backbone,
    )
