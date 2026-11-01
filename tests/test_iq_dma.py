import numpy as np
import pytest

from rfsig.iq_io import decode_iq_dma_s16, load_iq_csv


def _pack(frames, dtype="<i2"):
    return np.asarray(frames, dtype=dtype).tobytes()


def test_four_channel_decode_picks_the_requested_pair():
    # frames: [I1, Q1, I2, Q2]
    frames = [[10, -10, 99, -99], [20, -20, 98, -98]]
    iq = decode_iq_dma_s16(_pack(frames), channels=4)
    assert iq.shape == (2,)
    np.testing.assert_allclose(iq.real, [10, 20])
    np.testing.assert_allclose(iq.imag, [-10, -20])


def test_four_channel_decode_can_select_the_second_pair():
    frames = [[10, -10, 99, -99], [20, -20, 98, -98]]
    iq = decode_iq_dma_s16(_pack(frames), channels=4, i_index=2, q_index=3)
    np.testing.assert_allclose(iq.real, [99, 98])
    np.testing.assert_allclose(iq.imag, [-99, -98])


def test_two_channel_decode_still_works():
    frames = [[5, -5], [7, -7], [9, -9]]
    iq = decode_iq_dma_s16(_pack(frames), channels=2)
    np.testing.assert_allclose(iq.real, [5, 7, 9])
    np.testing.assert_allclose(iq.imag, [-5, -7, -9])


def test_same_bytes_decoded_as_two_channels_would_be_wrong():
    # This is the trap the docstring warns about: 8192 bytes of a 4-channel
    # dump is 1024 frames, but treating it as 2-channel yields 2048 pairs with
    # interleaved channels.
    frames = [[1, 2, 3, 4], [5, 6, 7, 8]]
    raw = _pack(frames)
    four = decode_iq_dma_s16(raw, channels=4)
    two = decode_iq_dma_s16(raw, channels=2)
    assert four.shape == (2,)
    assert two.shape == (4,)
    # The 2-channel interpretation mixes I2/Q2 into the stream.
    np.testing.assert_allclose(two.real, [1, 3, 5, 7])


def test_twelve_bit_signed_values_survive_the_decode():
    frames = [[-2048, 2047, 0, 0]]
    iq = decode_iq_dma_s16(_pack(frames), channels=4)
    assert iq[0].real == -2048
    assert iq[0].imag == 2047


def test_decode_rejects_a_partial_frame():
    raw = _pack([[1, 2, 3, 4]])[:-2]        # drop 2 bytes
    with pytest.raises(ValueError):
        decode_iq_dma_s16(raw, channels=4)


def test_decode_rejects_empty_and_bad_channel_counts():
    with pytest.raises(ValueError):
        decode_iq_dma_s16(b"", channels=4)
    with pytest.raises(ValueError):
        decode_iq_dma_s16(_pack([[1, 2]]), channels=2, i_index=1, q_index=1)
    with pytest.raises(ValueError):
        decode_iq_dma_s16(_pack([[1, 2]]), channels=2, i_index=0, q_index=2)
    with pytest.raises(ValueError):
        decode_iq_dma_s16(_pack([[1, 2]]), channels=1)
    with pytest.raises(ValueError):
        decode_iq_dma_s16(_pack([[1, 2]]), channels=True)


def test_csv_loader_still_rejects_out_of_range(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("1,2\n40000,5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_iq_csv(path)
