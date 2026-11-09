"""DICOM frames for 2-D models, NRRD/MetaImage volumes for volumetric models, and the detached-data guard.

Every image here is generated in the test (small synthetic arrays, no patient data).
"""

import io
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from app.services import dicom_raster, volume_inference
from app.services.imaging_readers import ImagingReadError, check_attached_data, read_metadata


def _dataset(pixels: np.ndarray, modality="CT", interpretation="MONOCHROME2", frames=1, **tags):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = pydicom.Dataset()
    ds.file_meta = meta
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    if modality:
        ds.Modality = modality
    ds.Rows, ds.Columns = pixels.shape[-3:-1] if interpretation == "RGB" else pixels.shape[-2:]
    ds.PhotometricInterpretation = interpretation
    if interpretation == "RGB":
        ds.SamplesPerPixel, ds.PlanarConfiguration = 3, 0
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    else:
        ds.SamplesPerPixel = 1
        bits = 8 if pixels.dtype == np.uint8 else 16
        ds.BitsAllocated, ds.BitsStored, ds.HighBit = bits, bits, bits - 1
        ds.PixelRepresentation = 1 if pixels.dtype == np.int16 else 0
    if frames > 1:
        ds.NumberOfFrames = frames
    for key, value in tags.items():
        setattr(ds, key, value)
    ds.PixelData = np.ascontiguousarray(pixels).tobytes()
    return ds


def _write(tmp_path: Path, ds, name="frame.dcm") -> Path:
    path = tmp_path / name
    ds.save_as(path, enforce_file_format=True)
    return path


def _ct(values_hu, **tags):
    stored = (np.asarray(values_hu, dtype=np.int32) + 1024).astype(np.uint16)
    return _dataset(stored, RescaleSlope=1, RescaleIntercept=-1024, **tags)


def test_ct_frame_uses_its_voi_window_in_hounsfield_units(tmp_path):
    hu = np.array([[-1000, 0, 40], [80, 120, 2000]])
    frame = dicom_raster.read_frame(_write(tmp_path, _ct(hu, WindowCenter=40, WindowWidth=80)), "HEAD_CT")
    pixels = np.asarray(frame.image)
    assert frame.image.mode == "L" and pixels.shape == (2, 3)
    # LINEAR window (PS3.3 C.11.2.1.2): below the window is 0, above is 255, the centre is mid-grey.
    assert pixels[0, 0] == 0 and pixels[1, 2] == 255 and pixels[1, 1] == 255
    assert 126 <= pixels[0, 2] <= 130
    assert frame.provenance["window"]["source"] == "DICOM_VOI" and frame.provenance["frame_index"] == 0
    assert frame.provenance["pixel_grid"].startswith("Model input pixel (column, row) equals DICOM pixel")


def test_model_declared_window_replaces_the_frame_voi(tmp_path):
    hu = np.array([[0, 40, 80, 400]])
    declared = {"center": 40, "width": 80, "source": "estimated from the training images"}
    frame = dicom_raster.read_frame(_write(tmp_path, _ct(hu, WindowCenter=300, WindowWidth=1500)), "HEAD_CT", declared_window=declared)
    assert np.asarray(frame.image).tolist() == [[0, 128, 255, 255]]
    assert frame.provenance["window"]["source"] == "MODEL_DECLARED_WINDOW"
    assert frame.provenance["window"]["basis"] == "estimated from the training images"


def test_declared_floor_rounding_reproduces_a_truncating_exporter(tmp_path):
    hu = np.arange(-5, 90, dtype=np.int32)[None, :]
    declared = {"center": 40, "width": 80, "rounding": "floor"}
    frame = dicom_raster.read_frame(_write(tmp_path, _ct(hu)), "HEAD_CT", declared_window=declared)
    expected = np.floor(np.clip(hu * 255.0 / 80.0, 0, 255)).astype(np.uint8)
    assert np.array_equal(np.asarray(frame.image), expected)
    # Integer HU through an 80 HU window reach 79 of the inner grey levels 1..254, as measured on the RSNA PNGs.
    full = np.arange(-1000, 1000, dtype=np.int32)[None, :]
    levels = np.unique(np.asarray(dicom_raster.read_frame(_write(tmp_path, _ct(full), "full.dcm"), "HEAD_CT", declared_window=declared).image))
    assert int(((levels > 0) & (levels < 255)).sum()) == 79
    assert frame.provenance["window"]["rounding"] == "floor"


def test_monochrome1_is_inverted_after_windowing(tmp_path):
    stored = np.array([[0, 4095]], dtype=np.uint16)
    ds = _dataset(stored, modality="DX", interpretation="MONOCHROME1", WindowCenter=2048, WindowWidth=4096)
    frame = dicom_raster.read_frame(_write(tmp_path, ds), "XRAY")
    assert np.asarray(frame.image).tolist() == [[255, 0]]
    assert frame.provenance["window"]["monochrome1_inverted"] is True


