"""Stubs out the `av` package so importing faster_whisper doesn't load it.

faster_whisper/audio.py does `import av` unconditionally at module load,
even though decode_audio() -- the only function that touches av -- is never
called by this app (transcribe() always passes an already-decoded numpy
array, see faster_whisper/transcribe.py's `isinstance(audio, np.ndarray)`
check). On this machine av's compiled frame.pyd is blocked by Windows Smart
App Control, so importing faster_whisper crashes before any of our own code
runs. Registering a stub in sys.modules before faster_whisper is imported
satisfies its `import av` and attribute lookups without ever loading the
real (blocked) native extension.
"""

import sys
import types


def _unused(*_args, **_kwargs):
    raise RuntimeError(
        "av is stubbed out (see dictate/_av_stub.py) and red-shark never "
        "calls the faster_whisper code path that needs it. If you're "
        "seeing this, transcribe() was passed something other than a "
        "numpy array, which decode_audio() would need to handle for real."
    )


def install() -> None:
    if "av" in sys.modules:
        return

    av = types.ModuleType("av")
    av_audio = types.ModuleType("av.audio")
    av_audio_resampler = types.ModuleType("av.audio.resampler")
    av_audio_fifo = types.ModuleType("av.audio.fifo")
    av_error = types.ModuleType("av.error")

    av_audio_resampler.AudioResampler = _unused
    av_audio_fifo.AudioFifo = _unused
    av_error.InvalidDataError = type("InvalidDataError", (Exception,), {})
    av.open = _unused

    av_audio.resampler = av_audio_resampler
    av_audio.fifo = av_audio_fifo
    av.audio = av_audio
    av.error = av_error

    sys.modules["av"] = av
    sys.modules["av.audio"] = av_audio
    sys.modules["av.audio.resampler"] = av_audio_resampler
    sys.modules["av.audio.fifo"] = av_audio_fifo
    sys.modules["av.error"] = av_error
