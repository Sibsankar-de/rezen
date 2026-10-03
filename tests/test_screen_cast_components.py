import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from models.stream_chunk import ChunkType, FlagType, StreamChunk
from settings import settings
from screen_cast.h264 import H264Decoder, H264Encoder
from screen_cast.receiver import FrameBuffer, Receiver, _chunk_sort_key
from screen_cast.renderer import ScreenRenderer
from screen_cast.streamer import Streamer


def test_chunk_sort_key():
    assert _chunk_sort_key("chunk_0") == 0
    assert _chunk_sort_key("chunk_9") == 9
    assert _chunk_sort_key("chunk_10") == 10
    assert _chunk_sort_key("invalid") == 0


def test_frame_buffer_single_chunk():
    fb = FrameBuffer()
    chunk = StreamChunk(
        frame_id="frame_0",
        chunk_id="chunk_0",
        type=ChunkType.VIDEO,
        flag=FlagType.END_CHUNK,
        size=5,
        total_chunks=1,
        data=b"hello",
    )
    result = fb.add(chunk)
    assert result == b"hello"
    assert "frame_0" not in fb.frames


def test_frame_buffer_multi_chunk_ordering():
    fb = FrameBuffer()
    total = 12
    # Add chunks out of order: chunk_11, chunk_10, chunk_2, chunk_0, ...
    chunks = []
    for i in range(total):
        if i == total - 1:
            flag = FlagType.END_CHUNK
        elif i == 0:
            flag = FlagType.START_CHUNK
        else:
            flag = FlagType.MEDIATE_CHUNK
        chunks.append(
            StreamChunk(
                frame_id="frame_1",
                chunk_id=f"chunk_{i}",
                type=ChunkType.VIDEO,
                flag=flag,
                size=2,
                total_chunks=total,
                data=f"{i:02d}".encode(),
            )
        )

    # Add all except the last chunk
    for c in chunks[:-1]:
        res = fb.add(c)
        assert res is None

    # Add the last chunk (END_CHUNK)
    res = fb.add(chunks[-1])
    assert res is not None
    # Chunks must be sorted numerically 00, 01, 02, ... 10, 11
    expected = b"".join(f"{i:02d}".encode() for i in range(total))
    assert res == expected


def test_frame_buffer_incomplete_frame_discarded():
    fb = FrameBuffer()
    c0 = StreamChunk(
        frame_id="f",
        chunk_id="chunk_0",
        type=ChunkType.VIDEO,
        flag=FlagType.START_CHUNK,
        size=1,
        total_chunks=3,
        data=b"a",
    )
    c2 = StreamChunk(
        frame_id="f",
        chunk_id="chunk_2",
        type=ChunkType.VIDEO,
        flag=FlagType.END_CHUNK,
        size=1,
        total_chunks=3,
        data=b"c",
    )
    fb.add(c0)
    res = fb.add(c2)
    assert res is None
    assert "f" not in fb.frames


def test_streamer_chunk_flag_assignment():
    streamer = Streamer()
    chunks_1 = streamer._create_chunks(b"123", 100)
    assert len(chunks_1) == 1

    chunks_3 = streamer._create_chunks(b"123456", 2)
    assert len(chunks_3) == 3


@pytest.mark.asyncio
async def test_streamer_encode_and_send_chunk():
    mock_capture = MagicMock()
    mock_capture.width = 640
    mock_capture.height = 480
    mock_encoder = MagicMock()
    packet = MagicMock()
    packet.data = b"0123456789"
    mock_encoder.encode.return_value = [packet]

    streamer = Streamer(capture=mock_capture, encoder=mock_encoder)
    sent_chunks = []

    async def mock_send(chunk: StreamChunk):
        sent_chunks.append(chunk)

    frame = np.zeros((480, 640, 4), dtype=np.uint8)
    with patch("settings.settings.STREAM_CHUNK_SIZE", 4):
        await streamer.start(mock_send)
        await streamer._encode_and_send_chunk(frame)
        await streamer.stop()

    assert len(sent_chunks) == 3
    assert sent_chunks[0].flag == FlagType.START_CHUNK
    assert sent_chunks[1].flag == FlagType.MEDIATE_CHUNK
    assert sent_chunks[2].flag == FlagType.END_CHUNK
    assert b"".join(c.data for c in sent_chunks) == b"0123456789"


