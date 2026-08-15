import logging
import threading

import pystray
from PIL import Image, ImageDraw

from dictate import audio, config, hotkey, inject, transcribe

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    log_file = config.PROJECT_ROOT / "dictate.log"
    logging.basicConfig(
        level=logging.WARNING,  # quiets third-party libraries (httpx, PIL, ...)
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.getLogger("dictate").setLevel(logging.DEBUG)
    logging.getLogger("__main__").setLevel(logging.DEBUG)


def _make_icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64), "black")
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), fill="red")
    return img


class App:
    def __init__(self) -> None:
        self._recorder = audio.AudioRecorder()
        self._listener = hotkey.HotkeyListener(
            on_start=self._on_start,
            on_stop=self._on_stop,
            on_cancel=self._on_cancel,
        )
        self._icon = pystray.Icon(
            "red-shark",
            _make_icon_image(),
            "red-shark",
            menu=pystray.Menu(pystray.MenuItem("Quit", self._quit)),
        )

    def _on_start(self) -> None:
        logger.info("dictation armed: recording started")
        self._recorder.start_recording()

    def _on_stop(self) -> None:
        logger.info("dictation released: recording stopped")
        audio_data, sample_rate = self._recorder.stop_recording()
        logger.debug("captured %d samples at %dHz", audio_data.shape[0], sample_rate)
        if audio_data.shape[0] == 0:
            logger.warning("empty audio buffer, nothing to transcribe")
            return
        text = transcribe.transcribe(audio_data, sample_rate)
        logger.info("transcribed: %r", text)
        if text:
            inject.inject(text)
            logger.debug("injected %d characters", len(text))

    def _on_cancel(self) -> None:
        logger.info("dictation cancelled (third key pressed)")
        self._recorder.stop_recording()

    def _quit(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        logger.info("quit requested")
        self._listener.stop()
        icon.stop()

    def run(self) -> None:
        logger.info("preloading whisper model...")
        transcribe.preload()
        logger.info("model ready")

        def hook_thread_main() -> None:
            # The hook's callbacks are only delivered to the thread that
            # installed it, so start() and pump_messages() must run on the
            # same thread -- installing on the main thread and pumping on a
            # separate one means the hook silently never fires.
            self._listener.start()
            logger.info("keyboard hook installed, pumping messages")
            self._listener.pump_messages()

        threading.Thread(target=hook_thread_main, daemon=True).start()
        logger.info("tray icon starting")
        self._icon.run()


def main() -> None:
    _setup_logging()
    App().run()


if __name__ == "__main__":
    main()
