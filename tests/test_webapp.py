import importlib.util
import io
import json
import os
import shutil
import time
import unittest
import zipfile

# load webapp/app.py as module (the webapp folder is not a package)
_app_path = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "webapp", "app.py")
_spec = importlib.util.spec_from_file_location("webapp_app", _app_path)
webapp_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(webapp_app)

FIXTURE = "./tests/fixtures/Brahms-Da-unten-im-Tale.mid"


class TestWebapp(unittest.TestCase):
    def setUp(self):
        webapp_app.app.config["TESTING"] = True
        self.client = webapp_app.app.test_client()

    def _upload(self, file_name):
        with open(FIXTURE, "rb") as file_stream:
            data = {"file": (io.BytesIO(file_stream.read()), file_name)}
        return self.client.post("/midi-info", data=data,
                                content_type="multipart/form-data")

    def test_upload_returns_musicxml_and_parts(self):
        response = self._upload("Brahms.mid")
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.data)
        self.assertEqual(len(content["parts"]), 4)
        self.assertIn("score-partwise", content["musicxml"])

    def test_upload_file_name_cannot_escape_temp_folder(self):
        target = os.path.abspath("escaped.mid")
        self.addCleanup(lambda: os.path.exists(target) and os.remove(target))
        response = self._upload("../../escaped.mid")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(
            os.path.join(webapp_app.TEMP_FOLDER, "..", "escaped.mid")))

    def test_upload_rejects_unsupported_file_type(self):
        response = self._upload("script.sh")
        self.assertEqual(response.status_code, 400)

    def test_upload_without_file_is_rejected(self):
        response = self.client.post("/midi-info", data={},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)

    def test_request_does_not_delete_folders_of_other_requests(self):
        other_folder = os.path.join(webapp_app.TEMP_FOLDER, "other-request")
        os.makedirs(other_folder, exist_ok=True)
        self.addCleanup(shutil.rmtree, other_folder, True)
        self._upload("Brahms.mid")
        self.assertTrue(os.path.exists(other_folder))

    def test_download_returns_zip_and_removes_temp_folder(self):
        musicxml = json.loads(self._upload("Brahms.mid").data)["musicxml"]
        folders_before = set(os.listdir(webapp_app.TEMP_FOLDER))
        response = self.client.post("/download", data={
            "soprano": "0", "alto": "1", "tenor": "2", "bass": "3",
            "musicxml": musicxml}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        names = zipfile.ZipFile(io.BytesIO(response.data)).namelist()
        self.assertIn("all.mp3", names)
        self.assertIn("soprano 1 with accompaniment.mp3", names)
        self.assertEqual(set(os.listdir(webapp_app.TEMP_FOLDER)), folders_before)

    def _wait_for_job(self, job_id):
        for _ in range(300):
            status = json.loads(self.client.get(f"/jobs/{job_id}").data)
            if status["status"] in ("done", "failed"):
                return status
            time.sleep(0.1)
        self.fail("job did not finish")

    def test_job_reports_progress_and_returns_zip(self):
        musicxml = json.loads(self._upload("Brahms.mid").data)["musicxml"]
        response = self.client.post("/jobs", data={
            "soprano": "0", "alto": "1", "tenor": "2", "bass": "3",
            "musicxml": musicxml}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 202)
        job_id = json.loads(response.data)["id"]
        status = self._wait_for_job(job_id)
        self.assertEqual(status, {"status": "done", "percent": 100,
                                  "remaining_s": 0})
        response = self.client.get(f"/jobs/{job_id}/download")
        self.assertEqual(response.status_code, 200)
        names = zipfile.ZipFile(io.BytesIO(response.data)).namelist()
        self.assertIn("all.mp3", names)
        self.assertIn("soprano 1 with accompaniment.mp3", names)
        response.close()

    def test_failed_job_is_reported(self):
        response = self.client.post("/jobs", data={
            "soprano": "0", "musicxml": "not a score"},
            content_type="multipart/form-data")
        status = self._wait_for_job(json.loads(response.data)["id"])
        self.assertEqual(status["status"], "failed")

    def test_unknown_job(self):
        self.assertEqual(self.client.get("/jobs/unknown").status_code, 404)
        self.assertEqual(
            self.client.get("/jobs/unknown/download").status_code, 404)

    def test_job_without_musicxml_is_rejected(self):
        response = self.client.post("/jobs", data={"soprano": "0"},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)

    def test_download_without_musicxml_is_rejected(self):
        response = self.client.post("/download", data={"soprano": "0"},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
