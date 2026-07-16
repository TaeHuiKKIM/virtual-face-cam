import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

from virtual_cam import (
    VideoFrameSource,
    create_frame_source,
    load_recent_path,
    preview_image,
    save_recent_path,
    settings_path,
)


def make_test_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        12,
        (160, 90),
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV test video encoder is unavailable")
    for index in range(6):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        frame[:, :, index % 3] = 40 + index * 30
        writer.write(frame)
    writer.release()


class MediaSourceTests(unittest.TestCase):
    def test_video_repeats_and_keeps_output_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "loop.avi"
            make_test_video(path)
            source = VideoFrameSource(path, 640, 360, 30)
            try:
                fingerprints = []
                for _ in range(90):
                    frame = source.next_frame()
                    self.assertEqual(frame.shape, (360, 640, 3))
                    fingerprints.append(tuple(frame[180, 320]))
            finally:
                source.close()

            self.assertGreater(len(set(fingerprints)), 1)
            self.assertIn(fingerprints[0], fingerprints[20:])
            self.assertEqual(preview_image(path).size, (160, 90))

    def test_image_source_still_works(self):
        source = create_frame_source("assets/default_face.jpg", 640, 360, 30)
        try:
            self.assertEqual(source.next_frame().shape, (360, 640, 3))
        finally:
            source.close()

    def test_windows_gui_restores_recent_path_and_ignores_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "settings.json"
            media = root / "recent.mp4"
            media.touch()
            save_recent_path(media, config)
            self.assertEqual(load_recent_path(config), media.resolve())
            media.unlink()
            self.assertIsNone(load_recent_path(config))

    def test_windows_settings_use_appdata(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("virtual_cam.sys.platform", "win32"):
                with mock.patch.dict("virtual_cam.os.environ", {"APPDATA": directory}):
                    self.assertEqual(
                        settings_path(),
                        Path(directory) / "VirtualFaceCam" / "settings.json",
                    )


if __name__ == "__main__":
    unittest.main()
