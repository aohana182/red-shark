import threading

import pystray
from PIL import Image, ImageDraw

from dictate import audio, hotkey, inject, transcribe


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
        self._recorder.start_recording()

    def _on_stop(self) -> None:
        audio_data, sample_rate = self._recorder.stop_recording()
        if audio_data.shape[0] == 0:
            return
        text = transcribe.transcribe(audio_data, sample_rate)
        if text:
            inject.inject(text)

    def _on_cancel(self) -> None:
        self._recorder.stop_recording()

    def _quit(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._listener.stop()
        icon.stop()

    def run(self) -> None:
        transcribe.preload()
        self._listener.start()
        threading.Thread(target=self._listener.pump_messages, daemon=True).start()
        self._icon.run()


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