@pytest.mark.asyncio
async def test_receiver_start_stop():
    mock_renderer = MagicMock()
    mock_decoder = MagicMock()
    mock_buffer = MagicMock()

    receiver = Receiver(
        decoder=mock_decoder, buffer=mock_buffer, renderer=mock_renderer
    )
    await receiver.start()
    assert receiver._running is True

    await receiver.stop()
    assert receiver._running is False
    mock_buffer.clear.assert_called_once()
    mock_decoder.close.assert_called_once()
    mock_renderer.close.assert_called_once()


@pytest.mark.asyncio
async def test_receiver_handle_chunk():
    mock_renderer = MagicMock()
    mock_renderer.isClosed = False
    mock_decoder = MagicMock()
    dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_decoder.decode.return_value = [dummy_frame]

    mock_buffer = MagicMock()
    mock_buffer.add.return_value = b"encoded_bytes"

    receiver = Receiver(
        decoder=mock_decoder, buffer=mock_buffer, renderer=mock_renderer
    )
    await receiver.start()

    chunk = StreamChunk(
        frame_id="f1",
        chunk_id="c0",
        type=ChunkType.VIDEO,
        flag=FlagType.END_CHUNK,
        size=10,
        total_chunks=1,
        data=b"data",
    )

    await receiver.handle_chunk(chunk)
    mock_decoder.decode.assert_called_once_with(b"encoded_bytes")
    mock_renderer.display.assert_called_once_with(dummy_frame)
    await receiver.stop()


def test_h264_encoder_decoder_roundtrip():
    width, height = 320, 240
    encoder = H264Encoder(width, height, fps=30)
    decoder = H264Decoder()

    # Create dummy BGRA frame
    frame = np.full((height, width, 4), 128, dtype=np.uint8)
    packets = encoder.encode(frame)
    assert len(packets) > 0

    decoded_frames = []
    for pkt in packets:
        decoded_frames.extend(decoder.decode(pkt.data))

    encoder.close()
    decoder.close()
    assert len(decoded_frames) >= 1
    assert decoded_frames[0].shape == (height, width, 3)


def test_h264_decoder_resilience_to_bad_data():
    decoder = H264Decoder()
    res = decoder.decode(b"\x00\x01\x02\x03corrupt_stream_bytes")
    assert res == []
    decoder.close()


def test_screen_renderer_lifecycle():
    with (
        patch("cv2.namedWindow"),
        patch("cv2.imshow"),
        patch("cv2.waitKey", return_value=0),
        patch("cv2.getWindowProperty", return_value=1.0),
        patch("cv2.destroyWindow"),
    ):
        renderer = ScreenRenderer()
        assert renderer.isClosed is True
        renderer.start()
        assert renderer.isClosed is False

        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        assert renderer.display(frame) is True

        renderer.close()
        assert renderer.isClosed is True


def test_screen_renderer_is_window_open():
    renderer = ScreenRenderer()
    with patch("cv2.getWindowProperty", return_value=1.0):
        assert renderer._is_window_open() is True

    with patch("cv2.getWindowProperty", side_effect=Exception("Null pointer")):
        assert renderer._is_window_open() is False


def test_screen_capture_safe_fallback():
    from screen_cast.capture import ScreenCapture

    mock_sct = MagicMock()
    mock_sct.monitors = [
        {"top": 0, "left": 0, "width": 1921, "height": 1081},
        {"top": 0, "left": 0, "width": 1920, "height": 1080},
    ]
    with patch("mss.MSS", return_value=mock_sct):
        cap = ScreenCapture(monitor=1)
        assert cap.width == 1920
        assert cap.height == 1080
        cap.close()

        cap_fallback = ScreenCapture(monitor=99)
        assert cap_fallback.width == 1920
        assert cap_fallback.height == 1080
        cap_fallback.close()


def test_screen_capture_single_monitor_odd_dimensions():
    from screen_cast.capture import ScreenCapture

    mock_sct = MagicMock()
    mock_sct.monitors = [
        {"top": 0, "left": 0, "width": 1365, "height": 767},
    ]
    with patch("mss.MSS", return_value=mock_sct):
        cap = ScreenCapture(monitor=1)
        assert cap.width == 1364
        assert cap.height == 766
        cap.close()


