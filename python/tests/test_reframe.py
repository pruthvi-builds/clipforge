from clipforge.models import VideoMeta
from clipforge.video.reframe import plan_crop
from clipforge.video.render import build_filtergraph, RenderRequest
from clipforge.config import Settings


def _horizontal_meta() -> VideoMeta:
    return VideoMeta(
        path="x.mp4", duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True,
    )


def test_fit_mode_keeps_full_frame_no_crop():
    meta = _horizontal_meta()
    plan = plan_crop(meta, 0.0, 10.0, [], mode="fit", out_w=1080, out_h=1920)
    assert plan.fit is True
    assert plan.crop_w == meta.width
    assert plan.crop_h == meta.height
    assert plan.static is True


def test_center_mode_still_crops_horizontal_source():
    meta = _horizontal_meta()
    plan = plan_crop(meta, 0.0, 10.0, [], mode="center", out_w=1080, out_h=1920)
    assert plan.fit is False
    assert plan.crop_w < meta.width


def test_fit_mode_filtergraph_pads_instead_of_cropping(tmp_path):
    meta = _horizontal_meta()
    plan = plan_crop(meta, 0.0, 10.0, [], mode="fit", out_w=1080, out_h=1920)
    req = RenderRequest(
        src_video=tmp_path / "src.mp4",
        out_path=tmp_path / "out.mp4",
        start=0.0,
        end=10.0,
        plan=plan,
        ass_path=None,
        enhanced_audio=None,
        settings=Settings(),
        meta=meta,
    )
    graph, _ = build_filtergraph(req, tmp_path)
    assert "pad=1080:1920" in graph
    assert "force_original_aspect_ratio=decrease" in graph
    assert "force_original_aspect_ratio=increase" not in graph
