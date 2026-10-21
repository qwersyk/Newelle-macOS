"""Regression coverage for macOS paths affected by upstream synchronization."""
import gettext
import importlib
import importlib.util
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

ROOT = Path(__file__).resolve().parents[1]
gettext.install("newelle")
spec = importlib.util.spec_from_file_location("newelle", ROOT / "src/__init__.py", submodule_search_locations=[str(ROOT / "src")])
package = importlib.util.module_from_spec(spec)
sys.modules["newelle"] = package
spec.loader.exec_module(package)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")
from newelle.utility.audio_recorder import AudioRecorder
from newelle.utility import screenshot
from newelle.utility import pip as pip_helper


class AudioRecordingTests(unittest.TestCase):
    def test_device_fallback_and_native_sample_rate(self):
        recorder = AudioRecorder()
        interface = Mock()
        interface.get_default_input_device_info.side_effect = OSError("No default")
        interface.get_device_count.return_value = 2
        interface.get_device_info_by_index.side_effect = [
            {"index": 0, "maxInputChannels": 0},
            {"index": 1, "maxInputChannels": 2, "defaultSampleRate": 48000},
        ]
        interface.is_format_supported.return_value = True
        stream = interface.open.return_value
        def read(*_args, **_kwargs):
            recorder.stop_recording()
            return b"\x00\x00" * 1024
        stream.read.side_effect = read
        finished = []
        recorder.stop_function = lambda: finished.append(True)
        with tempfile.TemporaryDirectory() as directory, patch("newelle.utility.audio_recorder.pyaudio.PyAudio", return_value=interface):
            output = os.path.join(directory, "audio.wav")
            recorder.start_recording(output)
            with wave.open(output) as audio:
                self.assertEqual(audio.getframerate(), 48000)
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getnframes(), 1024)
        self.assertEqual(interface.open.call_args.kwargs["input_device_index"], 1)
        self.assertTrue(recorder.is_stopped())
        self.assertEqual(finished, [True])
        stream.close.assert_called_once()
        interface.terminate.assert_called_once()

    def test_missing_microphone_releases_worker_and_calls_back(self):
        recorder = AudioRecorder()
        interface = Mock()
        interface.get_default_input_device_info.side_effect = OSError()
        interface.get_device_count.return_value = 0
        finished = Mock()
        recorder.stop_function = finished
        with tempfile.TemporaryDirectory() as directory, patch("newelle.utility.audio_recorder.pyaudio.PyAudio", return_value=interface):
            recorder.start_recording(os.path.join(directory, "audio.wav"))
        self.assertTrue(recorder.is_stopped())
        self.assertIn("No microphone", recorder.last_error)
        finished.assert_called_once()
        interface.terminate.assert_called_once()