def test_screen_capture_warns_but_streams_on_black_frames():
    """A blank grab must not kill the stream: it warns and keeps returning frames."""
    import numpy as np

    from screen_cast.capture import ScreenCapture

    mock_sct = MagicMock()
    mock_sct.monitors = [
        {"top": 0, "left": 0, "width": 64, "height": 64, "is_primary": True},
    ]
    mock_sct.grab.return_value = np.zeros((64, 64, 4), dtype=np.uint8)

    with patch("mss.MSS", return_value=mock_sct):
        cap = ScreenCapture(monitor=1)
        blank_count = cap.BLANK_FRAME_WARN_THRESHOLD * 3
        for i in range(blank_count):
            assert cap.capture().max() == 0
        assert cap._warned_blank is True
        # A real frame must reset the warning state.
        mock_sct.grab.return_value = np.full((64, 64, 4), 7, dtype=np.uint8)
        assert cap.capture().max() == 7
        assert cap._blank_frames == 0
        assert cap._warned_blank is False
        cap.close()


def test_screen_capture_raises_on_empty_frame():
    import numpy as np

    from screen_cast.capture import ScreenCapture, ScreenCaptureError

    mock_sct = MagicMock()
    mock_sct.monitors = [
        {"top": 0, "left": 0, "width": 64, "height": 64, "is_primary": True},
    ]
    mock_sct.grab.return_value = np.zeros((0, 0, 4), dtype=np.uint8)

    with patch("mss.MSS", return_value=mock_sct):
        cap = ScreenCapture(monitor=1)
        with pytest.raises(ScreenCaptureError):
            cap.capture()
        cap.close()


def test_create_capture_prefers_mss_on_x11():
    """X11 sessions must not go through the Wayland portal path."""
    from screen_cast import capture as capture_module
    from screen_cast.capture import ScreenCapture, create_capture

    with patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}, clear=False):
        assert capture_module.create_capture() is not None
        # The real ScreenCapture is returned without touching the portal.
        instance = create_capture()
        assert isinstance(instance, ScreenCapture)
        instance.close()


def test_create_capture_honours_explicit_mss_backend():
    """SCREEN_CAPTURE_BACKEND=mss must skip the portal even on Wayland."""
    from screen_cast.capture import ScreenCapture, create_capture

    previous = settings.SCREEN_CAPTURE_BACKEND
    settings.SCREEN_CAPTURE_BACKEND = "mss"
    try:
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}, clear=False):
            instance = create_capture()
            assert isinstance(instance, ScreenCapture)
            instance.close()
    finally:
        settings.SCREEN_CAPTURE_BACKEND = previous


def test_pipewire_scaled_size_keeps_aspect_and_even_edges():
    from screen_cast.pipewire_capture import PipeWireScreenCapture

    scale = PipeWireScreenCapture._scaled_size

    assert scale(1920, 1080, 1920, 1080) == (1920, 1080)
    assert scale(1920, 1080, 1280, 720) == (1280, 720)
    assert scale(1280, 720, 1920, 1080) == (1280, 720)
    # Odd source sizes are floored to even edges for the encoder.
    width, height = scale(1365, 767, 1920, 1080)
    assert width % 2 == 0 and height % 2 == 0
    assert width <= 1365 and height <= 767


def test_portal_available_requires_wayland_session():
    from screen_cast import pipewire_capture

    with patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}, clear=False):
        assert pipewire_capture.portal_available() is False

    with patch.dict(
        os.environ, {"XDG_SESSION_TYPE": "wayland", "XDG_RUNTIME_DIR": ""}, clear=False
    ):
        assert pipewire_capture.portal_available() is False


def test_pipewire_requires_gstreamer():
    from screen_cast.pipewire_capture import PipeWireScreenCapture, PipeWireUnavailable

    with patch("shutil.which", return_value=None):
        with pytest.raises(PipeWireUnavailable):
            PipeWireScreenCapture()


def test_pipewire_requires_system_python_with_bindings():
    from screen_cast.pipewire_capture import (
        PipeWireScreenCapture,
        PipeWireUnavailable,
        find_system_python,
    )

    with patch("shutil.which", return_value="/usr/bin/gst-launch-1.0"):
        with patch(
            "screen_cast.pipewire_capture.find_system_python", return_value=None
        ):
            with pytest.raises(PipeWireUnavailable):
                PipeWireScreenCapture()

    assert callable(find_system_python)