def test_modality_tag_must_match_the_declared_input_type(tmp_path):
    path = _write(tmp_path, _dataset(np.zeros((2, 2), np.uint16), modality="MR"))
    with pytest.raises(dicom_raster.DicomRasterError, match="DICOM_MODALITY_MISMATCH"):
        dicom_raster.read_frame(path, "CT")


def test_missing_modality_tag_is_accepted_with_a_warning(tmp_path):
    path = _write(tmp_path, _dataset(np.array([[0, 200]], np.uint8), modality=""))
    frame = dicom_raster.read_frame(path, "ENDOSCOPY")
    assert any(item.startswith("DICOM_MODALITY_TAG_ABSENT") for item in frame.provenance["warnings"])


def test_multi_frame_files_need_a_frame_choice(tmp_path):
    stack = np.stack([np.full((2, 2), value, np.uint8) for value in (10, 20, 30)])
    path = _write(tmp_path, _dataset(stack, modality="XA", frames=3))
    with pytest.raises(dicom_raster.DicomRasterError, match="FRAME_INDEX_REQUIRED"):
        dicom_raster.read_frame(path, "ANGIOGRAPHY")
    with pytest.raises(dicom_raster.DicomRasterError, match="FRAME_INDEX_OUT_OF_RANGE"):
        dicom_raster.read_frame(path, "ANGIOGRAPHY", frame_index=3)
    frame = dicom_raster.read_frame(path, "ANGIOGRAPHY", frame_index=2)
    # 8-bit stored values without a VOI are used as stored.
    assert np.asarray(frame.image).tolist() == [[30, 30], [30, 30]]
    assert frame.provenance["frame_count"] == 3 and frame.provenance["window"]["source"] == "STORED_8_BIT_VALUES_NO_VOI"


def test_sixteen_bit_frame_without_voi_uses_its_full_range(tmp_path):
    path = _write(tmp_path, _dataset(np.array([[100, 300, 500]], np.uint16), modality="CR"))
    frame = dicom_raster.read_frame(path, "XRAY")
    assert np.asarray(frame.image).tolist() == [[0, 128, 255]]
    assert frame.provenance["window"]["source"] == "FRAME_FULL_RANGE_NO_VOI"


def test_rgb_frames_are_passed_through_unchanged(tmp_path):
    rgb = np.zeros((2, 2, 3), np.uint8)
    rgb[0, 0] = (200, 30, 40)
    path = _write(tmp_path, _dataset(rgb, modality="ES", interpretation="RGB"))
    frame = dicom_raster.read_frame(path, "ENDOSCOPY", declared_window={"center": 40, "width": 80})
    assert frame.image.mode == "RGB" and np.asarray(frame.image)[0, 0].tolist() == [200, 30, 40]
    assert any(item.startswith("MODEL_DECLARED_WINDOW_NOT_APPLIED") for item in frame.provenance["warnings"])


def test_enhanced_multiframe_rescale_and_window_come_from_the_frame_functional_groups(tmp_path):
    from pydicom.sequence import Sequence

    stored = np.stack([np.array([[1024, 1064], [1104, 3000]], np.uint16), np.array([[0, 40], [80, 2000]], np.uint16)])
    ds = _dataset(stored, frames=2)
    shared = pydicom.Dataset()
    voi = pydicom.Dataset()
    voi.WindowCenter, voi.WindowWidth = 40, 80
    shared.FrameVOILUTSequence = Sequence([voi])
    ds.SharedFunctionalGroupsSequence = Sequence([shared])
    frames = []
    for intercept in (-1024, 0):  # each frame its own rescale; the top level has none
        group = pydicom.Dataset()
        transformation = pydicom.Dataset()
        transformation.RescaleSlope, transformation.RescaleIntercept = 1, intercept
        group.PixelValueTransformationSequence = Sequence([transformation])
        frames.append(group)
    ds.PerFrameFunctionalGroupsSequence = Sequence(frames)
    path = _write(tmp_path, ds)
    first = dicom_raster.read_frame(path, "CT", frame_index=0)
    second = dicom_raster.read_frame(path, "CT", frame_index=1)
    # Both frames hold 0, 40 and 80 HU once their own intercept is applied: the same grey levels.
    assert np.asarray(first.image).tolist() == np.asarray(second.image).tolist()
    assert np.asarray(first.image)[0].tolist()[0] == 0 and np.asarray(first.image)[1, 0] == 255
    assert first.provenance["window"]["source"] == "DICOM_VOI_FRAME_FUNCTIONAL_GROUP"
    assert first.provenance["window"]["rescale_source"] == "FUNCTIONAL_GROUP_RESCALE"