class ScreenshotTests(unittest.TestCase):
    def test_cancel_before_start_does_not_launch_capture(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(screenshot.subprocess, "Popen") as process:
            with self.assertRaises(RuntimeError):
                screenshot._capture_macos_screenshot(directory, False, lambda: True)
            process.assert_not_called()

    def test_native_capture_uses_system_tool_and_private_file(self):
        def capture(command, **_kwargs):
            Path(command[-1]).write_bytes(b"image")
            process = Mock()
            process.poll.return_value = 0
            process.returncode = 0
            process.__enter__ = Mock(return_value=process)
            process.__exit__ = Mock(return_value=False)
            return process
        with tempfile.TemporaryDirectory() as directory, patch.object(screenshot.subprocess, "Popen", side_effect=capture) as process:
            path = screenshot.capture_screenshot(directory)
            self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
            self.assertEqual(process.call_args.args[0][0], "/usr/sbin/screencapture")
            self.assertIn("-m", process.call_args.args[0])


class ScreenRecordingTests(unittest.TestCase):
    def test_native_recording_finalizes_after_interrupt(self):
        from newelle.ui.screenrecorder import ScreenRecorder
        recorder = ScreenRecorder(Mock(), on_started=Mock(), on_finished=Mock())
        with tempfile.TemporaryDirectory() as directory:
            recorder.output_path = os.path.join(directory, "screen.mp4")
            process = Mock()
            process.poll.return_value = None
            with patch("newelle.ui.screenrecorder.subprocess.Popen", return_value=process), \
                 patch("newelle.ui.screenrecorder.GLib.timeout_add"), \
                 patch("newelle.ui.screenrecorder.GLib.timeout_add_seconds"), \
                 patch("newelle.ui.screenrecorder.GLib.source_remove"):
                recorder.start()
                recorder.on_started.assert_called_once()
                recorder.stop()
                process.send_signal.assert_called_once_with(signal.SIGINT)
                recorder.on_finished.assert_not_called()
                Path(recorder.output_path).write_bytes(b"video")
                process.poll.return_value = 0
                recorder._poll_macos()
                recorder.on_finished.assert_called_once_with(recorder.output_path)
                self.assertTrue(recorder.finished)

    def test_native_capture_failure_is_reported(self):
        from newelle.ui.screenrecorder import ScreenRecorder
        recorder = ScreenRecorder(Mock())
        recorder.native_process = Mock()
        recorder.native_process.poll.return_value = 1
        recorder._fail = Mock()
        recorder._poll_macos()
        recorder._fail.assert_called_once()


class WindowDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("macos_windowing_tests", ROOT / "macos/windowing.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_workaround_is_limited_to_affected_os(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(self.module.needs_manual_window_drag("26.6"))
            self.assertFalse(self.module.needs_manual_window_drag("27.1"))
            self.assertTrue(self.module.needs_manual_window_drag("27.2"))
            self.assertFalse(self.module.needs_manual_window_drag("27.3"))

    def test_drag_keeps_mouse_offset_on_negative_display_coordinates(self):
        self.assertEqual(self.module.drag_origin((-1000, 200), (-900, 600), (-800, 650)), (-900, 250))


class RuntimeTests(unittest.TestCase):
    def test_pip_uses_bundled_interpreter(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"NEWELLE_PYTHON_BIN": "/bundled/python"}), \
             patch.object(pip_helper, "find_module", return_value=True), \
             patch.object(pip_helper, "_pip_supports_raw_progress", return_value=False), \
             patch.object(pip_helper, "_run_pip", return_value=subprocess.CompletedProcess([], 0)) as run:
            result = pip_helper.install_module("example-package", directory, cache_dir=directory)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(run.call_args.args[0][:3], ["/bundled/python", "-m", "pip"])

    def test_llama_prebuilts_match_macos_and_architecture(self):
        modules = ("newelle.handlers.llm.llama_cpp_handler", "newelle.handlers.embeddings.llama_cpp_handler")
        for name in modules:
            with self.subTest(module=name):
                module = importlib.import_module(name)
                cls = getattr(module, "LlamaCPPHandler", None) or module.LlamaCPPEmbeddingHandler
                handler = object.__new__(cls)
                handler._detect_arch = lambda: "arm64"
                handler._populate_prebuilt_list = Mock()
                handler._show_prebuilt_error = Mock()
                assets = [{"name": n, "browser_download_url": "https://example.test/" + n, "size": 1} for n in (
                    "llama-bin-ubuntu-arm64.tar.gz", "llama-bin-macos-x64.tar.gz", "llama-bin-macos-arm64.tar.gz")]
                response = Mock()
                response.json.return_value = [{"tag_name": "test", "assets": assets}]
                with patch.object(module.requests, "get", return_value=response) as get, \
                     patch.object(module.GLib, "idle_add", side_effect=lambda f, *a: f(*a)), \
                     patch.object(module, "has_backend", return_value=False), \
                     patch.object(module, "detect_cuda_version", return_value=None):
                    handler._fetch_prebuilt_releases(None)
                handler._show_prebuilt_error.assert_not_called()
                selected = handler._populate_prebuilt_list.call_args.args[0]
                self.assertEqual([a["name"] for a in selected], ["llama-bin-macos-arm64.tar.gz"])
                self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
