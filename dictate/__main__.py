import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

import pystray
from PIL import Image, ImageDraw

from dictate import audio, cleanup, config, hotkey, inject, transcribe

logger = logging.getLogger(__name__)

# Console control events this app treats as "shut down cleanly": Ctrl+C,
# Ctrl+Break, the console window's X button, logoff, shutdown. Handled via
# SetConsoleCtrlHandler rather than Python's signal module because the main
# thread spends nearly all its time blocked inside pystray's native
# GetMessage loop -- a plain SIGINT handler can be delayed indefinitely until
# that call happens to return, whereas SetConsoleCtrlHandler's callback runs
# on its own OS thread regardless of what the main thread is doing.
_CTRL_C_EVENT = 0
_CTRL_BREAK_EVENT = 1
_CTRL_CLOSE_EVENT = 2
_CTRL_LOGOFF_EVENT = 5
_CTRL_SHUTDOWN_EVENT = 6
_SHUTDOWN_CTRL_TYPES = frozenset(
    {
        _CTRL_C_EVENT,
        _CTRL_BREAK_EVENT,
        _CTRL_CLOSE_EVENT,
        _CTRL_LOGOFF_EVENT,
        _CTRL_SHUTDOWN_EVENT,
    }
)

_HandlerRoutine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)


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


def _make_icon_image(state: str = "idle") -> Image.Image:
    img = Image.new("RGB", (64, 64), "black")
    draw = ImageDraw.Draw(img)
    if state == "paused":
        draw.ellipse((8, 8, 56, 56), fill="gray")
    elif state == "recording":
        draw.ellipse((8, 8, 56, 56), fill="red", outline="white", width=4)
    else:
        draw.ellipse((8, 8, 56, 56), fill="red")
    return img


class App:
    def __init__(
        self, icon_factory: Callable[..., pystray.Icon] = pystray.Icon
    ) -> None:
        self._paused = False
        self._recorder = audio.AudioRecorder()
        self._listener = hotkey.HotkeyListener(
            on_start=self._on_start,
            on_stop=self._on_stop,
            on_cancel=self._on_cancel,
        )
        self._icon = icon_factory(
            "red-shark",
            _make_icon_image("idle"),
            "red-shark",
            menu=pystray.Menu(
                pystray.MenuItem(
                    lambda _item: "Resume" if self._paused else "Pause",
                    self._toggle_pause,
                ),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    # _on_start/_on_stop/_on_cancel run synchronously inside the global
    # keyboard hook's callback (see hotkey.py). An exception escaping a
    # ctypes callback doesn't raise normally -- it gets swallowed by ctypes
    # with a bare stderr warning, bypassing our logging, and can leave the
    # hook's return value to Windows undefined. Since this pipeline touches
    # several things that can fail transiently (mic device, model
    # inference, SendInput), every entry point is defensive: log properly,
    # never let an exception reach the hook boundary.

    def _set_icon_state(self, state: str) -> None:
        self._icon.icon = _make_icon_image(state)

    def _toggle_pause(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._paused = not self._paused
        logger.info("dictation %s", "paused" if self._paused else "resumed")
        self._set_icon_state("paused" if self._paused else "idle")
        icon.update_menu()

    def _on_start(self) -> None:
        if self._paused:
            logger.debug("dictation hold ignored: paused")
            return
        try:
            logger.info("dictation armed: recording started")
            self._recorder.start_recording()
            self._set_icon_state("recording")
        except Exception:
            logger.exception("failed to start recording")

    def _on_stop(self) -> None:
        try:
            logger.info("dictation released: recording stopped")
            audio_data, sample_rate = self._recorder.stop_recording()
            logger.debug(
                "captured %d samples at %dHz", audio_data.shape[0], sample_rate
            )
            if audio_data.shape[0] == 0:
                logger.warning("empty audio buffer, nothing to transcribe")
                return
            text = transcribe.transcribe(audio_data, sample_rate)
            logger.info("transcribed: %r", text)
            if text:
                text = cleanup.cleanup(text)
                logger.info("cleaned: %r", text)
            if text:
                inject.inject(text)
                logger.debug("injected %d characters", len(text))
        except Exception:
            logger.exception("dictation pipeline failed")
        finally:
            self._set_icon_state("paused" if self._paused else "idle")

    def _on_cancel(self) -> None:
        try:
            logger.info("dictation cancelled (third key pressed)")
            self._recorder.stop_recording()
        except Exception:
            logger.exception("failed to stop recording on cancel")
        finally:
            self._set_icon_state("paused" if self._paused else "idle")

    def _quit(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        logger.info("quit requested")
        self._listener.stop()
        try:
            self._recorder.stop_recording()
        except Exception:
            logger.exception("failed to release microphone on quit")
        cleanup.shutdown()
        icon.stop()

    def handle_console_event(self, ctrl_type: int) -> bool:
        """Returns True if `ctrl_type` was handled (shutdown initiated)."""
        if ctrl_type not in _SHUTDOWN_CTRL_TYPES:
            return False
        logger.info("console control event %d received, shutting down", ctrl_type)
        self._listener.stop()
        try:
            self._recorder.stop_recording()
        except Exception:
            logger.exception("failed to release microphone on shutdown")
        cleanup.shutdown()
        self._icon.stop()
        return True

    def _install_console_handler(self) -> None:
        # Keep a reference on self -- ctypes doesn't, and a GC'd callback
        # would crash the process the next time Windows tries to invoke it.
        self._console_handler = _HandlerRoutine(self.handle_console_event)
        if not ctypes.windll.kernel32.SetConsoleCtrlHandler(
            self._console_handler, True
        ):
            logger.warning(
                "failed to install console control handler: %s", ctypes.get_last_error()
            )

    def run(self) -> None:
        logger.info("preloading whisper model...")
        transcribe.preload()
        logger.info("whisper model ready")

        logger.info("preloading cleanup model...")
        cleanup.preload()
        logger.info("cleanup model ready")

        def hook_thread_main() -> None:
            # The hook's callbacks are only delivered to the thread that
            # installed it, so start() and pump_messages() must run on the
            # same thread -- installing on the main thread and pumping on a
            # separate one means the hook silently never fires.
            self._listener.start()
            logger.info("keyboard hook installed, pumping messages")
            self._listener.pump_messages()

        threading.Thread(target=hook_thread_main, daemon=True).start()
        self._install_console_handler()
        logger.info("tray icon starting")
        self._icon.run()


def main() -> None:
    _setup_logging()
    App().run()


if __name__ == "__main__":
    main()