def test_the_viewer_renders_one_frame_of_a_colour_multiframe_file(tmp_path):
    from PIL import Image as PILImage

    from app.services.imaging_readers import render_slice

    rgb = np.zeros((3, 4, 5, 3), np.uint8)
    for index in range(3):
        rgb[index, ..., 0] = 60 * (index + 1)
    ds = _dataset(rgb, modality="ES", interpretation="RGB", frames=3)
    ds.Rows, ds.Columns = 4, 5
    png, info = render_slice(_write(tmp_path, ds), index=2)
    image = np.asarray(PILImage.open(io.BytesIO(png)))
    assert image.shape == (4, 5, 3) and image[0, 0].tolist() == [180, 0, 0]
    assert info["slice_index"] == 2 and info["slice_count"] == 3 and info["window"]["source"] == "COLOUR_AS_DECODED"


def test_a_file_without_pixels_is_refused(tmp_path):
    ds = _dataset(np.zeros((2, 2), np.uint16))
    del ds.PixelData
    with pytest.raises(dicom_raster.DicomRasterError, match="DICOM_NO_PIXEL_DATA"):
        dicom_raster.read_frame(_write(tmp_path, ds), "CT")


# --- NRRD / MetaImage -------------------------------------------------------------------------

def _nrrd(path: Path, extra: str = "", data: bytes = b"\x00" * 8) -> Path:
    header = ("NRRD0004\ntype: uint8\ndimension: 3\nsizes: 2 2 2\nencoding: raw\n" + extra + "\n").encode("ascii")
    path.write_bytes(header + data)
    return path


def test_nrrd_with_detached_data_is_refused(tmp_path):
    secret = tmp_path / "elsewhere.raw"
    secret.write_bytes(b"\x01" * 8)
    for field in (f"data file: {secret}\n", f"datafile: {secret}\n"):
        path = _nrrd(tmp_path / "detached.nrrd", field, data=b"")
        with pytest.raises(ImagingReadError, match="NRRD_DETACHED_DATA_REFUSED"):
            check_attached_data(path)
        with pytest.raises(ImagingReadError, match="NRRD_DETACHED_DATA_REFUSED"):
            read_metadata(path)


def test_nrrd_with_attached_data_passes_the_guard(tmp_path):
    check_attached_data(_nrrd(tmp_path / "attached.nrrd", "# a comment mentioning data file: nothing\n"))


def test_metaimage_must_carry_its_data(tmp_path):
    def mha(element: str) -> Path:
        path = tmp_path / "volume.mha"
        path.write_bytes(("ObjectType = Image\nNDims = 3\nDimSize = 2 2 2\nElementType = MET_UCHAR\n"
                          f"ElementDataFile = {element}\n").encode("ascii") + b"\x00" * 8)
        return path

    check_attached_data(mha("LOCAL"))
    for element in ("C:/somewhere/else.raw", "volume.raw", "LIST"):
        with pytest.raises(ImagingReadError, match="METAIMAGE_DETACHED_DATA_REFUSED"):
            check_attached_data(mha(element))
    # An incoming temporary file has no telling suffix; the container is passed explicitly.
    temporary = tmp_path / ".incoming.part"
    temporary.write_bytes(mha("other.raw").read_bytes())
    with pytest.raises(ImagingReadError, match="METAIMAGE_DETACHED_DATA_REFUSED"):
        check_attached_data(temporary, "METAIMAGE")


ENVELOPE = {"in_plane_spacing_mm": {"min": 0.5, "max": 2.0}, "slice_spacing_mm": {"min": 0.5, "max": 5.0},
            "matrix": {axis: {"min": 2, "max": 512} for axis in "ijk"}, "in_plane_square_pixels": True, "slice_axis_last": False}


def _itk_volume(tmp_path: Path, array_zyx: np.ndarray, spacing=(0.8, 0.8, 2.5), name="volume.nrrd", vector=False) -> Path:
    import SimpleITK as sitk

    image = sitk.GetImageFromArray(array_zyx, isVector=vector)
    image.SetSpacing(spacing)
    path = tmp_path / name
    sitk.WriteImage(image, str(path))
    return path


def test_nrrd_volume_is_read_in_nifti_voxel_order(tmp_path):
    rng = np.random.default_rng(0)
    array = rng.normal(size=(4, 5, 6)).astype(np.float32)  # (z, y, x)
    for name in ("volume.nrrd", "volume.mha"):
        volume = volume_inference.read_itk_volume(_itk_volume(tmp_path, array, name=name), ENVELOPE)
        assert volume.image.shape == (6, 5, 4)  # (i, j, k) = (x, y, z)
        assert volume.image[3, 2, 1] == array[1, 2, 3]
        assert volume.spacing_mm == pytest.approx((0.8, 0.8, 2.5))
        assert volume.warnings[0].startswith("ITK_CONTAINER")


