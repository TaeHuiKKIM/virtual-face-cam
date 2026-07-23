import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import mac.mac_virtual_face_cam as mac_app
from tests.test_media import make_test_video


def multipart_body(path: Path) -> tuple[bytes, str]:
    boundary = "virtual-face-cam-test-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{path.name}"\r\n'
        "Content-Type: video/x-msvideo\r\n\r\n"
    ).encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


class MacAppTests(unittest.TestCase):
    def test_frontend_requires_upload_before_selected_media_can_start(self):
        self.assertIn("let pendingSelection = false;", mac_app.HTML)
        self.assertIn(
            "const hasMedia = Boolean(data.mediaCount) && !uploadPending;",
            mac_app.HTML,
        )
        self.assertIn("startBtn.disabled = Boolean(data.running) || !hasMedia;", mac_app.HTML)
        self.assertIn(
            "Click Upload before starting the selected source.",
            mac_app.HTML,
        )

    def test_video_upload_range_stream_and_restart_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_video = root / "source.avi"
            make_test_video(source_video)

            originals = (
                mac_app.APP_SUPPORT,
                mac_app.UPLOAD_ROOT,
                mac_app.SETTINGS_PATH,
                mac_app.STATE,
            )
            mac_app.APP_SUPPORT = root / "support"
            mac_app.UPLOAD_ROOT = mac_app.APP_SUPPORT / "uploads"
            mac_app.SETTINGS_PATH = mac_app.APP_SUPPORT / "settings.json"
            mac_app.STATE = mac_app.AppState()

            server = mac_app.ThreadingHTTPServer(("127.0.0.1", 0), mac_app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
                body, content_type = multipart_body(source_video)
                connection.request(
                    "POST",
                    "/api/upload",
                    body=body,
                    headers={"Content-Type": content_type, "Content-Length": str(len(body))},
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(payload["mediaType"], "video")
                self.assertEqual(payload["count"], 1)

                connection.request("GET", "/api/media", headers={"Range": "bytes=0-31"})
                response = connection.getresponse()
                self.assertEqual(response.status, 206)
                self.assertEqual(len(response.read()), 32)

                connection.request("GET", "/api/video-poster")
                response = connection.getresponse()
                poster = response.read()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "image/jpeg")
                self.assertTrue(poster.startswith(b"\xff\xd8"))
                self.assertTrue(mac_app.SETTINGS_PATH.is_file())

                mac_app.STATE = mac_app.AppState()
                self.assertTrue(mac_app.load_saved_media())
                restored = mac_app.STATE.snapshot()
                self.assertEqual(restored["mediaType"], "video")
                self.assertEqual(restored["mediaCount"], 1)
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                (
                    mac_app.APP_SUPPORT,
                    mac_app.UPLOAD_ROOT,
                    mac_app.SETTINGS_PATH,
                    mac_app.STATE,
                ) = originals


if __name__ == "__main__":
    unittest.main()
