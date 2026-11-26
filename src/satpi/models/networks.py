"""Neural components (requires the `ml` extra: pip install -e ".[ml]").

Two networks:

1. `PerceptionHead` — a segmentation head attached to a frozen-or-finetuned
   GFM backbone (Clay v1.5 / Prithvi-EO-2.0 loaded via TerraTorch/TorchGeo at
   training time; the backbone is injected, not hard-coded, so the empirical
   sensor-vs-model selection from the benchmark phase is a config choice).

2. `PhysicsDownscaler` — residual U-Net that maps the coarse solver field +
   fine static layers to 10 m depth. Trained with `composite_loss`, which adds
   differentiable versions of the physics penalties in models/physics.py.

Everything here is import-guarded: the core platform, API, solver, and tests
run without torch installed.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised only with the ml extra
    import torch
    import torch.nn as nn
    import torch.nn.functional as F  # noqa: N812  (torch convention)

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    TORCH_AVAILABLE = False
    torch = None  # type: ignore[assignment]


def _require_torch() -> None:
    if not TORCH_AVAILABLE:
        raise ImportError("this component requires the ml extra: pip install 'satpi[ml]'")


if TORCH_AVAILABLE:  # pragma: no cover

    class ConvBlock(nn.Module):
        def __init__(self, c_in: int, c_out: int) -> None:
            super().__init__()
            self.block = nn.Sequential(
                nn.Conv2d(c_in, c_out, 3, padding=1, bias=False),
                nn.BatchNorm2d(c_out),
                nn.GELU(),
                nn.Conv2d(c_out, c_out, 3, padding=1, bias=False),
                nn.BatchNorm2d(c_out),
                nn.GELU(),
            )

        def forward(self, x):  # noqa: ANN001, ANN201
            return self.block(x)

    class PerceptionHead(nn.Module):
        """Segmentation head over injected GFM features.

        backbone: any module mapping (B, C_in, H, W) -> (B, C_feat, H/p, W/p).
        Classes: 0 background, 1 open-water flood, 2 urban flood (separate
        class per the urban under-observation strategy).
        """

        def __init__(self, backbone: nn.Module, feat_channels: int, n_classes: int = 3) -> None:
            super().__init__()
            self.backbone = backbone
            self.decode = nn.Sequential(
                ConvBlock(feat_channels, 128),
                nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
                ConvBlock(128, 64),
                nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
                nn.Conv2d(64, n_classes, 1),
            )

        def forward(self, x):  # noqa: ANN001, ANN201
            feats = self.backbone(x)
            logits = self.decode(feats)
            if logits.shape[-2:] != x.shape[-2:]:
                logits = F.interpolate(
                    logits, size=x.shape[-2:], mode="bilinear", align_corners=False
                )
            return logits

    class PhysicsDownscaler(nn.Module):
        """Coarse depth + fine static layers -> fine depth (residual learning).

        Inputs: coarse depth upsampled to fine grid (1ch) concatenated with
        static channels (DEM, HAND, imperviousness, ... — count from config).
        Output: non-negative fine depth; softplus keeps positivity smooth.
        The network predicts a *residual redistribution* around the physical
        prior, which is what keeps it honest and data-efficient.
        """

        def __init__(self, static_channels: int, width: int = 64) -> None:
            super().__init__()
            c_in = 1 + static_channels
            self.enc1 = ConvBlock(c_in, width)
            self.enc2 = ConvBlock(width, width * 2)
            self.dec1 = ConvBlock(width * 2 + width, width)
            self.out = nn.Conv2d(width, 1, 1)

        def forward(self, coarse_up, static):  # noqa: ANN001, ANN201
            x = torch.cat([coarse_up, static], dim=1)
            e1 = self.enc1(x)
            e2 = self.enc2(F.max_pool2d(e1, 2))
            up = F.interpolate(e2, scale_factor=2, mode="bilinear", align_corners=False)
            d1 = self.dec1(torch.cat([up, e1], dim=1))
            residual = self.out(d1)
            return F.softplus(coarse_up + residual) - F.softplus(torch.zeros_like(residual))

    # -- differentiable physics penalties (torch twins of models/physics.py) --

    def mass_conservation_loss(fine, coarse, scale: int):  # noqa: ANN001, ANN201
        b, _, hf, wf = fine.shape
        agg = F.avg_pool2d(fine, kernel_size=scale)  # mean == sum/scale^2
        wet = (coarse > 1e-4).float()
        rel = torch.abs(agg - coarse) / (coarse + 1e-6)
        return (rel * wet).sum() / wet.sum().clamp(min=1.0)

    def uphill_flow_loss(fine, dem, tol_m: float = 0.05):  # noqa: ANN001, ANN201
        wse = dem + fine
        wet = (fine > 1e-4).float()
        loss = fine.new_zeros(())
        for dim in (-1, -2):
            k = wse.shape[dim] - 1
            wse_a, wse_b = wse.narrow(dim, 0, k), wse.narrow(dim, 1, k)
            dem_a, dem_b = dem.narrow(dim, 0, k), dem.narrow(dim, 1, k)
            wet_a, wet_b = wet.narrow(dim, 0, k), wet.narrow(dim, 1, k)
            # wet -> dry-lower-neighbor overshoot, both directions
            loss = loss + (wet_a * (1 - wet_b) * F.relu(wse_a - dem_b - tol_m)).mean()
            loss = loss + (wet_b * (1 - wet_a) * F.relu(wse_b - dem_a - tol_m)).mean()
        return loss

    def composite_loss(
        pred_fine,  # noqa: ANN001
        target_fine,  # noqa: ANN001
        target_weight,  # noqa: ANN001  per-pixel tier/reliability weights
        coarse,  # noqa: ANN001
        dem_fine,  # noqa: ANN001
        scale: int,
        lambda_mass: float = 0.1,
        lambda_terrain: float = 0.1,
    ) -> dict[str, Any]:
        """Supervised (tier-weighted) + physics-consistency training loss."""
        sup = (target_weight * F.smooth_l1_loss(pred_fine, target_fine, reduction="none")).mean()
        l_mass = mass_conservation_loss(pred_fine, coarse, scale)
        l_terr = uphill_flow_loss(pred_fine, dem_fine)
        total = sup + lambda_mass * l_mass + lambda_terrain * l_terr
        return {"total": total, "supervised": sup, "mass": l_mass, "terrain": l_terr}