def test_itk_orientation_is_compared_as_nifti_codes(tmp_path):
    array = np.random.default_rng(1).normal(size=(3, 3, 3)).astype(np.float32)
    path = _itk_volume(tmp_path, array, spacing=(1.0, 1.0, 1.0))
    # An identity ITK direction is LPS; the development set below was stored RAS, so the volume is refused.
    with pytest.raises(volume_inference.VolumeInputError, match="ORIENTATION_OUTSIDE_DEVELOPMENT_SET"):
        volume_inference.read_itk_volume(path, {**ENVELOPE, "orientations": ["RAS"]})
    assert volume_inference.read_itk_volume(path, {**ENVELOPE, "orientations": ["LPS"]}).image.shape == (3, 3, 3)


def test_multichannel_models_take_vector_components_in_channel_order(tmp_path):
    array = np.zeros((3, 4, 5, 2), np.float32)  # (z, y, x, component)
    array[..., 0], array[..., 1] = 1.0, 2.0
    array[0, 0, 0] = (5.0, 7.0)
    path = _itk_volume(tmp_path, array, spacing=(1.0, 1.0, 1.0), vector=True)
    volume = volume_inference.read_itk_volume(path, {**ENVELOPE, "channels": ["DWI", "ADC"]})
    assert volume.image.shape == (2, 5, 4, 3)
    assert volume.image[0, 0, 0, 0] == 5.0 and volume.image[1, 0, 0, 0] == 7.0
    with pytest.raises(volume_inference.VolumeInputError, match="CHANNEL_COUNT_MISMATCH"):
        volume_inference.read_itk_volume(path, {**ENVELOPE, "channels": ["FLAIR", "T1", "T1c", "T2"]})


def test_a_ct_series_is_reoriented_exactly_and_its_mask_returns_to_the_series_grid():
    rng = np.random.default_rng(3)
    series = rng.normal(size=(5, 6, 7)).astype(np.float32)  # (slices, rows, columns) as dicom_series assembles
    # Columns run to the patient's left (+x), rows posterior (+y), slices superior (+z): LPS in NIfTI codes.
    affine = np.diag([0.8, 0.9, 2.5, 1.0])
    envelope = {**ENVELOPE, "orientations": ["RAS"], "in_plane_square_pixels": False}
    assert volume_inference.series_axcodes(affine) == "LPS"
    volume = volume_inference.from_series(series, {"column": 0.8, "row": 0.9, "slice": 2.5}, envelope, affine)
    native = np.transpose(series, (2, 1, 0))  # (i = column, j = row, k = slice)
    assert np.array_equal(volume.image, native[::-1, ::-1, :]) and volume.spacing_mm == (0.8, 0.9, 2.5)
    assert volume.reorientation["from"] == "LPS" and volume.reorientation["to"] == "RAS"
    mask = (volume.image > 0).astype(np.uint8)
    restored, on_grid = volume_inference.to_series_grid(mask, volume)
    assert np.array_equal(restored, (native > 0).astype(np.uint8)) and on_grid.spacing_mm == (0.8, 0.9, 2.5)
    # Already in a development orientation: untouched.
    same = volume_inference.from_series(series, {"column": 0.8, "row": 0.9, "slice": 2.5}, {**envelope, "orientations": ["LPS"]}, affine)
    assert same.reorientation is None and np.array_equal(same.image, native)
    # A transposed in-plane layout is permuted, with the spacing following its axis.
    swapped = np.array([[0, 0.9, 0, 0], [0.8, 0, 0, 0], [0, 0, 2.5, 0], [0, 0, 0, 1.0]])  # columns run posterior, rows left
    permuted = volume_inference.from_series(series, {"column": 0.8, "row": 0.9, "slice": 2.5}, {**envelope, "orientations": ["LPS"]}, swapped)
    assert permuted.image.shape == (6, 7, 5) and permuted.spacing_mm == (0.9, 0.8, 2.5)


def test_detached_itk_volume_is_refused_by_the_volume_reader(tmp_path):
    secret = tmp_path / "elsewhere.raw"
    secret.write_bytes(b"\x01" * 8)
    path = _nrrd(tmp_path / "detached.nrrd", f"data file: {secret}\n", data=b"")
    with pytest.raises(volume_inference.VolumeInputError, match="ITK_HEADER_REFUSED"):
        volume_inference.read_itk_volume(path, ENVELOPE)
