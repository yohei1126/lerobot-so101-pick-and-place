"""ACT policy factory aligned with configs/contract.yaml."""

from __future__ import annotations

from typing import Any

from lerobot.configs.types import FeatureType, PolicyFeature
from lerobot.policies.act.configuration_act import ACTConfig
from lerobot.policies.act.modeling_act import ACTPolicy

from port_pick_align.contract import validate_contract


def build_act_policy(
    contract: dict[str, Any],
    *,
    device: str = "cpu",
    dim_model: int = 64,
    n_heads: int = 4,
    dim_feedforward: int = 256,
    n_encoder_layers: int = 2,
    n_decoder_layers: int = 1,
    use_vae: bool = True,
) -> ACTPolicy:
    """Build a small ResNet18 ACT policy for 2-camera / 6-DoF smoke training."""
    validate_contract(contract)
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
        # Avoid downloading ImageNet weights in CI / offline smoke runs.
        pretrained_backbone_weights=None,
        pre_norm=True,
        dim_model=dim_model,
        n_heads=n_heads,
        dim_feedforward=dim_feedforward,
        n_encoder_layers=n_encoder_layers,
        n_decoder_layers=n_decoder_layers,
        use_vae=use_vae,
        temporal_ensemble_coeff=None,
        dropout=0.1,
        device=device,
    )
    return ACTPolicy(config)
