"""ACT policy factory aligned with configs/contract.yaml."""

from __future__ import annotations

from typing import Any

from lerobot.configs.types import FeatureType, PolicyFeature
from lerobot.policies.act.configuration_act import ACTConfig
from lerobot.policies.act.modeling_act import ACTPolicy

from port_pick_align.contract import validate_contract

# smoke: CI / synthetic API check. full: Phase 1.5 sim-expert closed-loop target.
ARCH_PRESETS: dict[str, dict[str, Any]] = {
    "smoke": {
        "dim_model": 64,
        "n_heads": 4,
        "dim_feedforward": 256,
        "n_encoder_layers": 2,
        "n_decoder_layers": 1,
        "pretrained_backbone_weights": None,
    },
    "full": {
        "dim_model": 256,
        "n_heads": 8,
        "dim_feedforward": 1024,
        "n_encoder_layers": 4,
        "n_decoder_layers": 1,
        "pretrained_backbone_weights": "ResNet18_Weights.IMAGENET1K_V1",
    },
}


def resolve_arch(name: str) -> dict[str, Any]:
    key = name.strip().lower()
    if key not in ARCH_PRESETS:
        raise ValueError(f"Unknown arch {name!r}. Expected one of {sorted(ARCH_PRESETS)}.")
    return dict(ARCH_PRESETS[key])


def build_act_policy(
    contract: dict[str, Any],
    *,
    device: str = "cpu",
    arch: str = "smoke",
    dim_model: int | None = None,
    n_heads: int | None = None,
    dim_feedforward: int | None = None,
    n_encoder_layers: int | None = None,
    n_decoder_layers: int | None = None,
    use_vae: bool = True,
    pretrained_backbone_weights: str | None | object = ...,
) -> ACTPolicy:
    """Build a ResNet18 ACT policy for 2-camera / 6-DoF training.

    ``arch=smoke`` keeps the small CI network. ``arch=full`` is for sim-expert
    Phase 1.5 training. Explicit dimension kwargs override the preset.
    """
    validate_contract(contract)
    preset = resolve_arch(arch)
    resolved = {
        "dim_model": dim_model if dim_model is not None else preset["dim_model"],
        "n_heads": n_heads if n_heads is not None else preset["n_heads"],
        "dim_feedforward": (
            dim_feedforward if dim_feedforward is not None else preset["dim_feedforward"]
        ),
        "n_encoder_layers": (
            n_encoder_layers if n_encoder_layers is not None else preset["n_encoder_layers"]
        ),
        "n_decoder_layers": (
            n_decoder_layers if n_decoder_layers is not None else preset["n_decoder_layers"]
        ),
        "pretrained_backbone_weights": (
            preset["pretrained_backbone_weights"]
            if pretrained_backbone_weights is ...
            else pretrained_backbone_weights
        ),
        "arch": arch,
    }
    top = contract["cameras"]["top"]
    visual_shape = (int(top["channels"]), int(top["height"]), int(top["width"]))
    action_dim = int(contract["model"]["action_dim"])
    chunk_size = int(contract["model"]["chunk_size"])
    backbone = str(contract["model"]["vision_backbone"])

    config = ACTConfig(
        input_features={
            "observation.images.top": PolicyFeature(FeatureType.VISUAL, visual_shape),
            "observation.images.wrist": PolicyFeature(FeatureType.VISUAL, visual_shape),
            "observation.state": PolicyFeature(FeatureType.STATE, (action_dim,)),
        },
        output_features={
            "action": PolicyFeature(FeatureType.ACTION, (action_dim,)),
        },
        chunk_size=chunk_size,
        n_action_steps=1,
        vision_backbone=backbone,
        pretrained_backbone_weights=resolved["pretrained_backbone_weights"],
        pre_norm=True,
        dim_model=int(resolved["dim_model"]),
        n_heads=int(resolved["n_heads"]),
        dim_feedforward=int(resolved["dim_feedforward"]),
        n_encoder_layers=int(resolved["n_encoder_layers"]),
        n_decoder_layers=int(resolved["n_decoder_layers"]),
        use_vae=use_vae,
        temporal_ensemble_coeff=None,
        dropout=0.1,
        device=device,
    )
    policy = ACTPolicy(config)
    policy._port_pick_align_arch = resolved  # type: ignore[attr-defined]
    return policy
